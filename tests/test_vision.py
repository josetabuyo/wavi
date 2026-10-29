"""
Tests del pipeline de visión wavi.

Cubre funciones puras que no requieren browser ni imágenes reales.
Correr:
    cd /Users/josetabuyo/Development/wavi
    source .venv/bin/activate
    pytest tests/ -v
"""
import numpy as np
import pytest
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

    # Real OCR lines from captures where a clock time inside a text made the
    # bubble an "audio" (DataLake / Minis App Acces, 2026-10-28).
    def test_time_inside_sentence_is_text(self):
        blocks = _blocks("los intentos de AMBA eran pruebas mías",
                         "hoy miro que termine antes de las 12:40", "8:48 a. m. M")
        assert classify_msg_type(" ".join(b["text"] for b in blocks), blocks) == "text"

    def test_table_row_with_seconds_is_text(self):
        blocks = _blocks("2370506", "33763", "2026-10-26 22:49:00", "ZPruebabfbhdh")
        assert classify_msg_type(" ".join(b["text"] for b in blocks), blocks) == "text"

    def test_schedule_list_is_text(self):
        t = "quedan: 10:00 y 11:00 lun a vie (SAP) y 12:00 todos los dias"
        assert classify_msg_type(t, _blocks(t)) == "text"

    def test_audio_duration_with_waveform_and_time_on_one_line(self):
        t = "•||||| 4:40 4:35 p. m."
        assert classify_msg_type(t, _blocks(t)) == "audio"

    def test_audio_duration_with_cyrillic_ocr_timestamp(self):
        t = "0:26 1:54 р. m."  # OCR reads "p" as Cyrillic "р"
        assert classify_msg_type(t, _blocks(t)) == "audio"

    def test_group_audio_sender_name_on_its_own_line(self):
        blocks = _blocks("Lucas Avaca", "0:32", "9:54 a. m.")
        assert classify_msg_type("Lucas Avaca 0:32 9:54 a. m.", blocks) == "audio"

    # Fabian2025 (Minis App Acces, 2026-10-28): what was still "audio" in 0.11.5.
    def test_table_row_lines_are_text(self):
        blocks = _blocks("2370507", "33763", "2026-10-26 22:51:00", "ZPruebabfbhdh")
        assert classify_msg_type(" ".join(b["text"] for b in blocks), blocks) == "text"

    def test_photo_of_text_with_a_lone_time_line_is_not_audio(self):
        blocks = _blocks("Fabian Miranda", "Wia", "ООБРОИЬЯРОВАЛЬ", "KOOANA",
                         "NONT4 CMRQn0N", "SOUANHPANeVO", "12:49", "р.", "m.")
        assert classify_msg_type(" ".join(b["text"] for b in blocks), blocks) != "audio"

    def test_code_screenshot_with_waveform_looking_line_is_not_audio(self):
        blocks = _blocks("Alejandro Acosta", "PuOlc 10", "13.",
                         "Kaleseryneales gulles nawtes eslemks el",
                         "reiio (rMiiharles rportes)", "10:25 p. m.")
        assert classify_msg_type(" ".join(b["text"] for b in blocks), blocks) != "audio"

    def test_own_audio_waveform_without_bars(self):
        blocks = _blocks("n00000000000000000", "4:42 p. m. M")
        assert classify_msg_type("n00000000000000000 4:42 p. m. M", blocks) == "audio"

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
        assert result == "6:13 p. m."

    def test_cyrillic_ocr_artifact_separate_block(self):
        """Timestamp cirílico en bloque separado del duration."""
        blocks = [{"text": "0:19"}, {"text": "6:13 р."}]
        result = _extract_timestamp(blocks)
        assert result == "6:13 p. m."

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
        retorna '1:30 p. m.' (best-effort). Caso raro en práctica ya que duration y timestamp
        están separados espacialmente en WA y suelen quedar en bloques distintos.
        """
        blocks = [{"text": "1:30 р."}]
        # Comportamiento documentado: ambiguo, acepta '1:30 p. m.' como resultado
        result = _extract_timestamp(blocks)
        assert result == "1:30 p. m."

    def test_cyrillic_pm_keeps_afternoon_when_parsed(self):
        """'2:42 р. m.' es 14:42, no 02:42 — el marcador p.m. cirílico debe sobrevivir
        hasta _parse_time_str (bug real 2026-09-24: 17 audios de la tarde archivados
        como madrugada en un export)."""
        from wavi.vision import _parse_time_str
        blocks = [{"text": "1:33 2:42 р. m. M/"}]
        assert _parse_time_str(_extract_timestamp(blocks)) == "14:42"

    def test_cyrillic_am_artifact(self):
        """'а.' (а cirílica) es OCR de 'a.' → mañana."""
        from wavi.vision import _parse_time_str
        blocks = [{"text": "9:08 а. m."}]
        assert _parse_time_str(_extract_timestamp(blocks)) == "09:08"


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


class TestDateOrder:
    """Numeric dates are day-first in Spanish WA, month-first in US English."""

    @pytest.fixture(autouse=True)
    def _restore_order(self):
        from wavi import vision
        saved = vision._DAY_FIRST
        yield
        vision.set_date_order(saved)

    def test_unambiguous_sample_wins_over_language(self):
        from wavi.vision import infer_day_first
        assert infer_day_first("en", ["[9:00 AM, 25/10/2026] Ana: "]) is True
        assert infer_day_first("es", ["[9:00 a. m., 10/25/2026] Ana: "]) is False

    def test_language_decides_ambiguous(self):
        from wavi.vision import infer_day_first
        assert infer_day_first("es", ["[7:15 p. m., 8/10/2026] Jozbuyo: "]) is True
        assert infer_day_first("en", ["[7:15 PM, 8/10/2026] Jozbuyo: "]) is False
        assert infer_day_first("en-GB", []) is True
        assert infer_day_first(None, []) is True

    def test_pill_follows_explicit_and_global_order(self):
        from datetime import date

        from wavi.vision import _date_from_pill_text, set_date_order
        today = date(2026, 10, 8)
        assert _date_from_pill_text("5/10/2026", today) == date(2026, 10, 5)
        assert _date_from_pill_text("5/10/2026", today, day_first=False) == date(2026, 5, 10)
        set_date_order(False)
        assert _date_from_pill_text("5/10/2026", today) == date(2026, 5, 10)

    def test_pre_plain_and_viewer_header_follow_global_order(self):
        from datetime import date, datetime

        from wavi.media import parse_viewer_when
        from wavi.session import _parse_pre_plain
        from wavi.vision import set_date_order
        set_date_order(False)
        assert _parse_pre_plain("[4:38 PM, 8/10/2026] Ann: ") == datetime(2026, 8, 10, 16, 38)
        assert parse_viewer_when("5/10/2026 at 3:51 PM", date(2026, 10, 8)) == datetime(2026, 5, 10, 15, 51)


@pytest.mark.asyncio
async def test_detect_date_order_uses_wa_lang_not_navigator():
    from unittest.mock import AsyncMock, MagicMock

    from wavi import vision
    from wavi.session import WASession
    saved = vision._DAY_FIRST
    try:
        s = WASession.__new__(WASession)
        s._page = MagicMock()
        s._page.evaluate = AsyncMock(return_value={"lang": "en", "dates": ["[7:15 PM, 8/10/2026] X: "]})
        assert await s.detect_date_order() is False
        assert vision._DAY_FIRST is False
        s._page.evaluate = AsyncMock(side_effect=RuntimeError("page gone"))
        assert await s.detect_date_order() is None
    finally:
        vision.set_date_order(saved)


class TestMessageBubbleVision:
    """Visual invariants wavi edit/reply rely on to pick a message without
    the DOM: the quote's coloured left bar, coloured sender names, the
    context-menu entry found by OCR."""

    OWN_BG = (217, 253, 211)       # WA's own-bubble green
    QUOTE_BG = (209, 244, 204)
    BAR = (27, 135, 85)            # measured live 2026-10-12

    def _bubble(self, quote=True):
        from PIL import ImageDraw
        img = Image.new("RGB", (420, 100), self.OWN_BG)
        d = ImageDraw.Draw(img)
        if quote:
            d.rectangle((10, 6, 400, 50), fill=self.QUOTE_BG)
            d.rectangle((10, 6, 13, 50), fill=self.BAR)          # 4 px bar
        d.rectangle((20, 70, 160, 80), fill=(17, 27, 33))         # dark "text"
        return img

    def test_quote_band_found_from_the_bar(self):
        from wavi.vision import find_quote_band
        y0, y1 = find_quote_band(self._bubble())
        assert abs(y0 - 6) <= 1 and abs(y1 - 51) <= 1

    def test_no_quote_no_band(self):
        from wavi.vision import find_quote_band
        assert find_quote_band(self._bubble(quote=False)) is None

    def test_coloured_block_is_not_a_bar(self):
        from PIL import ImageDraw

        from wavi.vision import find_quote_band
        img = Image.new("RGB", (300, 120), self.OWN_BG)
        ImageDraw.Draw(img).rectangle((10, 10, 200, 100), fill=(200, 60, 40))   # a photo
        assert find_quote_band(img) is None

    def test_coloured_name_vs_black_text(self):
        from PIL import ImageDraw

        from wavi.vision import _is_colored_text
        img = Image.new("RGB", (200, 60), (255, 255, 255))
        d = ImageDraw.Draw(img)
        d.rectangle((5, 5, 100, 15), fill=(83, 189, 235))        # light-blue name
        d.rectangle((5, 30, 100, 40), fill=(17, 27, 33))         # message text
        assert _is_colored_text(img, (0, 0, 110, 20))
        assert not _is_colored_text(img, (0, 25, 110, 45))

    def test_strip_meta(self):
        from wavi.vision import _strip_meta
        assert _strip_meta("segunda respuesta ok, editada Editado 7:18 p. m. //") == \
            "segunda respuesta ok, editada"
        assert _strip_meta("Hola Wavi! 5:20 p. m. /") == "Hola Wavi!"
        assert _strip_meta("a las 5:30 nos vemos") == "a las 5:30 nos vemos"

    def test_find_menu_item_by_ocr(self, tmp_path, monkeypatch):
        import wavi.vision as vision
        shot = tmp_path / "menu.png"
        Image.new("RGB", (1280, 1920)).save(shot)
        monkeypatch.setattr(vision, "_run_ocr", lambda p: [
            {"text": "Copiar", "x": 0.85, "y": 0.80, "w": 0.05, "h": 0.01},
            {"text": "Responder ", "x": 0.85, "y": 0.78, "w": 0.06, "h": 0.01},
        ])
        x, y = vision.find_menu_item(shot, ("Responder", "Reply"))
        assert (x, y) == (int(0.88 * 1280), int(0.785 * 1920))
        assert vision.find_menu_item(shot, ("Editar", "Edit")) is None

    def test_menu_label_tolerates_the_entry_icon(self):
        """WA draws an icon per entry; OCR reads "@ Editar", "4 Fijar"
        (DataLake 2026-10-20). Chat text like "ok editar" is not an entry."""
        from wavi.vision import _is_menu_label
        want = {"editar", "edit"}
        assert _is_menu_label("@ Editar", want)
        assert _is_menu_label("Editar", want)
        assert _is_menu_label("* Responder", {"responder"})
        assert not _is_menu_label("ok editar", want)
        assert not _is_menu_label("@ Editar mensaje", want)

    def test_read_message_bubbles_splits_quote_and_inherits_sender(self, tmp_path, monkeypatch):
        from PIL import ImageDraw

        import wavi.vision as vision
        shot = tmp_path / "chat.png"
        full = Image.new("RGB", (1280, 1920), (239, 234, 226))
        d = ImageDraw.Draw(full)
        ox, oy = vision.SIDEBAR_PX, vision.HEADER_PX
        # other's bubble with a blue name label, then an unlabeled one (same run)
        d.rectangle((ox + 20, oy + 100, ox + 320, oy + 160), fill=(255, 255, 255))
        d.rectangle((ox + 30, oy + 105, ox + 150, oy + 115), fill=(83, 189, 235))
        d.rectangle((ox + 20, oy + 170, ox + 320, oy + 200), fill=(255, 255, 255))
        # own reply quoting it
        d.rectangle((ox + 300, oy + 300, ox + 680, oy + 400), fill=self.OWN_BG)
        d.rectangle((ox + 310, oy + 306, ox + 670, oy + 350), fill=self.QUOTE_BG)
        d.rectangle((ox + 310, oy + 306, ox + 313, oy + 350), fill=self.BAR)
        full.save(shot)

        def blk(text, x, y, w, h, bw, bh):
            return {"text": text, "x": x / bw, "y": y / bh, "w": w / bw, "h": h / bh}
        bubbles = [
            vision.Bubble(id=3, screen_id=3, sender="other", msg_type="text", timestamp="2026-10-09T13:31",
                          text="", bbox={"x": 20, "y": 100, "w": 300, "h": 60},
                          raw_blocks=[blk("Matías Cagnina", 10, 5, 120, 10, 300, 60),
                                      blk("recibido!!! 1:31 p. m.", 10, 30, 200, 15, 300, 60)]),
            vision.Bubble(id=2, screen_id=2, sender="other", msg_type="text", timestamp="2026-10-09T13:32",
                          text="", bbox={"x": 20, "y": 170, "w": 300, "h": 30},
                          raw_blocks=[blk("gracias Jose 1:32 p. m.", 10, 8, 200, 15, 300, 30)]),
            vision.Bubble(id=1, screen_id=1, sender="me", msg_type="text", timestamp="2026-10-09T13:40",
                          text="", bbox={"x": 300, "y": 300, "w": 380, "h": 100},
                          raw_blocks=[blk("Matías Cagnina", 20, 10, 120, 10, 380, 100),
                                      blk("recibido!!!", 20, 30, 100, 12, 380, 100),
                                      blk("de nada 1:40 p. m. //", 20, 70, 150, 15, 380, 100)]),
        ]
        monkeypatch.setattr(vision, "analyze", lambda *a, **k: bubbles)
        rows = vision.read_message_bubbles(shot, tmp_path)
        assert [r["key"] for r in rows] == ["v3", "v2", "v1"]           # oldest first
        assert rows[0]["sender"] == "Matías Cagnina" and rows[0]["text"] == "recibido!!!"
        assert rows[1]["sender"] == "Matías Cagnina" and rows[1]["text"] == "gracias Jose"
        assert rows[2]["own"] and rows[2]["sender"] == "Tú"
        assert rows[2]["text"] == "de nada" and rows[2]["quoted"] == "recibido!!!"
        # click point lands on the body, in page coordinates
        assert ox + 300 < rows[2]["click_x"] < ox + 680 and oy + 370 < rows[2]["click_y"] < oy + 390


def test_ocr_helper_is_found():
    """The swift OCR helper must resolve both in a checkout and in the wheel
    (pyproject force-include → wavi/_ocr/)."""
    import tomllib
    from pathlib import Path

    from wavi.vision import SWIFT_OCR
    assert SWIFT_OCR.exists()
    cfg = tomllib.loads((Path(__file__).parent.parent / "pyproject.toml").read_text())
    inc = cfg["tool"]["hatch"]["build"]["targets"]["wheel"]["force-include"]
    assert inc["swift/ocr_vision.swift"] == "wavi/_ocr/ocr_vision.swift"


class TestSplitStacked:
    """Same-sender bubbles ~2px apart came out as one (DataLake 2026-10-20)."""

    @staticmethod
    def _mask(*spans, h=200, w=100):
        import numpy as np
        m = np.zeros((h, w), dtype=np.uint8)
        for y0, y1 in spans:
            m[y0:y1, 5:95] = 1
        return m

    def test_short_gap_splits(self):
        from wavi.element_detector import _split_stacked
        b = {"x": 0, "y": 10, "w": 100, "h": 82, "type": "me"}
        pieces = _split_stacked(b, self._mask((10, 50), (52, 92)))
        assert [(p["y"], p["h"]) for p in pieces] == [(10, 40), (52, 40)]

    def test_long_gap_and_short_pieces_stay_whole(self):
        from wavi.element_detector import _split_stacked
        photo = {"x": 0, "y": 10, "w": 100, "h": 100, "type": "me"}
        assert _split_stacked(photo, self._mask((10, 40), (80, 110))) == [photo]
        thin = {"x": 0, "y": 10, "w": 100, "h": 42, "type": "me"}
        assert _split_stacked(thin, self._mask((10, 30), (32, 52))) == [thin]


# ── date_for_y ────────────────────────────────────────────────────────────────

class TestDateForY:
    PILLS = [(400, "2026-10-27"), (1130, "2026-10-28")]

    def test_bubble_below_a_pill_takes_its_date(self):
        from wavi.vision import date_for_y
        assert date_for_y(self.PILLS, 1200) == "2026-10-28"
        assert date_for_y(self.PILLS, 800) == "2026-10-27"

    def test_bubble_above_the_topmost_pill_gets_no_date(self):
        """Yesterday's 19:48 sat above a "Hoy" pill and was dated today."""
        from wavi.vision import date_for_y
        assert date_for_y([(1130, "2026-10-28")], 932) is None

    def test_no_pills_no_date(self):
        from wavi.vision import date_for_y
        assert date_for_y([], 500) is None
