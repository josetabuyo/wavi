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
PORT_FILE   = "chrome_daemon.port"

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

_GET_VISIBLE_MSG_IDS_JS = """
() => {
    const root = document.querySelector(
        '[data-testid="conversation-panel-messages"]'
    ) || document.querySelector('#main') || document;
    const vh = window.innerHeight;
    return [...root.querySelectorAll('[data-id]')]
        .map(r => {
            const rect = r.getBoundingClientRect();
            return { id: r.getAttribute('data-id'), vy: (rect.top + rect.bottom) / 2 };
        })
        .filter(r => r.vy > 0 && r.vy < vh);
}
"""

_FIND_COMPOSE_INPUT_JS = """
() => {
    const sels = [
        'footer [contenteditable="true"]',
        '#main footer [contenteditable="true"]',
        '[data-tab][contenteditable="true"]',
        '[data-testid="conversation-compose-box-input"]',
    ];
    for (const s of sels) {
        const el = document.querySelector(s);
        if (el) {
            const r = el.getBoundingClientRect();
            return { x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2), found: true, selector: s };
        }
    }
    return { found: false };
}
"""

_CHECK_COMPOSE_EMPTY_JS = """
() => {
    const sels = [
        'footer [contenteditable="true"]',
        '#main footer [contenteditable="true"]',
        '[data-tab][contenteditable="true"]',
        '[data-testid="conversation-compose-box-input"]',
    ];
    for (const s of sels) {
        const el = document.querySelector(s);
        if (el) return (el.innerText || el.textContent || '').trim() === '';
    }
    return true;
}
"""

_CLICK_SEND_BTN_JS = """
() => {
    // Prefer the icon-based selector (locale-agnostic).
    // Fall back to aria-label in Spanish and English.
    const iconEl = document.querySelector('span[data-icon="send"]');
    if (iconEl) {
        const btn = iconEl.closest('button') || iconEl;
        btn.click();
        return true;
    }
    for (const lbl of ['Enviar', 'Send']) {
        const btn = document.querySelector(`button[aria-label="${lbl}"]`);
        if (btn) { btn.click(); return true; }
    }
    return false;
}
"""

_OPEN_NEW_CHAT_JS = """
() => {
    const icon = document.querySelector('span[data-icon="new-chat-outline"]') ||
                 document.querySelector('span[data-icon="new-chat-alt"]');
    if (!icon) return false;
    const btn = icon.closest('button');
    if (!btn) return false;
    btn.click();
    return true;
}
"""

_EXTRACT_CONTACTS_JS = """
() => {
    const items = document.querySelectorAll('[role="listitem"]');
    const contacts = [];
    items.forEach(item => {
        const btn = item.querySelector('[role="button"]');
        if (!btn) return;
        const gridcell = item.querySelector('[role="gridcell"]');
        if (!gridcell) return;
        const name = gridcell.textContent.trim();
        if (!name) return;
        const contentDiv = gridcell.parentElement;
        const subtitleEl = contentDiv
            ? [...contentDiv.children].find(c => c !== gridcell)
            : null;
        const subtitle = subtitleEl ? subtitleEl.textContent.trim() : '';
        contacts.push({ name, subtitle });
    });
    return contacts;
}
"""

_CLOSE_NEW_CHAT_JS = """
() => {
    const icon = document.querySelector('span[data-icon="back-refreshed"]');
    if (!icon) return false;
    const btn = icon.closest('button');
    if (!btn) return false;
    btn.click();
    return true;
}
"""

_CONTACTS_SCROLL_STATE_JS = """
() => {
    const firstItem = document.querySelector('[role="listitem"]');
    if (!firstItem) return null;
    let el = firstItem.parentElement;
    while (el && el !== document.body) {
        const style = window.getComputedStyle(el);
        const ov = style.overflow + ' ' + style.overflowY;
        if ((ov.includes('auto') || ov.includes('scroll')) && el.scrollHeight > el.clientHeight) {
            return { scrollTop: el.scrollTop, scrollHeight: el.scrollHeight, clientHeight: el.clientHeight };
        }
        el = el.parentElement;
    }
    return null;
}
"""

_SCROLL_CONTACTS_DOWN_JS = """
(pixels) => {
    const firstItem = document.querySelector('[role="listitem"]');
    if (!firstItem) return null;
    let el = firstItem.parentElement;
    while (el && el !== document.body) {
        const style = window.getComputedStyle(el);
        const ov = style.overflow + ' ' + style.overflowY;
        if ((ov.includes('auto') || ov.includes('scroll')) && el.scrollHeight > el.clientHeight) {
            const before = el.scrollTop;
            el.scrollTop += pixels;
            return { before, after: el.scrollTop };
        }
        el = el.parentElement;
    }
    return null;
}
"""

_EXTRACT_VISIBLE_CONTACTS_JS = """
() => {
    const items = document.querySelectorAll('[role="listitem"]');
    const contacts = [];
    const vh = window.innerHeight;
    items.forEach(item => {
        const btn = item.querySelector('[role="button"]');
        if (!btn) return;
        const gridcell = item.querySelector('[role="gridcell"]');
        if (!gridcell) return;
        const name = gridcell.textContent.trim();
        if (!name) return;
        const rect = item.getBoundingClientRect();
        if (rect.bottom < 0 || rect.top > vh) return;
        const contentDiv = gridcell.parentElement;
        const subtitleEl = contentDiv
            ? [...contentDiv.children].find(c => c !== gridcell)
            : null;
        const subtitle = subtitleEl ? subtitleEl.textContent.trim() : '';
        contacts.push({ name, subtitle, vy: rect.top + rect.height / 2 });
    });
    return contacts;
}
"""

_EXTRACT_SIDEBAR_UPDATES_JS = """
() => {
    const results = [];

    // Strategy 1: find unread badges via data-testid (most stable across WA versions)
    const badges = document.querySelectorAll('[data-testid="icon-unread-count"]');
    if (badges.length > 0) {
        badges.forEach(badge => {
            const countText = (badge.textContent || '').trim();
            if (!countText || countText === '0') return;

            // Walk up to the conversation cell
            let cell = badge.parentElement;
            for (let i = 0; i < 12 && cell; i++) {
                const dt = cell.getAttribute('data-testid') || '';
                if (dt === 'cell-frame-container' || cell.tagName === 'LI' ||
                        cell.getAttribute('role') === 'listitem') break;
                cell = cell.parentElement;
            }
            if (!cell) return;

            const titleEl = cell.querySelector('[data-testid="cell-frame-title"]')
                         || cell.querySelector('span[title]')
                         || cell.querySelector('span[dir="auto"]');
            const name = titleEl
                ? (titleEl.getAttribute('title') || titleEl.textContent || '').trim()
                : '';
            if (!name) return;

            const count = parseInt(countText, 10) || countText;
            results.push({ name, unread_count: count });
        });
        return results;
    }

    // Strategy 2: aria-label fallback (some WA locales/versions)
    const chatList = document.querySelector('[data-testid="chat-list"]')
                  || document.querySelector('#pane-side');
    if (!chatList) return results;

    chatList.querySelectorAll('[aria-label]').forEach(el => {
        const lbl = el.getAttribute('aria-label') || '';
        if (!/unread|no le[ií]d/i.test(lbl)) return;
        const nameEl = el.querySelector('span[dir="auto"]');
        const name = nameEl ? (nameEl.textContent || '').trim() : '';
        if (name && !results.some(r => r.name === name))
            results.push({ name, unread_count: null });
    });

    return results;
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
        self._port: int    = self._load_port()

    # ── Daemon helpers ────────────────────────────────────────────────────────

    def _save_pid(self, pid: int) -> None:
        (self.profile_dir / PID_FILE).write_text(str(pid))

    def _load_pid(self) -> int | None:
        try:
            return int((self.profile_dir / PID_FILE).read_text().strip())
        except Exception:
            return None

    def _load_port(self) -> int:
        try:
            return int((self.profile_dir / PORT_FILE).read_text().strip())
        except Exception:
            return CDP_PORT  # fallback for old sessions

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
                    f"http://localhost:{self._port}", timeout=5_000
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
        _kill_port(self._port)
        (self.profile_dir / "SingletonLock").unlink(missing_ok=True)

        args = [
            str(REAL_CHROME),
            f"--user-data-dir={self.profile_dir}",
            f"--remote-debugging-port={self._port}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-blink-features=AutomationControlled",
            f"--user-agent={_UA}",
        ]
        # ADR-002: --force-device-scale-factor=1 ensures window-size maps 1:1 to
        # CSS pixels on macOS Retina (otherwise DPR=2 halves the effective viewport).
        args += ["--headless=new", f"--window-size={WINDOW_W},{WINDOW_H}",
                 "--force-device-scale-factor=1",
                 "--mute-audio"]  # prevent audio reaching speakers during blob capture

        self._chrome_proc = subprocess.Popen(
            ["arch", "-arm64"] + args + ["about:blank"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self._save_pid(self._chrome_proc.pid)

        for _ in range(30):
            try:
                self._browser = await self._pw.chromium.connect_over_cdp(
                    f"http://localhost:{self._port}", timeout=1_000
                )
                break
            except Exception:
                await asyncio.sleep(1)
        else:
            self._chrome_proc.terminate()
            raise RuntimeError(f"Chrome did not expose CDP on port {self._port}")

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
        (self.profile_dir / PORT_FILE).unlink(missing_ok=True)

    # ── Navigation ────────────────────────────────────────────────────────────

    async def navigate_to_contact(self, contact: str) -> None:
        # Click en el cuadro de búsqueda por coordenadas (ADR-001: sin locator)
        await self._page.mouse.click(self.SEARCH_X, self.SEARCH_Y)
        await self._page.wait_for_timeout(300)

        # Limpiar: seleccionar todo y borrar (Mac: Cmd+A, Windows: Ctrl+A)
        import sys as _sys
        _select_all = "Meta+a" if _sys.platform == "darwin" else "Control+a"
        await self._page.keyboard.press(_select_all)
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
        # After a prior full-sync-enhanced the virtualizer may restore the old (top) position,
        # so we verify scrollTop actually reached the bottom and retry up to 5 times.
        clicked = await self._page.evaluate(_CLICK_SCROLL_BOTTOM_BTN_JS)
        await self._page.wait_for_timeout(600)
        if not clicked:
            await self._page.evaluate(_SCROLL_DOWN_JS, 999_999)
        await self._page.wait_for_timeout(800)

        for attempt in range(5):
            state = await self.get_chat_scroll_state()
            if not state:
                break  # container not found (e.g. test env) — stop retrying
            slack = state["scrollHeight"] - state["scrollTop"] - state["clientHeight"]
            if slack <= 50:
                break  # confirmed at bottom
            # Not at bottom yet — prefer WA's own button, fall back to DOM
            clicked = await self._page.evaluate(_CLICK_SCROLL_BOTTOM_BTN_JS)
            await self._page.wait_for_timeout(600 if clicked else 200)
            if not clicked:
                await self._page.evaluate(_SCROLL_DOWN_JS, 999_999)
            await self._page.wait_for_timeout(500)
        else:
            import sys
            print("[wavi] ⚠️  navigate_to_contact: could not confirm bottom after 5 retries", file=sys.stderr)

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

    async def get_visible_message_ids(self) -> list[dict]:
        """Return [{id, vy}] of visible WA messages by DOM data-id (viewport CSS coords)."""
        return await self._page.evaluate(_GET_VISIBLE_MSG_IDS_JS)

    async def is_chat_at_top(self) -> bool:
        """Return True if the chat scroll container is at the top (scrollTop < 20)."""
        state = await self.get_chat_scroll_state()
        return state is not None and state["scrollTop"] < 20

    async def send_message(self, text: str) -> dict:
        """Type and send a message in the currently open chat.

        Handles multi-line text (\\n → Shift+Enter so WA doesn't send early).
        After pressing Enter, verifies compose box emptied; falls back to the
        send button if Enter was configured as new-line in this WA session.

        Returns metadata: {selector, x, y} of the input box used.
        Raises RuntimeError if no compose input is found or send fails.
        """
        info = await self._page.evaluate(_FIND_COMPOSE_INPUT_JS)
        if not info.get("found"):
            raise RuntimeError("No se encontró el input de mensajes (compose box) en el chat actual")

        await self._page.mouse.click(info["x"], info["y"])
        await self._page.wait_for_timeout(300)

        # Split on newlines — use Shift+Enter for line breaks so WA doesn't
        # send each line as a separate message.
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if line:
                await self._page.keyboard.type(line, delay=30)
            if i < len(lines) - 1:
                await self._page.keyboard.press("Shift+Enter")
        await self._page.wait_for_timeout(500)

        await self._page.keyboard.press("Enter")
        await self._page.wait_for_timeout(1000)

        # Verify the compose box is now empty (message was sent, not just new-lined).
        sent = await self._page.evaluate(_CHECK_COMPOSE_EMPTY_JS)
        if not sent:
            # WA may be configured to use Enter as new-line — click the send button.
            clicked = await self._page.evaluate(_CLICK_SEND_BTN_JS)
            await self._page.wait_for_timeout(800)
            if not clicked:
                raise RuntimeError("No se pudo enviar el mensaje: Enter no envió y no se encontró botón Send")
            still_there = not await self._page.evaluate(_CHECK_COMPOSE_EMPTY_JS)
            if still_there:
                raise RuntimeError("Mensaje sigue en el compose box después de intentar Send — no fue enviado")

        return {"selector": info.get("selector"), "x": info["x"], "y": info["y"]}

    async def navigate_to_new_chat(self) -> None:
        """Open the WhatsApp 'New chat' panel and wait for the contact list to appear."""
        clicked = await self._page.evaluate(_OPEN_NEW_CHAT_JS)
        if not clicked:
            raise RuntimeError("Could not find 'new-chat-outline' button in WA Web")
        # Wait for the contact list items to render
        await self._page.wait_for_selector('[role="listitem"]', timeout=8_000)
        await self._page.wait_for_timeout(500)

    async def extract_contacts(self) -> list[dict]:
        """Extract all visible contacts from the new-chat panel.

        Returns a list of dicts with keys 'name' (str) and 'subtitle' (str).
        Must be called after navigate_to_new_chat().
        """
        return await self._page.evaluate(_EXTRACT_CONTACTS_JS)

    async def close_new_chat(self) -> None:
        """Close the new-chat panel by clicking the back button (or pressing Escape)."""
        closed = await self._page.evaluate(_CLOSE_NEW_CHAT_JS)
        if not closed:
            await self._page.keyboard.press("Escape")
        await self._page.wait_for_timeout(400)

    async def get_contacts_scroll_state(self) -> dict | None:
        """Return {scrollTop, scrollHeight, clientHeight} of the contacts list container, or None."""
        return await self._page.evaluate(_CONTACTS_SCROLL_STATE_JS)

    async def scroll_contacts_down(self, css_pixels: int = 500) -> dict | None:
        """Scroll the contacts list down by css_pixels. Returns {before, after} scrollTop values."""
        return await self._page.evaluate(_SCROLL_CONTACTS_DOWN_JS, css_pixels)

    async def extract_visible_contacts(self) -> list[dict]:
        """Extract contacts currently visible in the viewport with their y-position.

        Returns list of {name, subtitle, vy} — only items within the viewport bounds.
        Must be called after navigate_to_new_chat().
        """
        return await self._page.evaluate(_EXTRACT_VISIBLE_CONTACTS_JS)

    async def extract_sidebar_updates(self) -> list[dict]:
        """Extract conversations with unread inbound messages from the main sidebar.

        Returns list of {name, unread_count} for each chat that has a visible
        unread-message badge.  unread_count may be an int or the raw string (e.g.
        '99+') depending on WA Web's rendering.
        """
        return await self._page.evaluate(_EXTRACT_SIDEBAR_UPDATES_JS)

    async def ensure_chat_list(self) -> None:
        """Close any overlay panel (New Chat, search, etc.) so the main chat list is visible."""
        # Try clicking the back button first — more reliable than Escape for the new-chat panel
        # left open by a previous list-contacts run.
        await self._page.evaluate(_CLOSE_NEW_CHAT_JS)
        await self._page.wait_for_timeout(300)
        # Escape as catch-all for search bars, drawers, or any other overlay.
        await self._page.keyboard.press("Escape")
        await self._page.wait_for_timeout(400)
        try:
            await self._page.wait_for_selector(
                '[data-testid="chat-list"], #pane-side', timeout=3_000
            )
        except Exception:
            # One more Escape in case a nested overlay was present.
            await self._page.keyboard.press("Escape")
            await self._page.wait_for_timeout(400)


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
