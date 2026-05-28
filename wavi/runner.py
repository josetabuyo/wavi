"""
runner.py — High-level orchestrator: session + vision + audio capture.

Combines WASession (Playwright) with vision.analyze() for message
classification, then uses DOM queries to locate exact play button positions
(bypasses element_detector bbox errors for "me" bubbles).
"""
from __future__ import annotations

import asyncio
import tempfile
from pathlib import Path
from typing import Optional

from wavi.session import WASession
from wavi.vision import Bubble, analyze

# ── JS helpers ────────────────────────────────────────────────────────────────

_FIND_PLAY_BTNS_JS = """
() => {
    const labels = ['Reproducir mensaje de voz', 'Play voice message',
                    'voz', 'voice message'];
    return [...document.querySelectorAll('button[aria-label]')]
        .filter(b => {
            const l = b.getAttribute('aria-label') || '';
            return labels.some(lbl => l.includes(lbl));
        })
        .map(b => {
            const r = b.getBoundingClientRect();
            return { vx: Math.round(r.x + r.width / 2),
                     vy: Math.round(r.y + r.height / 2) };
        })
        .filter(r => r.vx > 0 && r.vy > 0);
}
"""


# ── WARunner ──────────────────────────────────────────────────────────────────

class WARunner:
    """
    High-level interface built on top of WASession.

    Usage::

        runner = WARunner("data/sessions/5491155612767")
        await runner.connect()
        await runner.open_chat("Luiz Fernando Pita")

        bubbles = await runner.get_bubbles()
        audios  = await runner.capture_audio_bubbles()
        await runner.close()
    """

    def __init__(self, profile_dir: str | Path, headless: bool = True):
        self.session = WASession(profile_dir, headless=headless)
        self._assets_dir: Optional[Path] = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def connect(self) -> str:
        """Connect to WA Web. Returns 'restored', 'qr_needed', or 'timeout'."""
        return await self.session.connect()

    async def wait_for_auth(self, timeout_s: int = 120) -> bool:
        return await self.session.wait_for_auth(timeout_s)

    async def close(self) -> None:
        await self.session.close()

    # ── Chat navigation ───────────────────────────────────────────────────────

    async def open_chat(self, contact: str) -> None:
        await self.session.navigate_to_contact(contact)

    # ── Vision pipeline ───────────────────────────────────────────────────────

    async def get_bubbles(self, assets_dir: Path | None = None) -> list[Bubble]:
        """
        Take a screenshot, run the full vision pipeline, return classified bubbles.
        Bubbles are sorted id=1 (newest) → N (oldest).
        """
        data = await self.session.screenshot()
        if assets_dir:
            Path(assets_dir).mkdir(parents=True, exist_ok=True)
            shot_path = Path(assets_dir) / "screenshot.png"
        else:
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
                shot_path = Path(f.name)
        shot_path.write_bytes(data)
        return analyze(shot_path, assets_dir=assets_dir)

    # ── DOM play-button lookup ────────────────────────────────────────────────

    async def find_play_buttons(self) -> list[dict]:
        """
        Return viewport-coordinate centers of all visible play buttons via DOM.
        Each entry: {"vx": int, "vy": int}
        """
        return await self.session.eval(_FIND_PLAY_BTNS_JS)

    def _match_bubble_to_button(
        self,
        bubble: Bubble,
        play_buttons: list[dict],
        tolerance_px: int = 60,
    ) -> dict | None:
        """
        Match an audio bubble (crop-panel coords) to the nearest DOM play button
        (viewport coords) using y-coordinate proximity.
        """
        # Convert bubble crop-panel y-center to viewport coords
        bvy = bubble.bbox["y"] + bubble.bbox["h"] // 2 + WASession.HEADER_Y

        best, best_dist = None, float("inf")
        for btn in play_buttons:
            dist = abs(btn["vy"] - bvy)
            if dist < best_dist:
                best_dist = dist
                best = btn
        if best_dist <= tolerance_px:
            return best
        return None

    # ── Audio capture ─────────────────────────────────────────────────────────

    async def capture_audio_bubbles(
        self,
        assets_dir: Path | None = None,
        wait_ms: int = 3000,
    ) -> list[dict]:
        """
        For every audio bubble visible on screen:
          1. Locate play button via DOM (hybrid approach)
          2. Click it
          3. Drain captured blob URLs
          4. Download raw bytes
          5. Optionally save .ogg to assets_dir

        Returns list of dicts:
          {"bubble": Bubble, "blob_url": str, "data": bytes, "path": Path|None}
        """
        bubbles = await self.get_bubbles(assets_dir=assets_dir)
        audio_bubbles = [b for b in bubbles if b.msg_type == "audio"]

        if not audio_bubbles:
            return []

        play_buttons = await self.find_play_buttons()
        results = []
        # bubble_id → crop-panel (cx, cy) of the actual play button
        resolved_positions: dict[int, tuple[int, int]] = {}

        for bubble in audio_bubbles:
            btn = self._match_bubble_to_button(bubble, play_buttons)
            if btn is None:
                results.append({
                    "bubble": bubble,
                    "blob_url": None,
                    "data": None,
                    "path": None,
                    "error": "no_play_button_matched",
                })
                continue

            # Record exact play button position in crop-panel coords for debug image
            resolved_positions[bubble.id] = (
                btn["vx"] - WASession.SIDEBAR_X,
                btn["vy"] - WASession.HEADER_Y,
            )

            # Click in viewport coords directly (bypass crop-panel offset)
            await self.session._page.mouse.click(btn["vx"], btn["vy"])
            await self.session._page.wait_for_timeout(wait_ms)

            blobs = await self.session.drain_blobs()
            if not blobs:
                results.append({
                    "bubble": bubble,
                    "blob_url": None,
                    "data": None,
                    "path": None,
                    "error": "no_blob_captured",
                })
                continue

            blob_url = blobs[-1]["url"]
            data = await self.session.fetch_blob(blob_url)

            out_path = None
            if assets_dir and data:
                assets_dir = Path(assets_dir)
                assets_dir.mkdir(parents=True, exist_ok=True)
                out_path = assets_dir / f"audio_{bubble.id}.ogg"
                out_path.write_bytes(data)

            results.append({
                "bubble": bubble,
                "blob_url": blob_url,
                "data": data,
                "path": out_path,
            })

        # Redraw debug image with exact play button positions now that we know them
        if assets_dir and resolved_positions:
            from PIL import Image as PILImage
            from wavi.vision import _save_debug_image
            assets_dir = Path(assets_dir)
            cropped = assets_dir / "screenshot_cropped.png"
            debug_out = assets_dir / "screenshot_debug.png"
            if cropped.exists() and debug_out.exists():
                img = PILImage.open(cropped)
                _save_debug_image(img, bubbles, debug_out, play_positions=resolved_positions)

        return results


# ── Convenience coroutine ─────────────────────────────────────────────────────

async def run_once(
    profile_dir: str | Path,
    contact: str,
    assets_dir: Path | None = None,
    headless: bool = True,
) -> dict:
    """
    One-shot: connect → open chat → get bubbles + capture audios → close.
    Returns {"bubbles": [...], "audios": [...]}.
    """
    runner = WARunner(profile_dir, headless=headless)
    status = await runner.connect()
    if status == "qr_needed":
        await runner.close()
        raise RuntimeError(
            "QR scan required — run 'wavi connect' first to authenticate."
        )
    if status == "timeout":
        await runner.close()
        raise RuntimeError("Connection timed out.")

    await runner.open_chat(contact)
    bubbles = await runner.get_bubbles(assets_dir=assets_dir)
    audios  = await runner.capture_audio_bubbles(assets_dir=assets_dir)
    await runner.close()

    return {"bubbles": bubbles, "audios": audios}
