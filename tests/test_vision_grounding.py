"""
Tests de wavi.vision_grounding.

Cubre funciones puras (clustering por y-overlap, split de campos de una fila
de sidebar) que no requieren OmniParser ni sus pesos — importar el módulo no
dispara ninguna dependencia pesada (torch/easyocr/ultralytics se importan de
forma lazy dentro de las funciones que sí los necesitan). Para el pipeline
completo sobre el corpus real, ver tests/test_corpus_grounding.py (gateado
por WAVI_CORPUS=1).
"""
import re

from PIL import Image

from wavi import vision_grounding as vg
from wavi.vision_grounding import (
    WHATSAPP_WEB,
    ChatAppProfile,
    _cluster_by_y_overlap,
    _detect_row_direction,
    _split_contact_fields,
    _split_row_fields,
    locate_new_chat_button,
)


def _el(content, x0, y0, x1, y1):
    return {"content": content, "bbox": [x0, y0, x1, y1]}


# ── _cluster_by_y_overlap ───────────────────────────────────────────────────

class TestClusterByYOverlap:
    def test_single_line_stays_together(self):
        elements = [_el("Hola", 0, 10, 40, 30), _el("Mundo", 45, 10, 90, 30)]
        lines = _cluster_by_y_overlap(elements)
        assert len(lines) == 1
        assert len(lines[0]) == 2

    def test_two_vertically_separate_lines(self):
        elements = [_el("Arriba", 0, 10, 40, 30), _el("Abajo", 0, 60, 40, 80)]
        lines = _cluster_by_y_overlap(elements)
        assert len(lines) == 2

    def test_empty_input(self):
        assert _cluster_by_y_overlap([]) == []


# ── _split_row_fields ───────────────────────────────────────────────────────

class TestSplitRowFields:
    def test_name_and_timestamp_on_top_line_message_below(self):
        elements = [
            _el("Ana", 0, 10, 40, 30),
            _el("10:17 a. m.", 200, 10, 280, 30),
            _el("Nos vemos mañana", 0, 50, 150, 70),
        ]
        name, last_message, timestamp = _split_row_fields(elements)
        assert name == "Ana"
        assert timestamp == "10:17 a. m."
        assert last_message == "Nos vemos mañana"

    def test_no_timestamp_on_top_line(self):
        elements = [
            _el("Grupo de trabajo", 0, 10, 100, 30),
            _el("Última actualización", 0, 50, 130, 70),
        ]
        name, last_message, timestamp = _split_row_fields(elements)
        assert name == "Grupo de trabajo"
        assert last_message == "Última actualización"
        assert timestamp == ""

    def test_single_line_row_has_no_preview(self):
        elements = [_el("Solo nombre", 0, 10, 100, 30)]
        name, last_message, timestamp = _split_row_fields(elements)
        assert name == "Solo nombre"
        assert last_message == ""
        assert timestamp == ""

    def test_empty_row(self):
        assert _split_row_fields([]) == ("", "", "")

    def test_wrapped_preview_across_two_lines_both_join_last_message(self):
        elements = [
            _el("Ana", 0, 10, 40, 30),
            _el("9:00 a. m.", 200, 10, 280, 30),
            _el("primera línea", 0, 50, 100, 70),
            _el("segunda línea", 0, 90, 100, 110),
        ]
        name, last_message, timestamp = _split_row_fields(elements)
        assert name == "Ana"
        assert timestamp == "9:00 a. m."
        assert last_message == "primera línea segunda línea"

    def test_rightmost_timestamp_match_wins(self):
        # Pathological case: two elements on the top line both match the
        # timestamp regex. Layout guarantees the real timestamp is
        # right-aligned, so the rightmost match should be picked.
        elements = [
            _el("1:23 a. m.", 0, 10, 60, 30),
            _el("10:17 a. m.", 200, 10, 280, 30),
        ]
        _name, _last_message, timestamp = _split_row_fields(elements)
        assert timestamp == "10:17 a. m."

    def test_period_separated_timestamp_with_meridiem(self):
        # Real WA Web/EasyOCR output (confirmed against a live session,
        # 2026-09-18): period separator, not colon.
        elements = [
            _el("Comunidad UTN GIAR", 151, 10, 293, 30),
            _el("11.27 a. m.", 491, 10, 551, 30),
        ]
        name, _last_message, timestamp = _split_row_fields(elements)
        assert name == "Comunidad UTN GIAR"
        assert timestamp == "11.27 a. m."

    def test_bare_time_with_dropped_meridiem(self):
        # Real WA Web/EasyOCR output: the am/pm suffix is sometimes dropped
        # by OCR at this confidence threshold, leaving a bare "H.MM".
        elements = [
            _el("Javier Lurgo", 150, 10, 250, 30),
            _el("11.02", 497, 10, 525, 30),
        ]
        name, _last_message, timestamp = _split_row_fields(elements)
        assert name == "Javier Lurgo"
        assert timestamp == "11.02"

    def test_positional_fallback_for_relative_day_label(self):
        # No regex can enumerate every locale's relative-day/weekday labels
        # ("Ayer", "Lunes", ...) — real WA Web output, right-aligned with a
        # large gap from the name, same as a real timestamp would be.
        elements = [
            _el("BJJ Guerreros", 149, 1081, 255, 1102),
            _el("Ayer", 527, 1087, 555, 1101),
        ]
        name, _last_message, timestamp = _split_row_fields(elements)
        assert name == "BJJ Guerreros"
        assert timestamp == "Ayer"

    def test_positional_fallback_does_not_split_a_wrapped_multiword_name(self):
        # Negative case: two words of the same name/title, small gap
        # (real intra-phrase gaps observed: ~4-10px) — must NOT be treated
        # as name + timestamp just because there's no timestamp OCR'd at all.
        elements = [
            _el("María", 0, 10, 40, 30),
            _el("García", 45, 10, 90, 30),
        ]
        name, _last_message, timestamp = _split_row_fields(elements)
        assert name == "María García"
        assert timestamp == ""


# ── ChatAppProfile parametrization ──────────────────────────────────────────
# Proves `profile` actually drives behavior (not just a decorative parameter)
# — groundwork for adding a second chat app later without rewriting detection
# logic, per docs/plan-mejoras.md Fase 5. WHATSAPP_WEB is still the only real
# profile; these tests use a synthetic one purely to exercise the plumbing.

class TestChatAppProfile:
    def test_split_row_fields_defaults_to_whatsapp_web(self):
        elements = [
            _el("Ana", 0, 10, 40, 30),
            _el("10:17 a. m.", 200, 10, 280, 30),
        ]
        assert _split_row_fields(elements) == _split_row_fields(elements, WHATSAPP_WEB)

    def test_custom_profile_timestamp_regex_and_gap_override_defaults(self):
        custom = ChatAppProfile(
            name="synthetic",
            sidebar_px=WHATSAPP_WEB.sidebar_px,
            footer_band_frac=WHATSAPP_WEB.footer_band_frac,
            compose_placeholder_re=WHATSAPP_WEB.compose_placeholder_re,
            row_gap_px=WHATSAPP_WEB.row_gap_px,
            timestamp_re=re.compile(r"^TS-\d+$"),
            timestamp_gap_px=200,  # deliberately large: positional fallback must NOT fire
            direction_icon_band_px=WHATSAPP_WEB.direction_icon_band_px,
            header_band_px=WHATSAPP_WEB.header_band_px,
            accent_min_green_delta=WHATSAPP_WEB.accent_min_green_delta,
        )
        # Small gap (10px), well under either profile's threshold — only a
        # matching regex can identify "TS-42" as a timestamp here, never the
        # positional fallback. Isolates the regex's effect specifically.
        elements = [
            _el("Ana", 0, 10, 40, 30),
            _el("TS-42", 50, 10, 90, 30),
        ]

        # Default profile's clock regex doesn't match "TS-42", and the gap
        # (10px) is far under its positional threshold (60px) — stays in name.
        name, _last_message, timestamp = _split_row_fields(elements)
        assert timestamp == ""
        assert name == "Ana TS-42"

        # Custom profile's regex matches "TS-42" directly.
        name, _last_message, timestamp = _split_row_fields(elements, custom)
        assert timestamp == "TS-42"
        assert name == "Ana"


# ── _split_contact_fields ────────────────────────────────────────────────────

class TestSplitContactFields:
    def test_name_and_subtitle(self):
        elements = [
            _el("Juan Pérez", 0, 10, 100, 30),
            _el("+54 9 11 1234-5678", 0, 50, 130, 70),
        ]
        name, subtitle = _split_contact_fields(elements)
        assert name == "Juan Pérez"
        assert subtitle == "+54 9 11 1234-5678"

    def test_name_split_across_words_joins_left_to_right(self):
        elements = [
            _el("María", 0, 10, 40, 30),
            _el("García", 45, 10, 90, 30),
            _el("Disponible", 0, 50, 80, 70),
        ]
        name, subtitle = _split_contact_fields(elements)
        assert name == "María García"
        assert subtitle == "Disponible"

    def test_single_line_row_has_no_subtitle(self):
        elements = [_el("Solo nombre", 0, 10, 100, 30)]
        name, subtitle = _split_contact_fields(elements)
        assert name == "Solo nombre"
        assert subtitle == ""

    def test_empty_row(self):
        assert _split_contact_fields([]) == ("", "")

    def test_no_timestamp_regex_applied_to_contact_rows(self):
        # A contact row's subtitle can itself look like a timestamp-shaped
        # string (e.g. "last seen 10:17 a. m.") — unlike sidebar rows,
        # nothing here should try to strip it out into a separate field.
        elements = [
            _el("Ana", 0, 10, 40, 30),
            _el("últ. vez hoy a las 10:17 a. m.", 0, 50, 160, 70),
        ]
        name, subtitle = _split_contact_fields(elements)
        assert name == "Ana"
        assert subtitle == "últ. vez hoy a las 10:17 a. m."


# ── _detect_row_direction ────────────────────────────────────────────────────
# Mocks _yolo_available/_load_yolo_model/predict_yolo — no weights or torch
# behavior actually exercised here, just the crop-region + presence logic.
# End-to-end validation against real icons belongs in test_corpus_grounding.py
# once a corpus case captures both directions (see docs/plan-mejoras.md §4.8).

class TestDetectRowDirection:
    def _image(self, w=300, h=100):
        return Image.new("RGB", (w, h))

    def test_no_preview_line_returns_none(self, monkeypatch):
        monkeypatch.setattr(vg, "_yolo_available", lambda: True)
        elements = [_el("Solo nombre", 0, 10, 100, 30)]
        assert _detect_row_direction(self._image(), elements) is None

    def test_empty_row_returns_none(self, monkeypatch):
        monkeypatch.setattr(vg, "_yolo_available", lambda: True)
        assert _detect_row_direction(self._image(), []) is None

    def test_weights_missing_returns_none(self, monkeypatch):
        monkeypatch.setattr(vg, "_yolo_available", lambda: False)
        elements = [
            _el("Ana", 0, 10, 40, 30),
            _el("Nos vemos mañana", 40, 50, 150, 70),
        ]
        assert _detect_row_direction(self._image(), elements) is None

    def test_no_room_left_of_preview_text_is_inbound(self, monkeypatch):
        # Preview text starts at x=0 — nowhere for WA to have drawn a tick
        # icon, so this short-circuits without even calling predict_yolo.
        monkeypatch.setattr(vg, "_yolo_available", lambda: True)
        elements = [
            _el("Ana", 0, 10, 40, 30),
            _el("Nos vemos mañana", 0, 50, 150, 70),
        ]
        assert _detect_row_direction(self._image(), elements) == "inbound"

    def test_icon_detected_left_of_preview_is_outbound(self, monkeypatch):
        monkeypatch.setattr(vg, "_yolo_available", lambda: True)
        monkeypatch.setattr(vg, "_load_yolo_model", lambda: object())
        monkeypatch.setattr(
            "wavi._vendor.omniparser_utils.predict_yolo",
            lambda **kwargs: ([[2, 2, 12, 12]], [0.91]),
        )
        elements = [
            _el("Ana", 0, 10, 40, 30),
            _el("Nos vemos mañana", 40, 50, 150, 70),
        ]
        assert _detect_row_direction(self._image(), elements) == "outbound"

    def test_no_icon_detected_left_of_preview_is_inbound(self, monkeypatch):
        monkeypatch.setattr(vg, "_yolo_available", lambda: True)
        monkeypatch.setattr(vg, "_load_yolo_model", lambda: object())
        monkeypatch.setattr(
            "wavi._vendor.omniparser_utils.predict_yolo",
            lambda **kwargs: ([], []),
        )
        elements = [
            _el("Ana", 0, 10, 40, 30),
            _el("Nos vemos mañana", 40, 50, 150, 70),
        ]
        assert _detect_row_direction(self._image(), elements) == "inbound"


# ── locate_new_chat_button ───────────────────────────────────────────────────
# Mocks _yolo_available/_load_yolo_model/predict_yolo (no weights/torch
# needed) but draws real pixels, so the green-fill color check runs for
# real. End-to-end validation against real screenshots (including the
# real button's calibrated RGB, and older corpus screenshots that predate
# this WA redesign and correctly have no green button at all) lives in
# test_corpus_grounding.py.

class TestLocateNewChatButton:
    def _screenshot_with_patch(self, tmp_path, box, color, size=(580, 60)):
        from PIL import ImageDraw

        img = Image.new("RGB", size, (255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.rectangle(box, fill=color)
        path = tmp_path / "screenshot.png"
        img.save(path)
        return path

    def test_weights_missing_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vg, "_yolo_available", lambda: False)
        path = self._screenshot_with_patch(tmp_path, (10, 10, 40, 40), (0, 180, 90))
        assert locate_new_chat_button(path) is None

    def test_no_boxes_detected_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vg, "_yolo_available", lambda: True)
        monkeypatch.setattr(vg, "_load_yolo_model", lambda: object())
        monkeypatch.setattr(
            "wavi._vendor.omniparser_utils.predict_yolo", lambda **kwargs: ([], [])
        )
        path = self._screenshot_with_patch(tmp_path, (10, 10, 40, 40), (0, 180, 90))
        assert locate_new_chat_button(path) is None

    def test_green_square_icon_is_detected(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vg, "_yolo_available", lambda: True)
        monkeypatch.setattr(vg, "_load_yolo_model", lambda: object())
        box = (500, 10, 540, 50)  # square-ish, matches the real button's aspect
        monkeypatch.setattr(
            "wavi._vendor.omniparser_utils.predict_yolo",
            lambda **kwargs: ([box], [0.9]),
        )
        path = self._screenshot_with_patch(tmp_path, box, (0, 180, 90))
        result = locate_new_chat_button(path)
        assert result == {"x": 500, "y": 10, "w": 40, "h": 40}

    def test_gray_icon_is_not_detected(self, tmp_path, monkeypatch):
        # Same shape as the real button, but monochrome — like the "..."
        # menu or the archive icon on older WA screenshots.
        monkeypatch.setattr(vg, "_yolo_available", lambda: True)
        monkeypatch.setattr(vg, "_load_yolo_model", lambda: object())
        box = (500, 10, 540, 50)
        monkeypatch.setattr(
            "wavi._vendor.omniparser_utils.predict_yolo",
            lambda **kwargs: ([box], [0.9]),
        )
        path = self._screenshot_with_patch(tmp_path, box, (210, 210, 210))
        assert locate_new_chat_button(path) is None

    def test_wide_green_bar_rejected_by_aspect_ratio(self, tmp_path, monkeypatch):
        # A green but non-square region (e.g. a wide banner) shouldn't be
        # mistaken for the round button.
        monkeypatch.setattr(vg, "_yolo_available", lambda: True)
        monkeypatch.setattr(vg, "_load_yolo_model", lambda: object())
        box = (100, 10, 400, 30)  # 300x20, aspect 15 — way outside 0.6-1.6
        monkeypatch.setattr(
            "wavi._vendor.omniparser_utils.predict_yolo",
            lambda **kwargs: ([box], [0.9]),
        )
        path = self._screenshot_with_patch(tmp_path, box, (0, 180, 90))
        assert locate_new_chat_button(path) is None

    def test_greenest_candidate_wins_among_several(self, tmp_path, monkeypatch):
        monkeypatch.setattr(vg, "_yolo_available", lambda: True)
        monkeypatch.setattr(vg, "_load_yolo_model", lambda: object())
        gray_box = (10, 10, 40, 40)
        pale_green_box = (200, 10, 230, 40)
        strong_green_box = (500, 10, 540, 50)
        monkeypatch.setattr(
            "wavi._vendor.omniparser_utils.predict_yolo",
            lambda **kwargs: ([gray_box, pale_green_box, strong_green_box], [0.9, 0.8, 0.85]),
        )

        from PIL import ImageDraw

        img = Image.new("RGB", (580, 60), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.rectangle(gray_box, fill=(210, 210, 210))
        draw.rectangle(pale_green_box, fill=(190, 220, 200))
        draw.rectangle(strong_green_box, fill=(0, 180, 90))
        path = tmp_path / "screenshot.png"
        img.save(path)

        result = locate_new_chat_button(path)
        assert result == {"x": 500, "y": 10, "w": 40, "h": 40}
