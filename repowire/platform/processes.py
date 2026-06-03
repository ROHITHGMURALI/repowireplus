"""Cross-platform process helpers."""

from __future__ import annotations

import os
import subprocess

import psutil


class ProcessInspector:
    """Thin wrapper over psutil so tests and hooks share one process model."""

    @staticmethod
    def pid_exists(pid: int) -> bool:
        return psutil.pid_exists(pid)

    @staticmethod
    def command_name(pid: int) -> str | None:
        try:
            return os.path.basename(psutil.Process(pid).name()).lower()
        except (psutil.Error, OSError):
            return None

    @staticmethod
    def children_recursive(pid: int) -> list[int]:
        try:
            proc = psutil.Process(pid)
            return [child.pid for child in proc.children(recursive=True)]
        except (psutil.Error, OSError):
            return []

    @staticmethod
    def parent_pid(pid: int) -> int | None:
        try:
            return psutil.Process(pid).ppid()
        except (psutil.Error, OSError):
            return None

    @staticmethod
    def is_expected_agent_in_subtree(root_pid: int, expected: str) -> bool:
        return ProcessInspector.find_command_in_subtree(root_pid, expected) is not None

    @staticmethod
    def find_command_in_subtree(root_pid: int, expected: str) -> int | None:
        target = expected.lower()
        try:
            root = psutil.Process(root_pid)
            processes = [root, *root.children(recursive=True)]
        except (psutil.Error, OSError):
            return None
        for proc in processes:
            try:
                name = os.path.basename(proc.name()).lower()
            except (psutil.Error, OSError):
                continue
            if name == target or name == f"{target}.exe":
                return proc.pid
        return None

    @staticmethod
    def first_non_shell_command(root_pid: int, shell_names: set[str] | frozenset[str]) -> str | None:
        try:
            root = psutil.Process(root_pid)
            processes = [root, *root.children(recursive=True)]
        except (psutil.Error, OSError):
            return None
        for proc in processes:
            try:
                name = os.path.basename(proc.name()).lower()
            except (psutil.Error, OSError):
                continue
            if name and name not in shell_names and name.removesuffix(".exe") not in shell_names:
                return name
        return None


def terminate_pid(pid: int, *, force: bool = False) -> bool:
    try:
        proc = psutil.Process(pid)
        proc.kill() if force else proc.terminate()
        return True
    except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
        return False


def popen_detached_kwargs() -> dict:
    if os.name == "nt":
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}
