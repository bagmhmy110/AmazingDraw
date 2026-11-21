"""Windows fallback for the parts of :mod:`fcntl` used by cu-queue.py.

The upstream release imports ``fcntl`` unconditionally, which makes every
queue/worker entry point die on Windows with ``ModuleNotFoundError``.
This module reimplements ``flock`` on top of ``msvcrt.locking`` with the
same call shape (``flock(fileobj_or_fd, op)``), so the rest of the file
does not need to change.

Only the advisory-lock subset is provided: LOCK_EX, LOCK_SH, LOCK_UN,
LOCK_NB.
"""
from __future__ import annotations

import msvcrt
import os

LOCK_SH = 0x01
LOCK_EX = 0x02
LOCK_NB = 0x04
LOCK_UN = 0x08

# msvcrt locks a byte range starting at the current file position.
# Locking a single byte at offset 0 is enough for whole-file mutual exclusion.
_LOCK_BYTES = 1


def _fd_of(target) -> int:
    if isinstance(target, int):
        return target
    fileno = getattr(target, "fileno", None)
    if fileno is None:
        raise TypeError(f"flock() argument must be a file object or fd, got {type(target)!r}")
    return fileno()


def _seek_start(fd: int) -> None:
    try:
        os.lseek(fd, 0, os.SEEK_SET)
    except OSError:
        pass


def flock(target, operation: int) -> None:
    fd = _fd_of(target)
    _seek_start(fd)

    if operation & LOCK_UN:
        try:
            msvcrt.locking(fd, msvcrt.LK_UNLCK, _LOCK_BYTES)
        except OSError:
            # Nothing held, or the handle was closed underneath us.
            pass
        return

    blocking = not (operation & LOCK_NB)
    mode = msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK
    try:
        msvcrt.locking(fd, mode, _LOCK_BYTES)
    except OSError as exc:
        if operation & LOCK_NB:
            # Match POSIX behaviour: non-blocking failure raises BlockingIOError.
            raise BlockingIOError(exc.errno, "lock held by another process") from exc
        raise
