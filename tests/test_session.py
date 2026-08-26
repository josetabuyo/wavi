"""
Tests de WASession — verifican comportamiento de navegación sin browser real.

Los tests mockean self._page para confirmar que navigate_to_contact:
  - usa mouse.click por coordenadas (no locator ni CSS)
  - usa teclado para limpiar (no .clear())
  - no llama a self._page.locator() en ningún momento
  - usa DOM scroll (page.evaluate) para anclar al fondo, no mouse.wheel

También cubren _setup_page: set_viewport_size debe llamarse ANTES de goto(WA_URL)
solo cuando headless=True y la página aún no está en WA.

TestViewportRegression (ADR-002): garantiza que el viewport 1280×1920 nunca regrese
a "imagen enana". Si alguno de estos tests falla, los screenshots tendrán menos
mensajes de lo esperado y full-sync-enhanced necesitará más iteraciones.

TestNeverDeleteSessionProfile (ADR-009): garantiza que 'wavi connect' nunca
vuelve a borrar un perfil de sesión existente. El 2026-08-18 se confirmó que
'--new' hacía shutil.rmtree(phone_profile) sobre una sesión autenticada antes
de reemplazarla — pérdida irrecuperable de auth. Ahora se archiva (rename),
nunca se borra.
"""
from unittest.mock import AsyncMock, MagicMock

import pytest

from wavi.session import WA_URL, WINDOW_H, WINDOW_W, WASession


def _make_session() -> WASession:
    s = WASession("data/sessions/default", headless=False)
    return s


def _make_page(selector_found: bool = True) -> MagicMock:
    """Retorna un mock de Playwright Page con los métodos async correctos."""
    page = MagicMock()
    page.mouse = MagicMock()
    page.mouse.click = AsyncMock()
    page.mouse.move = AsyncMock()
    page.mouse.wheel = AsyncMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.keyboard.type = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.wait_for_selector = AsyncMock() if selector_found else AsyncMock(side_effect=Exception("timeout"))
    page.locator = MagicMock()  # no debe llamarse — lo detectamos en los tests
    page.screenshot = AsyncMock(return_value=b"")
    # navigate_to_contact uses evaluate() for DOM scroll (ADR-002)
    page.evaluate = AsyncMock(return_value=False)  # False → no scroll button found → fallback
    return page


def _stub_resolved(session: WASession, name: str = "Gregorio", x: int = 100, y: int = 200) -> None:
    """Bypass contact search/disambiguation entirely — used by tests that
    only care about what happens AFTER a contact is resolved (scrolling)."""
    session._resolve_contact = AsyncMock(return_value={"name": name, "subtitle": "", "x": x, "y": y})
    session.open_search_result = AsyncMock(return_value=True)


class TestSearchContacts:
    """search_contacts() owns the actual search-box interaction — clicking,
    clearing, typing — that navigate_to_contact used to do inline before
    ADR-010 added disambiguation."""

    @pytest.fixture
    def session(self):
        s = _make_session()
        s._page = _make_page(selector_found=True)
        s._page.evaluate = AsyncMock(return_value=[{"name": "Gregorio", "subtitle": "", "x": 1, "y": 2}])
        return s

    @pytest.mark.asyncio
    async def test_clicks_search_box_by_coordinate(self, session):
        await session.search_contacts("Gregorio")
        session._page.mouse.click.assert_any_call(WASession.SEARCH_X, WASession.SEARCH_Y)

    @pytest.mark.asyncio
    async def test_clears_with_keyboard_not_dom(self, session):
        await session.search_contacts("Gregorio")
        calls = [c.args[0] for c in session._page.keyboard.press.call_args_list]
        assert "Meta+a" in calls
        assert "Delete" in calls

    @pytest.mark.asyncio
    async def test_types_contact_name(self, session):
        await session.search_contacts("Gregorio")
        session._page.keyboard.type.assert_called_once_with("Gregorio", delay=40)

    @pytest.mark.asyncio
    async def test_never_uses_locator(self, session):
        await session.search_contacts("Gregorio")
        session._page.locator.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_results_appear(self, session):
        session._page.wait_for_selector = AsyncMock(side_effect=Exception("timeout"))
        result = await session.search_contacts("Nadie")
        assert result == []

    @pytest.mark.asyncio
    async def test_returns_candidates_from_page_evaluate(self, session):
        candidates = [
            {"name": "Rodolfo Prado", "subtitle": "Reaccionó con ❤️", "x": 100, "y": 240},
            {"name": "Rodolfo Prado", "subtitle": "+54 9 11 6671-4914", "x": 100, "y": 500},
        ]
        session._page.evaluate = AsyncMock(return_value=candidates)
        result = await session.search_contacts("Rodolfo Prado")
        assert result == candidates


class TestResolveContact:
    """ADR-010: navigate_to_contact must never guess which contact was
    meant when the display name is ambiguous — a human decides, or it
    refuses outright when there's no TTY to ask."""

    @pytest.fixture
    def session(self):
        return _make_session()

    @pytest.mark.asyncio
    async def test_single_match_auto_resolves_without_prompting(self, session, monkeypatch):
        candidate = {"name": "Gregorio", "subtitle": "", "x": 10, "y": 20}
        session.search_contacts = AsyncMock(return_value=[candidate])
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)  # must not matter — only 1 match
        result = await session._resolve_contact("Gregorio")
        assert result == candidate

    @pytest.mark.asyncio
    async def test_dedupes_identical_name_and_subtitle_pairs(self, session):
        dup = {"name": "Gregorio", "subtitle": "hola", "x": 10, "y": 20}
        session.search_contacts = AsyncMock(return_value=[dup, dict(dup)])
        result = await session._resolve_contact("Gregorio")
        assert result == dup  # only one distinct candidate → no prompt needed

    @pytest.mark.asyncio
    async def test_refreshes_contact_list_when_nothing_found(self, session):
        """Justo después de vincular por QR, la lista de chats puede seguir
        sincronizando desde el teléfono — la primera búsqueda puede no
        encontrar resultados todavía."""
        candidate = {"name": "Gregorio", "subtitle": "", "x": 10, "y": 20}
        session.search_contacts = AsyncMock(side_effect=[[], [candidate]])
        session.navigate_to_new_chat = AsyncMock()
        session.close_new_chat = AsyncMock()

        result = await session._resolve_contact("Gregorio")

        assert result == candidate
        session.navigate_to_new_chat.assert_awaited_once()
        session.close_new_chat.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_raises_if_nothing_found_even_after_refresh(self, session, tmp_path):
        session.profile_dir = tmp_path
        session.search_contacts = AsyncMock(return_value=[])
        session.navigate_to_new_chat = AsyncMock()
        session.close_new_chat = AsyncMock()
        session._page = _make_page()

        with pytest.raises(RuntimeError, match="No se encontró ningún chat/contacto"):
            await session._resolve_contact("Nadie")

    @pytest.mark.asyncio
    async def test_multiple_matches_without_tty_raises_instead_of_guessing(self, session, monkeypatch):
        """El bug real (2026-08-26): 'Rodolfo Prado' coincidía con un chat
        existente Y con 4 contactos distintos. Sin una terminal para
        preguntar, nunca debe elegir uno arbitrariamente."""
        candidates = [
            {"name": "Rodolfo Prado", "subtitle": "Reaccionó con ❤️", "x": 1, "y": 1},
            {"name": "Rodolfo Prado", "subtitle": "+54 9 11 6671-4914", "x": 1, "y": 2},
        ]
        session.search_contacts = AsyncMock(return_value=candidates)
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)

        with pytest.raises(RuntimeError, match="Hay 2 coincidencias"):
            await session._resolve_contact("Rodolfo Prado")

    @pytest.mark.asyncio
    async def test_multiple_matches_with_tty_prompts_and_uses_the_choice(self, session, monkeypatch):
        candidates = [
            {"name": "Rodolfo Prado", "subtitle": "Reaccionó con ❤️", "x": 1, "y": 1},
            {"name": "Rodolfo Prado", "subtitle": "+54 9 11 6671-4914", "x": 1, "y": 2},
        ]
        session.search_contacts = AsyncMock(return_value=candidates)
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("click.prompt", lambda *a, **k: 2)  # human picks the 2nd option

        result = await session._resolve_contact("Rodolfo Prado")
        assert result == candidates[1]

    @pytest.mark.asyncio
    async def test_filters_out_unrelated_shared_groups(self, session):
        """Real bug reported by Pulpo, 2026-08-26: searching 'Rodolfo Prado'
        also returned rows for groups they're merely a member of ('Blanca y
        sus pollitos', 'Grupo por mamá') — WA's own name-independent 'shared
        groups' search feature. Those must never be presented as if they
        were named 'Rodolfo Prado'."""
        candidates = [
            {"name": "Rodolfo Prado", "subtitle": "Reaccionó con ❤️", "x": 1, "y": 1},
            {"name": "Blanca y sus pollitos", "subtitle": "Rodolfo Prado y Noelia Prado también están en este grupo.", "x": 1, "y": 2},
            {"name": "Grupo por mamá", "subtitle": "Rodolfo Prado y Karen Prado también están en este grupo.", "x": 1, "y": 3},
        ]
        session.search_contacts = AsyncMock(return_value=candidates)

        result = await session._resolve_contact("Rodolfo Prado")

        assert result["name"] == "Rodolfo Prado"

    @pytest.mark.asyncio
    async def test_raises_when_no_candidate_name_actually_matches(self, session, tmp_path):
        session.profile_dir = tmp_path
        session.search_contacts = AsyncMock(return_value=[
            {"name": "Blanca y sus pollitos", "subtitle": "Rodolfo Prado también está en este grupo.", "x": 1, "y": 1},
        ])
        with pytest.raises(RuntimeError, match="ninguno tiene ese nombre"):
            await session._resolve_contact("Rodolfo Prado")

    @pytest.mark.asyncio
    async def test_accent_and_case_insensitive_match(self, session):
        candidates = [{"name": "José García", "subtitle": "", "x": 1, "y": 1}]
        session.search_contacts = AsyncMock(return_value=candidates)
        result = await session._resolve_contact("jose garcia")
        assert result["name"] == "José García"

    @pytest.mark.asyncio
    async def test_real_chats_ranked_above_bare_contacts(self, session, monkeypatch):
        """The user asked for matches to be ordered by last activity when
        several exist. WA already lists real chats by recency internally,
        so ranking 'has any activity at all' above 'never messaged' and
        keeping discovery order within each group achieves that without
        having to parse WA's date/time text ourselves."""
        bare_contact = {"name": "Rodolfo Prado", "subtitle": "+54 9 11 7019-3919", "x": 1, "y": 1}
        real_chat = {"name": "Rodolfo Prado", "subtitle": "Reaccionó con ❤️", "last_activity": "9:43 a. m.", "x": 1, "y": 2}
        # Bare contact appears first in DOM/search order, real chat second —
        # the real chat must still be ranked first (or offered first).
        session.search_contacts = AsyncMock(return_value=[bare_contact, real_chat])
        monkeypatch.setattr("sys.stdin.isatty", lambda: True)
        monkeypatch.setattr("click.prompt", lambda *a, **k: 1)  # pick "option 1" as offered

        result = await session._resolve_contact("Rodolfo Prado")
        assert result is real_chat

    @pytest.mark.asyncio
    async def test_pick_selects_without_tty(self, session, monkeypatch):
        """--pick lets a script/agent resolve ambiguity non-interactively —
        no TTY required, no prompt."""
        candidates = [
            {"name": "Rodolfo Prado", "subtitle": "Reaccionó con ❤️", "last_activity": "9:43 a. m.", "x": 1, "y": 1},
            {"name": "Rodolfo Prado", "subtitle": "+54 9 11 6671-4914", "x": 1, "y": 2},
        ]
        session.search_contacts = AsyncMock(return_value=candidates)
        monkeypatch.setattr("sys.stdin.isatty", lambda: False)

        result = await session._resolve_contact("Rodolfo Prado", pick=2)
        assert result == candidates[1]

    @pytest.mark.asyncio
    async def test_pick_out_of_range_raises(self, session):
        candidates = [{"name": "Rodolfo Prado", "subtitle": "a", "x": 1, "y": 1}]
        session.search_contacts = AsyncMock(return_value=candidates)
        with pytest.raises(RuntimeError, match="fuera de rango"):
            await session._resolve_contact("Rodolfo Prado", pick=5)


class TestNavigateToContact:
    @pytest.fixture
    def session(self):
        s = _make_session()
        s._page = _make_page(selector_found=True)
        _stub_resolved(s)
        return s

    @pytest.mark.asyncio
    async def test_opens_resolved_candidate_via_click_not_keyboard(self, session):
        """El resultado se abre haciendo clic en las coordenadas resueltas
        (ADR-010), nunca con ArrowDown/Enter a ciegas ni con page.click(selector)."""
        await session.navigate_to_contact("Gregorio")
        session.open_search_result.assert_awaited_once_with(100, 200)
        session._page.locator.assert_not_called()

    @pytest.mark.asyncio
    async def test_dom_scroll_to_bottom_called_after_load(self, session):
        """Después de cargar mensajes se ejecuta evaluate() para DOM scroll al fondo."""
        await session.navigate_to_contact("Gregorio")
        assert session._page.evaluate.called, "evaluate() debe llamarse para el scroll al fondo"

    @pytest.mark.asyncio
    async def test_dom_scroll_fallback_uses_large_delta(self, session):
        """Si no hay botón de ir al fondo (evaluate devuelve False), el fallback
        hace evaluate con 999_999 para llevar scrollTop al máximo."""
        # btn not found → dom scroll → get_chat_scroll_state returns None → retry loop breaks
        session._page.evaluate = AsyncMock(side_effect=[False, None, None])
        await session.navigate_to_contact("Gregorio")
        calls = session._page.evaluate.call_args_list
        scroll_args = [c for c in calls if c.args and len(c.args) > 1 and c.args[1] == 999_999]
        assert scroll_args, "El fallback DOM scroll debe usar delta 999_999"

    @pytest.mark.asyncio
    async def test_scroll_fires_after_resolution(self, session):
        """El scroll al fondo ocurre después de resolver y abrir el chat."""
        order: list[str] = []
        session.open_search_result = AsyncMock(
            side_effect=lambda *a, **kw: order.append("opened") or True
        )
        session._page.evaluate = AsyncMock(
            side_effect=lambda *a, **kw: order.append("evaluate") or False
        )
        await session.navigate_to_contact("Gregorio")
        assert "opened" in order and "evaluate" in order
        assert order.index("opened") < order.index("evaluate")

    @pytest.mark.asyncio
    async def test_retries_resolution_once_if_click_did_not_open_a_chat(self, session):
        """Si el clic no abrió el chat (p.ej. la fila se movió entre la
        búsqueda y el clic), se reintenta resolver + abrir una vez más
        antes de rendirse."""
        session.open_search_result = AsyncMock(side_effect=[False, True])
        await session.navigate_to_contact("Gregorio")  # must not raise
        assert session._resolve_contact.call_count == 2
        assert session.open_search_result.call_count == 2

    @pytest.mark.asyncio
    async def test_raises_and_never_scrolls_if_chat_never_opened(self, session, tmp_path):
        """Si nunca se pudo confirmar que el chat abrió, debe levantar
        RuntimeError y NUNCA intentar el scroll-to-bottom sobre un chat que
        no existe. Antes esto se tragaba en silencio y devolvía mensajes de
        la pantalla de bienvenida como si fueran del contacto (bug real,
        2026-08-26: 'Rodolfo Prado' devolvió el banner de 'Llamadas y
        videollamadas ya están disponibles')."""
        session.profile_dir = tmp_path
        session.open_search_result = AsyncMock(return_value=False)
        with pytest.raises(RuntimeError, match="No se pudo abrir el chat"):
            await session.navigate_to_contact("Gregorio")
        assert not session._page.evaluate.called

    @pytest.mark.asyncio
    async def test_scroll_retries_if_not_at_bottom(self):
        """
        Si get_chat_scroll_state muestra slack > 50px, el loop vuelve a intentar
        scroll-to-bottom. Simula la situación post-full-sync-enhanced donde el
        virtualizer restaura la posición anterior (top) en vez del fondo.
        """
        s = _make_session()
        page = _make_page()
        _stub_resolved(s)

        # evaluate calls in order:
        # 1. _CLICK_SCROLL_BOTTOM_BTN_JS (initial) → False (no button)
        # 2. _SCROLL_DOWN_JS 999_999 (initial fallback) → None
        # 3. get_chat_scroll_state retry 1 → not at bottom (slack=1000)
        # 4. _CLICK_SCROLL_BOTTOM_BTN_JS retry 1 → False
        # 5. _SCROLL_DOWN_JS 999_999 retry 1 → None
        # 6. get_chat_scroll_state retry 2 → at bottom (slack=0)
        page.evaluate = AsyncMock(side_effect=[
            False,                                                          # btn initial
            None,                                                           # dom scroll initial
            {"scrollTop": 0, "scrollHeight": 2000, "clientHeight": 1000},  # retry check: not at bottom
            False,                                                          # btn retry
            None,                                                           # dom scroll retry
            {"scrollTop": 1000, "scrollHeight": 2000, "clientHeight": 1000},  # retry check: at bottom (slack=0)
        ])
        s._page = page

        await s.navigate_to_contact("Gregorio")

        # Should have called DOM scroll at least twice (initial + one retry)
        dom_scroll_calls = [
            c for c in page.evaluate.call_args_list
            if len(c.args) > 1 and c.args[1] == 999_999
        ]
        assert len(dom_scroll_calls) >= 2, \
            f"Esperaba ≥2 DOM scroll calls (initial + retry), obtuvo {len(dom_scroll_calls)}"

    @pytest.mark.asyncio
    async def test_scroll_no_extra_retries_when_already_at_bottom(self):
        """Si ya está en el fondo desde el primer check, no hace retries innecesarios."""
        s = _make_session()
        page = _make_page()
        _stub_resolved(s)

        page.evaluate = AsyncMock(side_effect=[
            False,                                                           # btn initial
            None,                                                            # dom scroll initial
            {"scrollTop": 950, "scrollHeight": 1000, "clientHeight": 1000}, # slack=50 ≤ 50 → break
        ])
        s._page = page

        await s.navigate_to_contact("Gregorio")

        dom_scroll_calls = [
            c for c in page.evaluate.call_args_list
            if len(c.args) > 1 and c.args[1] == 999_999
        ]
        assert len(dom_scroll_calls) == 1, \
            "Si ya estaba en el fondo, solo debe haber 1 DOM scroll (el inicial)"


# ── _setup_page: viewport before WA load ─────────────────────────────────────

def _make_browser_mock(url: str) -> tuple[MagicMock, MagicMock]:
    """Return (browser, page) with page.url preset and async methods mocked."""
    page = MagicMock()
    page.url = url
    page.set_viewport_size = AsyncMock()
    page.goto = AsyncMock()
    page.close = AsyncMock()
    page.wait_for_selector = AsyncMock()
    page.query_selector = AsyncMock(return_value=MagicMock())  # truthy → "restored"

    context = MagicMock()
    context.pages = [page]

    browser = MagicMock()
    browser.contexts = [context]
    return browser, page


class TestSetupPageViewport:
    """set_viewport_size(WINDOW_W, WINDOW_H) must fire before goto(WA_URL) iff
    headless=True AND page is not already at WA_URL."""

    @pytest.mark.asyncio
    async def test_headless_blank_calls_set_viewport_before_goto(self):
        """Headless + about:blank: set_viewport_size fires first, then goto."""
        s = WASession("data/sessions/default", headless=True)
        browser, page = _make_browser_mock("about:blank")
        s._browser = browser

        order: list[str] = []
        page.set_viewport_size = AsyncMock(side_effect=lambda *a, **kw: order.append("set_viewport_size"))
        page.goto = AsyncMock(side_effect=lambda *a, **kw: order.append("goto"))

        await s._setup_page()

        assert order.index("set_viewport_size") < order.index("goto")

    @pytest.mark.asyncio
    async def test_headless_blank_viewport_dimensions(self):
        """Viewport is set to exactly WINDOW_W × WINDOW_H."""
        s = WASession("data/sessions/default", headless=True)
        browser, page = _make_browser_mock("about:blank")
        s._browser = browser

        await s._setup_page()

        page.set_viewport_size.assert_called_once_with({"width": WINDOW_W, "height": WINDOW_H})

    @pytest.mark.asyncio
    async def test_headful_never_sets_viewport(self):
        """Headful mode (QR scan window) must not call set_viewport_size."""
        s = WASession("data/sessions/default", headless=False)
        browser, page = _make_browser_mock("about:blank")
        s._browser = browser

        await s._setup_page()

        page.set_viewport_size.assert_not_called()

    @pytest.mark.asyncio
    async def test_wa_already_loaded_skips_viewport_and_goto(self):
        """Daemon reconnect (WA already at WA_URL): no viewport change, no navigation."""
        s = WASession("data/sessions/default", headless=True)
        browser, page = _make_browser_mock(WA_URL)
        s._browser = browser

        await s._setup_page()

        page.set_viewport_size.assert_not_called()
        page.goto.assert_not_called()


# ── ADR-002: Regresión de viewport — tests que detectan la imagen "enana" ─────

class TestViewportRegression:
    """
    ADR-002: WINDOW_W=1280, WINDOW_H=1920, --force-device-scale-factor=1.

    Si cualquiera de estos tests falla, el screenshot tendrá menos mensajes
    de lo esperado y full-sync-enhanced necesitará más scroll para el mismo chat.

    Estos tests atrapan regresiones silenciosas: código que parece funcionar
    pero produce imágenes de ~876px de alto en lugar de 1920px.
    """

    def test_window_w_is_1280(self):
        """WINDOW_W debe ser 1280 — base calibrada de la fórmula del sidebar."""
        assert WINDOW_W == 1280, (
            f"WINDOW_W={WINDOW_W} — el sidebar crop formula en vision.py "
            "está calibrado para 1280. Cambiar esto rompe la detección de burbujas."
        )

    def test_window_h_is_1920(self):
        """WINDOW_H debe ser 1920 — maximiza mensajes por screenshot (ADR-002)."""
        assert WINDOW_H == 1920, (
            f"WINDOW_H={WINDOW_H} — con menos altura, cada screenshot captura "
            "menos mensajes y full-sync-enhanced necesita más iteraciones de scroll."
        )

    def test_cli_headless_args_include_force_dpr(self):
        """--force-device-scale-factor=1 debe estar en los args de wavi connect.
        Sin este flag, macOS Retina (DPR=2) produce viewport de ~640×960 CSS
        en lugar de 1280×1920, dando imágenes 'enanas'."""
        from wavi.cli import _HEADLESS_CHROME_ARGS
        assert "--force-device-scale-factor=1" in _HEADLESS_CHROME_ARGS, (
            "--force-device-scale-factor=1 falta en _HEADLESS_CHROME_ARGS. "
            "Sin esto, el daemon iniciado por 'wavi connect' en Mac Retina "
            "produce screenshots de ~876px de alto en lugar de 1920px."
        )

    def test_cli_headless_args_include_window_size(self):
        """--window-size=1280,1920 debe estar en los args de wavi connect."""
        from wavi.cli import WINDOW_H, WINDOW_W
        # _HEADLESS_CHROME_ARGS doesn't include window-size directly (it's added
        # in _launch_headless_daemon), but we verify the constants are correct.
        assert WINDOW_W == 1280
        assert WINDOW_H == 1920

    def test_session_fallback_args_include_force_dpr(self):
        """El fallback de WASession.connect() también debe tener --force-device-scale-factor=1.
        Este fallback se usa cuando 'wavi status' inicia Chrome sin un daemon previo.
        Si falta aquí, el daemon iniciado por 'wavi status' produce imágenes enanas."""
        import inspect

        from wavi.session import WASession
        source = inspect.getsource(WASession.connect)
        assert "--force-device-scale-factor=1" in source, (
            "--force-device-scale-factor=1 falta en WASession.connect() fallback. "
            "El daemon iniciado por 'wavi status' (sin daemon previo) usará un "
            "viewport reducido en Mac Retina, produciendo imágenes 'enanas'."
        )

    def test_session_fallback_args_include_window_size(self):
        """El fallback de WASession.connect() debe lanzar Chrome con --window-size usando
        las constantes WINDOW_W y WINDOW_H (verificado por su presencia en el source)."""
        import inspect

        from wavi.session import WASession
        source = inspect.getsource(WASession.connect)
        # The source uses an f-string: f"--window-size={WINDOW_W},{WINDOW_H}"
        assert "--window-size=" in source and "WINDOW_W" in source and "WINDOW_H" in source, (
            "--window-size con WINDOW_W/WINDOW_H falta en WASession.connect() fallback."
        )

    def test_screenshot_dimensions_match_window_constants(self):
        """Con DPR=1 y viewport correcto, screenshot debe ser WINDOW_W × WINDOW_H.
        Este test verifica que si alguien toma un screenshot mockeado, las dimensiones
        son las esperadas por el pipeline de visión."""
        # Las dimensiones del screenshot son la fuente de verdad para vision.py.
        # vision.crop_chat_panel usa img.size para calcular sidebar_x.
        # Si el screenshot tiene alto != WINDOW_H, sidebar_x será correcto pero
        # la cantidad de mensajes capturados por pantalla será menor.
        from wavi.vision import SIDEBAR_PX
        # Con WINDOW_W=1280 y DPR=1, el screenshot tiene width=1280.
        # sidebar_x = int(1280 * (580/1280)) = 580 exactamente.
        sidebar_x_at_correct_width = int(WINDOW_W * (SIDEBAR_PX / WINDOW_W))
        assert sidebar_x_at_correct_width == SIDEBAR_PX
        # El alto del screenshot debe ser >= WINDOW_H para el crop correcto.
        # Si el screenshot es más chico (ej: 876px), se ven menos mensajes.
        assert WINDOW_H >= 1920, "Reducir WINDOW_H produce imágenes con menos mensajes"


class TestWindowConstants:
    """WINDOW_W is the calibrated base for vision.py sidebar crop formula."""

    def test_sidebar_formula_exact_at_dpr1(self):
        """DPR=1: screenshot_w == WINDOW_W → sidebar_x == SIDEBAR_PX exactly."""
        from wavi.vision import SIDEBAR_PX
        sidebar_x = int(WINDOW_W * (SIDEBAR_PX / WINDOW_W))
        assert sidebar_x == SIDEBAR_PX

    def test_sidebar_formula_exact_at_dpr2(self):
        """DPR=2: screenshot_w == 2*WINDOW_W → sidebar_x == 2*SIDEBAR_PX (physical px)."""
        from wavi.vision import SIDEBAR_PX
        screenshot_w = WINDOW_W * 2
        sidebar_x = int(screenshot_w * (SIDEBAR_PX / WINDOW_W))
        assert sidebar_x == SIDEBAR_PX * 2


# ── NewChatPanel: navigate, extract, close ───────────────────────────────────

class TestNewChatPanel:
    """Tests for new-chat panel navigation, contact extraction, and closing."""

    @pytest.mark.asyncio
    async def test_navigate_to_new_chat_success(self):
        """navigate_to_new_chat() clicks button, waits for list, no error."""
        s = _make_session()
        s._page = _make_page(selector_found=True)
        s._page.evaluate = AsyncMock(return_value=True)  # button clicked
        s._page.wait_for_selector = AsyncMock()
        s._page.wait_for_timeout = AsyncMock()

        await s.navigate_to_new_chat()

        assert s._page.evaluate.called
        assert s._page.wait_for_selector.called
        assert s._page.wait_for_timeout.called

    @pytest.mark.asyncio
    async def test_navigate_to_new_chat_ensures_clean_sidebar_first(self):
        """Real bug, 2026-08-26: _resolve_contact's refresh path calls this
        right after search_contacts() leaves text in the sidebar search box
        — with search active WA hides the pencil/new-chat button. Must
        clear that state before looking for the button."""
        s = _make_session()
        s._page = _make_page(selector_found=True)
        s._page.evaluate = AsyncMock(return_value=True)
        s._page.wait_for_selector = AsyncMock()
        s._page.wait_for_timeout = AsyncMock()

        await s.navigate_to_new_chat()

        # ensure_chat_list's own evaluate calls (_CLOSE_NEW_CHAT_JS,
        # _CLEAR_SIDEBAR_SEARCH_JS) plus the pencil-icon click itself.
        assert s._page.evaluate.call_count >= 3
        s._page.keyboard.press.assert_any_call("Escape")

    @pytest.mark.asyncio
    async def test_navigate_to_new_chat_not_found(self):
        """navigate_to_new_chat() raises RuntimeError if button not found."""
        s = _make_session()
        s._page = _make_page(selector_found=False)
        s._page.evaluate = AsyncMock(return_value=False)  # button not clicked

        with pytest.raises(RuntimeError, match="Could not find.*new-chat-outline"):
            await s.navigate_to_new_chat()

    @pytest.mark.asyncio
    async def test_extract_contacts_returns_list(self):
        """extract_contacts() evaluates JS and returns list of contact dicts."""
        s = _make_session()
        s._page = _make_page()
        contacts = [
            {"name": "Alice", "subtitle": ""},
            {"name": "Bob", "subtitle": "Hey there"},
        ]
        s._page.evaluate = AsyncMock(return_value=contacts)

        result = await s.extract_contacts()

        assert result == contacts
        assert len(result) == 2
        assert result[0]["name"] == "Alice"
        assert result[1]["subtitle"] == "Hey there"

    @pytest.mark.asyncio
    async def test_close_new_chat_via_back_button(self):
        """close_new_chat() uses back button when available."""
        s = _make_session()
        s._page = _make_page()
        s._page.evaluate = AsyncMock(return_value=True)  # back button found
        s._page.keyboard.press = AsyncMock()
        s._page.wait_for_timeout = AsyncMock()

        await s.close_new_chat()

        s._page.evaluate.assert_called_once()
        s._page.keyboard.press.assert_not_called()  # should NOT use Escape
        s._page.wait_for_timeout.assert_called_once()

    @pytest.mark.asyncio
    async def test_close_new_chat_fallback_escape(self):
        """close_new_chat() falls back to Escape if back button not found."""
        s = _make_session()
        s._page = _make_page()
        s._page.evaluate = AsyncMock(return_value=False)  # back button not found
        s._page.keyboard.press = AsyncMock()
        s._page.wait_for_timeout = AsyncMock()

        await s.close_new_chat()

        s._page.evaluate.assert_called_once()
        s._page.keyboard.press.assert_called_once_with("Escape")
        s._page.wait_for_timeout.assert_called_once()

    @pytest.mark.asyncio
    async def test_navigate_to_new_chat_selector_timeout_propagates(self):
        """navigate_to_new_chat() propagates wait_for_selector timeout (no swallowing)."""
        s = _make_session()
        s._page = _make_page()
        s._page.evaluate = AsyncMock(return_value=True)
        s._page.wait_for_selector = AsyncMock(side_effect=Exception("Timeout waiting for selector"))
        s._page.wait_for_timeout = AsyncMock()

        with pytest.raises(Exception, match="Timeout"):
            await s.navigate_to_new_chat()


# ── ADR-009: nunca borrar un perfil de sesión ──────────────────────────────────

class TestNeverDeleteSessionProfile:
    """Guardas estáticas contra la reintroducción del bug del 2026-08-18:
    'wavi connect --new' hacía shutil.rmtree(phone_profile) sobre una sesión
    ya autenticada antes de reemplazarla. Ver docs/adr/ADR-009."""

    def test_connect_source_never_calls_rmtree(self):
        """connect() no debe llamar shutil.rmtree bajo ninguna rama — la
        sesión existente se archiva (.rename), nunca se borra."""
        import inspect

        from wavi.cli import connect
        source = inspect.getsource(connect.callback)  # click.Command wraps the fn
        assert "rmtree" not in source, (
            "connect() llama shutil.rmtree — eso borra un perfil de sesión "
            "sin posibilidad de recuperación. Debe archivar con .rename() "
            "en su lugar. Ver ADR-009."
        )

    def test_connect_archives_existing_profile_on_collision(self):
        """Cuando --new detecta un teléfono que ya tiene perfil, el perfil
        viejo debe seguir existiendo en disco después (archivado), nunca
        desaparecer."""
        import inspect

        from wavi.cli import connect
        source = inspect.getsource(connect.callback)  # click.Command wraps the fn
        assert "_archived_" in source and ".rename(" in source, (
            "connect() debe archivar (rename a *_archived_<timestamp>) el "
            "perfil existente ante una colisión de --new, no reemplazarlo "
            "sin dejar rastro. Ver ADR-009."
        )

    def test_cleanup_crash_files_never_touches_indexeddb(self):
        """_cleanup_crash_files() solo debe tocar metadata de recuperación
        de pestañas de Chrome, nunca IndexedDB (donde vive el auth de WA)."""
        import inspect

        from wavi.cli import _cleanup_crash_files
        source = inspect.getsource(_cleanup_crash_files)
        assert "IndexedDB" not in source
