"""
Tests de WASession — verifican comportamiento de navegación sin browser real.

Los tests mockean self._page para confirmar que navigate_to_contact:
  - usa mouse.click por coordenadas (no locator ni CSS)
  - usa teclado para limpiar (no .clear())
  - no llama a self._page.locator() en ningún momento
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch
from pathlib import Path

from wavi.session import WASession


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
        assert "Control+a" in calls
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
    async def test_click_first_result_by_coordinate(self, session):
        await session.navigate_to_contact("Gregorio")
        # Debe haber un click en FIRST_RESULT_X / FIRST_RESULT_Y
        calls = session._page.mouse.click.call_args_list
        result_click = any(
            c == call(WASession.FIRST_RESULT_X, WASession.FIRST_RESULT_Y)
            for c in calls
        )
        assert result_click, f"No se encontró click en coordenadas del primer resultado. Calls: {calls}"

    @pytest.mark.asyncio
    async def test_fallback_keyboard_when_selector_not_found(self):
        s = _make_session()
        s._page = _make_page(selector_found=False)
        await s.navigate_to_contact("ContactoInexistente")
        calls = [c.args[0] for c in s._page.keyboard.press.call_args_list]
        assert "ArrowDown" in calls
        assert "Enter" in calls

    @pytest.mark.asyncio
    async def test_first_result_coordinate_below_search_box(self):
        assert WASession.FIRST_RESULT_Y > WASession.SEARCH_Y, (
            "El primer resultado debe estar más abajo que el search box"
        )
        assert WASession.FIRST_RESULT_X == WASession.SEARCH_X, (
            "El primer resultado comparte la X con el search box"
        )
