from __future__ import annotations

from unittest.mock import MagicMock, patch

from repowire.platform.locking import FileLock
from repowire.platform.processes import ProcessInspector, popen_detached_kwargs


def test_file_lock_nonblocking_reports_contested_lock(tmp_path) -> None:
    path = tmp_path / "state.lock"
    first = FileLock(path)
    second = FileLock(path)

    try:
        assert first.acquire(blocking=False) is True
        assert second.acquire(blocking=False) is False
    finally:
        first.release()
        second.release()


def test_process_inspector_uses_psutil_for_liveness() -> None:
    with patch("repowire.platform.processes.psutil.pid_exists", return_value=True) as pid_exists:
        assert ProcessInspector.pid_exists(1234) is True

    pid_exists.assert_called_once_with(1234)


def test_process_inspector_matches_expected_process_in_subtree() -> None:
    root = MagicMock()
    child = MagicMock()
    grandchild = MagicMock()
    root.name.return_value = "pwsh.exe"
    child.name.return_value = "python.exe"
    grandchild.name.return_value = "codex.exe"
    root.children.return_value = [child]
    child.children.return_value = [grandchild]
    grandchild.children.return_value = []

    with patch("repowire.platform.processes.psutil.Process", return_value=root):
        assert ProcessInspector.is_expected_agent_in_subtree(10, "codex") is True


def test_popen_detached_kwargs_uses_create_new_process_group_on_windows() -> None:
    with patch("repowire.platform.processes.os.name", "nt", create=True):
        kwargs = popen_detached_kwargs()

    assert kwargs["creationflags"] != 0
    assert "start_new_session" not in kwargs
