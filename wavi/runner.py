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

from wavi.session import WASession, WINDOW_W, WINDOW_H
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

    # ── Full history scroll-capture ───────────────────────────────────────────

    async def capture_full_history(
        self,
        assets_dir: Path | None = None,
        scroll_css_px: int = 1800,
        settle_ms: int = 2500,
        backoff_css_px: int = 200,
        max_iterations: int = 300,
    ) -> list[Bubble]:
        """
        Scroll from bottom to top capturing all unique messages.

        Algorithm: on each step, the topmost visible bubble ("anchor") is located
        in the next screenshot by content. Everything above the anchor's y-position
        is new content (positional dedup). Content-key dedup is a secondary guard.

        Stops when: (a) scrollTop reaches 0, (b) scroll stalls 3× in a row, or
        (c) max_iterations is reached.

        Limitation: media bubbles (photos, videos) are not detected by the vision
        pipeline and will be absent from the result. Text, audio, and file messages
        are captured fully.
        """
        def bubble_key(b: Bubble) -> tuple:
            return (b.sender, b.msg_type, b.text[:80].strip(), b.timestamp)

        all_bubbles: list[Bubble] = []
        seen_keys: set = set()

        # navigate_to_contact already scrolled to bottom and settled the DOM.
        # Do NOT scroll again here — a second programmatic jump destabilizes
        # WA's virtualizer and causes the initial capture to miss messages.

        # Compute actual scroll step from the chat container's visible height.
        # Scroll ~85% of viewport per step → guarantees ≥15% overlap between captures.
        init_state = await self.session.get_chat_scroll_state()
        if init_state and scroll_css_px == 1800:  # only override the default, not a custom value
            scroll_css_px = max(300, int(init_state["clientHeight"] * 0.85))
            print(f"[wavi] clientHeight={init_state['clientHeight']} → scroll_step={scroll_css_px}px", file=sys.stderr)

        def _iter_dir(n: int) -> Optional[Path]:
            return Path(assets_dir) / f"iter_{n:03d}" if assets_dir else None

        # First capture in iter_000 with debug image
        bubbles = await self.get_bubbles(assets_dir=_iter_dir(0), save_debug=True)
        for b in bubbles:
            k = bubble_key(b)
            if k not in seen_keys:
                seen_keys.add(k)
                all_bubbles.append(b)

        # Redraw iter_000 debug image with exact DOM play-button positions
        # (same as full-sync does via capture_audio_bubbles — no click/blob capture).
        iter0_dir = _iter_dir(0)
        if iter0_dir and bubbles:
            try:
                from PIL import Image as PILImage
                from wavi.vision import _save_debug_image
                dpr = await self.session.get_dpr()
                play_btns = await self.find_play_buttons()
                resolved: dict[int, tuple[int, int]] = {}
                for b in bubbles:
                    if b.msg_type in ("audio", "file"):
                        btn = self._match_bubble_to_button(b, play_btns, dpr=dpr)
                        if btn:
                            resolved[b.id] = (
                                int(btn["vx"] * dpr) - int(WASession.SIDEBAR_X * dpr),
                                int(btn["vy"] * dpr) - WASession.HEADER_Y,
                            )
                if resolved:
                    cropped = iter0_dir / "screenshot_cropped.png"
                    debug_out = iter0_dir / "screenshot_debug.png"
                    if cropped.exists():
                        img = PILImage.open(cropped)
                        _save_debug_image(img, bubbles, debug_out, play_positions=resolved)
            except Exception as e:
                print(f"[wavi] iter_000 debug redraw skipped: {e}", file=sys.stderr)

        stall_count = 0

        for iteration in range(max_iterations):
            # Read scrollTop BEFORE scrolling
            state = await self.session.get_chat_scroll_state()
            if state is None:
                print(f"[wavi] iter={iteration+1}: scroll container not found — stopping", file=sys.stderr)
                break

            scroll_top_before = state["scrollTop"]

            if scroll_top_before < 20:
                print(f"[wavi] iter={iteration+1}: at top (scrollTop={scroll_top_before:.0f})", file=sys.stderr)
                break

            # Anchor = topmost visible = oldest = bubble with max id.
            # If current view is all-media (bubbles empty), skip anchor — key dedup handles it.
            anchor_key = bubble_key(max(bubbles, key=lambda b: b.id)) if bubbles else None

            await self.session.scroll_chat_up(scroll_css_px)
            await self.session._page.wait_for_timeout(settle_ms)

            # Stall detection: if scrollTop didn't move, the scroll had no effect
            new_state = await self.session.get_chat_scroll_state()
            scroll_top_after = new_state["scrollTop"] if new_state else scroll_top_before
            if abs(scroll_top_after - scroll_top_before) < 10:
                stall_count += 1
                print(f"[wavi] iter={iteration+1}: scroll stall #{stall_count}", file=sys.stderr)
                if stall_count >= 3:
                    print("[wavi] 3 consecutive stalls — stopping", file=sys.stderr)
                    break
            else:
                stall_count = 0

            # Each iteration saves to its own subdirectory with a debug image
            iter_assets = _iter_dir(iteration + 1)
            new_bubbles = await self.get_bubbles(assets_dir=iter_assets, save_debug=True)
            # Note: new_bubbles may be empty if the current view is all-media — keep scrolling.

            # Find anchor: take bottommost match (max y) so duplicate messages
            # don't shift the split point upward.
            _matches = [b for b in new_bubbles if bubble_key(b) == anchor_key] if anchor_key else []
            anchor_in_new = max(_matches, key=lambda b: b.bbox["y"]) if _matches else None

            # Backoff only when scrollTop barely moved AND anchor is missing
            # (likely overshot). If scrollTop changed significantly, anchor absence
            # means OCR mismatch — don't backoff (that would undo the progress).
            scroll_delta = abs(scroll_top_before - scroll_top_after)
            if anchor_in_new is None and scroll_delta < backoff_css_px * 2:
                print(f"[wavi] iter={iteration+1}: anchor missing + minimal scroll, backing off...", file=sys.stderr)
                max_backoff = scroll_css_px // backoff_css_px
                for _ in range(max_backoff):
                    await self.session.scroll_chat_down(backoff_css_px)
                    await self.session._page.wait_for_timeout(600)
                    new_bubbles = await self.get_bubbles(assets_dir=iter_assets, save_debug=True)
                    _matches = [b for b in new_bubbles if bubble_key(b) == anchor_key]
                    anchor_in_new = max(_matches, key=lambda b: b.bbox["y"]) if _matches else None
                    if anchor_in_new is not None:
                        break
            elif anchor_in_new is None:
                print(f"[wavi] iter={iteration+1}: anchor OCR mismatch (scrollTop moved {scroll_delta:.0f}px) — key dedup", file=sys.stderr)

            # New content = positional (y < anchor_y) when anchor found; key-based otherwise
            if anchor_in_new is not None:
                candidates = [b for b in new_bubbles if b.bbox["y"] < anchor_in_new.bbox["y"]]
            else:
                candidates = new_bubbles

            new_count = 0
            new_items: list[Bubble] = []
            for b in candidates:
                k = bubble_key(b)
                if k not in seen_keys:
                    seen_keys.add(k)
                    new_items.append(b)
                    new_count += 1
            # Prepend older content so the list stays chronological (oldest first)
            all_bubbles = new_items + all_bubbles

            print(
                f"[wavi] iter={iteration+1}: +{new_count} new, total={len(all_bubbles)}, "
                f"scrollTop {scroll_top_before:.0f}→{scroll_top_after:.0f}",
                file=sys.stderr,
            )

            if new_count == 0 and scroll_top_after < 20:
                print("[wavi] No new bubbles and at top — done.", file=sys.stderr)
                break

            bubbles = new_bubbles

        # Re-assign globally sequential IDs: id=1=newest, id=N=oldest
        n = len(all_bubbles)
        for i, b in enumerate(all_bubbles):
            b.id = n - i

        # Save aggregated result to assets_dir
        if assets_dir:
            import json
            assets_dir = Path(assets_dir)
            assets_dir.mkdir(parents=True, exist_ok=True)
            out = assets_dir / "history_bubbles.json"
            out.write_text(
                json.dumps([b.as_dict() for b in all_bubbles], indent=2, ensure_ascii=False)
            )
            print(f"[wavi] Saved {len(all_bubbles)} bubbles → {out}", file=sys.stderr)

        return all_bubbles

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


# ── Convenience coroutines ────────────────────────────────────────────────────

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


async def run_enhanced(
    profile_dir: str | Path,
    contact: str,
    assets_dir: Path | None = None,
    headless: bool = True,
    max_iterations: int = 300,
) -> dict:
    """
    Extrapolation of run_once: same connect → open chat flow, then scrolls up
    to capture the full message history instead of just the visible screen.

    iter_000/ holds the same initial capture that run_once produces.
    iter_001/, iter_002/, … hold successive screens scrolling toward the past.
    history_bubbles.json aggregates all deduplicated messages.

    Returns {"bubbles": [...all unique bubbles...]}.
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
    bubbles = await runner.capture_full_history(assets_dir=assets_dir, max_iterations=max_iterations)
    await runner.close()

    return {"bubbles": bubbles}
