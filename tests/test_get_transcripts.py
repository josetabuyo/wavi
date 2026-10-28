"""Audio transcripts reach every place an agent reads them: the bubbles
`wavi get` returns, its listing, its --json-out, and the skill's field table.

An agent once looked for `transcription`, found nothing and reported the
audios as untranscribed — the text was in `transcript` all along."""
import contextlib
import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from click.testing import CliRunner

import wavi.cli as cli
import wavi.queue as queue
import wavi.runner as runner
from wavi.vision import Bubble


def _bubble(id, msg_type="audio", text="0:12", transcript=None):
    return Bubble(id=id, sender="other", msg_type=msg_type, timestamp="12:00",
                  text=text, bbox={"x": 0, "y": 0, "w": 1, "h": 1}, transcript=transcript)


# ── runner._merge_transcripts ─────────────────────────────────────────────────

def test_merge_copies_transcript_from_json(tmp_path):
    p = tmp_path / "history_bubbles.json"
    p.write_text(json.dumps([{"id": 1, "msg_type": "audio", "transcript": "hola"},
                             {"id": 2, "msg_type": "text"}]))
    bubbles = [_bubble(1), _bubble(2, msg_type="text", text="hi")]
    runner._merge_transcripts(bubbles, p)
    assert bubbles[0].transcript == "hola"
    assert bubbles[1].transcript is None


def test_merge_missing_or_broken_json_is_harmless(tmp_path):
    bubbles = [_bubble(1)]
    runner._merge_transcripts(bubbles, tmp_path / "nope.json")
    (tmp_path / "bad.json").write_text("{not json")
    runner._merge_transcripts(bubbles, tmp_path / "bad.json")
    assert bubbles[0].transcript is None


@pytest.mark.asyncio
async def test_run_enhanced_returns_bubbles_with_transcript(tmp_path, monkeypatch):
    b = _bubble(1)

    class FakeRunner:
        def __init__(self, *a, **k): pass
        connect = AsyncMock(return_value="ok")
        open_chat = AsyncMock()
        close = AsyncMock()

        async def capture_full_history(self, assets_dir, **kw):
            (Path(assets_dir) / "history_bubbles.json").write_text(json.dumps([b.as_dict()]))
            return [b]

    async def fake_transcribe(d):
        p = Path(d) / "history_bubbles.json"
        data = json.loads(p.read_text())
        data[0]["transcript"] = "dicho en voz"
        p.write_text(json.dumps(data))

    monkeypatch.setattr(runner, "WARunner", FakeRunner)
    monkeypatch.setattr(runner, "transcribe_history_audios", fake_transcribe)
    result = await runner.run_enhanced(tmp_path, "X", assets_dir=tmp_path)
    assert result["bubbles"][0].transcript == "dicho en voz"


# ── wavi get output ───────────────────────────────────────────────────────────

def _get(monkeypatch, tmp_path, bubbles, *args):
    async def fake_run_enhanced(**kw):
        return {"bubbles": bubbles}

    monkeypatch.setattr(runner, "run_enhanced", fake_run_enhanced)
    monkeypatch.setattr(cli, "_profile", lambda s: tmp_path)
    monkeypatch.setattr(cli, "_lazy_session", lambda p: contextlib.nullcontext())
    monkeypatch.setattr(queue, "is_locked", lambda p: False)
    monkeypatch.setattr(queue, "session_lock", lambda *a, **k: contextlib.nullcontext())
    return CliRunner().invoke(cli.main, ["get", "default", "Ana", "--assets", str(tmp_path / "out"), *args])


def test_get_listing_shows_transcript_and_names_the_field(monkeypatch, tmp_path):
    res = _get(monkeypatch, tmp_path, [_bubble(1, transcript="nos vemos mañana"), _bubble(2)])
    assert res.exit_code == 0, res.output
    assert '🎤 "nos vemos mañana"' in res.output
    assert "🎤 (sin transcripción)" in res.output
    assert "2 audio(s), 1 transcripto(s)" in res.output
    assert "`transcript`" in res.output


def test_get_without_audios_prints_no_audio_summary(monkeypatch, tmp_path):
    res = _get(monkeypatch, tmp_path, [_bubble(1, msg_type="text", text="hola")])
    assert res.exit_code == 0, res.output
    assert "audio(s)" not in res.output
    assert "hola" in res.output


def test_get_json_out_carries_transcript_key(monkeypatch, tmp_path):
    res = _get(monkeypatch, tmp_path, [_bubble(1, transcript="hola")], "--json-out")
    assert res.exit_code == 0, res.output
    data = json.loads(res.stdout[res.stdout.index("["):])
    assert data[0]["transcript"] == "hola"
    assert "transcription" not in data[0]


# ── the skill documents the field ─────────────────────────────────────────────

def test_skill_names_the_transcript_field():
    skill = (Path(cli.__file__).parent / "skill" / "SKILL.md").read_text()
    assert "`transcript`" in skill
    assert "not `transcription`" in skill
