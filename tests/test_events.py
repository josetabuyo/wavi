"""
Tests de wavi/events.py — el log de eventos de sesión (ADR-009 / wa-session-guard:
"Log every connection event").

Verifican que:
  - log_event nunca lanza (una falla de logging no puede romper la operación real).
  - Cada línea es JSON válido con ts/session/event.
  - read_events filtra por sesión y respeta el límite.
"""
import json

from wavi.events import log_event, read_events


def test_log_event_writes_valid_json_line(tmp_path):
    log_event(tmp_path, "5491155612767", "connect_start", force_new=False)
    lines = (tmp_path / "events.log").read_text().splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["session"] == "5491155612767"
    assert record["event"] == "connect_start"
    assert record["force_new"] is False
    assert "ts" in record


def test_log_event_appends_not_overwrites(tmp_path):
    log_event(tmp_path, "s1", "connect_start")
    log_event(tmp_path, "s1", "qr_needed")
    log_event(tmp_path, "s1", "auth_wait_result", result="authenticated")
    lines = (tmp_path / "events.log").read_text().splitlines()
    assert len(lines) == 3


def test_log_event_never_raises_on_bad_dir(tmp_path):
    # A file where a directory is expected — must not propagate an exception.
    bad = tmp_path / "not_a_dir"
    bad.write_text("x")
    log_event(bad, "s1", "connect_start")  # should not raise


def test_read_events_filters_by_session(tmp_path):
    log_event(tmp_path, "session-a", "connect_start")
    log_event(tmp_path, "session-b", "connect_start")
    log_event(tmp_path, "session-a", "qr_needed")

    only_a = read_events(tmp_path, session="session-a")
    assert len(only_a) == 2
    assert all(r["session"] == "session-a" for r in only_a)


def test_read_events_respects_limit(tmp_path):
    for i in range(10):
        log_event(tmp_path, "s1", f"event_{i}")
    recent = read_events(tmp_path, session="s1", limit=3)
    assert len(recent) == 3
    assert recent[-1]["event"] == "event_9"


def test_read_events_returns_empty_list_when_no_log(tmp_path):
    assert read_events(tmp_path, session="nope") == []


def test_critical_profile_archived_event_is_logged(tmp_path):
    """El evento más crítico del ADR-009: cuando --new archiva un perfil
    existente en vez de borrarlo, debe quedar registrado con el nombre del
    archivo destino."""
    log_event(
        tmp_path, "5491155612767", "profile_archived",
        archived_to="5491155612767_archived_1786998216",
        reason="connect_new_collision",
    )
    events = read_events(tmp_path, session="5491155612767")
    assert events[0]["event"] == "profile_archived"
    assert events[0]["archived_to"] == "5491155612767_archived_1786998216"
