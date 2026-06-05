"""
Tests de WARunner — lógica de coordinadas y matching de botones de play.

No requiere browser real. Los métodos de session se mockean con AsyncMock.
"""
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from wavi.runner import WARunner
from wavi.vision import Bubble


def _runner() -> WARunner:
    return WARunner("data/sessions/default")


def _audio_bubble(crop_y: int, h: int = 136, sender: str = "other") -> Bubble:
    return Bubble(
        id=1, sender=sender, msg_type="audio",
        timestamp=None, text="",
        bbox={"x": 100, "y": crop_y, "w": 686, "h": h},
    )


# ── _match_bubble_to_button ────────────────────────────────────────────────────

class TestMatchBubbleToButton:
    """
    Verifica la conversión crop-physical → CSS-viewport con DPR variable.

    Fórmula: bvy_css = (crop_center_y + HEADER_PX) / dpr
    """

    def test_dpr1_direct_match(self):
        """DPR=1: sin escala. Bubble centro crop_y=362, HEADER=60 → bvy=422."""
        runner = _runner()
        bubble = _audio_bubble(crop_y=294)  # center = 294 + 68 = 362
        btn = {"vx": 670, "vy": 422}
        assert runner._match_bubble_to_button(bubble, [btn], dpr=1.0) == btn

    def test_dpr2_retina_match(self):
        """
        DPR=2 (Retina). Bubble crop_y=586, h=136 → center=654.
        bvy_css = (654 + 60) / 2 = 357.
        Botón real a vy=354 → distancia=3px < tolerancia 80px.
        """
        runner = _runner()
        bubble = _audio_bubble(crop_y=586)  # center = 586 + 68 = 654
        btn = {"vx": 670, "vy": 354}
        assert runner._match_bubble_to_button(bubble, [btn], tolerance_px=80, dpr=2.0) == btn

    def test_dpr1_would_fail_on_retina_data(self):
        """
        Si no se pasa DPR=2 para datos Retina, la misma burbuja NO matchea
        el botón correcto (demostrando por qué el fix importa).
        """
        runner = _runner()
        bubble = _audio_bubble(crop_y=586)  # bvy sin DPR = 654+60 = 714
        btn = {"vx": 670, "vy": 354}        # dist = |714-354| = 360 >> tolerancia
        assert runner._match_bubble_to_button(bubble, [btn], tolerance_px=80, dpr=1.0) is None

    def test_picks_nearest_of_multiple_buttons(self):
        runner = _runner()
        bubble = _audio_bubble(crop_y=586)  # bvy_css@DPR2 = 357
        buttons = [
            {"vx": 670, "vy": 200},   # dist=157
            {"vx": 670, "vy": 354},   # dist=3  ← ganador
            {"vx": 670, "vy": 500},   # dist=143
        ]
        result = runner._match_bubble_to_button(bubble, buttons, tolerance_px=80, dpr=2.0)
        assert result == buttons[1]

    def test_no_match_beyond_tolerance(self):
        runner = _runner()
        bubble = _audio_bubble(crop_y=586)  # bvy_css@DPR2 = 357
        btn = {"vx": 670, "vy": 100}        # dist=257
        assert runner._match_bubble_to_button(bubble, [btn], tolerance_px=80, dpr=2.0) is None

    def test_empty_buttons_returns_none(self):
        runner = _runner()
        bubble = _audio_bubble(crop_y=300)
        assert runner._match_bubble_to_button(bubble, [], dpr=1.0) is None

    def test_tall_bubble_center_used(self):
        """Burbuja alta (reply + audio, h=261): el centro se usa para el match."""
        runner = _runner()
        bubble = _audio_bubble(crop_y=874, h=261)  # center = 874 + 130 = 1004
        # bvy_css@DPR1 = (1004 + 60) / 1 = 1064
        btn = {"vx": 670, "vy": 1064}
        assert runner._match_bubble_to_button(bubble, [btn], tolerance_px=80, dpr=1.0) == btn


# ── WASession.install_blob_monitor / get_dpr ──────────────────────────────────

class TestInstallBlobMonitor:
    @pytest.mark.asyncio
    async def test_calls_evaluate_with_init_script(self):
        from wavi.session import WASession, _BLOB_INIT_SCRIPT
        s = WASession("data/sessions/default")
        s._page = MagicMock()
        s._page.evaluate = AsyncMock(return_value=None)

        await s.install_blob_monitor()

        s._page.evaluate.assert_called_once_with(_BLOB_INIT_SCRIPT)

    @pytest.mark.asyncio
    async def test_script_contains_guard(self):
        """El script tiene el guard __wavi_installed para no instalar dos veces."""
        from wavi.session import _BLOB_INIT_SCRIPT
        assert "__wavi_installed" in _BLOB_INIT_SCRIPT


class TestGetDpr:
    @pytest.mark.asyncio
    async def test_returns_page_device_pixel_ratio(self):
        from wavi.session import WASession
        s = WASession("data/sessions/default")
        s._page = MagicMock()
        s._page.evaluate = AsyncMock(return_value=2.0)

        result = await s.get_dpr()

        assert result == 2.0
        s._page.evaluate.assert_called_once()
        # Verifica que pregunta por devicePixelRatio
        call_arg = s._page.evaluate.call_args[0][0]
        assert "devicePixelRatio" in call_arg


# ── capture_full_history ───────────────────────────────────────────────────────

def _hist_bubble(screen_id: int, sender: str, text: str, y: int,
                 timestamp: str = "1:00 p.m.") -> Bubble:
    return Bubble(
        id=screen_id, screen_id=screen_id, sender=sender, msg_type="text",
        timestamp=timestamp, text=text,
        bbox={"x": 0, "y": y, "w": 200, "h": 50},
    )


def _mock_runner_for_history(iter0_bubbles, iter1_bubbles):
    """
    Return a WARunner with all async browser dependencies mocked.

    Simulates two captures:
      - iter_0: bottom of chat (newest messages)
      - iter_1: after one scroll-up (older content above iter_0's anchor)
    Scroll state: starts at scrollTop=500, drops to 0 after one scroll → loop ends.
    """
    runner = _runner()

    call_idx = 0

    async def fake_get_bubbles(*args, **kwargs):
        nonlocal call_idx
        result = iter0_bubbles if call_idx == 0 else iter1_bubbles
        call_idx += 1
        return result

    runner.get_bubbles = fake_get_bubbles
    runner.find_play_buttons = AsyncMock(return_value=[])

    page_mock = MagicMock()
    page_mock.wait_for_timeout = AsyncMock()
    runner.session._page = page_mock
    runner.session.install_blob_monitor = AsyncMock()
    runner.session.reset_blobs = AsyncMock()
    runner.session.drain_blobs = AsyncMock(return_value=[])
    runner.session.get_dpr = AsyncMock(return_value=1.0)
    runner.session.scroll_chat_up = AsyncMock()
    runner.session.scroll_chat_down = AsyncMock()
    runner.session.get_visible_message_ids = AsyncMock(return_value=[])
    runner.session.get_chat_scroll_state = AsyncMock(side_effect=[
        # 1. init_state (outside loop) → computes scroll_css_px
        {"scrollTop": 500, "scrollHeight": 1000, "clientHeight": 500},
        # 2. state before loop iter 0 → scrollTop>20, continue
        {"scrollTop": 500, "scrollHeight": 1000, "clientHeight": 500},
        # 3. new_state after scroll → moved to top (no stall)
        {"scrollTop": 0,   "scrollHeight": 1000, "clientHeight": 500},
        # 4. state at loop iter 1 → scrollTop<20, BREAK
        {"scrollTop": 0,   "scrollHeight": 1000, "clientHeight": 500},
    ])

    return runner


class TestCaptureFullHistory:
    """
    Garantiza el contrato de capture_full_history:
      - IDs globalmente únicos y secuenciales (1=más antiguo, N=más reciente)
      - Orden cronológico: mensajes de scroll-ups anteriores aparecen primero
      - screen_id preserva el ID local de la pantalla original
      - Burbujas en la zona de solapamiento se deduplan (una sola vez)
    """

    # Fixtures compartidas entre tests:
    # iter_0 = pantalla más nueva (fondo del chat), 3 mensajes A, B, C
    # iter_1 = pantalla anterior (scroll arriba), D y E son nuevos; A es el anchor/solapamiento
    _ITER0 = [
        _hist_bubble(screen_id=3, sender="me",    text="A", y=100, timestamp="1:02 p.m."),
        _hist_bubble(screen_id=2, sender="me",    text="B", y=200, timestamp="1:03 p.m."),
        _hist_bubble(screen_id=1, sender="me",    text="C", y=300, timestamp="1:04 p.m."),
    ]
    _ITER1 = [
        _hist_bubble(screen_id=3, sender="other", text="D", y=100, timestamp="1:00 p.m."),
        _hist_bubble(screen_id=2, sender="other", text="E", y=200, timestamp="1:01 p.m."),
        _hist_bubble(screen_id=1, sender="me",    text="A", y=300, timestamp="1:02 p.m."),  # solapamiento con iter0
    ]

    @pytest.mark.asyncio
    async def test_ids_sequential_and_unique(self):
        """El historial completo tiene IDs 1..N sin huecos ni duplicados (1=newest, N=oldest)."""
        runner = _mock_runner_for_history(self._ITER0, self._ITER1)
        result = await runner.capture_full_history(assets_dir=None)

        ids = [b.id for b in result]
        assert set(ids) == set(range(1, len(result) + 1)), \
            f"IDs deben formar el conjunto 1..{len(result)}, obtenidos: {ids}"
        # El mensaje más nuevo (C, último en lista) debe tener id=1
        assert result[-1].text == "C" and result[-1].id == 1
        # El mensaje más antiguo (D, primero en lista) debe tener id=N
        assert result[0].text == "D" and result[0].id == len(result)

    @pytest.mark.asyncio
    async def test_chronological_order(self):
        """Mensajes de scroll-ups más profundos (más antiguos) aparecen antes."""
        runner = _mock_runner_for_history(self._ITER0, self._ITER1)
        result = await runner.capture_full_history(assets_dir=None)

        texts = [b.text for b in result]
        # D y E son más antiguos que A (fueron hallados al scrollear arriba)
        assert texts.index("D") < texts.index("A"), "D (más antiguo) debe preceder a A"
        assert texts.index("E") < texts.index("A"), "E (más antiguo) debe preceder a A"
        # A, B, C deben mantener su orden relativo
        assert texts.index("A") < texts.index("B") < texts.index("C")

    @pytest.mark.asyncio
    async def test_screen_id_preserved(self):
        """screen_id mantiene el ID local de la pantalla, aunque id se reasigne globalmente."""
        runner = _mock_runner_for_history(self._ITER0, self._ITER1)
        result = await runner.capture_full_history(assets_dir=None)

        by_text = {b.text: b for b in result}
        # D tenía screen_id=3 en iter_1 (era el tope de esa pantalla)
        assert by_text["D"].screen_id == 3
        # C tenía screen_id=1 en iter_0 (el más nuevo, fondo de pantalla)
        assert by_text["C"].screen_id == 1
        # id global (5=oldest D en un historial de 5) ≠ screen_id local (3)
        assert by_text["D"].id == 5 and by_text["D"].screen_id == 3

    @pytest.mark.asyncio
    async def test_overlap_counted_once(self):
        """Burbuja en zona de solapamiento entre iteraciones se incluye una sola vez."""
        runner = _mock_runner_for_history(self._ITER0, self._ITER1)
        result = await runner.capture_full_history(assets_dir=None)

        texts = [b.text for b in result]
        assert texts.count("A") == 1, \
            f"'A' aparece en iter_0 e iter_1 pero debe contarse solo una vez, encontrado: {texts.count('A')}"
        # Total: D, E (nuevos de iter_1) + A, B, C (de iter_0) = 5
        assert len(result) == 5

    @pytest.mark.asyncio
    async def test_empty_iteration_is_noop(self):
        """
        Si el scroll produce una iteración donde todos los candidatos son overlap
        (no hay mensajes nuevos), el resultado no tiene duplicados ni cambia el orden.
        """
        # iter_1 devuelve solo el anchor (A) — sin contenido nuevo sobre él
        iter1_all_overlap = [
            _hist_bubble(screen_id=1, sender="me", text="A", y=100, timestamp="1:02 p.m."),
        ]
        runner = _mock_runner_for_history(self._ITER0, iter1_all_overlap)
        result = await runner.capture_full_history(assets_dir=None)

        texts = [b.text for b in result]
        assert texts.count("A") == 1
        # Solo los 3 mensajes de iter_0 (iter_1 no aportó nada nuevo)
        assert len(result) == 3
        ids = [b.id for b in result]
        assert set(ids) == {1, 2, 3}

    @pytest.mark.asyncio
    async def test_identical_text_different_timestamp_both_survive(self):
        """
        Dos mensajes con texto idéntico pero timestamp diferente deben contarse ambos.
        Cubre el riesgo de colisión en el content-key dedup.
        """
        # iter_0: dos "ok" en minutos distintos
        iter0 = [
            _hist_bubble(screen_id=2, sender="me", text="ok", y=100, timestamp="2:00 p.m."),
            _hist_bubble(screen_id=1, sender="me", text="ok", y=200, timestamp="3:00 p.m."),
        ]
        # iter_1: un "ok" más antiguo + el anchor (2:00 p.m.)
        iter1 = [
            _hist_bubble(screen_id=2, sender="me", text="ok", y=100, timestamp="1:00 p.m."),
            _hist_bubble(screen_id=1, sender="me", text="ok", y=200, timestamp="2:00 p.m."),  # anchor
        ]
        runner = _mock_runner_for_history(iter0, iter1)
        result = await runner.capture_full_history(assets_dir=None)

        timestamps = sorted(b.timestamp for b in result)
        # Los 3 "ok" de 1pm, 2pm y 3pm deben aparecer (no colapsados)
        assert timestamps == ["1:00 p.m.", "2:00 p.m.", "3:00 p.m."], \
            f"Timestamps encontrados: {timestamps}"
        assert len(result) == 3


# ── _assign_dom_ids ───────────────────────────────────────────────────────────

class TestAssignDomIds:
    """
    Verifica la asignación de dom_id por proximidad en y-viewport.
    """

    def test_assign_dom_ids_matches_by_y(self):
        """_assign_dom_ids asigna el dom_id al bubble más cercano en y."""
        b = Bubble(
            id=1, screen_id=1, sender="me", msg_type="text",
            timestamp=None, text="hola",
            bbox={"x": 0, "y": 100, "w": 200, "h": 40},
        )

        # bubble_vy = (100 + 20 + 60) / 1.0 = 180 CSS px
        dom_msgs = [
            {"id": "msg-correct", "vy": 182.0},   # closest
            {"id": "msg-far",     "vy": 300.0},
        ]

        runner = _runner()
        runner._assign_dom_ids([b], dom_msgs, dpr=1.0)
        assert b.dom_id == "msg-correct"

    def test_assign_dom_ids_no_match_beyond_tolerance(self):
        """No asigna dom_id si está fuera del rango de tolerancia."""
        b = Bubble(
            id=1, screen_id=1, sender="me", msg_type="text",
            timestamp=None, text="hola",
            bbox={"x": 0, "y": 100, "w": 200, "h": 40},
        )

        dom_msgs = [{"id": "msg-far", "vy": 400.0}]  # 400 vs 180 = 220px diff > 50

        runner = _runner()
        runner._assign_dom_ids([b], dom_msgs, dpr=1.0)
        assert b.dom_id is None

    def test_assign_dom_ids_empty_dom_msgs_noop(self):
        """Si dom_msgs está vacío, no asigna nada."""
        b = Bubble(
            id=1, screen_id=1, sender="me", msg_type="text",
            timestamp=None, text="hola",
            bbox={"x": 0, "y": 100, "w": 200, "h": 40},
        )

        runner = _runner()
        runner._assign_dom_ids([b], [], dpr=1.0)
        assert b.dom_id is None


# ── Anchor matching strategy ──────────────────────────────────────────────────

class TestAnchorMatchingStrategy:
    """Anchor matching prefers dom_id over OCR key."""

    def test_anchor_found_by_dom_id_even_if_ocr_differs(self):
        """When anchor has dom_id, finds it in new_bubbles by dom_id regardless of OCR."""
        from wavi.vision import Bubble

        def _make_bubble(bid, dom_id, text, y):
            b = Bubble(id=bid, screen_id=bid, sender="other", msg_type="text",
                       timestamp="1:00 p. m.", text=text,
                       bbox={"x": 0, "y": y, "w": 200, "h": 40})
            b.dom_id = dom_id
            return b

        # Anchor from previous iteration
        anchor_bubble = _make_bubble(5, "dom_ABC", "Hola", y=10)
        anchor_dom_id = anchor_bubble.dom_id

        # Same message appears in new screenshot with different OCR text
        ocr_variant = _make_bubble(3, "dom_ABC", "H0la", y=800)
        unrelated   = _make_bubble(2, "dom_XYZ", "Otra cosa", y=200)
        new_bubbles = [unrelated, ocr_variant]

        # DOM-based matching
        matches = [b for b in new_bubbles if b.dom_id == anchor_dom_id]
        assert len(matches) == 1
        assert matches[0].text == "H0la"  # found despite OCR difference

    def test_anchor_falls_back_to_ocr_when_no_dom_id(self):
        """When anchor has no dom_id, falls back to bubble_key OCR matching."""
        from wavi.vision import Bubble

        def bubble_key(b):
            return (b.sender, b.msg_type, b.text[:80].strip(), b.timestamp)

        def _make_bubble(bid, dom_id, text, ts, y):
            b = Bubble(id=bid, screen_id=bid, sender="other", msg_type="text",
                       timestamp=ts, text=text,
                       bbox={"x": 0, "y": y, "w": 200, "h": 40})
            b.dom_id = dom_id
            return b

        anchor_bubble = _make_bubble(5, None, "Hola mundo", "1:00 p. m.", y=10)
        anchor_ocr_key = bubble_key(anchor_bubble)

        # New screenshot: same message with same OCR text
        same_msg = _make_bubble(3, None, "Hola mundo", "1:00 p. m.", y=750)
        other = _make_bubble(2, None, "Otro mensaje", "2:00 p. m.", y=200)
        new_bubbles = [other, same_msg]

        # No dom_id → OCR fallback
        matches = [b for b in new_bubbles if b.dom_id == anchor_bubble.dom_id] if anchor_bubble.dom_id else []
        if not matches:
            matches = [b for b in new_bubbles if bubble_key(b) == anchor_ocr_key]
        assert len(matches) == 1
        assert matches[0].text == "Hola mundo"


class TestBubbleKeyWithDomId:
    """bubble_key uses dom_id as primary key when available (stable unique identity)."""

    def test_dom_id_takes_priority_over_ocr(self):
        """Same dom_id → same key, even if OCR text differs."""
        from wavi.vision import Bubble

        def bubble_key(b):
            if b.dom_id:
                return ("dom", b.dom_id)
            return (b.sender, b.msg_type, b.text[:80].strip(), b.timestamp)

        b1 = Bubble(id=1, screen_id=1, sender="me", msg_type="text",
                    timestamp="1:30 p. m.", text="jaja",
                    bbox={"x": 0, "y": 0, "w": 100, "h": 30})
        b1.dom_id = "true_+54@c.us_MSG001"

        b2 = Bubble(id=2, screen_id=2, sender="me", msg_type="text",
                    timestamp="1:30 p. m.", text="jaj a",  # OCR ruido
                    bbox={"x": 0, "y": 0, "w": 100, "h": 30})
        b2.dom_id = "true_+54@c.us_MSG001"  # mismo mensaje

        assert bubble_key(b1) == bubble_key(b2)

    def test_different_dom_ids_not_deduped(self):
        """Two identical texts with different dom_ids are distinct messages."""
        from wavi.vision import Bubble

        def bubble_key(b):
            if b.dom_id:
                return ("dom", b.dom_id)
            return (b.sender, b.msg_type, b.text[:80].strip(), b.timestamp)

        b1 = Bubble(id=1, screen_id=1, sender="me", msg_type="text",
                    timestamp="1:30 p. m.", text="jaja",
                    bbox={"x": 0, "y": 0, "w": 100, "h": 30})
        b1.dom_id = "true_+54@c.us_MSG001"

        b2 = Bubble(id=2, screen_id=2, sender="me", msg_type="text",
                    timestamp="1:30 p. m.", text="jaja",  # mismo texto
                    bbox={"x": 0, "y": 0, "w": 100, "h": 30})
        b2.dom_id = "true_+54@c.us_MSG002"  # mensaje DISTINTO

        assert bubble_key(b1) != bubble_key(b2)

    def test_fallback_to_ocr_when_no_dom_id(self):
        """Without dom_id, falls back to OCR-based key."""
        from wavi.vision import Bubble

        def bubble_key(b):
            if b.dom_id:
                return ("dom", b.dom_id)
            return (b.sender, b.msg_type, b.text[:80].strip(), b.timestamp)

        b = Bubble(id=1, screen_id=1, sender="me", msg_type="text",
                   timestamp="1:30 p. m.", text="hola",
                   bbox={"x": 0, "y": 0, "w": 100, "h": 30})
        # b.dom_id es None por default

        key = bubble_key(b)
        assert key == ("me", "text", "hola", "1:30 p. m.")
        assert key[0] != "dom"


# ── list_contacts ────────────────────────────────────────────────────────────

class TestListContacts:
    """Tests for list_contacts() orchestration method."""

    @pytest.mark.asyncio
    async def test_list_contacts_returns_contacts(self):
        """list_contacts() with no assets_dir returns contacts, screenshot=None."""
        runner = _runner()
        runner.session.connect = AsyncMock(return_value="restored")
        runner.session.navigate_to_new_chat = AsyncMock()
        runner.session.extract_contacts = AsyncMock(return_value=[
            {"name": "Alice", "subtitle": "Online"},
            {"name": "Bob", "subtitle": "Last seen 2 hours ago"},
        ])
        runner.session.close_new_chat = AsyncMock()
        runner.session.close = AsyncMock()

        result = await runner.list_contacts()

        assert result["screenshot"] is None
        assert result["assets_dir"] is None
        assert len(result["contacts"]) == 2
        assert result["contacts"][0]["name"] == "Alice"
        assert result["contacts"][1]["name"] == "Bob"
        runner.session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_contacts_with_assets_dir(self, tmp_path):
        """list_contacts() saves screenshot.png + contacts_list.json to assets_dir."""
        runner = _runner()
        runner.session.connect = AsyncMock(return_value="restored")
        runner.session.navigate_to_new_chat = AsyncMock()
        runner.session.extract_contacts = AsyncMock(return_value=[
            {"name": "Alice", "subtitle": ""},
        ])
        runner.session.screenshot_to_file = AsyncMock()
        runner.session.close_new_chat = AsyncMock()
        runner.session.close = AsyncMock()

        result = await runner.list_contacts(assets_dir=str(tmp_path))

        runner.session.screenshot_to_file.assert_called_once()
        assert result["screenshot"] is not None
        assert result["assets_dir"] is not None
        assert (tmp_path / "contacts_list.json").exists()
        assert len(result["contacts"]) == 1

    @pytest.mark.asyncio
    async def test_list_contacts_closes_on_error(self):
        """list_contacts() calls session.close() even if extract_contacts fails."""
        runner = _runner()
        runner.session.connect = AsyncMock(return_value="restored")
        runner.session.navigate_to_new_chat = AsyncMock()
        runner.session.extract_contacts = AsyncMock(side_effect=Exception("DOM changed"))
        runner.session.close_new_chat = AsyncMock()
        runner.session.close = AsyncMock()

        with pytest.raises(Exception, match="DOM changed"):
            await runner.list_contacts()

        runner.session.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_list_contacts_raises_if_not_authenticated(self):
        """list_contacts() raises RuntimeError when session is not authenticated."""
        for status in ("qr_needed", "timeout"):
            runner = _runner()
            runner.session.connect = AsyncMock(return_value=status)
            runner.session.close = AsyncMock()

            with pytest.raises(RuntimeError, match="not authenticated"):
                await runner.list_contacts()


# ── _download_audio_for_bubbles ───────────────────────────────────────────────

class TestDownloadAudioForBubbles:
    """_download_audio_for_bubbles skips non-audio bubbles and returns empty list for text."""

    @pytest.mark.asyncio
    async def test_returns_empty_for_no_audio_bubbles(self):
        """Si no hay burbujas de audio, devuelve lista vacía."""
        runner = _runner()
        runner.session.reset_blobs = AsyncMock()

        text_bubble = Bubble(
            id=1, screen_id=1, sender="me", msg_type="text",
            timestamp=None, text="hola",
            bbox={"x": 0, "y": 0, "w": 100, "h": 30},
        )

        result = await runner._download_audio_for_bubbles([text_bubble])
        assert result == []

    @pytest.mark.asyncio
    async def test_filters_out_non_audio_bubbles(self):
        """Procesa solo audio_bubbles, ignora text y file."""
        runner = _runner()
        runner.session.reset_blobs = AsyncMock()
        runner.session.get_dpr = AsyncMock(return_value=1.0)
        runner.find_play_buttons = AsyncMock(return_value=[])

        # Mock para session._page
        page_mock = MagicMock()
        page_mock.wait_for_timeout = AsyncMock()
        runner.session._page = page_mock

        audio_bubble = Bubble(
            id=1, screen_id=1, sender="other", msg_type="audio",
            timestamp=None, text="",
            bbox={"x": 0, "y": 0, "w": 100, "h": 136},
        )
        text_bubble = Bubble(
            id=2, screen_id=2, sender="me", msg_type="text",
            timestamp=None, text="hola",
            bbox={"x": 0, "y": 200, "w": 100, "h": 30},
        )

        result = await runner._download_audio_for_bubbles([audio_bubble, text_bubble])

        # Solo procesa el audio_bubble (aunque falle por no tener play button)
        assert len(result) == 1
        assert result[0]["bubble"].id == 1
        assert result[0]["error"] == "no_play_button_matched"

    @pytest.mark.asyncio
    async def test_skips_already_downloaded_dom_id(self):
        """Bubble with dom_id already in downloaded_ids is skipped."""
        runner = _runner()
        runner.session.reset_blobs = AsyncMock()
        runner.session.get_dpr = AsyncMock(return_value=1.0)
        runner.find_play_buttons = AsyncMock(return_value=[])

        # Mock para session._page
        page_mock = MagicMock()
        page_mock.wait_for_timeout = AsyncMock()
        runner.session._page = page_mock

        audio = Bubble(
            id=1, screen_id=1, sender="other", msg_type="audio",
            timestamp="1:00 p. m.", text="0:15",
            bbox={"x": 0, "y": 100, "w": 200, "h": 60}
        )
        audio.dom_id = "true_+54@c.us_AUDIO001"

        already_seen = {"true_+54@c.us_AUDIO001"}

        # Llamamos con downloaded_ids ya poblado
        result = await runner._download_audio_for_bubbles(
            [audio], downloaded_ids=already_seen
        )

        # Debe estar vacío porque el audio fue skipeado
        assert len(result) == 0


# ── TestCaptureFullHistoryNewest ──────────────────────────────────────────

class TestCaptureFullHistoryNewest:
    """Test --newest flag: incremental history update with duplicate detection."""

    @pytest.mark.asyncio
    async def test_newest_stops_at_first_duplicate(self, tmp_path):
        """Given existing JSON with some bubbles, newest=True stops at first duplicate."""
        import json

        # Setup: existing history with 2 bubbles (A, B) — A is oldest
        existing = [
            _hist_bubble(screen_id=1, sender="me", text="A", y=100, timestamp="1:00 p.m."),
            _hist_bubble(screen_id=2, sender="me", text="B", y=200, timestamp="1:01 p.m."),
        ]

        # iter_0: newest screen with C and D (both new, not in existing)
        # B is at the bottom as anchor/potential duplicate
        iter0 = [
            _hist_bubble(screen_id=4, sender="other", text="D", y=100, timestamp="1:03 p.m."),
            _hist_bubble(screen_id=3, sender="other", text="C", y=200, timestamp="1:02 p.m."),
            _hist_bubble(screen_id=2, sender="me", text="B", y=300, timestamp="1:01 p.m."),  # bottom/anchor
        ]

        # iter_1: after scroll up — E is new, B is anchor/duplicate
        iter1 = [
            _hist_bubble(screen_id=5, sender="other", text="E", y=100, timestamp="1:04 p.m."),
            _hist_bubble(screen_id=2, sender="me", text="B", y=300, timestamp="1:01 p.m."),  # anchor
        ]

        # Setup: save existing JSON
        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        json_path = assets_dir / "history_bubbles.json"
        json_path.write_text(json.dumps([b.as_dict() for b in existing], indent=2, ensure_ascii=False))

        # Mock runner
        runner = _runner()

        call_idx = 0
        async def fake_get_bubbles(*args, **kwargs):
            nonlocal call_idx
            if call_idx == 0:
                result = iter0
            elif call_idx == 1:
                result = iter1
            else:
                # During backoff or additional calls, keep returning iter1 or empty
                result = iter1 if call_idx == 2 else iter1  # For backoff attempts
            call_idx += 1
            return result

        runner.get_bubbles = fake_get_bubbles
        runner.find_play_buttons = AsyncMock(return_value=[])

        page_mock = MagicMock()
        page_mock.wait_for_timeout = AsyncMock()
        runner.session._page = page_mock
        runner.session.install_blob_monitor = AsyncMock()
        runner.session.reset_blobs = AsyncMock()
        runner.session.drain_blobs = AsyncMock(return_value=[])
        runner.session.get_dpr = AsyncMock(return_value=1.0)
        runner.session.scroll_chat_up = AsyncMock()
        runner.session.scroll_chat_down = AsyncMock()
        runner.session.get_visible_message_ids = AsyncMock(return_value=[])
        runner.session.get_chat_scroll_state = AsyncMock(side_effect=[
            # init_state
            {"scrollTop": 500, "scrollHeight": 1000, "clientHeight": 500},
            # state before iter 0 → continue
            {"scrollTop": 500, "scrollHeight": 1000, "clientHeight": 500},
            # new_state after scroll iter 0 → continue (moved 300+, so no backoff)
            {"scrollTop": 100, "scrollHeight": 1000, "clientHeight": 500},
            # state before iter 1 → continue (now at 100)
            {"scrollTop": 100, "scrollHeight": 1000, "clientHeight": 500},
            # new_state after scroll iter 1 → at top, stop
            {"scrollTop": 0, "scrollHeight": 1000, "clientHeight": 500},
        ])

        result = await runner.capture_full_history(assets_dir=assets_dir, newest=True)

        # After iter_0: D, C (new)
        # At iter_1: E (new), but then B appears as duplicate → should_stop_newest=True
        # So result should be: E, D, C (no B)
        texts = [b.text for b in result]
        assert "D" in texts and "C" in texts and "E" in texts, f"Should capture D, C, E, got: {texts}"
        assert "B" not in texts, f"B is the duplicate anchor in iter_1, should not appear in new result"
        assert "A" not in texts, f"A is from existing, should not appear in new result"

        # Check merged result in JSON
        json_result = json.loads(json_path.read_text())
        json_texts = [b["text"] for b in json_result]
        # Final order should be: E, D, C (new, newest first) + A, B (existing, in original order)
        assert json_texts == ["E", "D", "C", "A", "B"], f"Merged order incorrect: {json_texts}"

    @pytest.mark.asyncio
    async def test_newest_falls_back_when_no_json(self, tmp_path):
        """If no history_bubbles.json exists, newest=True falls back to normal full capture."""
        # iter_0 and iter_1 like normal tests
        iter0 = [
            _hist_bubble(screen_id=3, sender="me", text="A", y=100, timestamp="1:00 p.m."),
            _hist_bubble(screen_id=2, sender="me", text="B", y=200, timestamp="1:01 p.m."),
            _hist_bubble(screen_id=1, sender="me", text="C", y=300, timestamp="1:02 p.m."),
        ]
        iter1 = [
            _hist_bubble(screen_id=3, sender="other", text="D", y=100, timestamp="1:03 p.m."),
            _hist_bubble(screen_id=2, sender="other", text="E", y=200, timestamp="1:04 p.m."),
            _hist_bubble(screen_id=1, sender="me", text="A", y=300, timestamp="1:00 p.m."),  # anchor
        ]

        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        # No history_bubbles.json exists!

        runner = _mock_runner_for_history(iter0, iter1)

        result = await runner.capture_full_history(assets_dir=assets_dir, newest=True)

        # Should have all 5 bubbles (normal behavior)
        texts = [b.text for b in result]
        assert len(result) == 5, f"Should capture all 5 bubbles, got {len(result)}"
        assert set(texts) == {"A", "B", "C", "D", "E"}

    @pytest.mark.asyncio
    async def test_newest_merges_and_renumbers(self, tmp_path):
        """After merge, id=1 should be newest; ids should be sequential 1..N."""
        import json

        # Existing: B, A (B is newer in list, id=2; A older, id=1)
        existing = [
            _hist_bubble(screen_id=1, sender="me", text="A", y=100, timestamp="1:00 p.m."),
            _hist_bubble(screen_id=2, sender="me", text="B", y=200, timestamp="1:01 p.m."),
        ]

        # New capture: D, C (D is newest, will be first after merge)
        iter0 = [
            _hist_bubble(screen_id=3, sender="other", text="D", y=100, timestamp="1:03 p.m."),
            _hist_bubble(screen_id=4, sender="other", text="C", y=200, timestamp="1:02 p.m."),
        ]

        assets_dir = tmp_path / "assets"
        assets_dir.mkdir()
        json_path = assets_dir / "history_bubbles.json"
        # Save existing with id=1 for A (oldest), id=2 for B (newest)
        existing_with_ids = [{"id": 1, **b.as_dict()} for b in existing]
        # Reorder: oldest first
        existing_with_ids = [existing_with_ids[1], existing_with_ids[0]]  # B, A
        existing_with_ids[0]["id"] = 1  # B = id 1
        existing_with_ids[1]["id"] = 2  # A = id 2
        json_path.write_text(json.dumps(existing_with_ids, indent=2, ensure_ascii=False))

        runner = _runner()

        call_idx = 0
        async def fake_get_bubbles(*args, **kwargs):
            nonlocal call_idx
            result = iter0 if call_idx == 0 else []
            call_idx += 1
            return result

        runner.get_bubbles = fake_get_bubbles
        runner.find_play_buttons = AsyncMock(return_value=[])

        page_mock = MagicMock()
        page_mock.wait_for_timeout = AsyncMock()
        runner.session._page = page_mock
        runner.session.install_blob_monitor = AsyncMock()
        runner.session.reset_blobs = AsyncMock()
        runner.session.drain_blobs = AsyncMock(return_value=[])
        runner.session.get_dpr = AsyncMock(return_value=1.0)
        runner.session.scroll_chat_up = AsyncMock()
        runner.session.scroll_chat_down = AsyncMock()
        runner.session.get_visible_message_ids = AsyncMock(return_value=[])
        runner.session.get_chat_scroll_state = AsyncMock(side_effect=[
            {"scrollTop": 500, "scrollHeight": 1000, "clientHeight": 500},
            {"scrollTop": 500, "scrollHeight": 1000, "clientHeight": 500},
            {"scrollTop": 0, "scrollHeight": 1000, "clientHeight": 500},
        ])

        await runner.capture_full_history(assets_dir=assets_dir, newest=True)

        # Check final JSON
        json_result = json.loads(json_path.read_text())
        ids = [b["id"] for b in json_result]
        texts = [b["text"] for b in json_result]

        # IDs must be sequential 1..4
        assert ids == [1, 2, 3, 4], f"IDs should be [1,2,3,4], got {ids}"
        # D is newest (id=1), A is oldest (id=4)
        assert texts[0] == "D", f"First (id=1) should be D (newest), got {texts[0]}"
        assert texts[-1] == "A", f"Last (id=4) should be A (oldest), got {texts[-1]}"
        # Order: D (new), C (new), B (existing), A (existing)
        assert texts == ["D", "C", "B", "A"], f"Order should be [D,C,B,A], got {texts}"
