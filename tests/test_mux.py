from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from repowire.config.models import Config, DaemonConfig, MuxConfig
from repowire.mux import (
    MuxProviderKind,
    NoMuxProvider,
    PsmuxProvider,
    TmuxProvider,
    resolve_mux_provider,
)


def test_mux_config_defaults_to_auto_provider() -> None:
    cfg = Config()

    assert cfg.daemon.mux.provider == MuxProviderKind.AUTO
    assert cfg.daemon.mux.command is None


def test_resolve_auto_uses_psmux_on_windows_when_tmux_alias_exists() -> None:
    cfg = Config(daemon=DaemonConfig(mux=MuxConfig(provider=MuxProviderKind.AUTO)))

    with (
        patch.object(sys, "platform", "win32"),
        patch("repowire.mux.shutil.which", side_effect=lambda name: f"C:/bin/{name}.exe"),
        patch("repowire.mux._looks_like_psmux", return_value=True),
    ):
        provider = resolve_mux_provider(cfg.daemon.mux)

    assert isinstance(provider, PsmuxProvider)
    assert provider.command == "tmux"


def test_resolve_auto_uses_tmux_on_non_windows() -> None:
    cfg = Config(daemon=DaemonConfig(mux=MuxConfig(provider=MuxProviderKind.AUTO)))

    with (
        patch.object(sys, "platform", "linux"),
        patch("repowire.mux.shutil.which", return_value="/usr/bin/tmux"),
    ):
        provider = resolve_mux_provider(cfg.daemon.mux)

    assert isinstance(provider, TmuxProvider)


def test_resolve_auto_degrades_to_none_when_no_mux_binary() -> None:
    cfg = Config(daemon=DaemonConfig(mux=MuxConfig(provider=MuxProviderKind.AUTO)))

    with patch("repowire.mux.shutil.which", return_value=None):
        provider = resolve_mux_provider(cfg.daemon.mux)

    assert isinstance(provider, NoMuxProvider)


def test_psmux_list_panes_uses_utf8_text_decoding() -> None:
    provider = PsmuxProvider("tmux")
    output = "%1\t123\tpwsh\tC:\\repo\tdev\t0\n"

    with patch("repowire.mux.subprocess.run", return_value=MagicMock(returncode=0, stdout=output)):
        panes = provider.list_panes()

    assert panes == [
        {
            "pane_id": "%1",
            "pid": 123,
            "command": "pwsh",
            "cwd": "C:\\repo",
            "session": "dev",
            "window": "0",
        }
    ]


def test_psmux_send_keys_uses_tmux_compatible_literal_sequence() -> None:
    provider = PsmuxProvider("tmux")

    with patch("repowire.mux.subprocess.run", return_value=MagicMock(returncode=0)) as run:
        assert provider.send_keys("%7", "hello", literal=True) is True

    run.assert_called_once_with(
        ["tmux", "send-keys", "-t", "%7", "-l", "hello"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
        timeout=5,
    )


def test_psmux_install_lifecycle_hooks_uses_tmux_set_hook() -> None:
    provider = PsmuxProvider("tmux")

    with patch("repowire.mux.subprocess.run", return_value=MagicMock(returncode=0)) as run:
        installed = provider.install_lifecycle_hooks("127.0.0.1", 8377)

    assert "pane-exited" in installed
    assert run.call_args_list[0].args[0][0:2] == ["tmux", "set-hook"]
