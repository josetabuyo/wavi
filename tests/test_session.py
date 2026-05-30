"""
Tests de WASession — verifican comportamiento de navegación sin browser real.

Los tests mockean self._page para confirmar que navigate_to_contact:
  - usa mouse.click por coordenadas (no locator ni CSS)
  - usa teclado para limpiar (no .clear())
  - no llama a self._page.locator() en ningún momento

También cubren _setup_page: set_viewport_size debe llamarse ANTES de goto(WA_URL)
solo cuando headless=True y la página aún no está en WA.
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
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()
    page.keyboard.type = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.wait_for_selector = AsyncMock() if selector_found else AsyncMock(side_effect=Exception("timeout"))
    page.locator = MagicMock()  # no debe llamarse — lo detectamos en los tests
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
        session._page.locator.assert_not_called()  # doble check: sin locator


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
