"""
Tests del pipeline de visión wavi.

Cubre funciones puras que no requieren browser ni imágenes reales.
Correr:
    cd /Users/josetabuyo/Development/wavi
    source .venv/bin/activate
    pytest tests/ -v
"""
import pytest
import numpy as np
from PIL import Image

from wavi.vision import (
    classify_msg_type,
    _is_waveform_garbage,
    _extract_timestamp,
    _classify_x,
    _is_noise,
)


def _blocks(*texts):
    return [{"text": t} for t in texts]


# ── classify_msg_type ─────────────────────────────────────────────────────────

class TestClassifyMsgType:
    def test_plain_text(self):
        assert classify_msg_type("Hola cómo estás?", _blocks("Hola cómo estás?")) == "text"

    def test_audio_by_duration(self):
        assert classify_msg_type("0:21 7:15 p. m.", _blocks("0:21", "7:15 p. m.")) == "audio"

    def test_audio_duration_not_confused_with_time(self):
        assert classify_msg_type("Nos vemos a las 7:15 p. m.", _blocks("Nos vemos a las 7:15 p. m.")) == "text"

    def test_audio_by_waveform_garbage(self):
        assert classify_msg_type("", _blocks("||00||0|1|0||10||")) == "audio"

    def test_file_by_extension(self):
        assert classify_msg_type("presupuesto.xlsx 48 kB", _blocks("presupuesto.xlsx", "48 kB")) == "file"

    def test_file_by_size(self):
        assert classify_msg_type("reporte.pdf 1.2 MB", _blocks("reporte.pdf", "1.2 MB")) == "file"

    def test_file_takes_priority_over_audio(self):
        assert classify_msg_type("grabacion.mp4 2.5 MB", _blocks("grabacion.mp4", "2.5 MB")) == "file"

    def test_media_empty_text(self):
        assert classify_msg_type("", _blocks()) == "media"

    def test_media_blank_blocks(self):
        assert classify_msg_type("  ", _blocks("  ")) == "media"

    def test_multiline_text(self):
        result = classify_msg_type(
            "si, te decía si querías subir la página",
            _blocks("si, te decía si querías subir la página", "7:17 p. m."),
        )
        assert result == "text"


# ── _is_waveform_garbage ──────────────────────────────────────────────────────

class TestIsWaveformGarbage:
    def test_waveform_noise(self):
        assert _is_waveform_garbage("||0||0|019 0") is True

    def test_waveform_pipe_heavy(self):
        assert _is_waveform_garbage("|•01-[]lL|•01") is True

    def test_normal_text(self):
        assert _is_waveform_garbage("Hola cómo estás?") is False

    def test_too_short(self):
        assert _is_waveform_garbage("|0|") is False

    def test_mixed_but_below_threshold(self):
        assert _is_waveform_garbage("hola|") is False


# ── _extract_timestamp ────────────────────────────────────────────────────────

class TestExtractTimestamp:
    def test_standalone_block(self):
        blocks = [{"text": "Hola"}, {"text": "7:15 p. m."}]
        assert _extract_timestamp(blocks) == "7:15 p. m."

    def test_embedded_at_end(self):
        blocks = [{"text": "Que haces capo??!! 7:29 p. m."}]
        result = _extract_timestamp(blocks)
        assert result is not None
        assert "7:29" in result

    def test_am_time(self):
        blocks = [{"text": "10:03 a. m."}]
        assert _extract_timestamp(blocks) == "10:03 a. m."

    def test_no_timestamp(self):
        blocks = [{"text": "Hola"}, {"text": "cómo estás"}]
        assert _extract_timestamp(blocks) is None

    def test_duration_not_matched_as_timestamp(self):
        blocks = [{"text": "0:21"}]
        assert _extract_timestamp(blocks) is None

    def test_prefers_standalone_over_embedded(self):
        blocks = [
            {"text": "queres que hablemos por telefono? 7:17 p. m."},
            {"text": "7:17 p. m."},
        ]
        result = _extract_timestamp(blocks)
        assert result == "7:17 p. m."


# ── _classify_x ───────────────────────────────────────────────────────────────

class TestClassifyX:
    def test_right_edge_is_me(self):
        assert _classify_x(0.6, 0.3) == "me"   # right_edge=0.9 > 0.75

    def test_left_edge_is_other(self):
        assert _classify_x(0.05, 0.3) == "other"  # x=0.05 < 0.15

    def test_center_right_is_me(self):
        assert _classify_x(0.4, 0.3) == "me"   # center=0.55 > 0.50

    def test_center_left_is_other(self):
        assert _classify_x(0.2, 0.3) == "other"  # center=0.35 < 0.50


# ── _is_noise ─────────────────────────────────────────────────────────────────

class TestIsNoise:
    def test_empty(self):
        assert _is_noise("") is True

    def test_single_char(self):
        assert _is_noise("a") is True

    def test_plus_sign(self):
        assert _is_noise("+") is True

    def test_real_text(self):
        assert _is_noise("Hola cómo estás?") is False

    def test_audio_duration_kept(self):
        assert _is_noise("0:21") is False

    def test_cyrillic_filtered(self):
        assert _is_noise("Привет") is True
