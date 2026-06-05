"""
runner.py — High-level orchestrator: session + vision + audio capture.

Combines WASession (Playwright) with vision.analyze() for message
classification, then uses DOM queries to locate exact play button positions
(bypasses element_detector bbox errors for "me" bubbles).
"""
from __future__ import annotations

import asyncio
import re as _re
import sys
import tempfile
from datetime import date as _Date, timedelta as _td
from pathlib import Path
from typing import Optional

from wavi.transcription import transcribe as _transcribe_audio
from wavi.vision import extract_day_pills as _extract_day_pills, _date_from_pill_text

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


# ── Date-pill parser ─────────────────────────────────────────────────────────



def _parse_pill_date(text: str, today: _Date) -> _Date | None:
    """Thin wrapper around vision._date_from_pill_text for use in runner."""
    return _date_from_pill_text(text, today)


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

    async def _redraw_debug_with_dom_positions(
        self,
        bubbles: list,
        assets_dir: "Path",
    ) -> None:
        """Redraw the debug image for assets_dir with exact DOM play-button positions."""
        try:
            from PIL import Image as PILImage
            from wavi.vision import _save_debug_image
            dpr = await self.session.get_dpr()
            play_btns = await self.find_play_buttons()
            resolved: dict = {}
            for b in bubbles:
                if b.msg_type in ("audio", "file"):
                    btn = self._match_bubble_to_button(b, play_btns, dpr=dpr)
                    if btn:
                        resolved[b.id] = (
                            int(btn["vx"] * dpr) - int(WASession.SIDEBAR_X * dpr),
                            int(btn["vy"] * dpr) - WASession.HEADER_Y,
                        )
            if resolved:
                assets_dir = Path(assets_dir)
                cropped = assets_dir / "screenshot_cropped.png"
                debug_out = assets_dir / "screenshot_debug.png"
                if cropped.exists():
                    img = PILImage.open(cropped)
                    _save_debug_image(img, bubbles, debug_out, play_positions=resolved)
        except Exception as e:
            import sys
            print(f"[wavi] debug redraw skipped: {e}", file=sys.stderr)

    async def _download_audio_for_bubbles(
        self,
        bubbles: list,
        assets_dir: "Path | None" = None,
        wait_ms: int = 3_000,
        blob_timeout_ms: int = 30_000,
        downloaded_ids: set | None = None,
    ) -> list[dict]:
        """
        Download audio blobs for audio bubbles currently visible on screen.
        Blob monitor must be installed before calling this.
        Resets the blob queue before starting so previous-iteration blobs don't leak.

        If downloaded_ids is provided, skips bubbles whose dom_id is already in the set
        (prevents duplicate downloads in overlapping scroll regions).
        """
        audio_bubbles = [b for b in bubbles if b.msg_type == "audio"]
        if not audio_bubbles:
            return []

        await self.session.reset_blobs()
        dpr = await self.session.get_dpr()
        play_buttons = await self.find_play_buttons()
        print(
            f"[wavi] _download_audio: {len(audio_bubbles)} audio bubbles, "
            f"{len(play_buttons)} play buttons",
            file=sys.stderr,
        )

        results = []
        for bubble in audio_bubbles:
            # Saltar si ya se descargó este audio (evita duplicados en overlaps)
            if downloaded_ids is not None and bubble.dom_id and bubble.dom_id in downloaded_ids:
                print(f"[wavi]   bubble#{bubble.id} dom_id ya descargado — skip", file=sys.stderr)
                continue
            btn = self._match_bubble_to_button(bubble, play_buttons, dpr=dpr)
            if btn is None:
                print(f"[wavi]   bubble#{bubble.id}: no play button matched", file=sys.stderr)
                results.append({
                    "bubble": bubble, "blob_url": None,
                    "data": None, "path": None, "error": "no_play_button_matched",
                })
                continue

            print(f"[wavi]   click bubble#{bubble.id} → vp({btn['vx']},{btn['vy']})", file=sys.stderr)
            await self.session._page.mouse.click(btn["vx"], btn["vy"])

            blobs: list[dict] = []
            waited = 0
            poll_ms = 500
            while waited < blob_timeout_ms:
                await self.session._page.wait_for_timeout(poll_ms)
                waited += poll_ms
                blobs = await self.session.drain_blobs()
                if blobs:
                    break

            print(f"[wavi]   blobs after {waited}ms: {len(blobs)}", file=sys.stderr)
            if not blobs:
                results.append({
                    "bubble": bubble, "blob_url": None,
                    "data": None, "path": None, "error": "no_blob_captured",
                })
                continue

            blob_url = blobs[-1]["url"]
            data = await self.session.fetch_blob(blob_url)

            out_path = None
            if assets_dir and data:
                Path(assets_dir).mkdir(parents=True, exist_ok=True)
                out_path = Path(assets_dir) / f"audio_{bubble.id}.ogg"
                out_path.write_bytes(data)
                # Store relative path so transcribe_history_audios can find it
                # regardless of screen_id vs global_id renaming at the end.
                bubble.audio_path = str(out_path)
                print(f"[wavi]   saved {len(data)} bytes → {out_path.name}", file=sys.stderr)

            # NOTE: transcription happens in a second pass (transcribe_history_audios)
            # after the browser is closed, to avoid blocking Playwright during scroll.

            # Registrar que descargamos este dom_id para evitar duplicados
            if downloaded_ids is not None and bubble.dom_id:
                downloaded_ids.add(bubble.dom_id)

            results.append({
                "bubble": bubble,
                "blob_url": blob_url,
                "data": data,
                "path": out_path,
            })

        return results

    def _assign_dom_ids(
        self,
        bubbles: list,
        dom_msgs: list[dict],
        dpr: float,
        tolerance_css_px: float = 80.0,
    ) -> None:
        """Assign DOM data-id to each bubble by closest viewport-y match."""
        if not dom_msgs:
            return
        for bubble in bubbles:
            bubble_vy = (bubble.bbox["y"] + bubble.bbox["h"] / 2 + WASession.HEADER_Y) / dpr
            best = min(dom_msgs, key=lambda d: abs(d["vy"] - bubble_vy))
            if abs(best["vy"] - bubble_vy) <= tolerance_css_px:
                bubble.dom_id = best["id"]

    # ── Full history scroll-capture ───────────────────────────────────────────

    async def capture_full_history(
        self,
        assets_dir: Path | None = None,
        scroll_css_px: int = 1800,
        settle_ms: int = 2500,
        backoff_css_px: int = 200,
        max_iterations: int = 300,
        from_date: "_Date | None" = None,
        newest: bool = False,
    ) -> list[Bubble]:
        """
        Scroll from bottom to top capturing all unique messages.

        Algorithm: on each step, the topmost visible bubble ("anchor") is located
        in the next screenshot by content. Everything above the anchor's y-position
        is new content (positional dedup). Content-key dedup is a secondary guard.

        Stops when: (a) scrollTop reaches 0, (b) scroll stalls 3× in a row, or
        (c) max_iterations is reached.

        When newest=True, loads existing history_bubbles.json and stops when the
        first already-known message is found, then prepends new messages to the
        existing list and re-numbers IDs.

        Limitation: media bubbles (photos, videos) are not detected by the vision
        pipeline and will be absent from the result. Text, audio, and file messages
        are captured fully.
        """
        def bubble_key(b) -> tuple:
            # Works with both Bubble objects and dicts (from JSON)
            if isinstance(b, dict):
                if b.get("dom_id"):
                    return ("dom", b["dom_id"])
                return (b.get("sender"), b.get("msg_type"), b.get("text", "")[:80].strip(), b.get("timestamp"))
            # Bubble object
            if b.dom_id:
                return ("dom", b.dom_id)
            return (b.sender, b.msg_type, b.text[:80].strip(), b.timestamp)

        existing_bubbles: list[dict] = []
        known_keys: set = set()
        should_stop_newest = False

        if newest and assets_dir:
            json_path = Path(assets_dir) / "history_bubbles.json"
            if json_path.exists():
                import json
                try:
                    existing_bubbles = json.loads(json_path.read_text())
                    for bubble_dict in existing_bubbles:
                        k = bubble_key(bubble_dict)
                        known_keys.add(k)
                    print(f"[wavi] newest: loaded {len(existing_bubbles)} existing bubbles", file=sys.stderr)
                except Exception as e:
                    print(f"[wavi] newest: failed to load history_bubbles.json: {e}", file=sys.stderr)

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

        # Install blob monitor ONCE before starting captures
        await self.session.install_blob_monitor()

        # Inicializar set para rastrear dom_ids descargados (evita duplicados en overlaps)
        downloaded_audio_ids: set = set()

        # First capture in iter_000 with debug image
        dpr = await self.session.get_dpr()
        dom_msgs_0 = await self.session.get_visible_message_ids()
        bubbles = await self.get_bubbles(assets_dir=_iter_dir(0), save_debug=True)
        self._assign_dom_ids(bubbles, dom_msgs_0, dpr)

        # Check for duplicates in initial capture (newest mode)
        if newest and known_keys:
            filtered_bubbles = []
            for b in bubbles:
                k = bubble_key(b)
                if k in known_keys:
                    print(f"[wavi] iter_000: found duplicate (newest mode) — stopping", file=sys.stderr)
                    should_stop_newest = True
                    break
                filtered_bubbles.append(b)
            bubbles = filtered_bubbles

        for b in bubbles:
            k = bubble_key(b)
            if k not in seen_keys:
                seen_keys.add(k)
                all_bubbles.append(b)

        # Redraw iter_000 debug image with exact DOM play-button positions
        iter0_dir = _iter_dir(0)
        if iter0_dir and bubbles:
            await self._redraw_debug_with_dom_positions(bubbles, iter0_dir)

        # Descargar audios del iter_000 (DESPUÉS del redraw)
        iter0_audios = await self._download_audio_for_bubbles(
            bubbles, iter0_dir, downloaded_ids=downloaded_audio_ids
        )
        if iter0_audios:
            n_ok = sum(1 for a in iter0_audios if a.get("path"))
            print(f"[wavi] iter_000: {n_ok}/{len(iter0_audios)} audios descargados", file=sys.stderr)

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
            anchor_bubble = max(bubbles, key=lambda b: b.id) if bubbles else None
            anchor_dom_id  = anchor_bubble.dom_id if anchor_bubble else None
            anchor_ocr_key = bubble_key(anchor_bubble) if anchor_bubble else None

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
            dom_msgs = await self.session.get_visible_message_ids()
            iter_assets = _iter_dir(iteration + 1)
            new_bubbles = await self.get_bubbles(assets_dir=iter_assets, save_debug=True)
            self._assign_dom_ids(new_bubbles, dom_msgs, dpr)
            # Note: new_bubbles may be empty if the current view is all-media — keep scrolling.
            if iter_assets and any(b.msg_type in ("audio", "file") for b in new_bubbles):
                await self._redraw_debug_with_dom_positions(new_bubbles, iter_assets)

            # Descargar audios en esta iteración (DESPUÉS del redraw)
            iter_audios = await self._download_audio_for_bubbles(
                new_bubbles, iter_assets, downloaded_ids=downloaded_audio_ids
            )
            if iter_audios:
                n_ok = sum(1 for a in iter_audios if a.get("path"))
                print(
                    f"[wavi] iter={iteration+1}: {n_ok}/{len(iter_audios)} audios descargados",
                    file=sys.stderr,
                )

            # Find anchor in new screenshot: prefer DOM id (immune to OCR variation),
            # fall back to OCR key if no dom_id was assigned.
            _matches: list = []
            if anchor_dom_id:
                _matches = [b for b in new_bubbles if b.dom_id == anchor_dom_id]
            if not _matches and anchor_ocr_key:
                _matches = [b for b in new_bubbles if bubble_key(b) == anchor_ocr_key]
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
                    backoff_dom_msgs = await self.session.get_visible_message_ids()
                    new_bubbles = await self.get_bubbles(assets_dir=iter_assets, save_debug=True)
                    self._assign_dom_ids(new_bubbles, backoff_dom_msgs, dpr)
                    _matches = []
                    if anchor_dom_id:
                        _matches = [b for b in new_bubbles if b.dom_id == anchor_dom_id]
                    if not _matches and anchor_ocr_key:
                        _matches = [b for b in new_bubbles if bubble_key(b) == anchor_ocr_key]
                    anchor_in_new = max(_matches, key=lambda b: b.bbox["y"]) if _matches else None
                    if anchor_in_new is not None:
                        # Descargar audios si encontró el ancla en backoff
                        await self._download_audio_for_bubbles(
                            new_bubbles, iter_assets, downloaded_ids=downloaded_audio_ids
                        )
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

            # Check for duplicates with existing history (--newest mode)
            if newest and known_keys:
                filtered_new_items = []
                for b in new_items:
                    k = bubble_key(b)
                    if k in known_keys:
                        print(f"[wavi] iter={iteration+1}: found duplicate (newest mode) — stopping", file=sys.stderr)
                        should_stop_newest = True
                        break
                    filtered_new_items.append(b)
                new_items = filtered_new_items
                new_count = len(new_items)

            # ── Detect day pills: assign dates + optional from_date stop ─────
            # Runs always (dates are useful metadata regardless of from_date).
            should_stop_from_date = False
            if iter_assets:
                cropped = iter_assets / "screenshot_cropped.png"
                if cropped.exists():
                    _pills = _extract_day_pills(cropped)
                    _today = _Date.today()
                    _parsed = [(p["y"], _parse_pill_date(p["text"], _today)) for p in _pills]
                    _parsed = [(y, d) for y, d in _parsed if d is not None]
                    if _parsed:
                        if from_date is not None:
                            top_date = min(_parsed, key=lambda x: x[0])[1]
                            print(
                                f"[wavi] iter={iteration+1}: day pills={[p['text'] for p in _pills]}, oldest={top_date}",
                                file=sys.stderr,
                            )
                            if top_date < from_date:
                                sorted_pills = sorted(_parsed, key=lambda x: x[0])
                                kept = []
                                for b in new_items:
                                    by = b.bbox["y"]
                                    date_of_bubble = sorted_pills[0][1]
                                    for pill_y, pill_date in sorted_pills:
                                        if pill_y <= by:
                                            date_of_bubble = pill_date
                                        else:
                                            break
                                    if date_of_bubble >= from_date:
                                        kept.append(b)
                                dropped = len(new_items) - len(kept)
                                new_items = kept
                                new_count = len(kept)
                                print(
                                    f"[wavi] reached {top_date} < --from {from_date} "
                                    f"— kept {new_count}, dropped {dropped} (older)",
                                    file=sys.stderr,
                                )
                                should_stop_from_date = True

            # Prepend older content so the list stays chronological (oldest first)
            all_bubbles = new_items + all_bubbles

            print(
                f"[wavi] iter={iteration+1}: +{new_count} new, total={len(all_bubbles)}, "
                f"scrollTop {scroll_top_before:.0f}→{scroll_top_after:.0f}",
                file=sys.stderr,
            )

            if should_stop_newest:
                break

            if should_stop_from_date:
                break

            if new_count == 0 and scroll_top_after < 20:
                print("[wavi] No new bubbles and at top — done.", file=sys.stderr)
                break

            bubbles = new_bubbles

        # Re-assign globally sequential IDs: id=1=newest, id=N=oldest
        if newest and existing_bubbles:
            # Merge: new bubbles (all_bubbles) + old bubbles (existing_bubbles)
            final_bubbles = [b.as_dict() for b in all_bubbles] + existing_bubbles
            n = len(final_bubbles)
            for i, item in enumerate(final_bubbles):
                item["id"] = i + 1
            print(f"[wavi] newest: merged {len(all_bubbles)} new + {len(existing_bubbles)} existing = {len(final_bubbles)} total", file=sys.stderr)
        else:
            final_bubbles = [b.as_dict() for b in all_bubbles]
            n = len(all_bubbles)
            for i, b in enumerate(all_bubbles):
                b.id = n - i
            for i, item in enumerate(final_bubbles):
                item["id"] = i + 1

        # Save aggregated result to assets_dir
        if assets_dir:
            import json
            assets_dir = Path(assets_dir)
            assets_dir.mkdir(parents=True, exist_ok=True)
            out = assets_dir / "history_bubbles.json"
            out.write_text(
                json.dumps(final_bubbles, indent=2, ensure_ascii=False)
            )
            print(f"[wavi] Saved {len(final_bubbles)} bubbles → {out}", file=sys.stderr)

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
        results = await self._download_audio_for_bubbles(
            audio_bubbles, assets_dir, wait_ms, blob_timeout_ms
        )

        # Redraw debug image with resolved play-button positions
        if assets_dir:
            try:
                from PIL import Image as PILImage
                from wavi.vision import _save_debug_image
                dpr = await self.session.get_dpr()
                play_btns = await self.find_play_buttons()
                resolved: dict = {}
                for b in audio_bubbles:
                    btn = self._match_bubble_to_button(b, play_btns, dpr=dpr)
                    if btn:
                        resolved[b.id] = (
                            int(btn["vx"] * dpr) - int(WASession.SIDEBAR_X * dpr),
                            int(btn["vy"] * dpr) - WASession.HEADER_Y,
                        )
                if resolved:
                    assets_dir = Path(assets_dir)
                    cropped = assets_dir / "screenshot_cropped.png"
                    debug_out = assets_dir / "screenshot_debug.png"
                    if cropped.exists() and debug_out.exists():
                        img = PILImage.open(cropped)
                        _save_debug_image(img, bubbles, debug_out, play_positions=resolved)
            except Exception as e:
                print(f"[wavi] capture_audio_bubbles debug redraw skipped: {e}", file=sys.stderr)

        return results

    async def list_contacts(
        self,
        assets_dir: "Path | str | None" = None,
    ) -> dict:
        """Open the 'New chat' panel and return all visible contacts.

        Saves contacts_list.json and screenshot.png to assets_dir (overwriting).

        Returns::

            {
                "contacts": [{"name": str, "subtitle": str}, ...],
                "screenshot": str | None,   # absolute path inside assets_dir
                "assets_dir": str | None,
            }
        """
        import json as _json
        from pathlib import Path as _Path

        status = await self.session.connect()
        if status in ("qr_needed", "timeout"):
            raise RuntimeError(
                f"Session not authenticated (status={status!r}). Run 'wavi connect' first."
            )
        try:
            await self.session.navigate_to_new_chat()
            contacts = await self.session.extract_contacts()
            shot_path: str | None = None
            assets_path: str | None = None
            if assets_dir is not None:
                d = _Path(assets_dir)
                d.mkdir(parents=True, exist_ok=True)
                shot_p = d / "screenshot.png"
                await self.session.screenshot_to_file(shot_p)
                shot_path = str(shot_p.resolve())
                json_p = d / "contacts_list.json"
                json_p.write_text(
                    _json.dumps({"contacts": contacts}, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                assets_path = str(d.resolve())
            await self.session.close_new_chat()
        finally:
            await self.session.close()

        return {"contacts": contacts, "screenshot": shot_path, "assets_dir": assets_path}


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
    from_date: "_Date | None" = None,
    newest: bool = False,
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
    bubbles = await runner.capture_full_history(
        assets_dir=assets_dir, max_iterations=max_iterations, from_date=from_date, newest=newest,
    )
    await runner.close()

    # Transcribe after browser is closed — avoids blocking Playwright during scroll
    if assets_dir:
        await transcribe_history_audios(Path(assets_dir))

    return {"bubbles": bubbles}


async def transcribe_history_audios(history_dir: Path | str) -> int:
    """
    Second-pass transcription over already-downloaded audio files.

    Reads history_bubbles.json, finds audio bubbles without a transcript,
    locates the .ogg via bubble["audio_path"] (set during download), transcribes
    each one, and rewrites history_bubbles.json with the transcript fields added.

    Returns the number of audio bubbles successfully transcribed.
    Call this after run_enhanced() if GROQ_API_KEY was not set during scraping,
    or to retry failed transcriptions.
    """
    import json
    history_dir = Path(history_dir)
    json_path = history_dir / "history_bubbles.json"
    if not json_path.exists():
        raise FileNotFoundError(f"history_bubbles.json not found in {history_dir}")

    bubbles = json.loads(json_path.read_text())

    transcribed = 0
    failed_ids: list[int] = []
    for bubble in bubbles:
        if bubble.get("msg_type") != "audio":
            continue
        if bubble.get("transcript") is not None:
            continue
        bid = bubble["id"]
        raw_path = bubble.get("audio_path")
        if not raw_path:
            print(f"[wavi] transcribe_history: no audio_path for bubble#{bid}", file=sys.stderr)
            failed_ids.append(bid)
            continue
        ogg_path = Path(raw_path)
        if not ogg_path.exists():
            print(f"[wavi] transcribe_history: file missing for bubble#{bid}: {ogg_path}", file=sys.stderr)
            failed_ids.append(bid)
            continue
        result = await _transcribe_audio(ogg_path)
        if result is not None:
            bubble["transcript"] = result
            transcribed += 1
            print(f"[wavi] transcribed bubble#{bid}: {result[:80]!r}", file=sys.stderr)
        else:
            failed_ids.append(bid)
            print(f"[wavi] transcription failed for bubble#{bid}", file=sys.stderr)

    json_path.write_text(json.dumps(bubbles, indent=2, ensure_ascii=False))
    if failed_ids:
        print(f"[wavi] {len(failed_ids)} bubbles not transcribed: {failed_ids}", file=sys.stderr)
    print(f"[wavi] transcribe_history_audios: {transcribed} new transcripts → {json_path}", file=sys.stderr)
    return transcribed
