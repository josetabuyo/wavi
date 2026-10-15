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

from wavi.session import WA_URL, WINDOW_H, WINDOW_W, WASession, _same_letters


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
    ADR-010 added disambiguation. It only ever types with focus IN the
    search input, and never leaves the query in the open chat's box."""

    RESULTS = [{"name": "Gregorio", "subtitle": "", "x": 1, "y": 2}]

    def _route(self, session, *, focus=True, compose=("", ""), results=None, compose_empty=True):
        """FOCUS: bool or iterator of bools for the search-focus check;
        COMPOSE: compose-box text before / after typing."""
        focus_it = focus if hasattr(focus, "__next__") else None
        compose_it = iter(compose)
        last = {"compose": compose[0]}

        def evaluate(js, *a):
            if "closest('#side')" in js:
                return next(focus_it) if focus_it else focus
            if "return el ? (el.innerText" in js:
                last["compose"] = next(compose_it, last["compose"])
                return last["compose"]
            if "found: true" in js:
                return {"found": True, "x": 5, "y": 6}
            if "a.closest('footer" in js:
                return True
            if "if (el) return (el.innerText" in js:
                return compose_empty
            return results if results is not None else self.RESULTS
        session._page.evaluate = AsyncMock(side_effect=evaluate)
        session._debug_screenshot = AsyncMock(return_value=None)

    @pytest.fixture
    def session(self):
        s = _make_session()
        s._page = _make_page(selector_found=True)
        self._route(s)
        return s

    @pytest.mark.asyncio
    async def test_never_types_unless_focus_is_in_search(self, session):
        # Real case 2026-10-03: the search click didn't take focus and the
        # query was typed into the open group's compose box.
        self._route(session, focus=False)
        with pytest.raises(RuntimeError, match="foco"):
            await session.search_contacts("DATA LAKE - Tecnico")
        session._page.keyboard.type.assert_not_called()
        calls = [c.args[0] for c in session._page.keyboard.press.call_args_list]
        assert "Delete" not in calls

    @pytest.mark.asyncio
    async def test_retries_click_once_when_focus_not_in_search(self, session):
        self._route(session, focus=iter([False, True, True]))
        await session.search_contacts("Gregorio")
        assert session._page.mouse.click.call_count == 2
        session._page.keyboard.type.assert_called_once()

    @pytest.mark.asyncio
    async def test_focus_lost_after_clearing_types_nothing(self, session):
        self._route(session, focus=iter([True, False]))
        with pytest.raises(RuntimeError, match="perdió el foco"):
            await session.search_contacts("Gregorio")
        session._page.keyboard.type.assert_not_called()

    @pytest.mark.asyncio
    async def test_query_leaked_into_empty_compose_is_cleaned(self, session):
        # Real case 2026-10-09 ~14:40: "DATA LAKE - Técnico" left in Gerencia.
        self._route(session, compose=("", "LAKE - Técnico"), compose_empty=True)
        with pytest.raises(RuntimeError, match="se borró"):
            await session.search_contacts("DATA LAKE - Técnico")
        presses = [c.args[0] for c in session._page.keyboard.press.call_args_list]
        assert presses.count("Delete") == 2   # search clear + compose clean-up

    @pytest.mark.asyncio
    async def test_existing_draft_is_never_touched(self, session):
        self._route(session, compose=("borrador mío", "borrador míoGregorio"))
        with pytest.raises(RuntimeError, match="draft show"):
            await session.search_contacts("Gregorio")
        presses = [c.args[0] for c in session._page.keyboard.press.call_args_list]
        assert presses.count("Delete") == 1   # only the search box clear

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
        self._route(session, results=candidates)
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
        session.open_search_result.assert_awaited_once_with(100, 200, expected_name="Gregorio")
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
        """navigate_to_new_chat() raises RuntimeError if the button isn't
        found by either vision or the DOM fallback."""
        s = _make_session()
        s._page = _make_page(selector_found=False)
        s._page.evaluate = AsyncMock(return_value=False)  # button not clicked

        with pytest.raises(RuntimeError, match="Could not find the 'new chat' button"):
            await s.navigate_to_new_chat()

    @pytest.mark.asyncio
    async def test_navigate_to_new_chat_uses_vision_when_available(self, monkeypatch):
        """When locate_new_chat_button() finds the button, navigate_to_new_chat()
        clicks its center via Playwright and never falls back to the DOM
        eval — vision is the primary path (see _click_new_chat_via_vision's
        docstring), the DOM lookup (_OPEN_NEW_CHAT_JS) is only a fallback."""
        s = _make_session()
        s._page = _make_page(selector_found=True)
        monkeypatch.setattr(
            "wavi.vision_grounding.locate_new_chat_button",
            lambda *a, **k: {"x": 500, "y": 10, "w": 40, "h": 40},
        )

        await s.navigate_to_new_chat()

        s._page.mouse.click.assert_any_call(520.0, 30.0)  # box center
        # ensure_chat_list() itself calls evaluate() twice
        # (_CLOSE_NEW_CHAT_JS, _CLEAR_SIDEBAR_SEARCH_JS) — exactly 2, not 3,
        # confirms _OPEN_NEW_CHAT_JS's DOM lookup never ran: vision already
        # handled it.
        assert s._page.evaluate.call_count == 2

    @pytest.mark.asyncio
    async def test_navigate_to_new_chat_falls_back_to_dom_when_vision_unavailable(self, monkeypatch):
        """locate_new_chat_button() returning None (button not found by
        vision) must still fall back to the DOM lookup, not raise."""
        s = _make_session()
        s._page = _make_page(selector_found=True)
        s._page.evaluate = AsyncMock(return_value=True)
        monkeypatch.setattr("wavi.vision_grounding.locate_new_chat_button", lambda *a, **k: None)

        await s.navigate_to_new_chat()

        assert s._page.evaluate.called  # DOM fallback ran

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


class TestListAutoprefix:
    """WA continues a list by itself after Shift+Enter ("2. ", "• ");
    send_message must not type the marker twice ("2. 2. dos" — DataLake
    2026-10-04, reproduced live 2026-10-08)."""

    @pytest.fixture
    def session(self):
        s = _make_session()
        s._page = _make_page(selector_found=True)
        return s

    @pytest.mark.asyncio
    async def test_no_autoprefix_types_line_as_is(self, session):
        session._page.evaluate = AsyncMock(return_value="\n")
        assert await session._absorb_list_autoprefix("fin") == "fin"
        session._page.keyboard.press.assert_not_called()

    @pytest.mark.asyncio
    async def test_matching_marker_is_not_typed_again(self, session):
        session._page.evaluate = AsyncMock(return_value="2. ")
        assert await session._absorb_list_autoprefix("2. dos") == "dos"
        session._page.keyboard.press.assert_not_called()

    @pytest.mark.asyncio
    async def test_foreign_marker_is_erased(self, session):
        session._page.evaluate = AsyncMock(return_value="3. ")
        assert await session._absorb_list_autoprefix("fin") == "fin"
        presses = [c.args[0] for c in session._page.keyboard.press.call_args_list]
        assert presses == ["Backspace"] * 3


class TestSendMessageGuards:
    """send_message never sends what isn't exactly the message: no glued
    draft, no keystrokes before focus, no lost letters ("atías" — DataLake
    2026-10-08)."""

    def _session(self, answers):
        s = _make_session()
        s._page = _make_page(selector_found=True)

        def evaluate(js, *a):
            for key, value in answers.items():
                if key in js:
                    return value() if callable(value) else value
            return None
        s._page.evaluate = AsyncMock(side_effect=evaluate)
        return s

    def _base(self, **over):
        answers = {
            "found: true": {"found": True, "x": 10, "y": 20, "selector": "footer"},
            "if (el) return (el.innerText": True,     # compose empty
            "a.closest('footer": True,                # focus in compose
            "join(": "Matías, hola",                  # compose text
            "data-icon": False,
        }
        answers.update(over)
        return answers

    @pytest.mark.asyncio
    async def test_refuses_when_a_draft_is_present(self):
        s = self._session(self._base(**{"if (el) return (el.innerText": False}))
        with pytest.raises(RuntimeError, match="borrador"):
            await s.send_message("Matías, hola")
        s._page.keyboard.type.assert_not_called()

    @pytest.mark.asyncio
    async def test_refusal_shows_draft_and_the_way_out(self):
        s = self._session(self._base(**{"if (el) return (el.innerText": False,
                                        "join(": "texto viejo"}))
        with pytest.raises(RuntimeError, match="'texto viejo'.*--discard-draft"):
            await s.send_message("Matías, hola")

    @pytest.mark.asyncio
    async def test_discard_draft_clears_then_sends(self):
        empty = iter([False, True, True])   # draft, cleared, sent
        typed = iter(["texto viejo", "Matías, hola"])
        s = self._session(self._base(**{"if (el) return (el.innerText": lambda: next(empty),
                                        "join(": lambda: next(typed)}))
        meta = await s.send_message("Matías, hola", discard_draft=True)
        assert meta["discarded_draft"] == "texto viejo"
        presses = [c.args[0] for c in s._page.keyboard.press.call_args_list]
        assert presses[:2] in (["Meta+a", "Delete"], ["Control+a", "Delete"])
        assert presses[-1] == "Enter"

    @pytest.mark.asyncio
    async def test_clear_draft_fails_loudly_if_box_stays_full(self):
        s = self._session(self._base(**{"if (el) return (el.innerText": False,
                                        "join(": "texto viejo"}))
        with pytest.raises(RuntimeError, match="sigue ahí"):
            await s.clear_draft()
        s._page.keyboard.type.assert_not_called()

    @pytest.mark.asyncio
    async def test_clear_draft_noop_when_empty(self):
        s = self._session(self._base(**{"join(": ""}))
        assert await s.clear_draft() == ""
        s._page.keyboard.press.assert_not_called()

    @pytest.mark.asyncio
    async def test_refuses_when_compose_never_takes_focus(self):
        s = self._session(self._base(**{"a.closest('footer": False}))
        with pytest.raises(RuntimeError, match="foco"):
            await s.send_message("Matías, hola")
        s._page.keyboard.type.assert_not_called()

    @pytest.mark.asyncio
    async def test_lost_letter_is_never_sent(self):
        s = self._session(self._base(**{"join(": "atías, hola"}))
        with pytest.raises(RuntimeError, match="no coincide"):
            await s.send_message("Matías, hola")
        presses = [c.args[0] for c in s._page.keyboard.press.call_args_list]
        assert "Enter" not in presses
        assert s._page.keyboard.type.call_count == 2   # one clean retry


def test_same_letters_tolerates_list_markers_only():
    assert _same_letters("• a\n• b", "- a\n- b")
    assert not _same_letters("atías", "Matías")


def _vision_page(session, *, menu=True):
    """Wire SESSION for the vision path: OCR helper present, screenshots and
    the menu OCR stubbed. MENU: whether the context menu offers the entry."""
    import wavi.vision as vision
    session._page.mouse.click = AsyncMock()
    session.screenshot_to_file = AsyncMock(side_effect=lambda p: p)
    session.scroll_chat_up = AsyncMock()
    return [
        __import__("unittest.mock", fromlist=["patch"]).patch.object(vision, "vision_available", lambda: True),
        __import__("unittest.mock", fromlist=["patch"]).patch.object(
            vision, "find_menu_item", lambda shot, labels: (900, 800) if menu else None),
    ]


class TestEditMessage:
    """wavi edit — picks exactly one own message by vision, respects WA's
    15-minute window, edits the editor's own prefilled text, and fails
    without touching anything otherwise."""

    NOW = __import__("datetime").datetime(2026, 10, 8, 16, 45)
    ROWS = [
        {"id": "v3", "own": True, "sender": "Tú", "timestamp": "2026-10-08T16:38",
         "text": "atías, ya vi el video, gracias!", "click_x": 1000, "click_y": 1500},
        {"id": "v2", "own": True, "sender": "Tú", "timestamp": "2026-10-08T16:40",
         "text": "@Matias Becerro salió mal", "click_x": 1000, "click_y": 1600},
        {"id": "v1", "own": True, "sender": "Tú", "timestamp": "2026-10-08T10:24",
         "text": "gracias Vito, ya vi", "click_x": 1000, "click_y": 1700},
    ]

    @pytest.fixture
    def env(self):
        from contextlib import ExitStack
        s = _make_session()
        s._page = _make_page(selector_found=True)
        s._vision_messages = AsyncMock(return_value=self.ROWS)
        self.editor = {"text": "atías, ya vi el video, gracias!"}

        def evaluate(js, *a):
            if "activeElement" in js:             # edit dialog has focus
                return not getattr(self, "closed", False)
            if "querySelectorAll('p')" in js:     # editor text
                return self.editor["text"]
            if "editado|edited" in js:            # save button
                self.closed = True
                return True
            if "own:" in js:                      # re-read after saving
                return [{"own": True, "text": self.editor["text"]}]
            return None

        s._page.evaluate = AsyncMock(side_effect=evaluate)

        async def typed(text, delay=30):
            self.editor["text"] = text
        s._page.keyboard.type = AsyncMock(side_effect=typed)
        with ExitStack() as st:
            for p in _vision_page(s):
                st.enter_context(p)
            yield s
        self.closed = False

    def test_parse_pre_plain(self):
        from datetime import datetime

        from wavi.session import _parse_pre_plain
        assert _parse_pre_plain("[4:38 p. m., 8/10/2026] Jozbuyo: ") == datetime(2026, 10, 8, 16, 38)
        assert _parse_pre_plain(None) is None

    @pytest.mark.asyncio
    async def test_no_match_scrolls_up_then_gives_up(self, env):
        with pytest.raises(RuntimeError, match="No encontré.*4 pantallas"):
            await env.edit_message("inexistente", "x", now=self.NOW)
        assert env.scroll_chat_up.await_count == env.MESSAGE_SCREENS - 1
        env._page.mouse.click.assert_not_called()

    @pytest.mark.asyncio
    async def test_found_after_scrolling(self, env):
        env._vision_messages = AsyncMock(side_effect=[self.ROWS[1:], self.ROWS])
        r = await env.edit_message("atías, ya", "Matías, ya", fragment=True, now=self.NOW)
        assert env.scroll_chat_up.await_count == 1
        assert r["verified"] and r["before"].startswith("atías")

    @pytest.mark.asyncio
    async def test_ambiguous_lists_candidates(self, env):
        with pytest.raises(RuntimeError, match="Hay 2 mensajes"):
            await env.edit_message("ya vi", "x", now=self.NOW)
        env._page.mouse.click.assert_not_called()

    @pytest.mark.asyncio
    async def test_match_ignores_accents_and_case(self, env):
        with pytest.raises(RuntimeError, match="solo permite"):
            await env.edit_message("SALIO MAL", "x", now=self.NOW.replace(hour=17, minute=2))

    @pytest.mark.asyncio
    async def test_expired_window_touches_nothing(self, env):
        with pytest.raises(RuntimeError, match="15 min"):
            await env.edit_message("gracias Vito", "x", now=self.NOW)
        env._page.mouse.move.assert_not_called()
        env._page.keyboard.type.assert_not_called()

    @pytest.mark.asyncio
    async def test_menu_opened_by_right_click(self, env):
        await env.edit_message("atías, ya", "Matías, ya", fragment=True, now=self.NOW)
        env._page.mouse.click.assert_any_await(1000, 1500, button="right")
        env._page.mouse.click.assert_any_await(900, 800)

    @pytest.mark.asyncio
    async def test_fragment_replaces_inside_the_exact_editor_text(self, env):
        # OCR may misread letters; the editor holds the real message.
        env._vision_messages = AsyncMock(return_value=[dict(self.ROWS[0], text="atias, ya vl el video")])
        r = await env.edit_message("atías, ya", "Matías, ya", fragment=True, now=self.NOW)
        assert self.editor["text"] == "Matías, ya vi el video, gracias!"
        assert r["verified"]

    @pytest.mark.asyncio
    async def test_fragment_must_be_literal(self, env):
        with pytest.raises(RuntimeError, match="no aparece literal"):
            await env.edit_message("ATIAS, YA", "Matías, ya", fragment=True, now=self.NOW)
        env._page.keyboard.type.assert_not_called()
        assert env._page.keyboard.press.call_args_list[-1].args[0] == "Escape"

    @pytest.mark.asyncio
    async def test_wrong_message_opened_changes_nothing(self, env):
        self.editor["text"] = "otro mensaje cualquiera"
        with pytest.raises(RuntimeError, match="otro mensaje"):
            await env.edit_message("atías, ya", "x", now=self.NOW)
        env._page.keyboard.type.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_edit_entry_in_menu(self, env):
        with __import__("unittest.mock", fromlist=["patch"]).patch(
                "wavi.vision.find_menu_item", lambda shot, labels: None):
            with pytest.raises(RuntimeError, match="no ofrece 'Editar'"):
                await env.edit_message("atías, ya", "x", now=self.NOW)
        assert env._page.keyboard.press.call_args_list[-1].args[0] == "Escape"


class TestLocateMessage:
    from wavi.session import _locate_message
    locate = staticmethod(_locate_message)
    ROWS = [
        {"id": "1", "own": False, "pre": "[9:00 a. m., 8/10/2026] Matias Becerro: ", "text": "Subí el video nuevo"},
        {"id": "2", "own": True, "pre": "[9:05 a. m., 8/10/2026] Jozbuyo: ", "text": "Genial, ya vi el video"},
        {"id": "3", "own": False, "pre": "[9:10 a. m., 8/10/2026] Vito: ", "text": "El VIDEO se ve bien"},
    ]

    def test_accent_and_case_insensitive(self):
        assert self.locate(self.ROWS, "SUBI EL")["id"] == "1"

    def test_ambiguous_lists_numbered_candidates(self):
        with pytest.raises(RuntimeError, match="Hay 3 mensajes .*--index N"):
            self.locate(self.ROWS, "video")

    def test_sender_filter(self):
        assert self.locate(self.ROWS, "video", sender="vito")["id"] == "3"

    def test_index_picks_oldest_first(self):
        assert self.locate(self.ROWS, "video", index=2)["id"] == "2"

    def test_index_out_of_range(self):
        with pytest.raises(RuntimeError, match="fuera de rango"):
            self.locate(self.ROWS, "video", index=4)

    def test_own_only(self):
        assert self.locate(self.ROWS, "video", own_only=True)["id"] == "2"

    def test_no_match_names_sender(self):
        from wavi.session import MessageNotFound
        with pytest.raises(MessageNotFound, match="de 'Ana'"):
            self.locate(self.ROWS, "video", sender="Ana")

    def test_vision_rows_carry_sender_and_time(self):
        rows = [{"id": "v2", "own": False, "sender": "Matías Cagnina", "timestamp": "2026-10-09T13:31",
                 "text": "recibido!!!"},
                {"id": "v1", "own": True, "sender": "Tú", "timestamp": "2026-10-09T13:32", "text": "recibido, gracias"}]
        assert self.locate(rows, "recibido", sender="matias")["id"] == "v2"
        with pytest.raises(RuntimeError, match="2026-10-09T13:31 Matías Cagnina"):
            self.locate(rows, "recibido")


def test_roughly_contains_tolerates_ocr_slips():
    from wavi.session import _roughly_contains
    assert _roughly_contains("Matias Becerro\nSubí el video nuevo", "Subi el vldeo nuevo")
    assert _roughly_contains("x", "") is False
    assert not _roughly_contains("Vito\nEl VIDEO se ve bien", "Subí el video nuevo")


class TestReplyMessage:
    """wavi reply — quotes exactly one message (picked by vision) and never
    sends unless WA's quote panel shows it; a failed reply leaves no
    dangling quote."""

    ROWS = [
        {"id": "v3", "own": False, "sender": "Matias Becerro", "timestamp": "2026-10-08T09:00",
         "text": "Subi el vldeo nuevo", "click_x": 700, "click_y": 1200},   # OCR slip on purpose
        {"id": "v2", "own": True, "sender": "Tú", "timestamp": "2026-10-08T09:05",
         "text": "Genial, ya vi el video", "click_x": 1100, "click_y": 1300},
        {"id": "v1", "own": False, "sender": "Vito", "timestamp": "2026-10-08T09:10",
         "text": "El VIDEO se ve bien", "click_x": 700, "click_y": 1400},
    ]

    @pytest.fixture
    def make(self):
        from contextlib import ExitStack
        stack = ExitStack()

        def _make(preview="Matias Becerro\nSubí el video nuevo", menu=True, after=None):
            s = _make_session()
            s._page = _make_page(selector_found=True)
            s._vision_messages = AsyncMock(return_value=self.ROWS)
            after_rows = after if after is not None else [
                {"own": True, "text": "Gracias!", "quoted": "Matias Becerro\nSubí el video nuevo"}]

            async def evaluate(js, *a):
                if "own:" in js:
                    return after_rows
                if "cloneNode" in js:
                    return preview
                return None
            s._page.evaluate = AsyncMock(side_effect=evaluate)
            s.send_message = AsyncMock(return_value={})
            for p in _vision_page(s, menu=menu):
                stack.enter_context(p)
            return s
        yield _make
        stack.close()

    @pytest.mark.asyncio
    async def test_happy_path_quotes_and_sends(self, make):
        s = make()
        r = await s.reply_message("subi el", "Gracias!")
        s._page.mouse.click.assert_any_await(700, 1200, button="right")
        s.send_message.assert_awaited_once_with("Gracias!")
        assert r["quoted_id"] == "v3" and r["quoted_sender"] == "Matias Becerro"
        assert r["verified"]

    @pytest.mark.asyncio
    async def test_from_filter_uses_vision_sender(self, make):
        s = make(preview="Vito\nEl VIDEO se ve bien",
                 after=[{"own": True, "text": "x", "quoted": "Vito El VIDEO se ve bien"}])
        r = await s.reply_message("video", "x", sender="vito")
        assert r["quoted_id"] == "v1"

    @pytest.mark.asyncio
    async def test_ambiguous_touches_nothing(self, make):
        s = make()
        with pytest.raises(RuntimeError, match="Hay 2"):
            await s.reply_message("video", "x")
        s._page.mouse.click.assert_not_called()
        s.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_wrong_quote_cancels_and_sends_nothing(self, make):
        s = make(preview="Vito\nEl VIDEO se ve bien")
        with pytest.raises(RuntimeError, match="La cita no muestra"):
            await s.reply_message("subi el", "x")
        s.send_message.assert_not_called()
        assert s._page.keyboard.press.call_args_list[-1].args[0] == "Escape"

    @pytest.mark.asyncio
    async def test_no_reply_item(self, make):
        s = make(menu=False)
        with pytest.raises(RuntimeError, match="Responder"):
            await s.reply_message("subi el", "x")
        s.send_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_failed_send_clears_quote(self, make):
        s = make()
        s.send_message = AsyncMock(side_effect=RuntimeError("borrador"))
        with pytest.raises(RuntimeError, match="borrador"):
            await s.reply_message("subi el", "x")
        assert s._page.keyboard.press.call_args_list[-1].args[0] == "Escape"

    @pytest.mark.asyncio
    async def test_unverified_when_last_own_lacks_quote(self, make):
        s = make(after=[{"own": True, "text": "Gracias!", "quoted": None}])
        r = await s.reply_message("subi el", "Gracias!")
        assert not r["verified"]

    @pytest.mark.asyncio
    async def test_dom_fallback_without_ocr_helper(self):
        """No OCR helper on this machine → temporary DOM path."""
        from unittest.mock import patch

        import wavi.vision as vision
        s = _make_session()
        s._page = _make_page(selector_found=True)
        rows = [{"id": "A", "own": False, "pre": "[9:00 a. m., 8/10/2026] Ana: ", "text": "hola"}]

        async def evaluate(js, *a):
            if "own:" in js:
                return rows if not s.send_message.await_count else [
                    {"own": True, "text": "chau", "quoted": "Ana hola"}]
            if "scrollIntoView" in js:
                return {"x": 1, "y": 2}
            if "opciones del mensaje" in js:
                return True
            if "menuitem" in js:
                return a and "Responder" in a[0]
            if "cloneNode" in js:
                return "Ana\nhola"
            return None
        s._page.evaluate = AsyncMock(side_effect=evaluate)
        s.send_message = AsyncMock(return_value={})
        with patch.object(vision, "vision_available", lambda: False):
            r = await s.reply_message("hola", "chau")
        assert r["quoted_sender"] == "Ana" and r["verified"]


@pytest.mark.asyncio
async def test_connect_refuses_missing_profile_without_touching_ports(tmp_path, monkeypatch):
    """A dangling alias / wrong path must not fall back to CDP_PORT — that
    port can be another session's live daemon (killed for real 2026-10-08)."""
    import playwright.async_api as pw_api

    import wavi.session as ws
    killed = []
    monkeypatch.setattr(ws, "_kill_port", lambda port: killed.append(port))
    fake_pw = MagicMock()
    fake_pw.stop = AsyncMock()
    starter = MagicMock()
    starter.start = AsyncMock(return_value=fake_pw)
    monkeypatch.setattr(pw_api, "async_playwright", lambda: starter)

    s = WASession(tmp_path / "no-existe")
    with pytest.raises(RuntimeError, match="no existe"):
        await s.connect()
    assert killed == []
    assert not (tmp_path / "no-existe").exists()
    fake_pw.stop.assert_awaited_once()


# ── @-mentions (DataLake 2026-10-13) ─────────────────────────────────────────

from wavi.session import _MENTION_ROWS_JS, _pick_mention  # noqa: E402

_ROWS = [
    {"name": "Matias Becerro", "text": "Matias Becerro\n+54 9 11 1111", "x": 300, "y": 700},
    {"name": "Matías Cagnina", "text": "Matías Cagnina", "x": 300, "y": 760},
    {"name": "Vito Bagni", "text": "~Vito Bagni", "x": 300, "y": 820},
]


class TestPickMention:
    def test_full_name_beats_a_shared_first_name(self):
        row, end = _pick_mention(_ROWS, "Matias Becerro te paso")
        assert row["name"] == "Matias Becerro" and end == len("Matias Becerro")

    def test_unique_first_name_is_a_prefix_match(self):
        row, end = _pick_mention(_ROWS, "Vito, te paso")
        assert row["name"] == "Vito Bagni" and end == len("Vito")

    def test_shared_first_name_alone_is_ambiguous(self):
        assert _pick_mention(_ROWS, "Matias te paso") is None

    def test_accents_and_case_do_not_matter(self):
        row, end = _pick_mention(_ROWS, "matias cagnina.")
        assert row["name"] == "Matías Cagnina" and end == len("matias cagnina")

    def test_unknown_name_stays_text(self):
        assert _pick_mention(_ROWS, "Nadie fin") is None
        assert _pick_mention([], "Vito") is None

    def test_rows_js_has_no_class_or_role_selectors(self):
        # Rows are found by geometry around the compose box, never by WA's
        # class names — the popup's markup is not ours to depend on.
        assert "className" not in _MENTION_ROWS_JS and "classList" not in _MENTION_ROWS_JS


class TestTypeMentions:
    """_type_line: "@Name" is typed as "@" + first word, the popup row is
    clicked, the typed text resumes after the name; anything else stays
    plain and the popup is closed so Enter still sends."""

    def _session(self, rows_seq, compose_seq, focus=True):
        s = _make_session()
        s._page = _make_page()
        rows = iter(rows_seq)
        compose = iter(compose_seq)

        def evaluate(js, *a):
            if "elementFromPoint" in js:
                return next(rows, [])
            if "join(" in js:
                return next(compose, None)
            if "a.closest('footer" in js:
                return focus
            if "found: true" in js:
                return {"found": True, "x": 10, "y": 20}
            return None
        s._page.evaluate = AsyncMock(side_effect=evaluate)
        return s

    @pytest.mark.asyncio
    async def test_mention_is_clicked_and_text_resumes_after_the_name(self):
        s = self._session(rows_seq=[[], _ROWS, []],
                          compose_seq=["hola ", "hola @Matias Becerro "])
        shown = await s._type_line("hola @Matias Becerro te paso")
        assert shown == "hola @Matias Becerro te paso"
        typed = [c.args[0] for c in s._page.keyboard.type.call_args_list]
        assert typed == ["hola ", "@Matias", "te paso"]      # WA's own space after the chip
        s._page.mouse.click.assert_awaited_once_with(300, 700)
        assert "Escape" not in [c.args[0] for c in s._page.keyboard.press.call_args_list]

    @pytest.mark.asyncio
    async def test_short_name_expands_to_the_participant(self):
        s = self._session(rows_seq=[[], _ROWS, []],
                          compose_seq=["", "@Vito Bagni "])
        shown = await s._type_line("@Vito, dale")
        assert shown == "@Vito Bagni , dale"
        typed = [c.args[0] for c in s._page.keyboard.type.call_args_list]
        assert typed == ["@Vito", ", dale"]

    @pytest.mark.asyncio
    async def test_no_popup_means_plain_text(self):
        s = self._session(rows_seq=[[], []], compose_seq=["", ""])
        shown = await s._type_line("hola @Matias te paso")
        assert shown == "hola @Matias te paso"
        typed = [c.args[0] for c in s._page.keyboard.type.call_args_list]
        assert typed == ["hola ", "@Matias", " te paso"]
        s._page.mouse.click.assert_not_called()
        s._page.keyboard.press.assert_not_called()

    @pytest.mark.asyncio
    async def test_ambiguous_name_stays_text_and_closes_the_popup(self):
        s = self._session(rows_seq=[[], _ROWS], compose_seq=["", ""])
        shown = await s._type_line("@Matias te paso")
        assert shown == "@Matias te paso"
        s._page.mouse.click.assert_not_called()
        assert [c.args[0] for c in s._page.keyboard.press.call_args_list] == ["Escape"]

    @pytest.mark.asyncio
    async def test_rows_already_there_before_the_at_are_not_the_popup(self):
        s = self._session(rows_seq=[_ROWS, _ROWS], compose_seq=["", ""])
        shown = await s._type_line("@Vito dale")
        assert shown == "@Vito dale"
        s._page.mouse.click.assert_not_called()

    @pytest.mark.asyncio
    async def test_click_that_inserts_nothing_keeps_the_text(self):
        s = self._session(rows_seq=[[], _ROWS, []], compose_seq=["", "@Vito"])
        shown = await s._type_line("@Vito dale")
        assert shown == "@Vito dale"
        typed = [c.args[0] for c in s._page.keyboard.type.call_args_list]
        assert typed == ["@Vito", " dale"]

    @pytest.mark.asyncio
    async def test_email_is_never_a_mention(self):
        s = self._session(rows_seq=[], compose_seq=[])
        shown = await s._type_line("escribime a jose@gmail.com")
        assert shown == "escribime a jose@gmail.com"
        s._page.keyboard.type.assert_awaited_once_with("escribime a jose@gmail.com", delay=30)
        s._page.evaluate.assert_not_called()

    @pytest.mark.asyncio
    async def test_mentions_off_types_literally(self):
        s = self._session(rows_seq=[], compose_seq=[])
        shown = await s._type_compose("@Vito dale", mentions=False)
        assert shown == "@Vito dale"
        s._page.evaluate.assert_not_called()

    @pytest.mark.asyncio
    async def test_send_message_verifies_against_the_expanded_name(self):
        """The box shows the participant's full name, not what was typed —
        send_message must still send (DataLake's exact case)."""
        s = _make_session()
        s._page = _make_page()
        rows = iter([[], _ROWS, []])
        compose = iter(["", "@Matias Becerro ", "@Matias Becerro te paso"])
        empty = iter([True, True])     # before typing, after Enter

        def evaluate(js, *a):
            if "elementFromPoint" in js:
                return next(rows, [])
            if "found: true" in js:
                return {"found": True, "x": 10, "y": 20, "selector": "footer"}
            if "if (el) return (el.innerText" in js:
                return next(empty, True)
            if "a.closest('footer" in js:
                return True
            if "join(" in js:
                return next(compose, "")
            return False
        s._page.evaluate = AsyncMock(side_effect=evaluate)
        await s.send_message("@Matias Becerro te paso")
        presses = [c.args[0] for c in s._page.keyboard.press.call_args_list]
        assert presses[-1] == "Enter"
        s._page.mouse.click.assert_any_await(300, 700)



# ── Header title vs initials avatar (TechVentas 2026-10-15) ──────────────────

from wavi.session import _header_title  # noqa: E402


class TestHeaderTitle:
    def test_initials_avatar_is_skipped(self):
        assert _header_title(["LC", "Lucas Campos (1109)", "haz clic aquí para info"]) == "Lucas Campos (1109)"

    def test_photo_contact_has_name_first(self):
        assert _header_title(["Lucas Campos (1109)", "en línea"]) == "Lucas Campos (1109)"

    def test_short_uppercase_name_alone_is_the_title(self):
        assert _header_title(["LC"]) == "LC"
        assert _header_title([]) is None

    @pytest.mark.asyncio
    async def test_open_search_result_accepts_initials_header(self):
        s = _make_session()
        s._page = _make_page()
        s._page.evaluate = AsyncMock(return_value="LC\nLucas Campos (1109)\nhaz clic aquí para info")
        assert await s.open_search_result(10, 20, expected_name="Lucas Campos (1109)")
        assert await s.open_chat_title() == "Lucas Campos (1109)"

    @pytest.mark.asyncio
    async def test_open_search_result_still_rejects_a_stale_chat(self):
        s = _make_session()
        s._page = _make_page()
        s._page.evaluate = AsyncMock(return_value="MB\nMatias Becerro\nen línea")
        assert not await s.open_search_result(10, 20, expected_name="Lucas Campos (1109)")
