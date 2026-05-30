"""
runner.py — High-level orchestrator: session + vision + audio capture.

Combines WASession (Playwright) with vision.analyze() for message
classification, then uses DOM queries to locate exact play button positions
(bypasses element_detector bbox errors for "me" bubbles).
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from typing import Optional

from wavi.session import WASession
from wavi.vision import Bubble, analyze

# ── JS helpers ────────────────────────────────────────────────────────────────

_FIND_PLAY_BTNS_JS = """
() => {
    const labels = ['Reproducir mensaje de voz', 'Play voice message'];
    return [...document.querySelectorAll('button[aria-label]')]
        .filter(b => {
            const l = b.getAttribute('aria-label') || '';
            return labels.some(lbl => l.toLowerCase().includes(lbl.toLowerCase()));
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

    async def get_bubbles(self, assets_dir: Path | None = None, save_debug: bool = False) -> list[Bubble]:
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
        return analyze(shot_path, assets_dir=assets_dir, save_debug=save_debug)

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
        tolerance_px: int = 80,
        dpr: float = 1.0,
    ) -> dict | None:
        """
        Match an audio bubble (crop-panel physical pixels) to the nearest DOM play
        button (CSS viewport pixels) using y-coordinate proximity.

        Conversion: physical_crop_y → CSS_viewport_y = (physical_crop_y + HEADER_PX) / dpr
        """
        bvy = (bubble.bbox["y"] + bubble.bbox["h"] // 2 + WASession.HEADER_Y) / dpr

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
        blob_timeout_ms: int = 30_000,
        save_debug: bool = False,
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
        bubbles = await self.get_bubbles(assets_dir=assets_dir, save_debug=save_debug)
        audio_bubbles = [b for b in bubbles if b.msg_type == "audio"]

        if not audio_bubbles:
            return []

        # Install blob URL monitor NOW (WA is fully loaded — safe to hook MediaElement)
        await self.session.install_blob_monitor()
        await self.session.reset_blobs()

        dpr = await self.session.get_dpr()
        play_buttons = await self.find_play_buttons()
        print(
            f"[wavi] audio bubbles={len(audio_bubbles)}  play_buttons_found={len(play_buttons)}"
            f"  dpr={dpr}",
            file=sys.stderr,
        )
        results = []
        # bubble_id → crop-panel physical (cx, cy) of the actual play button
        resolved_positions: dict[int, tuple[int, int]] = {}

        for bubble in audio_bubbles:
            btn = self._match_bubble_to_button(bubble, play_buttons, dpr=dpr)
            if btn is None:
                results.append({
                    "bubble": bubble,
                    "blob_url": None,
                    "data": None,
                    "path": None,
                    "error": "no_play_button_matched",
                })
                continue

            # Record play button in physical crop-panel coords for debug image
            # btn coords are CSS pixels → convert to physical, then subtract panel origin
            resolved_positions[bubble.id] = (
                int(btn["vx"] * dpr) - int(WASession.SIDEBAR_X * dpr),
                int(btn["vy"] * dpr) - WASession.HEADER_Y,
            )

            # Click in viewport coords directly (bypass crop-panel offset)
            print(f"[wavi]   click bubble#{bubble.id} → vp({btn['vx']},{btn['vy']})", file=sys.stderr)
            await self.session._page.mouse.click(btn["vx"], btn["vy"])

            # Wait for blob: poll every 500ms up to blob_timeout_ms
            # (long audios need WA to decrypt from server — can take several seconds)
            blobs: list[dict] = []
            waited = 0
            poll_ms = 500
            while waited < blob_timeout_ms:
                await self.session._page.wait_for_timeout(poll_ms)
                waited += poll_ms
                blobs = await self.session.drain_blobs()
                if blobs:
                    break
                if waited >= wait_ms and not blobs:
                    # Minimum wait elapsed — keep polling silently
                    pass

            print(f"[wavi]   blobs after {waited}ms: {len(blobs)}", file=sys.stderr)
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
    Saves screenshot.png, bubbles.json + debug images by default.
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
    bubbles = await runner.get_bubbles(assets_dir=assets_dir, save_debug=True)
    audios  = await runner.capture_audio_bubbles(assets_dir=assets_dir, save_debug=True)
    await runner.close()

    return {"bubbles": bubbles, "audios": audios}
