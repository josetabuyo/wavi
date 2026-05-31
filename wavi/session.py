"""
WASession — Playwright session for WhatsApp Web via CDP.

Architecture: Chrome runs as a long-lived daemon (started by 'wavi connect').
Playwright connects/disconnects for each operation but NEVER kills Chrome.
Killing Chrome mid-session corrupts the WA IndexedDB and invalidates the session.

Shutdown is only done via stop_daemon(), which navigates to about:blank first
to let WA flush its state before SIGTERM.
"""
from __future__ import annotations

import asyncio
import base64
import subprocess
from pathlib import Path

WA_URL      = "https://web.whatsapp.com/"
REAL_CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
CDP_PORT    = 9222
PID_FILE    = "chrome_daemon.pid"

# Viewport size for headless daemon. Width=1280 is the calibrated base for the
# sidebar crop formula (vision.py: sidebar_x = w * SIDEBAR_PX/1280).
# Height=1920 maximises messages captured per screenshot without resize events.
WINDOW_W = 1280
WINDOW_H = 1920

_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/148.0.0.0 Safari/537.36"
)

# ── JavaScript ────────────────────────────────────────────────────────────────

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

    const origDesc = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, 'src');
    Object.defineProperty(HTMLMediaElement.prototype, 'src', {
        set(url) { _capture(url); if (origDesc && origDesc.set) origDesc.set.call(this, url); },
        get() { return origDesc && origDesc.get ? origDesc.get.call(this) : undefined; },
        configurable: true,
    });

    const origPlay = HTMLMediaElement.prototype.play;
    HTMLMediaElement.prototype.play = function() {
        const url = origDesc && origDesc.get ? origDesc.get.call(this) : this.getAttribute('src');
        _capture(url);
        return origPlay.call(this);
    };

    const origCreate = URL.createObjectURL.bind(URL);
    URL.createObjectURL = function(obj) {
        const url = origCreate(obj);
        _capture(url);
        return url;
    };

})();
"""

_FETCH_BLOB_JS = """
async (blobUrl) => {
    try {
        const r = await fetch(blobUrl);
        const buf = new Uint8Array(await r.arrayBuffer());
        let s = '';
        const CHUNK = 8192;
        for (let i = 0; i < buf.length; i += CHUNK)
            s += String.fromCharCode(...buf.subarray(i, i + CHUNK));
        return btoa(s);
    } catch(e) { return null; }
}
"""

_DRAIN_JS = """
() => {
    const items = window.__wavi_blobs || [];
    window.__wavi_blobs = [];
    return items;
}
"""

_CLICK_SCROLL_BOTTOM_BTN_JS = """
() => {
    // WA shows a floating "scroll to bottom" button when not at the bottom of the chat.
    // Find it by position: it sits in the lower-right corner of the message panel.
    const panelSels = [
        '[data-testid="conversation-panel-messages"]',
        '#main div[role="region"]',
        '#main .copyable-area'
    ];
    let panel = null;
    for (const s of panelSels) {
        panel = document.querySelector(s);
        if (panel) break;
    }
    if (!panel) return false;

    const pr = panel.getBoundingClientRect();
    const buttons = document.querySelectorAll('#main button');
    for (const btn of buttons) {
        const br = btn.getBoundingClientRect();
        // Button must be visible, inside the right half of the panel, near its bottom edge
        if (br.width > 0 && br.height > 0
                && br.left > pr.left + pr.width * 0.5
                && br.bottom > pr.bottom - 120
                && br.bottom < pr.bottom + 20) {
            btn.click();
            return true;
        }
    }
    return false;
}
"""

_CHAT_SCROLL_JS = """
() => {
    const selectors = [
        '[data-testid="conversation-panel-messages"]',
        '#main div[role="region"]',
        '#main .copyable-area'
    ];
    for (const s of selectors) {
        const el = document.querySelector(s);
        if (el && el.scrollHeight > el.clientHeight)
            return { scrollTop: el.scrollTop, scrollHeight: el.scrollHeight, clientHeight: el.clientHeight };
    }
    return null;
}
"""

_SCROLL_UP_JS = """
(pixels) => {
    const selectors = [
        '[data-testid="conversation-panel-messages"]',
        '#main div[role="region"]',
        '#main .copyable-area'
    ];
    for (const s of selectors) {
        const el = document.querySelector(s);
        if (el && el.scrollHeight > el.clientHeight) {
            el.scrollTop -= pixels;
            return el.scrollTop;
        }
    }
    return null;
}
"""

_SCROLL_DOWN_JS = """
(pixels) => {
    const selectors = [
        '[data-testid="conversation-panel-messages"]',
        '#main div[role="region"]',
        '#main .copyable-area'
    ];
    for (const s of selectors) {
        const el = document.querySelector(s);
        if (el && el.scrollHeight > el.clientHeight) {
            el.scrollTop += pixels;
            return el.scrollTop;
        }
    }
    return null;
}
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _is_process_alive(pid: int) -> bool:
    try:
        import os
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


class WASession:
    """
    Connects to a long-lived Chrome daemon started by 'wavi connect'.

    Playwright connects for each operation and disconnects without killing
    Chrome.  Use stop_daemon() only when you intentionally want to end
    the session.

    Usage::

        session = WASession("data/sessions/default")
        await session.connect()           # connects to running daemon
        await session.navigate_to_contact("Luis Perez")
        shot = await session.screenshot()
        blobs = await session.drain_blobs()
        await session.close()             # disconnects — Chrome stays alive
    """

    from wavi.vision import SIDEBAR_PX as SIDEBAR_X, HEADER_PX as HEADER_Y

    SEARCH_X       = 317
    SEARCH_Y       = 80
    FIRST_RESULT_X = 317
    FIRST_RESULT_Y = 200  # primer resultado en lista de búsqueda (~120px bajo el search box)

    _AUTHED_SEL = "[data-testid='chat-list'], #side, input[role='textbox']"

    def __init__(self, profile_dir: str | Path, headless: bool = True):
        self.profile_dir   = Path(profile_dir)
        self.headless      = headless
        self._pw           = None
        self._browser      = None
        self._context      = None
        self._page         = None
        self._chrome_proc  = None  # set only when WE started Chrome

    # ── Daemon helpers ────────────────────────────────────────────────────────

    def _save_pid(self, pid: int) -> None:
        (self.profile_dir / PID_FILE).write_text(str(pid))

    def _load_pid(self) -> int | None:
        try:
            return int((self.profile_dir / PID_FILE).read_text().strip())
        except Exception:
            return None

    def daemon_alive(self) -> bool:
        pid = self._load_pid()
        return pid is not None and _is_process_alive(pid)

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    async def connect(self) -> str:
        """
        Connect to the running Chrome daemon.  If no daemon is alive, starts
        a headless Chrome (fallback for 'wavi status').

        Returns "restored" if session is authenticated, "qr_needed" otherwise.
        """
        from playwright.async_api import async_playwright
        self._pw = await async_playwright().start()

        # Try to connect to existing daemon first
        pid = self._load_pid()
        if pid and _is_process_alive(pid):
            try:
                self._browser = await self._pw.chromium.connect_over_cdp(
                    f"http://localhost:{CDP_PORT}", timeout=5_000
                )
                return await self._setup_page()
            except Exception as e:
                import sys
                print(f"⚠️  Daemon vivo (PID {pid}) pero CDP no responde: {e}", file=sys.stderr)
                pass  # daemon alive but CDP not responding — fall through

        # No daemon: start headless Chrome (status/run without a prior connect)
        import sys
        print(f"⚠️  No daemon detectado — abriendo Chrome en fallback headless...", file=sys.stderr)

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        _kill_port(CDP_PORT)
        (self.profile_dir / "SingletonLock").unlink(missing_ok=True)

        args = [
            str(REAL_CHROME),
            f"--user-data-dir={self.profile_dir}",
            f"--remote-debugging-port={CDP_PORT}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
            f"--user-agent={_UA}",
        ]
        # ADR-002: --force-device-scale-factor=1 ensures window-size maps 1:1 to
        # CSS pixels on macOS Retina (otherwise DPR=2 halves the effective viewport).
        args += ["--headless=new", f"--window-size={WINDOW_W},{WINDOW_H}",
                 "--force-device-scale-factor=1"]

        self._chrome_proc = subprocess.Popen(
            ["arch", "-arm64"] + args + ["about:blank"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._save_pid(self._chrome_proc.pid)

        for _ in range(30):
            try:
                self._browser = await self._pw.chromium.connect_over_cdp(
                    f"http://localhost:{CDP_PORT}", timeout=1_000
                )
                break
            except Exception:
                await asyncio.sleep(1)
        else:
            self._chrome_proc.terminate()
            raise RuntimeError(f"Chrome did not expose CDP on port {CDP_PORT}")

        return await self._setup_page()

    async def _setup_page(self) -> str:
        """Attach init scripts, get/navigate page, return auth status."""
        contexts = self._browser.contexts
        self._context = contexts[0] if contexts else await self._browser.new_context()

        # DISABLED: grant_permissions([]) was causing WA Web to go white on CDP attach
        # await self._context.grant_permissions([])

        # DISABLED: navigator.webdriver modification was breaking WA Web theme/styling
        # await self._context.add_init_script(
        #     "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        # )
        # DISABLED: _BLOB_INIT_SCRIPT modifies HTMLMediaElement.prototype, breaking WA Web styling
        # await self._context.add_init_script(_BLOB_INIT_SCRIPT)

        pages = self._context.pages
        # Close all pages except the first one (prevent restored tabs)
        for page in pages[1:]:
            await page.close()

        self._page = pages[0] if pages else await self._context.new_page()
        # DISABLED: bring_to_front() triggers visibility events that WA detects
        # await self._page.bring_to_front()

        if WA_URL not in self._page.url:
            if self.headless:
                # Set viewport BEFORE loading WA so it mounts at the right size.
                # Safe here: WA is not yet running, no resize event will be triggered.
                await self._page.set_viewport_size({"width": WINDOW_W, "height": WINDOW_H})
            await self._page.goto(WA_URL, wait_until="domcontentloaded", timeout=30_000)

        QR = "[data-testid='qrcode'], div[data-ref], canvas"
        try:
            await self._page.wait_for_selector(f"{self._AUTHED_SEL}, {QR}", timeout=60_000)
        except Exception:
            return "timeout"

        if await self._page.query_selector(self._AUTHED_SEL):
            return "restored"
        return "qr_needed"

    async def wait_for_auth(self, timeout_s: int = 120) -> bool:
        try:
            await self._page.wait_for_selector(self._AUTHED_SEL, timeout=timeout_s * 1000)
            return True
        except Exception:
            return False

    async def close(self) -> None:
        """
        Disconnect Playwright from Chrome — does NOT kill the Chrome process.
        Chrome keeps running as a daemon so the WA session stays alive.
        """
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()
        # Intentionally NOT terminating _chrome_proc here.

    async def stop_daemon(self) -> None:
        """
        Gracefully shut down the Chrome daemon.
        Navigates to about:blank first so WA can flush IndexedDB before exit.
        """
        if self._page:
            try:
                await self._page.goto("about:blank", timeout=5_000)
                await asyncio.sleep(2)
            except Exception:
                pass

        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

        # Load PID if we didn't start Chrome ourselves
        pid = self._load_pid()
        if pid and _is_process_alive(pid):
            import os, signal
            os.kill(pid, signal.SIGTERM)
            for _ in range(20):  # wait up to 10s for clean exit
                await asyncio.sleep(0.5)
                if not _is_process_alive(pid):
                    break
            else:
                os.kill(pid, signal.SIGKILL)

        (self.profile_dir / "SingletonLock").unlink(missing_ok=True)
        (self.profile_dir / PID_FILE).unlink(missing_ok=True)

    # ── Navigation ────────────────────────────────────────────────────────────

    async def navigate_to_contact(self, contact: str) -> None:
        # Click en el cuadro de búsqueda por coordenadas (ADR-001: sin locator)
        await self._page.mouse.click(self.SEARCH_X, self.SEARCH_Y)
        await self._page.wait_for_timeout(300)

        # Limpiar con teclado — Cmd+A selecciona todo en macOS, Delete borra
        await self._page.keyboard.press("Meta+a")
        await self._page.wait_for_timeout(100)
        await self._page.keyboard.press("Delete")
        await self._page.wait_for_timeout(200)

        # Escribir el contacto con delays realistas
        await self._page.keyboard.type(contact, delay=40)
        await self._page.wait_for_timeout(1500)

        # Abrir primer resultado con teclado — más robusto que coordenadas o selectores
        await self._page.keyboard.press("ArrowDown")
        await self._page.wait_for_timeout(300)
        await self._page.keyboard.press("Enter")

        # Esperar a que WA pinte los mensajes
        bubble_ready = (
            "[data-testid='msg-container'], "
            "[data-testid='conversation-panel-messages'], "
            ".copyable-text, [class*='message-']"
        )
        try:
            await self._page.wait_for_selector(bubble_ready, timeout=15_000)
        except Exception:
            pass
        await self._page.wait_for_timeout(1500)

        # WA prepends older messages above the anchor after loading, which shifts the
        # scroll position up. Try the WA "scroll to bottom" button first — it triggers
        # WA's own virtualizer to render the latest messages. Fall back to DOM scrollTop.
        clicked = await self._page.evaluate(_CLICK_SCROLL_BOTTOM_BTN_JS)
        await self._page.wait_for_timeout(600)
        if not clicked:
            await self._page.evaluate(_SCROLL_DOWN_JS, 999_999)
        await self._page.wait_for_timeout(800)

    # ── Screenshot ────────────────────────────────────────────────────────────

    async def screenshot(self) -> bytes:
        return await self._page.screenshot(type="png", full_page=False)

    async def screenshot_to_file(self, path: str | Path) -> Path:
        out = Path(path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(await self.screenshot())
        return out

    # ── Interaction ───────────────────────────────────────────────────────────

    async def click(self, crop_x: int, crop_y: int, wait_ms: int = 2000) -> None:
        vx = crop_x + self.SIDEBAR_X
        vy = crop_y + self.HEADER_Y
        await self._page.mouse.click(vx, vy)
        if wait_ms:
            await self._page.wait_for_timeout(wait_ms)

    async def eval(self, js: str):
        return await self._page.evaluate(js)

    # ── Audio blob capture ────────────────────────────────────────────────────

    async def install_blob_monitor(self) -> None:
        """Inject blob URL monitor into the already-running page (lazy, safe post-load)."""
        await self._page.evaluate(_BLOB_INIT_SCRIPT)

    async def get_dpr(self) -> float:
        """Return the page's devicePixelRatio (e.g. 2.0 on Retina)."""
        return await self._page.evaluate("() => window.devicePixelRatio")

    async def reset_blobs(self) -> None:
        await self._page.evaluate(
            "() => { window.__wavi_blobs = []; window.__wavi_seen = new Set(); }"
        )

    async def drain_blobs(self) -> list[dict]:
        return await self._page.evaluate(_DRAIN_JS)

    async def fetch_blob(self, blob_url: str) -> bytes | None:
        b64 = await self._page.evaluate(_FETCH_BLOB_JS, blob_url)
        if b64:
            return base64.b64decode(b64)
        return None

    # ── Scroll helpers ────────────────────────────────────────────────────────

    async def scroll_chat_up(self, css_pixels: int = 1800) -> None:
        """Scroll chat up by css_pixels via direct DOM scrollTop manipulation."""
        await self._page.evaluate(_SCROLL_UP_JS, css_pixels)

    async def scroll_chat_down(self, css_pixels: int = 300) -> None:
        """Scroll chat down by css_pixels via direct DOM scrollTop manipulation."""
        await self._page.evaluate(_SCROLL_DOWN_JS, css_pixels)

    async def get_chat_scroll_state(self) -> dict | None:
        """Return {scrollTop, scrollHeight, clientHeight} of the chat container, or None."""
        return await self._page.evaluate(_CHAT_SCROLL_JS)

    async def is_chat_at_top(self) -> bool:
        """Return True if the chat scroll container is at the top (scrollTop < 20)."""
        state = await self.get_chat_scroll_state()
        return state is not None and state["scrollTop"] < 20


# ── Module-level helpers ──────────────────────────────────────────────────────

def _kill_port(port: int) -> None:
    """Kill any process listening on port (cleanup zombie Chromes)."""
    result = subprocess.run(
        ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
        capture_output=True, text=True,
    )
    for pid in result.stdout.strip().split("\n"):
        if pid.strip():
            subprocess.run(["kill", "-9", pid.strip()], capture_output=True)
