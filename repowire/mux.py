"""Terminal multiplexer abstraction for tmux-compatible providers."""

from __future__ import annotations

import logging
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Protocol, TypedDict

logger = logging.getLogger(__name__)


class MuxProviderKind(str, Enum):
    AUTO = "auto"
    TMUX = "tmux"
    PSMUX = "psmux"
    NONE = "none"


class PaneInfo(TypedDict):
    pane_id: str
    pid: int
    command: str
    cwd: str
    session: str
    window: str


@dataclass(frozen=True)
class PaneEvidence:
    pane_id: str
    tmux_session: str
    path: str
    pid: int | None = None


@dataclass(frozen=True)
class MuxSpawnResult:
    display_name: str
    tmux_session: str
    pane_id: str


class MuxProvider(Protocol):
    kind: MuxProviderKind
    command: str

    def is_available(self) -> bool: ...
    def list_panes(self) -> list[PaneInfo]: ...
    def get_pane_info(self, pane_id: str) -> PaneEvidence | None: ...
    def send_keys(self, pane_id: str, text: str, *, literal: bool = False) -> bool: ...
    def spawn_window(
        self, *, session_name: str, window_name: str, cwd: str, command: str
    ) -> MuxSpawnResult: ...
    def unique_window_name(self, session_name: str, base_name: str) -> str: ...
    def kill_pane(self, pane_id: str) -> bool: ...
    def install_lifecycle_hooks(self, host: str = "127.0.0.1", port: int = 8377) -> list[str]: ...
    def uninstall_lifecycle_hooks(self) -> list[str]: ...


_PANE_FORMAT = (
    "#{pane_id}\t#{pane_pid}\t#{pane_current_command}\t"
    "#{pane_current_path}\t#{session_name}\t#{window_index}"
)


class TmuxCompatibleProvider:
    kind = MuxProviderKind.TMUX

    def __init__(self, command: str = "tmux") -> None:
        self.command = command

    def _run(self, args: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        return subprocess.run(
            [self.command, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
            **kwargs,
        )

    def is_available(self) -> bool:
        if not shutil.which(self.command):
            return False
        try:
            return self._run(["display-message", "-p", ""], timeout=3).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def list_panes(self) -> list[PaneInfo]:
        try:
            result = self._run(["list-panes", "-a", "-F", _PANE_FORMAT], timeout=3)
        except (OSError, subprocess.SubprocessError) as e:
            logger.debug("list_panes failed: %s", e)
            return []
        if result.returncode != 0:
            return []
        panes: list[PaneInfo] = []
        for line in result.stdout.splitlines():
            parts = line.split("\t")
            if len(parts) != 6:
                continue
            pane_id, pid_str, command, cwd, session, window = parts
            try:
                pid = int(pid_str)
            except ValueError:
                continue
            panes.append(
                PaneInfo(
                    pane_id=pane_id,
                    pid=pid,
                    command=command,
                    cwd=cwd,
                    session=session,
                    window=window,
                )
            )
        return panes

    def get_pane_info(self, pane_id: str) -> PaneEvidence | None:
        if not pane_id:
            return None
        try:
            result = self._run(
                [
                    "display-message",
                    "-t",
                    pane_id,
                    "-p",
                    "#{session_name}\t#{window_name}\t#{pane_current_path}\t#{pane_pid}",
                ],
                timeout=3,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        if result.returncode != 0:
            return None
        parts = result.stdout.strip().split("\t")
        if len(parts) < 4:
            return None
        try:
            pid = int(parts[3])
        except ValueError:
            pid = None
        return PaneEvidence(
            pane_id=pane_id,
            tmux_session=f"{parts[0]}:{parts[1]}",
            path=parts[2],
            pid=pid,
        )

    def send_keys(self, pane_id: str, text: str, *, literal: bool = False) -> bool:
        args = ["send-keys", "-t", pane_id]
        if literal:
            args.append("-l")
        args.append(text)
        try:
            return self._run(args, timeout=5).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def _session_exists(self, session_name: str) -> bool:
        try:
            return self._run(["has-session", "-t", session_name], timeout=3).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def _window_names(self, session_name: str) -> set[str]:
        try:
            result = self._run(["list-windows", "-t", session_name, "-F", "#{window_name}"])
        except (OSError, subprocess.SubprocessError):
            return set()
        if result.returncode != 0:
            return set()
        return {line.strip() for line in result.stdout.splitlines() if line.strip()}

    def unique_window_name(self, session_name: str, base_name: str) -> str:
        existing = self._window_names(session_name)
        if base_name not in existing:
            return base_name
        i = 2
        while f"{base_name}-{i}" in existing:
            i += 1
        return f"{base_name}-{i}"

    def spawn_window(
        self, *, session_name: str, window_name: str, cwd: str, command: str
    ) -> MuxSpawnResult:
        if self._session_exists(session_name):
            result = self._run(
                ["new-window", "-d", "-t", session_name, "-n", window_name, "-c", cwd],
                timeout=10,
            )
        else:
            result = self._run(
                ["new-session", "-d", "-s", session_name, "-n", window_name, "-c", cwd],
                timeout=10,
            )
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or "failed to create mux window")

        target = f"{session_name}:{window_name}"
        pane_result = self._run(["display-message", "-t", target, "-p", "#{pane_id}"], timeout=5)
        if pane_result.returncode != 0:
            raise RuntimeError(pane_result.stderr.strip() or "failed to resolve mux pane")
        pane_id = pane_result.stdout.strip()
        if not pane_id:
            raise RuntimeError("failed to resolve mux pane")
        if command and not self.send_keys(pane_id, command, literal=True):
            raise RuntimeError("failed to send spawn command to mux pane")
        if command and not self.send_keys(pane_id, "Enter"):
            raise RuntimeError("failed to submit spawn command to mux pane")
        return MuxSpawnResult(
            display_name=window_name,
            tmux_session=target,
            pane_id=pane_id,
        )

    def kill_pane(self, pane_id: str) -> bool:
        if not pane_id:
            return False
        try:
            return self._run(["kill-pane", "-t", pane_id]).returncode == 0
        except (OSError, subprocess.SubprocessError):
            return False

    def install_lifecycle_hooks(self, host: str = "127.0.0.1", port: int = 8377) -> list[str]:
        from repowire.hooks.tmux_lifecycle import hook_specs

        installed: list[str] = []
        for hook_name, flag, command in hook_specs(host, port):
            tmux_cmd = f"run-shell -b -- {shlex.quote(command)}"
            try:
                result = self._run(
                    ["set-hook", flag, f"{hook_name}[42]", tmux_cmd],
                    timeout=5,
                )
            except (OSError, subprocess.SubprocessError):
                continue
            if result.returncode == 0:
                installed.append(hook_name)
        return installed

    def uninstall_lifecycle_hooks(self) -> list[str]:
        from repowire.hooks.tmux_lifecycle import hook_specs

        removed: list[str] = []
        for hook_name, flag, _ in hook_specs("127.0.0.1", 8377):
            unsetter = flag + "u"
            try:
                result = self._run(["set-hook", unsetter, f"{hook_name}[42]"], timeout=5)
            except (OSError, subprocess.SubprocessError):
                continue
            if result.returncode == 0:
                removed.append(hook_name)
        return removed


class TmuxProvider(TmuxCompatibleProvider):
    kind = MuxProviderKind.TMUX


class PsmuxProvider(TmuxCompatibleProvider):
    kind = MuxProviderKind.PSMUX


class NoMuxProvider:
    kind = MuxProviderKind.NONE
    command = ""

    def is_available(self) -> bool:
        return False

    def list_panes(self) -> list[PaneInfo]:
        return []

    def get_pane_info(self, pane_id: str) -> PaneEvidence | None:
        return None

    def send_keys(self, pane_id: str, text: str, *, literal: bool = False) -> bool:
        return False

    def spawn_window(
        self, *, session_name: str, window_name: str, cwd: str, command: str
    ) -> MuxSpawnResult:
        raise RuntimeError("No terminal multiplexer available")

    def unique_window_name(self, session_name: str, base_name: str) -> str:
        return base_name

    def kill_pane(self, pane_id: str) -> bool:
        return False

    def install_lifecycle_hooks(self, host: str = "127.0.0.1", port: int = 8377) -> list[str]:
        return []

    def uninstall_lifecycle_hooks(self) -> list[str]:
        return []


def _looks_like_psmux(command: str) -> bool:
    try:
        result = subprocess.run(
            [command, "-V"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    text = f"{result.stdout}\n{result.stderr}".lower()
    return "psmux" in text


def resolve_mux_provider(mux_config: Any | None = None) -> MuxProvider:
    provider_raw = getattr(mux_config, "provider", MuxProviderKind.AUTO)
    command = getattr(mux_config, "command", None)
    provider = MuxProviderKind(provider_raw)

    if provider == MuxProviderKind.NONE:
        return NoMuxProvider()
    if provider == MuxProviderKind.TMUX:
        return TmuxProvider(command or "tmux")
    if provider == MuxProviderKind.PSMUX:
        return PsmuxProvider(command or "tmux")

    if sys.platform == "win32":
        if command:
            return PsmuxProvider(command) if _looks_like_psmux(command) else TmuxProvider(command)
        if shutil.which("tmux") and _looks_like_psmux("tmux"):
            return PsmuxProvider("tmux")
        if shutil.which("psmux"):
            return PsmuxProvider("psmux")
        return NoMuxProvider()

    resolved = command or "tmux"
    if shutil.which(resolved):
        return TmuxProvider(resolved)
    return NoMuxProvider()


def current_mux_provider() -> MuxProvider:
    from repowire.config.models import load_config

    return resolve_mux_provider(load_config().daemon.mux)
