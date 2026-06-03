"""Tests for service installer lifecycle helpers."""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from repowire.service import installer


def test_restart_service_dispatches_macos() -> None:
    with patch("repowire.service.installer.get_platform", return_value="macos"):
        with patch(
            "repowire.service.installer._restart_macos_service",
            return_value=(True, "Service restarted"),
        ) as mock_restart:
            success, message = installer.restart_service()

    assert success is True
    assert message == "Service restarted"
    mock_restart.assert_called_once_with()


def test_restart_service_dispatches_linux() -> None:
    with patch("repowire.service.installer.get_platform", return_value="linux"):
        with patch(
            "repowire.service.installer._restart_linux_service",
            return_value=(True, "Service restarted"),
        ) as mock_restart:
            success, message = installer.restart_service()

    assert success is True
    assert message == "Service restarted"
    mock_restart.assert_called_once_with()


def test_restart_service_dispatches_windows() -> None:
    with patch("repowire.service.installer.get_platform", return_value="windows"):
        with patch(
            "repowire.service.installer._restart_windows_service",
            return_value=(True, "Service restarted"),
        ) as mock_restart:
            success, message = installer.restart_service()

    assert success is True
    assert message == "Service restarted"
    mock_restart.assert_called_once_with()


def test_restart_service_unsupported_platform() -> None:
    with patch("repowire.service.installer.get_platform", return_value="unsupported"):
        with patch.object(installer.sys, "platform", "unknown-os"):
            success, message = installer.restart_service()

    assert success is False
    assert message == "Unsupported platform: unknown-os"


def test_restart_macos_service_returns_not_installed() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        plist_path = Path(tmpdir) / "io.repowire.daemon.plist"

        with patch("repowire.service.installer._get_launchd_plist_path", return_value=plist_path):
            success, message = installer._restart_macos_service()

    assert success is False
    assert message == "Service is not installed"


def test_restart_macos_service_reloads_launchd_service() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        plist_path = Path(tmpdir) / "io.repowire.daemon.plist"
        plist_path.write_text("dummy")

        run_result = MagicMock(returncode=0, stderr="")

        with patch("repowire.service.installer._get_launchd_plist_path", return_value=plist_path):
            with patch(
                "repowire.service.installer.subprocess.run", return_value=run_result
            ) as mock_run:
                success, message = installer._restart_macos_service()

    assert success is True
    assert message == "Service restarted"
    assert mock_run.call_count == 2
    assert mock_run.call_args_list[0].args[0] == ["launchctl", "unload", str(plist_path)]
    assert mock_run.call_args_list[1].args[0] == ["launchctl", "load", str(plist_path)]


def test_restart_linux_service_returns_not_installed() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        service_path = Path(tmpdir) / "repowire.service"

        with patch(
            "repowire.service.installer._get_systemd_service_path", return_value=service_path
        ):
            success, message = installer._restart_linux_service()

    assert success is False
    assert message == "Service is not installed"


def test_restart_macos_service_load_failure() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        plist_path = Path(tmpdir) / "io.repowire.daemon.plist"
        plist_path.write_text("dummy")

        unload_result = MagicMock(returncode=0, stderr="")
        load_result = MagicMock(returncode=1, stderr="Could not load plist")

        with patch("repowire.service.installer._get_launchd_plist_path", return_value=plist_path):
            with patch(
                "repowire.service.installer.subprocess.run",
                side_effect=[unload_result, load_result],
            ):
                success, message = installer._restart_macos_service()

    assert success is False
    assert "Failed to restart service" in message
    assert "Could not load plist" in message


def test_restart_linux_service_systemctl_failure() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        service_path = Path(tmpdir) / "repowire.service"
        service_path.write_text("dummy")

        run_result = MagicMock(returncode=1, stderr="Unit not found")

        with patch(
            "repowire.service.installer._get_systemd_service_path", return_value=service_path
        ):
            with patch(
                "repowire.service.installer.subprocess.run", return_value=run_result
            ):
                success, message = installer._restart_linux_service()

    assert success is False
    assert "Failed to restart service" in message
    assert "Unit not found" in message


def test_restart_linux_service_runs_systemctl_restart() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        service_path = Path(tmpdir) / "repowire.service"
        service_path.write_text("dummy")

        run_result = MagicMock(returncode=0, stderr="")

        with patch(
            "repowire.service.installer._get_systemd_service_path", return_value=service_path
        ):
            with patch(
                "repowire.service.installer.subprocess.run", return_value=run_result
            ) as mock_run:
                success, message = installer._restart_linux_service()

    assert success is True
    assert message == "Service restarted"
    mock_run.assert_called_once_with(
        ["systemctl", "--user", "restart", installer.LINUX_SERVICE_NAME],
        capture_output=True,
        text=True,
    )


def test_get_platform_detects_windows() -> None:
    with patch.object(installer.sys, "platform", "win32"):
        assert installer.get_platform() == "windows"


def test_install_windows_service_uses_schtasks_create() -> None:
    run_result = MagicMock(returncode=0, stderr="")

    with (
        patch("repowire.service.installer._get_repowire_executable", return_value="repowire"),
        patch("repowire.service.installer._get_log_path", return_value=Path("C:/Users/test/.repowire/daemon.log")),
        patch("repowire.service.installer.subprocess.run", return_value=run_result) as mock_run,
    ):
        success, message = installer._install_windows_service()

    assert success is True
    assert "RepowireDaemon" in message
    args = mock_run.call_args.args[0]
    assert args[:4] == ["schtasks", "/Create", "/TN", installer.WINDOWS_TASK_NAME]
    assert "/SC" in args
    assert "ONLOGON" in args
    assert "/TR" in args
    assert "repowire serve" in args[args.index("/TR") + 1]
    assert "Set-Location" in args[args.index("/TR") + 1]


def test_get_windows_service_status_parses_running_task() -> None:
    query_result = MagicMock(returncode=0, stdout="TaskName: RepowireDaemon\r\nStatus: Running")

    with patch("repowire.service.installer.subprocess.run", return_value=query_result):
        status = installer._get_windows_service_status()

    assert status["installed"] is True
    assert status["running"] is True
    assert status["path"] == installer.WINDOWS_TASK_NAME
