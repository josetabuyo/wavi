"""'wavi media --type' routing: documents come from the chat walk, photos and
videos from the viewer, and --limit is shared between them."""
import contextlib
from unittest.mock import AsyncMock, MagicMock

import pytest
from click.testing import CliRunner

import wavi.cli as cli
import wavi.media as media
import wavi.queue as queue
import wavi.session as session


@pytest.fixture
def calls(monkeypatch, tmp_path):
    got = {}

    async def docs(s, out_dir, **kw):
        got["document"] = kw
        return [{"kind": "document", "timestamp": None, "sender": "M", "bytes": 1, "file": "a.zip"}]

    async def viewer(s, out_dir, **kw):
        got["viewer"] = kw
        return []

    monkeypatch.setattr(media, "download_chat_documents", docs)
    monkeypatch.setattr(media, "download_chat_media", viewer)
    fake = MagicMock()
    fake.connect = fake.navigate_to_contact = fake.close = AsyncMock()
    monkeypatch.setattr(session, "WASession", lambda *a: fake)
    monkeypatch.setattr(cli, "_profile", lambda s: tmp_path)
    monkeypatch.setattr(cli, "_lazy_session", lambda p: contextlib.nullcontext())
    monkeypatch.setattr(queue, "is_locked", lambda p: False)
    monkeypatch.setattr(queue, "session_lock", lambda *a, **k: contextlib.nullcontext())
    return got


def _run(*args, tmp_path):
    return CliRunner().invoke(cli.main, ["media", "default", "Matias", "--assets", str(tmp_path), *args])


def test_type_document_only_walks_documents(calls, tmp_path):
    result = _run("--type", "document", "--from", "2026-10-21", tmp_path=tmp_path)
    assert result.exit_code == 0, result.output
    assert set(calls) == {"document"}
    assert calls["document"]["chat_name"] == "Matias"


def test_all_takes_documents_then_viewer_sharing_the_limit(calls, tmp_path):
    result = _run("--limit", "3", tmp_path=tmp_path)
    assert result.exit_code == 0, result.output
    assert calls["document"]["limit"] == 3
    assert calls["viewer"]["kinds"] == ("video", "image")
    assert calls["viewer"]["limit"] == 2


def test_limit_used_up_by_documents_skips_viewer(calls, tmp_path):
    _run("--limit", "1", tmp_path=tmp_path)
    assert "viewer" not in calls
