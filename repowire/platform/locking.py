"""Small cross-platform file lock wrapper."""

from __future__ import annotations

import os
from pathlib import Path

if os.name == "nt":
    import msvcrt
else:
    import fcntl


class FileLock:
    """Exclusive byte-range/file lock usable on Windows and POSIX."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self._file = None
        self._locked = False

    def acquire(self, *, blocking: bool = True) -> bool:
        if self._file is not None:
            return self._locked
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = open(self.path, "a+")
        try:
            if os.name == "nt":
                mode = msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK
                self._file.seek(0)
                msvcrt.locking(self._file.fileno(), mode, 1)
            else:
                flags = fcntl.LOCK_EX
                if not blocking:
                    flags |= fcntl.LOCK_NB
                fcntl.flock(self._file.fileno(), flags)
        except OSError:
            self._file.close()
            self._file = None
            return False
        self._locked = True
        return True

    def release(self) -> None:
        if not self._file:
            return
        try:
            if self._locked:
                if os.name == "nt":
                    self._file.seek(0)
                    try:
                        msvcrt.locking(self._file.fileno(), msvcrt.LK_UNLCK, 1)
                    except OSError:
                        pass
                else:
                    fcntl.flock(self._file.fileno(), fcntl.LOCK_UN)
        finally:
            self._locked = False
            self._file.close()
            self._file = None

    def close(self) -> None:
        self.release()

    def __enter__(self) -> FileLock:
        self.acquire(blocking=True)
        return self

    def __exit__(self, *_exc: object) -> None:
        self.release()
