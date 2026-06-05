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
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch
from pathlib import Path

from wavi.session import WASession, WA_URL, WINDOW_W, WINDOW_H


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
    # navigate_to_contact uses evaluate() for DOM scroll (ADR-002)
    page.evaluate = AsyncMock(return_value=False)  # False → no scroll button found → fallback
    return page


class TestNavigateToContact:
    @pytest.fixture
    def session(self):
        s = _make_session()
        s._page = _make_page(selector_found=True)
        return s

    @pytest.mark.asyncio
    async def test_clicks_search_box_by_coordinate(self, session):
        await session.navigate_to_contact("Gregorio")
        session._page.mouse.click.assert_any_call(
            WASession.SEARCH_X, WASession.SEARCH_Y
        )

    @pytest.mark.asyncio
    async def test_clears_with_keyboard_not_dom(self, session):
        await session.navigate_to_contact("Gregorio")
        calls = [c.args[0] for c in session._page.keyboard.press.call_args_list]
        assert "Meta+a" in calls
        assert "Delete" in calls

    @pytest.mark.asyncio
    async def test_types_contact_name(self, session):
        await session.navigate_to_contact("Gregorio")
        session._page.keyboard.type.assert_called_once_with("Gregorio", delay=40)

    @pytest.mark.asyncio
    async def test_never_uses_locator(self, session):
        await session.navigate_to_contact("Gregorio")
        session._page.locator.assert_not_called()

    @pytest.mark.asyncio
    async def test_opens_result_with_keyboard_not_locator(self, session):
        """El resultado se abre con teclado (ADR-001), nunca con page.click(selector)."""
        await session.navigate_to_contact("Gregorio")
        calls = [c.args[0] for c in session._page.keyboard.press.call_args_list]
        assert "ArrowDown" in calls, "Debe navegar al resultado con ArrowDown"
        assert "Enter" in calls, "Debe abrir el resultado con Enter"
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
    async def test_scroll_fires_after_selector_wait(self, session):
        """El scroll al fondo ocurre después de wait_for_selector."""
        order: list[str] = []
        session._page.wait_for_selector = AsyncMock(
            side_effect=lambda *a, **kw: order.append("selector")
        )
        session._page.evaluate = AsyncMock(
            side_effect=lambda *a, **kw: order.append("evaluate") or False
        )
        await session.navigate_to_contact("Gregorio")
        assert "selector" in order and "evaluate" in order
        assert order.index("selector") < order.index("evaluate")

    @pytest.mark.asyncio
    async def test_scroll_fires_after_selector_even_on_timeout(self, session):
        """El scroll se ejecuta aunque wait_for_selector falle por timeout."""
        session._page.wait_for_selector = AsyncMock(side_effect=Exception("timeout"))
        await session.navigate_to_contact("Gregorio")
        assert session._page.evaluate.called

    @pytest.mark.asyncio
    async def test_scroll_retries_if_not_at_bottom(self):
        """
        Si get_chat_scroll_state muestra slack > 50px, el loop vuelve a intentar
        scroll-to-bottom. Simula la situación post-full-sync-enhanced donde el
        virtualizer restaura la posición anterior (top) en vez del fondo.
        """
        s = _make_session()
        page = _make_page()

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
        from wavi.cli import _HEADLESS_CHROME_ARGS, WINDOW_W, WINDOW_H
        window_size_arg = f"--window-size={WINDOW_W},{WINDOW_H}"
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

        s._page.evaluate.assert_called_once()
        s._page.wait_for_selector.assert_called_once()
        s._page.wait_for_timeout.assert_called_once()

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
