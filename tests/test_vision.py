"""
Tests del pipeline de visión wavi.

Cubre funciones puras que no requieren browser ni imágenes reales.
Correr:
    cd /Users/josetabuyo/Development/wavi
    source .venv/bin/activate
    pytest tests/ -v
"""
import numpy as np
from PIL import Image

from wavi.element_detector import detect_bubbles
from wavi.vision import (
    Bubble,
    _extract_reaction,
    _extract_timestamp,
    _find_reaction_badge,
    _is_noise,
    _is_waveform_garbage,
    _save_debug_image,
    classify_msg_type,
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

    def test_cyrillic_ocr_artifact_single_block(self):
        """'р.' es OCR de 'p.' — el tiempo que precede a 'р.' es el timestamp."""
        blocks = [{"text": "0:19 6:13 р. т. /"}]
        result = _extract_timestamp(blocks)
        assert result == "6:13"

    def test_cyrillic_ocr_artifact_separate_block(self):
        """Timestamp cirílico en bloque separado del duration."""
        blocks = [{"text": "0:19"}, {"text": "6:13 р."}]
        result = _extract_timestamp(blocks)
        assert result == "6:13"

    def test_cyrillic_does_not_match_zero_duration(self):
        """'0:19 р.' no matchea: el patrón requiere [1-9] como primer dígito."""
        blocks = [{"text": "0:19 р."}]
        assert _extract_timestamp(blocks) is None

    def test_cyrillic_does_not_match_plain_russian_text(self):
        """Texto ruso normal sin 'X:YY р.' no dispara el fallback."""
        blocks = [{"text": "Привет как дела"}]
        assert _extract_timestamp(blocks) is None

    def test_cyrillic_long_duration_ambiguous_edge_case(self):
        """
        Audio de 1:30 min cuyo bloque OCR funde duration+timestamp como '1:30 р.':
        retorna '1:30' (best-effort). Caso raro en práctica ya que duration y timestamp
        están separados espacialmente en WA y suelen quedar en bloques distintos.
        """
        blocks = [{"text": "1:30 р."}]
        # Comportamiento documentado: ambiguo, acepta '1:30' como resultado
        result = _extract_timestamp(blocks)
        assert result == "1:30"


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
        # Use realistic WA dimensions: me audio needs room for play btn (x+93), h=136
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

        # me audio: cross at x+93, y+h-37  (calibrated from DOM measurement 2026-05-30)
        assert is_red(result.getpixel((me_audio_bbox["x"] + 93, me_audio_bbox["y"] + me_audio_bbox["h"] - 37))), "me audio cross missing"
        # other file: cross at x+38, y+h-37
        assert is_red(result.getpixel((other_file_bbox["x"] + 38, other_file_bbox["y"] + other_file_bbox["h"] - 37))), "other file cross missing"
        # text: no red cross at the audio cross position
        assert not is_red(result.getpixel((text_bbox["x"] + 38, text_bbox["y"] + text_bbox["h"] // 2))), "text must not have cross"

    def test_cross_me_vs_other_x_offset(self, tmp_path):
        """
        'me' cross must be at x+93 (play btn position, calibrated from DOM 2026-05-30).
        'other' cross must be at x+38 (play btn near left edge, calibrated from DOM).
        Old uncalibrated values (x+188, x+78) were Δx=95 and Δx=40 off respectively.
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

        me_cy    = me_bbox["y"]    + me_bbox["h"]    - 37
        other_cy = other_bbox["y"] + other_bbox["h"] - 37

        # Calibrated positions (DOM measurement 2026-05-30)
        assert is_red(result.getpixel((me_bbox["x"] + 93, me_cy))),     "me cross at x+93 missing"
        assert is_red(result.getpixel((other_bbox["x"] + 38, other_cy))), "other cross at x+38 missing"
        # Old uncalibrated positions must NOT have cross
        assert not is_red(result.getpixel((me_bbox["x"] + 188, me_cy))),  "me cross must not be at old x+188"
        assert not is_red(result.getpixel((other_bbox["x"] + 78, other_cy))), "other cross must not be at old x+78"

    def test_cross_tall_bubble_bottom_anchored(self, tmp_path):
        """
        For tall bubbles (quoted reply on top + audio at bottom), the cross must land
        in the audio player row at the bottom — not at the vertical center of the whole bubble.
        h=136 is a standard audio-only bubble; h=261 simulates a quoted reply above it.
        Both must yield a cross 37px from the bottom edge (calibrated from DOM 2026-05-30).
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

        cx = 10 + 38  # "other" x offset (calibrated)

        # Both crosses must be 37px from their respective bottom edges
        assert is_red(result.getpixel((cx, short_bbox["y"] + short_bbox["h"] - 37))), "short bubble cross wrong"
        assert is_red(result.getpixel((cx, tall_bbox["y"]  + tall_bbox["h"]  - 37))), "tall bubble cross wrong"

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


# ── _extract_reaction ────────────────────────────────────────────────────────
# Real bug, 2026-08-26: a reaction badge sits on/near a bubble's edge and gets
# swept into the same OCR pass as the message/duration text next to it. This
# used to leave garbage like "1:01 1 reacción 9 1" as the message's own text
# and threw away the reaction info entirely. Now it's split out into its own
# field on Bubble instead of being lost or corrupting the message text.

class TestExtractReaction:
    def test_no_reaction_returns_text_unchanged(self):
        text, reaction = _extract_reaction("Hola cómo estás?")
        assert text == "Hola cómo estás?"
        assert reaction is None

    def test_extracts_reaction_with_count_from_audio_duration_text(self):
        """Real capture: an audio bubble's own OCR text ('1:01' duration +
        stray digits) had a reaction badge mixed into it."""
        text, reaction = _extract_reaction("1:01 1 reacción 9 1")
        assert reaction == "1 reacción"
        assert "reacción" not in text

    def test_extracts_plural_reacciones(self):
        text, reaction = _extract_reaction("hola 3 reacciones chau")
        assert reaction == "3 reacciones"
        assert text == "hola chau"

    def test_extracts_reaction_without_leading_count(self):
        text, reaction = _extract_reaction("reacción Rodolfo Prado")
        assert reaction == "reacción"
        assert text == "Rodolfo Prado"

    def test_collapses_extra_whitespace_after_removal(self):
        text, _ = _extract_reaction("excelente   1 reacción   gracias")
        assert text == "excelente gracias"

    def test_case_insensitive_and_accent_insensitive(self):
        _, reaction = _extract_reaction("1 REACCION")
        assert reaction is not None


# ── Bubble.as_dict — reaction field ──────────────────────────────────────────

class TestBubbleReactionField:
    def test_reaction_omitted_when_none(self):
        b = Bubble(id=1, sender="me", msg_type="text", timestamp=None, text="hola", bbox={})
        assert "reaction" not in b.as_dict()

    def test_reaction_included_when_present(self):
        b = Bubble(id=1, sender="me", msg_type="text", timestamp=None, text="hola", bbox={}, reaction="1 reacción")
        assert b.as_dict()["reaction"] == "1 reacción"

    def test_has_reaction_omitted_when_false(self):
        b = Bubble(id=1, sender="me", msg_type="text", timestamp=None, text="hola", bbox={})
        assert "has_reaction" not in b.as_dict()

    def test_has_reaction_and_image_included_when_present(self):
        b = Bubble(
            id=1, sender="me", msg_type="text", timestamp=None, text="hola", bbox={},
            has_reaction=True, reaction_image="shot_reaction_1.png",
        )
        d = b.as_dict()
        assert d["has_reaction"] is True
        assert d["reaction_image"] == "shot_reaction_1.png"


# ── _find_reaction_badge ──────────────────────────────────────────────────────
# Real bug, 2026-08-26: a small always-visible reaction emoji badge sits just
# outside a bubble's own edge (bottom-right for outgoing, bottom-left for
# incoming) and was never captured at all. Detected generically by color
# (small, highly-saturated blob against WA's low-saturation wallpaper/bubble
# fills) — we don't try to identify which emoji or how many reacted.

def _wallpaper_canvas(w: int = 300, h: int = 200) -> np.ndarray:
    """Low-saturation beige background, like WA's default wallpaper."""
    arr = np.full((h, w, 3), (230, 222, 208), dtype=np.uint8)
    return arr


class TestFindReactionBadge:
    def test_no_badge_on_plain_wallpaper(self):
        arr = _wallpaper_canvas()
        img = Image.fromarray(arr, mode="RGB")
        bubble = {"type": "me", "x": 50, "y": 50, "w": 150, "h": 40}
        assert _find_reaction_badge(img, bubble) is None

    def test_detects_saturated_blob_near_outgoing_bubble_corner(self):
        """Mirrors the real case: a red heart badge just below-right of an
        outgoing ('me') bubble's bottom edge."""
        arr = _wallpaper_canvas()
        bubble = {"type": "me", "x": 50, "y": 50, "w": 150, "h": 40}
        x1, y1 = bubble["x"] + bubble["w"], bubble["y"] + bubble["h"]
        # Small, highly-saturated red blob (a real emoji badge), positioned
        # just outside the bubble's bottom-right corner.
        arr[y1 + 2:y1 + 16, x1 - 20:x1 - 6] = (220, 20, 20)
        img = Image.fromarray(arr, mode="RGB")

        box = _find_reaction_badge(img, bubble)

        assert box is not None
        bx0, by0, bx1, by1 = box
        assert bx0 < x1 and bx1 > x1 - 25  # roughly where we placed the blob

    def test_detects_badge_near_incoming_bubble_left_edge(self):
        arr = _wallpaper_canvas()
        bubble = {"type": "other", "x": 100, "y": 50, "w": 150, "h": 40}
        x0, y1 = bubble["x"], bubble["y"] + bubble["h"]
        arr[y1 + 2:y1 + 16, x0 + 6:x0 + 20] = (30, 160, 60)
        img = Image.fromarray(arr, mode="RGB")

        assert _find_reaction_badge(img, bubble) is not None

    def test_ignores_large_saturated_area_as_false_positive(self):
        """A big colorful region (e.g. a media thumbnail poking into the
        search strip) must not be mistaken for a small reaction badge."""
        arr = _wallpaper_canvas()
        bubble = {"type": "me", "x": 50, "y": 50, "w": 150, "h": 40}
        x1, y1 = bubble["x"] + bubble["w"], bubble["y"] + bubble["h"]
        arr[y1:y1 + 40, x1 - 100:x1 + 10] = (200, 30, 30)  # spans the whole strip
        img = Image.fromarray(arr, mode="RGB")

        assert _find_reaction_badge(img, bubble) is None

    def test_ignores_wa_accent_blue_as_false_positive(self):
        """Real bug: WA's own UI chrome (blue double-check 'read' mark,
        audio playback-position dot) is saturated and sits right at a
        bubble's edge — it must not be mistaken for a reaction badge."""
        arr = _wallpaper_canvas()
        bubble = {"type": "me", "x": 50, "y": 50, "w": 150, "h": 40}
        x1, y1 = bubble["x"] + bubble["w"], bubble["y"] + bubble["h"]
        wa_blue_rgb = (80, 196, 247)  # sampled from the real playback dot
        arr[y1 + 2:y1 + 16, x1 - 20:x1 - 6] = wa_blue_rgb
        img = Image.fromarray(arr, mode="RGB")

        assert _find_reaction_badge(img, bubble) is None

    def test_ignores_badge_too_far_from_bubble_edge(self):
        arr = _wallpaper_canvas()
        bubble = {"type": "me", "x": 50, "y": 50, "w": 150, "h": 40}
        x1, y1 = bubble["x"] + bubble["w"], bubble["y"] + bubble["h"]
        arr[y1 + 60:y1 + 74, x1 - 20:x1 - 6] = (220, 20, 20)  # well outside search_h
        img = Image.fromarray(arr, mode="RGB")

        assert _find_reaction_badge(img, bubble) is None
