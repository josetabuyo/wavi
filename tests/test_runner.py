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
