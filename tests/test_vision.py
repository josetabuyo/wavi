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
from pathlib import Path
from PIL import Image

from wavi.vision import (
    classify_msg_type,
    _is_waveform_garbage,
    _extract_timestamp,
    _classify_x,
    _is_noise,
    _save_debug_image,
    Bubble,
)
from wavi.element_detector import detect_bubbles


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


# ── _save_debug_image ─────────────────────────────────────────────────────────

def _make_bubble(id: int, sender: str, msg_type: str = "text", bbox: dict | None = None) -> Bubble:
    return Bubble(
        id=id, sender=sender, msg_type=msg_type,
        timestamp="7:00 p. m.", text="hola",
        bbox=bbox or {"x": 10, "y": 10 + id * 50, "w": 200, "h": 40},
    )


class TestSaveDebugImage:
    def test_creates_file(self, tmp_path):
        img = Image.new("RGB", (400, 300), color=(243, 238, 231))
        out = tmp_path / "debug.png"
        bubbles = [_make_bubble(1, "me"), _make_bubble(2, "other")]
        _save_debug_image(img, bubbles, out)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_output_is_valid_image(self, tmp_path):
        img = Image.new("RGB", (400, 300), color=(243, 238, 231))
        out = tmp_path / "debug.png"
        _save_debug_image(img, [_make_bubble(1, "me")], out)
        result = Image.open(out)
        assert result.size == (400, 300)
        assert result.mode == "RGB"

    def test_empty_bubbles(self, tmp_path):
        img = Image.new("RGB", (400, 300), color=(243, 238, 231))
        out = tmp_path / "debug.png"
        _save_debug_image(img, [], out)
        assert out.exists()

    def test_box_drawn_changes_pixels(self, tmp_path):
        img = Image.new("RGB", (400, 300), color=(243, 238, 231))
        out = tmp_path / "debug.png"
        bubble = _make_bubble(1, "me", bbox={"x": 50, "y": 50, "w": 200, "h": 80})
        _save_debug_image(img, [bubble], out)
        result = Image.open(out)
        region = result.crop((50, 50, 250, 130))
        original = img.crop((50, 50, 250, 130))
        assert list(region.get_flattened_data()) != list(original.get_flattened_data())

    def test_cross_drawn_only_on_audio_and_file(self, tmp_path):
        """Cross appears on audio/file bubbles; absent on text/media."""
        bg = (243, 238, 231)
        img = Image.new("RGB", (800, 600), color=bg)
        # Use realistic WA dimensions: me audio needs room for avatar (x+188), h=136
        me_audio_bbox   = {"x": 10, "y": 50,  "w": 250, "h": 136}
        other_file_bbox = {"x": 10, "y": 250, "w": 200, "h": 136}
        text_bbox       = {"x": 10, "y": 450, "w": 200, "h": 60}
        bubbles = [
            _make_bubble(1, "me",    "audio", me_audio_bbox),
            _make_bubble(2, "other", "file",  other_file_bbox),
            _make_bubble(3, "me",    "text",  text_bbox),
        ]
        out = tmp_path / "debug.png"
        _save_debug_image(img, bubbles, out)
        result = Image.open(out).convert("RGB")

        def is_red(px):
            r, g, b = px
            return r > 150 and g < 100 and b < 100

        # me audio: cross at x+188, y+h-75
        assert is_red(result.getpixel((me_audio_bbox["x"] + 188, me_audio_bbox["y"] + me_audio_bbox["h"] - 75))), "me audio cross missing"
        # other file: cross at x+78, y+h-75
        assert is_red(result.getpixel((other_file_bbox["x"] + 78, other_file_bbox["y"] + other_file_bbox["h"] - 75))), "other file cross missing"
        # text: no red cross at the audio cross position
        assert not is_red(result.getpixel((text_bbox["x"] + 78, text_bbox["y"] + text_bbox["h"] // 2))), "text must not have cross"

    def test_cross_me_vs_other_x_offset(self, tmp_path):
        """
        'me' cross must be at x+188 (avatar on left before play btn).
        'other' cross must be at x+78 (play btn near left edge).
        Neither should appear at the old wrong offset x+22.
        """
        bg = (243, 238, 231)
        img = Image.new("RGB", (800, 400), color=bg)
        me_bbox    = {"x": 10, "y": 20,  "w": 250, "h": 136}
        other_bbox = {"x": 10, "y": 200, "w": 200, "h": 136}
        bubbles = [
            _make_bubble(1, "me",    "audio", me_bbox),
            _make_bubble(2, "other", "audio", other_bbox),
        ]
        out = tmp_path / "debug.png"
        _save_debug_image(img, bubbles, out)
        result = Image.open(out).convert("RGB")

        def is_red(px):
            r, g, b = px
            return r > 150 and g < 100 and b < 100

        me_cy    = me_bbox["y"]    + me_bbox["h"]    - 75
        other_cy = other_bbox["y"] + other_bbox["h"] - 75

        # Correct positions
        assert is_red(result.getpixel((me_bbox["x"] + 188, me_cy))),    "me cross at x+188 missing"
        assert is_red(result.getpixel((other_bbox["x"] + 78, other_cy))), "other cross at x+78 missing"
        # Old wrong position must NOT have cross
        assert not is_red(result.getpixel((me_bbox["x"] + 22, me_cy))),    "me cross must not be at old x+22"
        assert not is_red(result.getpixel((other_bbox["x"] + 22, other_cy))), "other cross must not be at old x+22"

    def test_cross_tall_bubble_bottom_anchored(self, tmp_path):
        """
        For tall bubbles (quoted reply on top + audio at bottom), the cross must land
        in the audio player row at the bottom — not at the vertical center of the whole bubble.
        h=136 is a standard audio-only bubble; h=261 simulates a quoted reply above it.
        Both must yield a cross 75px from the bottom edge.
        """
        bg = (243, 238, 231)
        img = Image.new("RGB", (800, 600), color=bg)
        short_bbox = {"x": 10, "y": 20,  "w": 700, "h": 136}  # audio only
        tall_bbox  = {"x": 10, "y": 200, "w": 700, "h": 261}  # quoted reply + audio
        bubbles = [
            _make_bubble(1, "other", "audio", short_bbox),
            _make_bubble(2, "other", "audio", tall_bbox),
        ]
        out = tmp_path / "debug.png"
        _save_debug_image(img, bubbles, out)
        result = Image.open(out).convert("RGB")

        def is_red(px):
            r, g, b = px
            return r > 150 and g < 100 and b < 100

        cx = 10 + 78  # "other" x offset

        # Both crosses must be 75px from their respective bottom edges
        assert is_red(result.getpixel((cx, short_bbox["y"] + short_bbox["h"] - 75))), "short bubble cross wrong"
        assert is_red(result.getpixel((cx, tall_bbox["y"]  + tall_bbox["h"]  - 75))), "tall bubble cross wrong"

        # The tall bubble's cross must NOT be at the vertical center (that's the old bug)
        wrong_cy = tall_bbox["y"] + tall_bbox["h"] // 2
        assert not is_red(result.getpixel((cx, wrong_cy))), "tall bubble cross must not be at vertical center"

    def test_cross_uses_exact_play_position_when_provided(self, tmp_path):
        """When play_positions are given, the cross is drawn at those coords, not estimated."""
        bg = (243, 238, 231)
        img = Image.new("RGB", (400, 200), color=bg)
        bbox = {"x": 10, "y": 50, "w": 200, "h": 60}
        bubble = _make_bubble(1, "me", "audio", bbox)
        exact_cx, exact_cy = 45, 80   # exact play button position (not at x+22)

        out = tmp_path / "debug.png"
        _save_debug_image(img, [bubble], out, play_positions={1: (exact_cx, exact_cy)})
        result = Image.open(out).convert("RGB")

        def is_red(px):
            r, g, b = px
            return r > 150 and g < 100 and b < 100

        assert is_red(result.getpixel((exact_cx, exact_cy))), "cross must be at exact position"
        estimated_x = bbox["x"] + 22
        assert not is_red(result.getpixel((estimated_x, exact_cy))), "cross must NOT be at estimated position"


# ── detect_bubbles with embedded content ───────────────────────────────────────

class TestEmbeddedImageFooters:
    """Test bubbles with timestamps in footers below embedded images."""

    def test_footer_below_image_is_merged(self):
        """
        Simulates a message with embedded image:
        - Green bubble body (y=10, h=60)
        - Image zone (y=70, h=100, non-uniform colors)
        - Green footer with timestamp (y=170, h=28)

        Should merge footer into bubble, resulting in single bubble with h=188.
        """
        w, h = 500, 300
        arr = np.ones((h, w, 3), dtype=np.uint8)
        # Beige background
        arr[:, :] = [243, 238, 231]

        # Green bubble body (y=10-70, x=300-480)
        GREEN = [217, 253, 211]
        arr[10:70, 300:480] = GREEN

        # Image zone (y=70-170) with varied colors (not green/white)
        # Simulate random image colors
        np.random.seed(42)
        arr[70:170, 300:480] = np.random.randint(100, 200, (100, 180, 3), dtype=np.uint8)

        # Green footer (y=170-198, x=300-480, h=28)
        arr[170:198, 300:480] = GREEN

        img = Image.fromarray(arr, mode="RGB")
        bubbles = detect_bubbles(img, footer_px=70)

        # Should have 1 bubble (footer merged with body)
        assert len(bubbles) == 1, f"Expected 1 bubble, got {len(bubbles)}"
        bubble = bubbles[0]
        assert bubble["type"] == "me"
        assert bubble["x"] == 300
        assert bubble["y"] == 10
        # Height should include body + image + footer = 188
        assert bubble["h"] >= 160, f"Expected h >= 160 (to include footer), got {bubble['h']}"

    def test_white_footer_below_image_is_merged(self):
        """Similar to above but with white bubble (received message)."""
        w, h = 500, 300
        arr = np.ones((h, w, 3), dtype=np.uint8)
        arr[:, :] = [243, 238, 231]  # beige background

        # White bubble body (y=10-70, x=20-200)
        WHITE = [255, 255, 255]
        arr[10:70, 20:200] = WHITE

        # Image zone (y=70-170) with random colors
        np.random.seed(42)
        arr[70:170, 20:200] = np.random.randint(100, 200, (100, 180, 3), dtype=np.uint8)

        # White footer (y=170-198, x=20-200, h=28)
        arr[170:198, 20:200] = WHITE

        img = Image.fromarray(arr, mode="RGB")
        bubbles = detect_bubbles(img, footer_px=70)

        # Should have 1 bubble (footer merged with body)
        assert len(bubbles) == 1, f"Expected 1 bubble, got {len(bubbles)}"
        bubble = bubbles[0]
        assert bubble["type"] == "other"
        assert bubble["x"] == 20
        assert bubble["y"] == 10
        assert bubble["h"] >= 160, f"Expected h >= 160, got {bubble['h']}"

    def test_two_bubbles_separate_images(self):
        """Two bubbles with separate images should NOT be merged."""
        w, h = 500, 400
        arr = np.ones((h, w, 3), dtype=np.uint8)
        arr[:, :] = [243, 238, 231]

        GREEN = [217, 253, 211]
        WHITE = [255, 255, 255]

        # Green bubble 1 with footer (y=10-70, then image 70-170, then footer 170-198)
        arr[10:70, 300:480] = GREEN
        np.random.seed(42)
        arr[70:170, 300:480] = np.random.randint(100, 200, (100, 180, 3), dtype=np.uint8)
        arr[170:198, 300:480] = GREEN

        # White bubble 2 separate (y=220-280, then image 280-360, then footer 360-388)
        arr[220:280, 20:200] = WHITE
        np.random.seed(43)
        arr[280:360, 20:200] = np.random.randint(100, 200, (80, 180, 3), dtype=np.uint8)
        arr[360:388, 20:200] = WHITE

        img = Image.fromarray(arr, mode="RGB")
        bubbles = detect_bubbles(img, footer_px=70)

        # Should have 2 bubbles (no merge across types)
        assert len(bubbles) == 2, f"Expected 2 bubbles, got {len(bubbles)}"
        assert bubbles[0]["type"] == "me"     # sorted by y, green comes first (y=10)
        assert bubbles[1]["type"] == "other"  # white comes second (y=220)
