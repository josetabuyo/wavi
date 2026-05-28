"""
WASession — Playwright session for WhatsApp Web.

Manages a persistent Chrome profile so WA session survives restarts without
needing a QR re-scan. The audio blob interceptor is installed as an init script
so it runs before WhatsApp's JavaScript on every page load.
"""
from __future__ import annotations

import asyncio
import base64
import json
import time
from pathlib import Path
from typing import Optional

WA_URL = "https://web.whatsapp.com/"

# ── JavaScript injected before WA's code on every page load ──────────────────

_BLOB_INIT_SCRIPT = """
(function() {
    if (window.__wavi_installed) return;
    window.__wavi_installed = true;
    window.__wavi_blobs = [];
    window.__wavi_seen  = new Set();

    function _capture(url) {
        if (!url || !url.startsWith('blob:')) return;
        if (window.__wavi_seen.has(url)) return;
        window.__wavi_seen.add(url);
        window.__wavi_blobs.push({ url, ts: Date.now() });
    }

    // Hook 1: src property setter
    const origDesc = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'src');
    Object.defineProperty(HTMLMediaElement.prototype, 'src', {
        set(url) { _capture(url); if (origDesc && origDesc.set) origDesc.set.call(this, url); },
        get() { return origDesc && origDesc.get ? origDesc.get.call(this) : undefined; },
        configurable: true,
    });

    // Hook 2: play() — catches blobs already assigned before play() call
    const origPlay = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = function() {
        const url = origDesc && origDesc.get ? origDesc.get.call(this) : this.getAttribute('src');
        _capture(url);
        return origPlay.call(this);
    };

    // Hook 3: URL.createObjectURL — catches blob creation at the source
    const origCreate = URL.createObjectURL.bind(URL);
    URL.createObjectURL = function(obj) {
        const url = origCreate(obj);
        _capture(url);
        return url;
    };

    // Hook 4: setAttribute on media elements
    const origSetAttr = Element.prototype.setAttribute;
    Element.prototype.setAttribute = function(name, value) {
        if (this instanceof HTMLMediaElement && name === 'src') _capture(value);
        return origSetAttr.call(this, name, value);
    };
})();
"""

_FETCH_BLOB_JS = """
async (blobUrl) => {
    try {
        const r = await fetch(blobUrl);
        const buf = await r.arrayBuffer();
        return btoa(String.fromCharCode(...new Uint8Array(buf)));
    } catch(e) {
        return null;
    }
}
"""

_DRAIN_JS = """
() => {
    const items = window.__wavi_blobs || [];
    window.__wavi_blobs = [];
    return items;
}
"""


class WASession:
    """
    Wraps a Playwright persistent-context browser pointed at WhatsApp Web.

    Usage::

        session = WASession("data/sessions/5491155612767")
        await session.connect()
        await session.navigate_to_contact("Luis Perez")
        shot = await session.screenshot()
        await session.click(320, 450)          # crop-panel coords
        blobs = await session.drain_blobs()
        audio = await session.fetch_blob(blobs[0]["url"])
        await session.close()
    """

    SIDEBAR_X = 580
    HEADER_Y  = 60

    def __init__(self, profile_dir: str | Path, headless: bool = True):
        self.profile_dir = Path(profile_dir)
        self.headless    = headless
        self._pw         = None
        self._context    = None
        self._page       = None

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def connect(self) -> str:
        """
        Launch browser with the persistent profile and navigate to WA Web.

        Returns "restored" if session loaded without QR, "qr_needed" otherwise.
        """
        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        self._context = await self._pw.chromium.launch_persistent_context(
            user_data_dir=str(self.profile_dir),
            headless=self.headless,
            args=[
                "--disable-blink-features=AutomationControlled",
                "--no-sandbox",
                "--disable-setuid-sandbox",
            ],
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
            locale="es-AR",
        )
        await self._context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )
        await self._context.add_init_script(_BLOB_INIT_SCRIPT)

        pages = self._context.pages
        self._page = pages[0] if pages else await self._context.new_page()
        await self._page.goto(WA_URL, wait_until="domcontentloaded", timeout=30_000)

        AUTHED = "[data-testid='chat-list'], #side, [data-testid='search-input']"
        QR     = "[data-testid='qrcode'], div[data-ref], canvas"
        try:
            await self._page.wait_for_selector(f"{AUTHED}, {QR}", timeout=60_000)
        except Exception:
            return "timeout"

        if await self._page.query_selector(AUTHED):
            return "restored"
        return "qr_needed"

    async def wait_for_auth(self, timeout_s: int = 120) -> bool:
        """Block until WA shows the main chat UI (user scanned QR). Returns True on success."""
        AUTHED = "[data-testid='chat-list'], #side"
        try:
            await self._page.wait_for_selector(AUTHED, timeout=timeout_s * 1000)
            return True
        except Exception:
            return False

    async def close(self) -> None:
        if self._context:
            await self._context.close()
        if self._pw:
            await self._pw.stop()

    # ── Navigation ────────────────────────────────────────────────────────────

    async def navigate_to_contact(self, contact: str) -> None:
        """Open a specific chat by typing the contact name in the WA search box."""
        search_sel = "[data-testid='chat-list-search']"
        await self._page.click(search_sel)
        await self._page.fill(search_sel, contact)
        await self._page.wait_for_timeout(800)

        # Click the first result
        result_sel = f"[title='{contact}']"
        try:
            await self._page.wait_for_selector(result_sel, timeout=5_000)
            await self._page.click(result_sel)
        except Exception:
            # Fallback: click first list item
            await self._page.keyboard.press("Enter")

        await self._page.wait_for_timeout(1000)

    # ── Screenshot ────────────────────────────────────────────────────────────

    async def screenshot(self) -> bytes:
        """Return PNG bytes of the current viewport."""
        return await self._page.screenshot(type="png", full_page=False)

    async def screenshot_to_file(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        data = await self.screenshot()
        out.write_bytes(data)
        return out

    # ── Interaction ───────────────────────────────────────────────────────────

    async def click(self, crop_x: int, crop_y: int, wait_ms: int = 2000) -> None:
        """
        Click at crop-panel coordinates (no sidebar, no header).
        Internally adds SIDEBAR_X and HEADER_Y to convert to viewport coords.
        """
        vx = crop_x + self.SIDEBAR_X
        vy = crop_y + self.HEADER_Y
        await self._page.mouse.click(vx, vy)
        if wait_ms:
            await self._page.wait_for_timeout(wait_ms)

    async def eval(self, js: str):
        """Evaluate arbitrary JS and return the result."""
        return await self._page.evaluate(js)

    # ── Audio blob capture ────────────────────────────────────────────────────

    def reset_blobs(self) -> None:
        """Clear captured blob list (call before a click that should produce audio)."""
        asyncio.get_event_loop().run_until_complete(self._reset_blobs_async())

    async def reset_blobs_async(self) -> None:
        await self._page.evaluate(
            "() => { window.__wavi_blobs = []; window.__wavi_seen = new Set(); }"
        )

    async def drain_blobs(self) -> list[dict]:
        """Return and clear the list of captured blob URLs."""
        return await self._page.evaluate(_DRAIN_JS)

    async def fetch_blob(self, blob_url: str) -> bytes | None:
        """Download a blob URL from the page context and return raw bytes."""
        b64 = await self._page.evaluate(_FETCH_BLOB_JS, blob_url)
        if b64:
            return base64.b64decode(b64)
        return None
