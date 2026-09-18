"""
Tests de wavi.vision_grounding.

Cubre funciones puras (clustering por y-overlap, split de campos de una fila
de sidebar) que no requieren OmniParser ni sus pesos — importar el módulo no
dispara ninguna dependencia pesada (torch/easyocr/ultralytics se importan de
forma lazy dentro de las funciones que sí los necesitan). Para el pipeline
completo sobre el corpus real, ver tests/test_corpus_grounding.py (gateado
por WAVI_CORPUS=1).
"""
from wavi.vision_grounding import _cluster_by_y_overlap, _split_contact_fields, _split_row_fields


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
