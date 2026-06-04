"""
Tests for wavi.transcription and Bubble.transcript integration.

All tests are offline — no real Groq API calls or audio files needed.
"""
import os
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from wavi.transcription import transcribe, _transcribe_local
from wavi.vision import Bubble


# ── helpers ───────────────────────────────────────────────────────────────────

def _audio_bubble(**kwargs) -> Bubble:
    defaults = dict(
        id=1, sender="other", msg_type="audio",
        timestamp="12:00", text="",
        bbox={"x": 0, "y": 0, "w": 100, "h": 60},
    )
    defaults.update(kwargs)
    return Bubble(**defaults)


# ── Bubble.transcript field ───────────────────────────────────────────────────

class TestBubbleTranscript:
    def test_transcript_default_is_none(self):
        b = _audio_bubble()
        assert b.transcript is None

    def test_transcript_absent_from_as_dict_when_none(self):
        b = _audio_bubble()
        assert "transcript" not in b.as_dict()

    def test_transcript_present_in_as_dict_when_set(self):
        b = _audio_bubble()
        b.transcript = "hola mundo"
        d = b.as_dict()
        assert d["transcript"] == "hola mundo"

    def test_transcript_not_added_to_non_audio_bubble(self):
        b = Bubble(id=1, sender="me", msg_type="text",
                   timestamp="12:00", text="hi",
                   bbox={"x": 0, "y": 0, "w": 100, "h": 30})
        assert b.transcript is None
        assert "transcript" not in b.as_dict()

    def test_as_dict_does_not_include_empty_string_as_none(self):
        """Empty string is a valid transcript (silence), must be included."""
        b = _audio_bubble()
        b.transcript = ""
        d = b.as_dict()
        assert "transcript" in d
        assert d["transcript"] == ""


# ── transcribe() — Groq success path ─────────────────────────────────────────

class TestTranscribeGroqSuccess:
    @pytest.mark.asyncio
    async def test_returns_groq_text_on_success(self, tmp_path):
        fake_ogg = tmp_path / "audio.ogg"
        fake_ogg.write_bytes(b"fake")

        mock_result = MagicMock()
        mock_result.text = "texto transcripto"

        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_result

        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test"}):
            with patch("groq.Groq", return_value=mock_client):
                result = await transcribe(fake_ogg)

        assert result == "texto transcripto"
        mock_client.audio.transcriptions.create.assert_called_once()

    @pytest.mark.asyncio
    async def test_groq_called_with_correct_model_and_language(self, tmp_path):
        fake_ogg = tmp_path / "audio.ogg"
        fake_ogg.write_bytes(b"fake")

        mock_result = MagicMock()
        mock_result.text = "ok"
        mock_client = MagicMock()
        mock_client.audio.transcriptions.create.return_value = mock_result

        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test"}):
            with patch("groq.Groq", return_value=mock_client):
                await transcribe(fake_ogg)

        call_kwargs = mock_client.audio.transcriptions.create.call_args
        assert call_kwargs.kwargs.get("model") == "whisper-large-v3"
        assert call_kwargs.kwargs.get("language") == "es"


# ── transcribe() — fallback paths ────────────────────────────────────────────

class TestTranscribeFallback:
    @pytest.mark.asyncio
    async def test_returns_none_when_no_key_and_no_pywhispercpp(self, tmp_path):
        fake_ogg = tmp_path / "audio.ogg"
        fake_ogg.write_bytes(b"fake")

        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GROQ_API_KEY", None)
            with patch.dict("sys.modules", {"pywhispercpp": None, "pywhispercpp.model": None}):
                result = await transcribe(fake_ogg)

        assert result is None

    @pytest.mark.asyncio
    async def test_falls_back_to_local_when_groq_fails(self, tmp_path):
        fake_ogg = tmp_path / "audio.ogg"
        fake_ogg.write_bytes(b"fake")

        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test"}):
            with patch("groq.Groq", side_effect=Exception("network error")):
                with patch("wavi.transcription._transcribe_local", return_value="fallback text"):
                    result = await transcribe(fake_ogg)

        assert result == "fallback text"

    @pytest.mark.asyncio
    async def test_returns_none_when_both_methods_fail(self, tmp_path):
        fake_ogg = tmp_path / "audio.ogg"
        fake_ogg.write_bytes(b"fake")

        with patch.dict(os.environ, {"GROQ_API_KEY": "gsk_test"}):
            with patch("groq.Groq", side_effect=Exception("network error")):
                with patch("wavi.transcription._transcribe_local",
                           side_effect=RuntimeError("pywhispercpp not installed")):
                    result = await transcribe(fake_ogg)

        assert result is None

    @pytest.mark.asyncio
    async def test_no_key_skips_groq_directly(self, tmp_path):
        """Without GROQ_API_KEY, Groq must not be called at all (ValueError raised early)."""
        fake_ogg = tmp_path / "audio.ogg"
        fake_ogg.write_bytes(b"fake")

        mock_groq_cls = MagicMock()
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("GROQ_API_KEY", None)
            with patch("groq.Groq", mock_groq_cls):
                with patch("wavi.transcription._transcribe_local",
                           side_effect=RuntimeError("no local")):
                    result = await transcribe(fake_ogg)

        mock_groq_cls.assert_not_called()
        assert result is None


# ── download does NOT transcribe inline ──────────────────────────────────────

class TestRunnerDownloadNoInlineTranscription:
    """
    Transcription is deferred to a second pass after browser close.
    _download_audio_for_bubbles must NOT set bubble.transcript.
    """

    @pytest.mark.asyncio
    async def test_download_does_not_set_transcript(self, tmp_path):
        from wavi.runner import WARunner
        runner = WARunner("data/sessions/default")
        runner.session = MagicMock()
        runner.session.reset_blobs = AsyncMock()
        runner.session.get_dpr = AsyncMock(return_value=1.0)
        runner.session.drain_blobs = AsyncMock(return_value=[{"url": "blob:fake"}])
        runner.session._page = MagicMock()
        runner.session._page.mouse = MagicMock()
        runner.session._page.mouse.click = AsyncMock()
        runner.session._page.wait_for_timeout = AsyncMock()
        runner.session.fetch_blob = AsyncMock(return_value=b"\x00" * 100)

        bubble = _audio_bubble(id=5)
        mock_transcribe = AsyncMock(return_value="should not be called")
        with patch.object(runner, "find_play_buttons", AsyncMock(return_value=[{"vx": 100, "vy": 100}])):
            with patch.object(runner, "_match_bubble_to_button", return_value={"vx": 100, "vy": 100}):
                with patch("wavi.runner._transcribe_audio", mock_transcribe):
                    await runner._download_audio_for_bubbles([bubble], assets_dir=tmp_path)

        mock_transcribe.assert_not_called()
        assert bubble.transcript is None


# ── transcribe_history_audios ─────────────────────────────────────────────────

class TestTranscribeHistoryAudios:
    @pytest.mark.asyncio
    async def test_adds_transcript_to_audio_bubbles(self, tmp_path):
        import json
        from wavi.runner import transcribe_history_audios

        ogg = tmp_path / "audio_1.ogg"
        ogg.write_bytes(b"\x00" * 50)

        data = [
            {"id": 1, "msg_type": "audio", "sender": "other", "audio_path": str(ogg)},
            {"id": 2, "msg_type": "text",  "sender": "me", "text": "hello"},
        ]
        json_path = tmp_path / "history_bubbles.json"
        json_path.write_text(json.dumps(data))

        with patch("wavi.runner._transcribe_audio", AsyncMock(return_value="transcripto")):
            count = await transcribe_history_audios(tmp_path)

        assert count == 1
        result = json.loads(json_path.read_text())
        assert result[0]["transcript"] == "transcripto"
        assert "transcript" not in result[1]  # text bubble untouched

    @pytest.mark.asyncio
    async def test_skips_already_transcribed_bubbles(self, tmp_path):
        import json
        from wavi.runner import transcribe_history_audios

        data = [{"id": 1, "msg_type": "audio", "transcript": "ya existe"}]
        json_path = tmp_path / "history_bubbles.json"
        json_path.write_text(json.dumps(data))

        mock_fn = AsyncMock(return_value="nuevo")
        with patch("wavi.runner._transcribe_audio", mock_fn):
            count = await transcribe_history_audios(tmp_path)

        assert count == 0
        mock_fn.assert_not_called()

    @pytest.mark.asyncio
    async def test_raises_if_json_missing(self, tmp_path):
        from wavi.runner import transcribe_history_audios
        with pytest.raises(FileNotFoundError):
            await transcribe_history_audios(tmp_path)

    @pytest.mark.asyncio
    async def test_skips_bubble_without_audio_path(self, tmp_path):
        """Bubble without audio_path (never downloaded) stays without transcript."""
        import json
        from wavi.runner import transcribe_history_audios

        data = [{"id": 99, "msg_type": "audio"}]  # no audio_path key
        json_path = tmp_path / "history_bubbles.json"
        json_path.write_text(json.dumps(data))

        with patch("wavi.runner._transcribe_audio", AsyncMock(return_value="x")):
            count = await transcribe_history_audios(tmp_path)

        assert count == 0
        result = json.loads(json_path.read_text())
        assert "transcript" not in result[0]

    @pytest.mark.asyncio
    async def test_ogg_found_via_audio_path(self, tmp_path):
        """audio_path points directly to the file regardless of screen_id vs global_id."""
        import json
        from wavi.runner import transcribe_history_audios

        iter_dir = tmp_path / "iter_002"
        iter_dir.mkdir()
        ogg = iter_dir / "audio_17.ogg"  # screen_id=17, but global_id=40
        ogg.write_bytes(b"\x00" * 50)

        data = [{"id": 40, "msg_type": "audio", "audio_path": str(ogg)}]
        json_path = tmp_path / "history_bubbles.json"
        json_path.write_text(json.dumps(data))

        with patch("wavi.runner._transcribe_audio", AsyncMock(return_value="encontrado")):
            count = await transcribe_history_audios(tmp_path)

        assert count == 1
        result = json.loads(json_path.read_text())
        assert result[0]["transcript"] == "encontrado"
