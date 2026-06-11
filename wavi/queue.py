"""
Per-session operation queue via POSIX file locks (fcntl.flock).

Guarantees at most one heavyweight operation (e.g. `get`) runs per session at
a time.  Concurrent callers block on flock(LOCK_EX) until the current holder
releases the lock — the OS handles the wait and wakeup automatically.

Files written inside the session profile directory:
  session_queue.lock  — POSIX advisory lock (always held by the running process)
  session_queue.json  — JSON status while the lock is held; removed on release
"""
from __future__ import annotations

import fcntl
import json
import os
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path

_LOCK_FILE   = "session_queue.lock"
_STATUS_FILE = "session_queue.json"


def _lock_path(profile: Path) -> Path:
    return profile / _LOCK_FILE


def _status_path(profile: Path) -> Path:
    return profile / _STATUS_FILE


@contextmanager
def session_lock(profile: Path, operation: str, **meta):
    """
    Acquire an exclusive file lock for the session.

    Blocks until the lock is free, then writes a JSON status file and yields.
    The status file is removed and the lock released when the context exits,
    even if an exception is raised.

    Usage::
        with session_lock(profile, "get", contact="Luis Perez"):
            await run_enhanced(...)
    """
    profile.mkdir(parents=True, exist_ok=True)
    lock_path   = _lock_path(profile)
    status_path = _status_path(profile)

    with open(lock_path, "w") as lock_fh:
        fcntl.flock(lock_fh, fcntl.LOCK_EX)
        try:
            status_path.write_text(json.dumps({
                "operation":  operation,
                "pid":        os.getpid(),
                "started_at": datetime.now(UTC).isoformat(),
                **meta,
            }))
            yield
        finally:
            status_path.unlink(missing_ok=True)
            fcntl.flock(lock_fh, fcntl.LOCK_UN)


def get_status(profile: Path) -> dict | None:
    """
    Read the current queue status without blocking.

    Returns None when idle or when the recorded process is no longer alive
    (stale status from a crashed run).
    """
    status_path = _status_path(profile)
    if not status_path.exists():
        return None

    try:
        data = json.loads(status_path.read_text())
    except Exception:
        return None

    pid = data.get("pid")
    if pid:
        try:
            os.kill(pid, 0)
        except (OSError, ProcessLookupError):
            return None  # process gone — stale file

    return data


def is_locked(profile: Path) -> bool:
    """Non-blocking check: True if the session lock is currently held."""
    lock_path = _lock_path(profile)
    if not lock_path.exists():
        return False
    try:
        with open(lock_path) as f:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            fcntl.flock(f, fcntl.LOCK_UN)
            return False
    except OSError:
        return True
