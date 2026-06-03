"""Core spawn functionality for creating new peer sessions."""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import libtmux
from libtmux.exc import LibTmuxException, ObjectDoesNotExist

from repowire.agent_backends import DEFAULT_SPAWN_COMMANDS
from repowire.agent_types import AgentType
from repowire.mux import MuxProviderKind, current_mux_provider
from repowire.spawn_hints import write_hint

# Default commands for each agent type
AGENT_COMMANDS: dict[AgentType, str] = dict(DEFAULT_SPAWN_COMMANDS)


@dataclass
class SpawnConfig:
    """Configuration for spawning a new peer."""

    path: str
    circle: str
    backend: AgentType
    command: str = ""  # Full command to run (e.g., "claude --model opus")
    message: str | None = None  # Optional warmup intent passed to post_spawn_warmup
    role: str | None = None  # Optional peer role (e.g. "orchestrator"); default agent
    peer_id: str | None = None  # Optional same-id reconnect hint for durable restart

    @property
    def display_name(self) -> str:
        """Derive display name from path."""
        return Path(self.path).name


@dataclass
class SpawnResult:
    """Result of spawning a peer."""

    display_name: str
    tmux_session: str  # e.g., "circle:name"
    pane_id: str  # tmux pane id (e.g. "%42") for post-spawn warmup
    message: str | None = None  # Echo of the warmup intent (None = use default)


def spawn_peer(config: SpawnConfig) -> SpawnResult:
    """Spawn a new peer in a tmux window.

    Registration happens automatically via WebSocket when the agent starts.

    Args:
        config: Spawn configuration

    Returns:
        SpawnResult with display_name and tmux_session

    Raises:
        ValueError: If agent type is unknown
        RuntimeError: If tmux operations fail
    """
    display_name = config.display_name

    # Determine command to run
    if config.command:
        cmd = config.command
    elif config.backend in AGENT_COMMANDS:
        cmd = AGENT_COMMANDS[config.backend]
    else:
        raise ValueError(f"Unknown agent type: {config.backend}")

    # Drop a hint so runtimes that strip tmux env (codex) can still discover
    # the requested circle when their MCP/hook subprocess registers. Role is
    # included for spawns that need a non-default role (e.g. orchestrator).
    write_hint(
        config.path,
        config.backend.value,
        config.circle,
        role=config.role,
        peer_id=config.peer_id,
        pending_first_turn=bool(config.message),
    )

    provider = current_mux_provider()
    if provider.kind == MuxProviderKind.NONE:
        raise RuntimeError("No terminal multiplexer available for spawn")
    window_name = provider.unique_window_name(config.circle, display_name)
    result = provider.spawn_window(
        session_name=config.circle,
        window_name=window_name,
        cwd=config.path,
        command=cmd,
    )

    return SpawnResult(
        display_name=result.display_name,
        tmux_session=result.tmux_session,
        pane_id=result.pane_id,
        message=config.message,
    )


def _get_or_create_session(server: libtmux.Server, session_name: str) -> libtmux.Session:
    """Get existing session or create new one."""
    try:
        session = server.sessions.get(session_name=session_name)
        if session:
            return session
    except (LibTmuxException, ObjectDoesNotExist):
        pass

    return server.new_session(session_name=session_name)


def _unique_window_name(session: libtmux.Session, base_name: str) -> str:
    """Generate unique window name, appending suffix if needed."""
    existing_names = {w.name for w in session.windows if w.name}

    if base_name not in existing_names:
        return base_name

    # Find next available suffix
    i = 2
    while f"{base_name}-{i}" in existing_names:
        i += 1
    return f"{base_name}-{i}"


def attach_session(tmux_session: str) -> None:
    """Attach to a tmux session (blocks until detach)."""
    if ":" in tmux_session:
        session_name, window_name = tmux_session.split(":", 1)
        target = f"{session_name}:{window_name}"
    else:
        target = tmux_session

    mux_command = current_mux_provider().command or "tmux"
    subprocess.run([mux_command, "select-window", "-t", target], check=False)
    subprocess.run([mux_command, "attach-session", "-t", target.split(":")[0]], check=True)


def kill_peer(tmux_session: str) -> bool:
    """Kill a tmux window by session:window string.

    Window-name based, so vulnerable to renames. Prefer kill_pane(pane_id)
    when a stable pane id is available.
    """
    if ":" not in tmux_session:
        return False

    session_name, window_name = tmux_session.split(":", 1)
    server = libtmux.Server()

    try:
        session = server.sessions.get(session_name=session_name)
        if session is None:
            return False

        window = session.windows.get(window_name=window_name)
        if window is None:
            return False

        window.kill()
        return True
    except (LibTmuxException, ObjectDoesNotExist):
        return False


def kill_pane(pane_id: str) -> bool:
    """Kill a tmux pane by stable pane id (e.g. "%42").

    Pane ids survive window renames, so this is the preferred kill handle
    for daemon-spawned peers.
    """
    if not pane_id:
        return False
    return current_mux_provider().kill_pane(pane_id)
