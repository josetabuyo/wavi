"""
events.py — append-only, timestamped log of WhatsApp session lifecycle events.

Exists because there was no forensic trail: when a session unexpectedly
showed up as qr_needed, there was no way to reconstruct what happened right
before it (a reload? an expired QR nobody scanned? the daemon restarting?).
See docs/adr/ADR-009 and .claude/skills/wa-session-guard.md — "Log every
connection event" was a known, unaddressed gap until this file.

One JSON line per event in <sessions_dir>/events.log. Never raises — a
logging failure must never break the actual session operation.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

_LOG_FILENAME = "events.log"


def log_event(sessions_dir: Path, session: str, event: str, **fields) -> None:
    """Append one JSON line: {ts, session, event, **fields}."""
    try:
        record = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
            "session": session,
            "event": event,
            **fields,
        }
        path = Path(sessions_dir) / _LOG_FILENAME
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def read_events(sessions_dir: Path, session: str | None = None, limit: int = 200) -> list[dict]:
    """Return the last `limit` events, optionally filtered by session name."""
    path = Path(sessions_dir) / _LOG_FILENAME
    if not path.exists():
        return []
    out: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except Exception:
            continue
        if session is None or record.get("session") == session:
            out.append(record)
    return out[-limit:]
