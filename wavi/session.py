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

# ── DOM scraping inventory ────────────────────────────────────────────────────
#
# All JS constants below query the WhatsApp Web DOM directly.  They are fast
# and reliable as long as WA's internal selectors stay stable.  When any of
# them starts returning wrong/empty results after a WA update, the selector
# listed in the table is the first thing to check.  Each entry also notes
# the vision-based fallback to implement if the DOM approach breaks for good.
#
# Constant                    | Key selector / signal            | Vision fallback
# ----------------------------|----------------------------------|----------------------------------
# _FETCH_BLOB_JS              | browser Fetch API (stable)       | N/A — pure browser API
# _DRAIN_JS                   | window.__wavi_blobs (injected)   | N/A — wavi-owned global
# _CLICK_SCROLL_BOTTOM_BTN_JS | position heuristic in #main      | find round button near bottom-right of chat panel
# _CHAT_SCROLL_JS             | conversation-panel-messages      | N/A — scroll state only
# _SCROLL_UP/DOWN_JS          | conversation-panel-messages      | N/A — scroll control only
# _GET_VISIBLE_MSG_IDS_JS     | [data-id] on message rows        | OCR fallback already used in runner.get()
# _FIND_COMPOSE_INPUT_JS      | footer [contenteditable="true"]  | locate text box by position (bottom of #main)
# _CHECK_COMPOSE_EMPTY_JS     | same as above                    | screenshot → check if compose area is blank
# _CLICK_SEND_BTN_JS          | span[data-icon="send"]           | locate arrow icon via vision near bottom-right
# _OPEN_NEW_CHAT_JS           | span[data-icon="new-chat-outline"]| locate pencil/compose icon in left sidebar
# _EXTRACT_CONTACTS_JS        | [role="listitem"] > [role="gridcell"] | OCR the "Nuevo chat" panel contact list
# _CLOSE_NEW_CHAT_JS          | span[data-icon="back-refreshed"] | locate back-arrow icon via vision in panel header
# _CLEAR_SIDEBAR_SEARCH_JS    | span[data-icon="search-back-btn"]| locate back-arrow at left of sidebar search bar
#                             |   or [data-testid="back"] in     |   via vision; or click search bar + Escape
#                             |   #side/#pane-side; fallback:    |
#                             |   clear input via React setter   |
# _CONTACTS_SCROLL_STATE_JS   | computed overflow on listitem parent | N/A — scroll state only
# _SCROLL_CONTACTS_DOWN_JS    | same as above                    | N/A — scroll control only
# _EXTRACT_VISIBLE_CONTACTS_JS| [role="listitem"] > [role="gridcell"] | OCR visible contact names
# _EXTRACT_SIDEBAR_UPDATES_JS | cell-frame-container cells;      | OCR sidebar: parse name + last-message +
#                             |   name via span[title],          |   timestamp per row; detect tick icon
#                             |   direction via msg-* tick icons |   via vision for inbound/outbound
# _CHAT_MESSAGES_JS           | #main [data-id] rows; own = tick | OCR chat bubbles (vision.py) →
#                             |   aria-label; quoted-message     |   bbox; own = right-aligned bubble
# _OPEN_MSG_MENU_JS           | aria-label "Opciones del mensaje"| hover bubble → locate chevron icon
# _CLICK_REPLY_ITEM_JS        | [role=menuitem] "Responder"      | OCR the open menu for "Responder"
# _REPLY_PREVIEW_JS           | #main footer minus the editor    | OCR the strip above the compose box
#
# ─────────────────────────────────────────────────────────────────────────────

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
    // Primary selector: always return its state even when not scrollable so the
    // caller can detect scrollTop≈0 and stop gracefully instead of treating a
    // short (single-message) chat as "panel not found".
    const primary = document.querySelector('[data-testid="conversation-panel-messages"]');
    if (primary)
        return { scrollTop: primary.scrollTop, scrollHeight: primary.scrollHeight, clientHeight: primary.clientHeight };
    // Fallback selectors: require scrollability to avoid matching unrelated containers.
    for (const s of ['#main div[role="region"]', '#main .copyable-area']) {
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

# Safety guard for search_contacts: true when keyboard focus sits inside the
# open chat's panel (#main — its compose box). A search-box click that doesn't
# take focus leaves it there, and the query would be typed as a draft into
# whatever chat is open (real case 2026-10-03, "DATA LAKE - Tecnico" ended up
# in the compose box of "DATA LAKE - Gerencia"). Read-only check, not a locator.
_FOCUS_IN_CHAT_PANEL_JS = """
() => {
    const a = document.activeElement;
    return !!(a && a.closest && a.closest('#main'));
}
"""

# Text of the compose box's last paragraph. After Shift+Enter inside a list
# WA's editor auto-continues it ("2. ", "• "), so typing the caller's own
# "2. dos" produced "2. 2. dos" (reported by DataLake 2026-10-04).
_LAST_COMPOSE_LINE_JS = """
() => {
    // The focused editor (compose box or the edit dialog), else the compose box.
    const a = document.activeElement;
    const ed = (a && a.closest && a.closest('[contenteditable="true"]'))
            || document.querySelector('footer [contenteditable="true"]');
    const ps = ed ? ed.querySelectorAll('p') : [];
    return ps.length ? ps[ps.length - 1].innerText : null;
}
"""

# Full compose text, one line per paragraph (empty paragraphs → "").
_COMPOSE_TEXT_JS = """
() => {
    const ps = document.querySelectorAll('footer [contenteditable="true"] p');
    if (!ps.length) return null;  // unknown editor DOM — can't verify
    return [...ps].map(p => p.innerText.replace(/\\n$/, '')).join('\\n');
}
"""

_FOCUS_IN_COMPOSE_JS = """
() => {
    const a = document.activeElement;
    return !!(a && a.closest && a.closest('footer [contenteditable="true"]'));
}
"""


def _same_letters(a: str, b: str) -> bool:
    """Compare ignoring everything but letters/digits — WA's editor rewrites
    list markers ("- " → "• ") and may style markdown, but a lost or extra
    character is a real difference."""
    def keep(s: str) -> str:
        return "".join(ch for ch in s if ch.isalnum())
    return keep(a) == keep(b)


# ── Edit / reply (wavi edit, wavi reply) ─────────────────────────────────────
# Temporary DOM bridge (vision-first policy, docs/plan-mejoras.md §4.8): the
# rows below are what _locate_message() picks from. Vision replacement: OCR
# the chat bubbles (wavi/vision.py) → bbox → hover the bubble.
# Own messages carry a hidden "Tú:"/"You:" label; data-pre-plain-text holds
# "[5:35 p. m., 8/10/2026] Name: ". Text is rebuilt with emoji <img alt>.
_CHAT_MESSAGES_JS = """
() => {
    const textOf = (el) => {
        let out = '';
        el.childNodes.forEach(n => {
            if (n.nodeType === 3) out += n.textContent;
            else if (n.tagName === 'IMG') out += n.getAttribute('alt') || '';
            else if (n.tagName === 'BR') out += '\\n';
            else out += textOf(n);
        });
        return out;
    };
    // "Tú:" only labels some own bubbles (first of a run); the delivery
    // ticks ("Leído", "Entregado", …) are on every own message and no other.
    const OWN = /^(t[uú]:|you:|le[ií]do|entregado|enviado|pendiente|read|delivered|sent|pending)$/i;
    const rows = [...document.querySelectorAll('#main [data-id]')];
    return rows.map(r => {
            const pre = r.querySelector('[data-pre-plain-text]');
            const quote = r.querySelector('[data-testid="quoted-message"]');
            const bodies = [...r.querySelectorAll('[data-testid="selectable-text"]')]
                .filter(e => !(quote && quote.contains(e)));
            const body = bodies[bodies.length - 1];
            return {
                id: r.getAttribute('data-id'),
                own: [...r.querySelectorAll('[aria-label]')].some(e =>
                    OWN.test((e.getAttribute('aria-label') || '').trim())),
                pre: pre ? pre.getAttribute('data-pre-plain-text') : null,
                text: body ? textOf(body) : '',
                quoted: quote ? (quote.innerText || '') : null,
            };
        }).filter(m => m.pre || m.text);
}
"""

_CLICK_REPLY_ITEM_JS = """
() => {
    const it = [...document.querySelectorAll('[role="menuitem"]')].find(e =>
        /^(responder|reply)$/i.test((e.innerText || '').trim()));
    if (!it) return false;
    it.click();
    return true;
}
"""

# Text of the quote panel WA shows above the compose box after "Responder":
# everything in the footer except the editor itself. null → no footer.
_REPLY_PREVIEW_JS = """
() => {
    const f = document.querySelector('#main footer');
    if (!f) return null;
    const c = f.cloneNode(true);
    c.querySelectorAll('[contenteditable="true"]').forEach(e => e.remove());
    return (c.innerText || '').trim();
}
"""


def _pre_sender(pre: str | None) -> str:
    """'[4:38 p. m., 8/10/2026] Matias Becerro: ' → 'Matias Becerro'."""
    if not pre or "] " not in pre:
        return ""
    return pre.split("] ", 1)[1].rstrip().rstrip(":").strip()


def _locate_message(
    rows: list[dict], match: str, *, sender: str | None = None,
    index: int | None = None, own_only: bool = False,
) -> dict:
    """Pick exactly one chat message whose text contains MATCH (accent/case
    insensitive). SENDER narrows by the name in data-pre-plain-text; INDEX
    (1-based, oldest first) picks among several hits. Zero hits, or several
    without INDEX, raise RuntimeError listing what was seen."""
    pool = [m for m in rows if m.get("own")] if own_only else rows
    kind = "mensaje propio" if own_only else "mensaje"
    q = _normalize_name(match)
    hits = [m for m in pool if q and q in _normalize_name(m.get("text") or "")]
    if sender:
        sq = _normalize_name(sender)
        hits = [m for m in hits if sq in _normalize_name(_pre_sender(m.get("pre")))]
    if not hits:
        of = f" de '{sender}'" if sender else ""
        raise RuntimeError(
            f"No encontré un {kind}{of} que contenga '{match}' entre los "
            f"{len(pool)} mensajes {'propios ' if own_only else ''}cargados del chat."
        )
    if index is not None:
        if not 1 <= index <= len(hits):
            raise RuntimeError(f"--index {index} fuera de rango: hay {len(hits)} coincidencia(s).")
        return hits[index - 1]
    if len(hits) > 1:
        lines = "\n".join(
            f"  {i}. {m.get('pre') or '?'} {m['text'][:60]!r}" for i, m in enumerate(hits, 1))
        raise RuntimeError(
            f"Hay {len(hits)} {kind.replace('mensaje', 'mensajes').replace('propio', 'propios')} "
            f"que contienen '{match}' — usá un fragmento más específico"
            f"{'' if own_only else ' o --index N'}:\n{lines}"
        )
    return hits[0]

_OPEN_MSG_MENU_JS = """
(id) => {
    const row = document.querySelector('#main [data-id="' + id + '"]');
    if (!row) return false;
    const btn = [...row.querySelectorAll('[aria-label]')].find(e =>
        /opciones del mensaje|message options|context menu|men[uú] contextual/i.test(e.getAttribute('aria-label')));
    if (!btn) return false;
    btn.click();
    return true;
}
"""

_MSG_BUBBLE_POS_JS = """
(id) => {
    const row = document.querySelector('#main [data-id="' + id + '"]');
    if (!row) return null;
    const el = row.querySelector('[data-testid="msg-container"]') || row;
    el.scrollIntoView({block: 'center'});
    const r = el.getBoundingClientRect();
    return {x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2)};
}
"""

_CLICK_EDIT_ITEM_JS = """
() => {
    const it = [...document.querySelectorAll('[role="menuitem"]')].find(e =>
        /^(editar|edit)$/i.test((e.innerText || '').trim()));
    if (!it) return false;
    it.click();
    return true;
}
"""

_EDIT_DIALOG_TEXT_JS = """
() => {
    const d = document.querySelector('[role="dialog"]');
    const ed = d && d.querySelector('[contenteditable="true"]');
    if (!ed) return null;
    const ps = ed.querySelectorAll('p');
    const line = (p) => {
        let out = '';
        p.childNodes.forEach(function walk(n) {
            if (n.nodeType === 3) out += n.textContent;
            else if (n.tagName === 'IMG') out += n.getAttribute('alt') || '';
            else n.childNodes.forEach(walk);
        });
        return out;
    };
    return ps.length ? [...ps].map(line).join('\\n') : ed.innerText;
}
"""

_EDIT_DIALOG_FOCUS_JS = """
() => {
    const a = document.activeElement;
    return !!(a && a.closest && a.closest('[role="dialog"] [contenteditable="true"]'));
}
"""

_CLICK_SEND_EDIT_JS = """
() => {
    const d = document.querySelector('[role="dialog"]');
    if (!d) return false;
    const b = [...d.querySelectorAll('[aria-label]')].find(e =>
        /editado|edited/i.test(e.getAttribute('aria-label')));
    if (!b) return false;
    (b.closest('button') || b).click();
    return true;
}
"""

EDIT_WINDOW_MIN = 15

_PRE_RE = __import__("re").compile(r"^\[(?P<time>[^,\]]+),\s*(?P<date>[^\]]+)\]")


def _parse_pre_plain(pre: str | None, day_first: bool | None = None):
    """'[5:35 p. m., 8/10/2026] Name: ' → datetime (session's date order)."""
    from datetime import datetime as _DT

    from wavi.vision import _parse_time_str, split_numeric_date
    m = _PRE_RE.match(pre or "")
    if not m:
        return None
    hhmm = _parse_time_str(m.group("time"))
    parts = m.group("date").strip().split("/")
    if not hhmm or len(parts) != 3:
        return None
    try:
        a, b, y = (int(x) for x in parts)
        d, mo = split_numeric_date(a, b, day_first)
        h, mi = (int(x) for x in hhmm.split(":"))
        return _DT(y if y > 100 else 2000 + y, mo, d, h, mi)
    except ValueError:
        return None


# WA's own UI language (<html lang>; navigator.language is Chrome's and can
# differ) plus the dates of the loaded messages — see vision.infer_day_first.
_DATE_ORDER_SIGNALS_JS = """
() => ({
    lang: document.documentElement.lang || null,
    dates: [...document.querySelectorAll('#main [data-pre-plain-text]')]
        .map(e => e.getAttribute('data-pre-plain-text')),
})
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

# DOM signal: span[data-icon="send"] — the send arrow button in the compose footer.
# Vision fallback: locate the send-arrow icon near the bottom-right of #main via screenshot.
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

# NOT the primary path anymore — see navigate_to_new_chat() below, which
# tries vision first (locate_new_chat_button() in wavi/vision_grounding.py)
# and only falls back to this DOM lookup if vision can't find anything
# (missing extra/weights, or a screen this function isn't calibrated for).
# Kept only as a temporary, strategic bridge for that fallback case — per
# project policy (docs/plan-mejoras.md §4.8), a DOM patch is never treated
# as the permanent resolution for a signal vision can locate instead, even
# when the patch itself is correct. This is that patch:
#
# DOM signal: span[data-icon="new-chat-outline"] (left sidebar compose button).
# Confirmed broken against a live session, 2026-09-18: WA replaced the
# pencil icon with a green "+" button that carries no data-icon attribute
# at all anymore — inspected live via 'wavi debug-open', the only remaining
# anchor is aria-label="Nuevo chat" (its SVG <title> is "ic-add", shared
# with an unrelated "Nueva lista" button elsewhere in the DOM, so the icon
# alone is ambiguous; aria-label is the one attribute that picks out this
# specific button). Kept the old data-icon lookups first in case a future
# WA build reverts, same locale-agnostic-first, aria-label-fallback pattern
# as _CLICK_SEND_BTN_JS above.
_OPEN_NEW_CHAT_JS = """
() => {
    const icon = document.querySelector('span[data-icon="new-chat-outline"]') ||
                 document.querySelector('span[data-icon="new-chat-alt"]');
    if (icon) {
        const btn = icon.closest('button');
        if (btn) { btn.click(); return true; }
    }
    for (const lbl of ['Nuevo chat', 'New chat']) {
        const btn = document.querySelector(`button[aria-label="${lbl}"]`);
        if (btn) { btn.click(); return true; }
    }
    return false;
}
"""

# DOM signal: [role="listitem"] > [role="gridcell"] inside the "Nuevo chat" panel.
# Vision fallback: OCR the panel — contact names appear as a vertical list of
#   strings in a fixed-width column on the left side of the screen.
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

# DOM signal: span[data-icon="back-refreshed"] — the back arrow in the "Nuevo chat" header.
# Vision fallback: locate a left-pointing arrow icon in the top-left of the left panel.
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

# DOM signal: span[data-icon="search-back-btn"] or [data-testid="back"] inside #side/#pane-side.
# Clicking the search back button exits search mode and restores the normal sidebar — the only
# clean exit when the sidebar search bar is filled but the page focus is elsewhere (e.g. after
# navigate_to_contact opens a chat and leaves the search bar filled but unfocused).
# Fallback: clear the input value directly via React's native setter so the framework detects
# the change without needing DOM focus.
# Vision fallback: locate the left-pointing arrow at the left edge of the sidebar search bar.
_CLEAR_SIDEBAR_SEARCH_JS = """
() => {
    // Try to click the search back button (exits search mode entirely).
    const backBtn =
        document.querySelector('span[data-icon="search-back-btn"]')?.closest('button')
     || document.querySelector('#side [data-testid="back"]')
     || document.querySelector('#pane-side [data-testid="back"]');
    if (backBtn) {
        backBtn.click();
        return 'back_btn';
    }
    // Fallback: find the sidebar search input and clear it programmatically.
    // React controls the input value, so we use the native setter to bypass
    // the synthetic event layer and then fire 'input' so React reconciles.
    const inp =
        document.querySelector('[data-testid="search-input"]')
     || document.querySelector('#side input[type="text"]')
     || document.querySelector('#pane-side input[type="text"]');
    if (inp && inp.value) {
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
        setter.call(inp, '');
        inp.dispatchEvent(new Event('input', { bubbles: true }));
        return 'cleared_input';
    }
    return null;
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

# DOM signals used by this function:
#   - Root:      [data-testid="chat-list"] or #pane-side
#   - Cells:     [data-testid="cell-frame-container"] or li[role="listitem"]
#   - Name:      [data-testid="cell-frame-title"] > span[title]  ← title attr = clean name
#   - Preview:   various subtitle selectors (see inline comments)
#   - Timestamp: [data-testid="cell-frame-timestamp"]
#   - Direction: span[data-icon="msg-check|msg-dbl-check|msg-dbl-check-ack|msg-time"]
#                present → outbound; absent → inbound
#
# Vision fallback: screenshot the sidebar, OCR each visible row.
#   - Name: first bold/large text per row (left-aligned)
#   - Preview: smaller text below the name
#   - Timestamp: right-aligned text in the row header
#   - Direction: presence of a tick icon (✓ or ✓✓) to the left of the preview text
_EXTRACT_SIDEBAR_UPDATES_JS = """
() => {
    const chatList = document.querySelector('[data-testid="chat-list"]')
                  || document.querySelector('#pane-side');
    if (!chatList) return [];

    const results = [];
    const cells = chatList.querySelectorAll(
        '[data-testid="cell-frame-container"], li[role="listitem"], [role="listitem"]'
    );

    cells.forEach(cell => {
        // Contact name: prefer span with title attribute (clean, no badge text)
        const titleEl = cell.querySelector('[data-testid="cell-frame-title"] span[title]')
                     || cell.querySelector('span[title]')
                     || cell.querySelector('[data-testid="cell-frame-title"]');
        const name = titleEl
            ? (titleEl.getAttribute('title') || titleEl.textContent || '').trim()
            : '';
        if (!name) return;

        // Last message preview
        const subtitleEl = cell.querySelector('[data-testid="last-msg-status"] ~ span')
                        || cell.querySelector('[data-testid="cell-frame-secondary-detail"] span[dir]')
                        || cell.querySelector('span[data-testid="last-msg"]')
                        || cell.querySelector('span[dir="ltr"] ~ span[dir="auto"]')
                        || cell.querySelector('span[dir="ltr"]');
        const last_message = subtitleEl
            ? (subtitleEl.textContent || '').trim()
            : '';

        // Timestamp
        const tsEl = cell.querySelector('[data-testid="cell-frame-timestamp"]')
                  || cell.querySelector('div[class*="last-msg-time"] span')
                  || cell.querySelector('span[dir="auto"] ~ div span');
        const timestamp = tsEl ? (tsEl.textContent || '').trim() : '';

        // Direction: outbound messages have a delivery-status tick icon;
        // inbound messages never show those icons in the sidebar.
        const tickIcon = cell.querySelector(
            'span[data-icon="msg-check"], span[data-icon="msg-dbl-check"], ' +
            'span[data-icon="msg-dbl-check-ack"], span[data-icon="msg-time"]'
        );
        const direction = tickIcon ? 'outbound' : 'inbound';

        results.push({ name, last_message, timestamp, direction });
    });

    return results;
}
"""

# Search-box results: WA groups matches under "Chats" / "Contactos" /
# "Grupos en común" / "Mensajes" headers, and the SAME display name can
# legitimately appear more than once (an existing chat plus one or more
# unrelated contacts sharing that name) — see ADR-010 / navigate_to_contact.
# We deliberately do NOT try to tell sections apart here (fragile: headers
# aren't tagged with a stable selector); instead every distinct
# (name, subtitle) row is surfaced so the caller can disambiguate with a
# human instead of guessing.
# The self-chat ("Name (Tú)") is not a cell-frame-container: WA renders it
# as [data-testid="message-yourself-row"], with its time in
# cell-frame-primary-detail — without both it never shows up as a result
# (seen 2026-10-08). DOM bridge until search moves to vision.
_RESULT_ROW_SEL = '[data-testid="cell-frame-container"], [data-testid="message-yourself-row"]'

_SEARCH_RESULTS_JS = """
() => {
    const cells = document.querySelectorAll('""" + _RESULT_ROW_SEL + """');
    const out = [];
    cells.forEach((cell) => {
        const titleEl = cell.querySelector('[data-testid="cell-frame-title"] span[title]')
                     || cell.querySelector('span[title]')
                     || cell.querySelector('[data-testid="cell-frame-title"]');
        const name = titleEl
            ? (titleEl.getAttribute('title') || titleEl.textContent || '').trim()
            : '';
        if (!name) return;

        const subtitleEl = cell.querySelector('[data-testid="cell-frame-secondary-detail"] span')
                        || cell.querySelector('[data-testid="cell-frame-secondary-detail"]');
        const subtitle = subtitleEl ? (subtitleEl.textContent || '').trim() : '';

        // Only present on actual chats (Chats section) — a bare saved/unsaved
        // contact with no conversation history has no last-activity time.
        // Used to rank real chats above never-messaged contacts when a name
        // is ambiguous, without trying to parse WA's date/time formats.
        const tsEl = cell.querySelector('[data-testid="cell-frame-timestamp"]')
                  || cell.querySelector('[data-testid="cell-frame-primary-detail"]');
        const last_activity = tsEl ? (tsEl.textContent || '').trim() : '';

        const rect = cell.getBoundingClientRect();
        out.push({
            name,
            subtitle,
            last_activity,
            x: Math.round(rect.x + rect.width / 2),
            y: Math.round(rect.y + rect.height / 2),
        });
    });
    return out;
}
"""


# ── Helpers ───────────────────────────────────────────────────────────────────

def _normalize_name(s: str) -> str:
    """Lowercase, strip accents, collapse whitespace — for name matching."""
    import unicodedata
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return " ".join(s.lower().split())


def _name_matches(query: str, candidate_name: str) -> bool:
    """True if CANDIDATE_NAME could plausibly be what QUERY refers to.

    WA's search also returns rows from unrelated "shared groups" — a group
    whose own name doesn't contain the query at all, just because the
    person being searched for is a member. Those must never be presented as
    if they were a match on the query itself.
    """
    q, c = _normalize_name(query), _normalize_name(candidate_name)
    return q in c or c in q


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

    from wavi.vision import HEADER_PX as HEADER_Y
    from wavi.vision import SIDEBAR_PX as SIDEBAR_X

    SEARCH_X       = 317
    SEARCH_Y       = 80

    _AUTHED_SEL = "[data-testid='chat-list'], #side, input[role='textbox']"

    def __init__(
        self,
        profile_dir: str | Path,
        headless: bool = True,
        chrome_path: Path | None = None,
    ):
        self.profile_dir   = Path(profile_dir)
        self.headless      = headless
        self.chrome_path   = Path(chrome_path) if chrome_path else REAL_CHROME
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

        # A session that doesn't exist (dangling alias, wrong path) has no
        # port file → CDP_PORT, which may be another session's live daemon:
        # the fallback below would kill it and open an empty profile. Real
        # case 2026-10-08: a wrong relative path killed the default daemon.
        if not self.profile_dir.is_dir():
            await self._pw.stop()
            self._pw = None
            raise RuntimeError(
                f"La sesión no existe: {self.profile_dir} — no se abrió nada. "
                f"Revisá 'wavi alias list' o creala con 'wavi connect'."
            )

        # No daemon: start headless Chrome (status/run without a prior connect)
        import sys
        print("⚠️  No daemon detectado — abriendo Chrome en fallback headless...", file=sys.stderr)

        self.profile_dir.mkdir(parents=True, exist_ok=True)
        _kill_port(self._port)
        (self.profile_dir / "SingletonLock").unlink(missing_ok=True)

        args = [
            str(self.chrome_path),
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
            import os
            import signal
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

    async def _debug_screenshot(self, tag: str) -> Path | None:
        import time as _time
        debug_dir = self.profile_dir / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        shot_path = debug_dir / f"{tag}_{int(_time.time())}.png"
        try:
            await self._page.screenshot(path=str(shot_path))
            return shot_path
        except Exception:
            return None

    async def search_contacts(self, query: str, *, wait_results_ms: int = 5_000) -> list[dict]:
        """Type QUERY into the search box and return every distinct result
        row ({name, subtitle, x, y}) — chats, saved contacts, and unsaved
        numbers alike. Returns [] if nothing showed up within the timeout
        (e.g. a freshly-linked session still syncing its chat list — see
        navigate_to_contact's refresh-and-retry)."""
        # Click en el cuadro de búsqueda por coordenadas (ADR-001: sin locator)
        await self._page.mouse.click(self.SEARCH_X, self.SEARCH_Y)
        await self._page.wait_for_timeout(300)

        # Never type while focus is still in the open chat: Cmd+A/Delete
        # would wipe its draft and the query would land in its compose box.
        if await self._page.evaluate(_FOCUS_IN_CHAT_PANEL_JS):
            await self._page.wait_for_timeout(700)
            await self._page.mouse.click(self.SEARCH_X, self.SEARCH_Y)
            await self._page.wait_for_timeout(300)
            if await self._page.evaluate(_FOCUS_IN_CHAT_PANEL_JS):
                shot_path = await self._debug_screenshot("search_focus_lost")
                raise RuntimeError(
                    "El click en el buscador no tomó el foco (sigue en el chat "
                    "abierto) — no se escribió nada para no dejar texto en ese "
                    f"chat. Ver captura: {shot_path}"
                )

        # Limpiar: seleccionar todo y borrar (Mac: Cmd+A, Windows: Ctrl+A)
        import sys as _sys
        _select_all = "Meta+a" if _sys.platform == "darwin" else "Control+a"
        await self._page.keyboard.press(_select_all)
        await self._page.wait_for_timeout(100)
        await self._page.keyboard.press("Delete")
        await self._page.wait_for_timeout(200)

        # Escribir el contacto con delays realistas
        await self._page.keyboard.type(query, delay=40)

        try:
            await self._page.wait_for_selector(
                _RESULT_ROW_SEL, timeout=wait_results_ms
            )
        except Exception:
            return []
        await self._page.wait_for_timeout(400)
        return await self._page.evaluate(_SEARCH_RESULTS_JS)

    async def open_search_result(
        self, x: int, y: int, expected_name: str | None = None
    ) -> bool:
        """Click a result row (coordinates from search_contacts) and verify
        a real conversation ended up open — never assume success from the
        click alone.

        A conversation panel being present is NOT enough: if some other chat
        was already open (the previous capture's), a click that silently
        misses (list re-render, an incoming-call popup stealing the event —
        real case 2026-09-24, a whole capture landed under the wrong
        contact's folder) leaves that stale chat on screen and the panel
        check passes anyway. When EXPECTED_NAME is given, the open chat's
        header title must actually match it.
        """
        await self._page.mouse.click(x, y)
        try:
            await self._page.wait_for_selector(
                "[data-testid='conversation-panel-messages']", timeout=15_000
            )
        except Exception:
            return False
        await self._page.wait_for_timeout(1500)
        if expected_name is None:
            return True
        title = await self.open_chat_title()
        if title and _name_matches(expected_name, title):
            return True
        import sys
        print(
            f"[wavi] open_search_result: header shows {title!r}, expected "
            f"{expected_name!r} — click did not open the chat", file=sys.stderr,
        )
        return False

    async def open_chat_title(self) -> str | None:
        """Display name in the header of the currently open chat (first line
        of `#main header`), or None if no chat is open."""
        try:
            text = await self._page.evaluate(
                "() => document.querySelector('#main header')?.innerText || null"
            )
        except Exception:
            return None
        if not text:
            return None
        return text.strip().split("\n", 1)[0].strip() or None

    async def _resolve_contact(self, contact: str, pick: int | None = None) -> dict:
        """Find CONTACT's chat/entry, disambiguating with a human when more
        than one distinct match exists rather than guessing which one they
        meant — the same display name can legitimately belong to an
        existing chat AND one or more unrelated saved/unsaved contacts.
        See docs/adr/ADR-010-contact-disambiguation.md.

        PICK (1-based) selects an option non-interactively — for scripts/
        agents that already know which index they want (e.g. from a prior
        failed call's printed list), without needing a TTY.

        Never returns a wrong contact silently: raises RuntimeError if
        nothing matches (even after refreshing the contact list) or if
        disambiguation is needed but no human/PICK is available to resolve it.
        """
        import sys as _sys

        candidates = await self.search_contacts(contact)
        if not candidates:
            # Refresh: forcing the "New chat" panel open makes WA sync/render
            # its full contact list, surfacing entries the sidebar search
            # may not have indexed yet (e.g. right after a fresh QR link).
            try:
                await self.navigate_to_new_chat()
                await self.close_new_chat()
            except Exception:
                pass
            candidates = await self.search_contacts(contact, wait_results_ms=15_000)

        if not candidates:
            shot_path = await self._debug_screenshot("no_contact_found")
            raise RuntimeError(
                f"No se encontró ningún chat/contacto que coincida con "
                f"'{contact}', ni siquiera después de actualizar la lista "
                f"de contactos. Ver captura: {shot_path}"
            )

        # WA's search also returns rows from unrelated "shared groups" (a
        # group whose OWN name doesn't match at all, just because CONTACT is
        # a member) — e.g. searching "Rodolfo Prado" surfacing "Blanca y sus
        # pollitos". Keep only rows whose own name actually matches the
        # query; never present those as if they were "Rodolfo Prado".
        matching = [c for c in candidates if _name_matches(contact, c["name"])]
        if not matching:
            shot_path = await self._debug_screenshot("no_contact_found")
            raise RuntimeError(
                f"WA devolvió resultados para '{contact}' pero ninguno tiene "
                f"ese nombre (probablemente grupos compartidos sin relación). "
                f"Ver captura: {shot_path}"
            )

        seen: set[tuple[str, str]] = set()
        unique: list[dict] = []
        for c in matching:
            key = (c["name"], c["subtitle"])
            if key in seen:
                continue
            seen.add(key)
            unique.append(c)

        # Real chats (have a last-activity time) ahead of bare contacts
        # that were never messaged — WA already orders actual chats by
        # recency, so a stable sort preserves that ordering within each group.
        unique.sort(key=lambda c: 0 if c.get("last_activity") else 1)

        if pick is not None:
            if not (1 <= pick <= len(unique)):
                raise RuntimeError(
                    f"--pick {pick} está fuera de rango — hay {len(unique)} "
                    f"coincidencia(s) para '{contact}'."
                )
            chosen = unique[pick - 1]
        elif len(unique) == 1:
            chosen = unique[0]
        else:
            import click as _click
            if not _sys.stdin.isatty():
                lines = "\n".join(
                    f"  [{i}] {c['name']}" + (f" — {c['subtitle']}" if c["subtitle"] else "")
                    for i, c in enumerate(unique, 1)
                )
                raise RuntimeError(
                    f"Hay {len(unique)} coincidencias para '{contact}' y no hay "
                    f"una terminal interactiva para preguntar cuál. Pasá "
                    f"--pick <n> con el número de la lista, o sé más "
                    f"específico (ej. incluí el número de teléfono):\n{lines}"
                )
            _click.echo(f"\nHay {len(unique)} coincidencias para '{contact}' — elegí una:\n")
            for i, c in enumerate(unique, 1):
                detail = f" — {c['subtitle']}" if c["subtitle"] else ""
                _click.echo(f"  [{i}] {c['name']}{detail}")
            choice = _click.prompt("\nNúmero", type=_click.IntRange(1, len(unique)))
            chosen = unique[choice - 1]

        detail = f" — {chosen['subtitle']}" if chosen["subtitle"] else ""
        print(f"[wavi] Contacto confirmado: {chosen['name']}{detail}", file=_sys.stderr)
        return chosen

    async def navigate_to_contact(self, contact: str, pick: int | None = None) -> None:
        chosen = await self._resolve_contact(contact, pick=pick)

        opened = await self.open_search_result(
            chosen["x"], chosen["y"], expected_name=chosen["name"]
        )
        if not opened:
            # The row's coordinates could have shifted (list re-rendered) —
            # resolve and click once more before giving up.
            chosen = await self._resolve_contact(contact, pick=pick)
            opened = await self.open_search_result(
                chosen["x"], chosen["y"], expected_name=chosen["name"]
            )

        if not opened:
            shot_path = await self._debug_screenshot("navigate_failed")
            import sys
            print(
                f"[wavi] navigate_to_contact: no se pudo abrir el chat con "
                f"'{contact}' — screenshot: {shot_path}", file=sys.stderr,
            )
            raise RuntimeError(
                f"No se pudo abrir el chat con '{contact}'. "
                f"Ver captura de debug: {shot_path}"
            )

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

        for _attempt in range(5):
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

        await self.detect_date_order()

    async def detect_date_order(self) -> bool | None:
        """Set the process-wide numeric date order (vision.set_date_order)
        from WA's UI language and the dates visible in the open chat.
        Returns day_first, or None when the page gave nothing to go on."""
        from wavi.vision import infer_day_first, set_date_order
        try:
            info = await self._page.evaluate(_DATE_ORDER_SIGNALS_JS)
        except Exception:
            return None  # best-effort: never let it break opening a chat
        if not isinstance(info, dict):
            return None
        day_first = infer_day_first(info.get("lang"), info.get("dates") or [])
        set_date_order(day_first)
        return day_first

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

    async def click_load_older_if_present(self) -> str | None:
        """Click the 'load older messages from phone' pill if visible.

        WA Web shows this pill at the top of a chat when there are messages on
        the phone that haven't been synced to the web client yet. Clicking it
        triggers a sync and reveals older messages.

        Returns the pill's text if clicked, None if not found.
        """
        return await self._page.evaluate("""
            () => {
                const KEYWORDS = [
                    'anteriores', 'older messages', 'obtener mensajes',
                    'load older', 'clic aquí', 'click here',
                ];
                // Walk all visible elements; prefer smaller containers over body/html.
                const candidates = document.querySelectorAll(
                    'div[role="button"], span[role="button"], button, [data-testid]'
                );
                for (const el of candidates) {
                    if (!el.offsetParent) continue;   // hidden
                    const text = el.textContent?.toLowerCase() || '';
                    if (KEYWORDS.some(k => text.includes(k)) && text.length < 200) {
                        el.click();
                        return el.textContent.trim();
                    }
                }
                return null;
            }
        """)

    async def edit_message(
        self, match: str, new_text: str, *, fragment: bool = False, now=None,
    ) -> dict:
        """Edit one of my own messages in the open chat (WA allows it for
        EDIT_WINDOW_MIN minutes after sending).

        MATCH picks the message: an own message whose text contains it
        (accent/case-insensitive). Exactly one must match — zero or several
        raise RuntimeError listing what was seen. With FRAGMENT, NEW_TEXT
        replaces MATCH inside the message; otherwise it replaces the whole
        text. Nothing is changed unless the editor ends up holding exactly
        the intended text.
        """
        import sys as _sys
        from datetime import datetime as _DT

        now = now or _DT.now()
        rows = await self._page.evaluate(_CHAT_MESSAGES_JS)
        target = _locate_message(rows, match, own_only=True)
        sent_at = _parse_pre_plain(target["pre"])
        if sent_at is not None:
            age_min = (now - sent_at).total_seconds() / 60
            if age_min > EDIT_WINDOW_MIN:
                raise RuntimeError(
                    f"El mensaje se envió a las {sent_at:%H:%M} ({age_min:.0f} min) — "
                    f"WhatsApp solo permite editar durante {EDIT_WINDOW_MIN} min."
                )

        if fragment:
            old = target["text"]
            if match in old:
                intended = old.replace(match, new_text, 1)
            else:
                raise RuntimeError(
                    f"'{match}' no aparece literal en el mensaje — pasá el texto "
                    f"completo nuevo sin --fragment."
                )
        else:
            intended = new_text

        pos = await self._page.evaluate(_MSG_BUBBLE_POS_JS, target["id"])
        if not pos:
            raise RuntimeError("El mensaje dejó de estar en pantalla")
        await self._page.mouse.move(pos["x"], pos["y"])
        await self._page.wait_for_timeout(600)
        if not await self._page.evaluate(_OPEN_MSG_MENU_JS, target["id"]):
            raise RuntimeError("No se encontró el menú de opciones del mensaje")
        await self._page.wait_for_timeout(800)
        if not await self._page.evaluate(_CLICK_EDIT_ITEM_JS):
            await self._page.keyboard.press("Escape")
            raise RuntimeError(
                "WhatsApp no ofrece 'Editar' para ese mensaje (pasaron más de "
                f"{EDIT_WINDOW_MIN} min, o no es editable)."
            )
        await self._page.wait_for_timeout(1200)
        if not await self._page.evaluate(_EDIT_DIALOG_FOCUS_JS):
            await self._page.keyboard.press("Escape")
            raise RuntimeError("El editor del mensaje no tomó el foco — no se cambió nada")

        def _cancel_reason(shown: str | None) -> str:
            return f"el editor muestra {(shown or '')[:60]!r}"

        try:
            for _attempt in range(2):
                _select_all = "Meta+a" if _sys.platform == "darwin" else "Control+a"
                await self._page.keyboard.press(_select_all)
                await self._page.keyboard.press("Delete")
                await self._page.wait_for_timeout(200)
                await self._type_compose(intended)
                shown = await self._page.evaluate(_EDIT_DIALOG_TEXT_JS)
                if shown is not None and _same_letters(shown, intended):
                    break
                print(f"[wavi] edit_message: {_cancel_reason(shown)} — reintento", file=_sys.stderr)
            else:
                raise RuntimeError(
                    f"El texto en el editor no coincide ({_cancel_reason(shown)}) — "
                    "se canceló la edición, el mensaje quedó como estaba."
                )
        except Exception:
            await self._page.keyboard.press("Escape")
            await self._page.wait_for_timeout(400)
            raise

        if not await self._page.evaluate(_CLICK_SEND_EDIT_JS):
            await self._page.keyboard.press("Enter")
        await self._page.wait_for_timeout(1500)
        if await self._page.evaluate(_EDIT_DIALOG_FOCUS_JS):
            await self._page.keyboard.press("Escape")
            raise RuntimeError("El diálogo de edición no se cerró — la edición no se guardó")

        after = {m["id"]: m for m in await self._page.evaluate(_CHAT_MESSAGES_JS)}
        saved = after.get(target["id"], {}).get("text")
        return {
            "id": target["id"],
            "sent_at": sent_at.isoformat(timespec="minutes") if sent_at else None,
            "before": target["text"],
            "after": saved,
            "verified": saved is not None and _same_letters(saved, intended),
        }

    async def reply_message(
        self, match: str, text: str, *, sender: str | None = None, index: int | None = None,
    ) -> dict:
        """Reply to (quote) one message of the open chat — own or someone else's.

        MATCH/SENDER/INDEX pick the message (see _locate_message). Nothing is
        sent unless WA's quote panel above the compose box shows that exact
        message; any failure cancels the quote with Escape. TEXT then goes
        through send_message() with all of its guards.
        """
        rows = await self._page.evaluate(_CHAT_MESSAGES_JS)
        target = _locate_message(rows, match, sender=sender, index=index)
        snippet = _normalize_name(target["text"])[:30]

        pos = await self._page.evaluate(_MSG_BUBBLE_POS_JS, target["id"])
        if not pos:
            raise RuntimeError("El mensaje dejó de estar en pantalla")
        await self._page.mouse.move(pos["x"], pos["y"])
        await self._page.wait_for_timeout(600)
        if not await self._page.evaluate(_OPEN_MSG_MENU_JS, target["id"]):
            raise RuntimeError("No se encontró el menú de opciones del mensaje")
        await self._page.wait_for_timeout(800)
        if not await self._page.evaluate(_CLICK_REPLY_ITEM_JS):
            await self._page.keyboard.press("Escape")
            raise RuntimeError("WhatsApp no ofrece 'Responder' para ese mensaje — no se envió nada")
        await self._page.wait_for_timeout(800)

        try:
            preview = await self._page.evaluate(_REPLY_PREVIEW_JS)
            if not preview or snippet not in _normalize_name(preview):
                raise RuntimeError(
                    f"La cita no muestra el mensaje elegido (muestra {(preview or '')[:60]!r}) "
                    "— no se envió nada"
                )
            await self.send_message(text)
        except Exception:
            # Leave no dangling quote: the next send would carry it.
            await self._page.keyboard.press("Escape")
            await self._page.wait_for_timeout(300)
            raise
        await self._page.wait_for_timeout(800)

        own = [m for m in await self._page.evaluate(_CHAT_MESSAGES_JS) if m.get("own")]
        last = own[-1] if own else {}
        verified = bool(last) and _same_letters(last.get("text") or "", text) \
            and snippet in _normalize_name(last.get("quoted") or "")
        return {
            "quoted_id": target["id"],
            "quoted_sender": _pre_sender(target.get("pre")) or None,
            "quoted_text": target["text"],
            "sent": text,
            "verified": verified,
        }

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

        # A draft already in the box would be sent glued to TEXT — and it may
        # be a leftover from a misdirected search (DataLake 2026-10-03).
        if not await self._page.evaluate(_CHECK_COMPOSE_EMPTY_JS):
            raise RuntimeError(
                "El chat tiene un borrador en la caja de mensaje — no se envía "
                "nada para no mezclarlo con el mensaje. Revisalo y borralo a mano."
            )

        # Never type before the compose box actually holds focus: keystrokes
        # sent while WA is still settling are lost — real case 2026-10-08,
        # "Matías, ya vi..." arrived as "atías, ya vi..." (DataLake).
        for _attempt in range(3):
            await self._page.mouse.click(info["x"], info["y"])
            await self._page.wait_for_timeout(300)
            if await self._page.evaluate(_FOCUS_IN_COMPOSE_JS):
                break
        else:
            raise RuntimeError("La caja de mensaje no tomó el foco — no se envió nada")

        # Type, then check the box holds exactly TEXT before pressing Enter.
        # One clean retry; if it still differs, nothing is sent.
        for _attempt in range(2):
            await self._type_compose(text)
            typed = await self._page.evaluate(_COMPOSE_TEXT_JS)
            if typed is None or _same_letters(typed, text):
                break
            import sys
            print(
                f"[wavi] send_message: compose shows {typed[:60]!r}, expected "
                f"{text[:60]!r} — clearing", file=sys.stderr,
            )
            _select_all = "Meta+a" if sys.platform == "darwin" else "Control+a"
            await self._page.keyboard.press(_select_all)
            await self._page.keyboard.press("Delete")
            await self._page.wait_for_timeout(300)
        else:
            raise RuntimeError(
                "El texto en la caja de mensaje no coincide con el mensaje "
                "(se perdieron o cambiaron caracteres) — no se envió nada"
            )

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

    async def _type_compose(self, text: str) -> None:
        """Type TEXT into the focused compose box. Newlines become Shift+Enter
        so WA doesn't send each line as a separate message."""
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if i > 0:
                line = await self._absorb_list_autoprefix(line)
            if line:
                await self._page.keyboard.type(line, delay=30)
            if i < len(lines) - 1:
                await self._page.keyboard.press("Shift+Enter")
                await self._page.wait_for_timeout(150)
        await self._page.wait_for_timeout(500)

    async def _absorb_list_autoprefix(self, line: str) -> str:
        """Reconcile LINE with whatever WA auto-inserted on the new line.

        Inside a list WA continues it on its own ("2. ", "• "). If LINE
        already starts with that marker, only the rest is typed; otherwise
        the marker is erased so LINE comes out exactly as written.
        """
        auto = await self._page.evaluate(_LAST_COMPOSE_LINE_JS)
        marker = (auto or "").strip()
        if not marker:
            return line
        if line.startswith(marker):
            return line[len(marker):].lstrip(" ")
        for _ in range(len(auto)):
            await self._page.keyboard.press("Backspace")
        return line

    async def _click_new_chat_via_vision(self) -> bool:
        """Locates the "new chat" button via vision
        (wavi/vision_grounding.py::locate_new_chat_button — the WA-green
        filled circular button, detected by icon presence + fill color, not
        by which SVG WA happens to draw inside it) and clicks its center
        with Playwright. This is the intended permanent path — see
        _OPEN_NEW_CHAT_JS's comment above: a DOM lookup is only ever this
        migration's temporary bridge, never treated as done.

        Returns False (never raises) if the vision-omniparser extra/weights
        aren't installed, or the button isn't found in the current
        screenshot — callers fall back to the DOM path in that case.
        """
        try:
            from wavi.vision_grounding import locate_new_chat_button
        except ImportError:
            return False

        import tempfile

        # Broad catch is deliberate: any failure to screenshot/locate means
        # "vision couldn't do this right now" (a mocked/fake page in tests,
        # a mid-navigation screenshot glitch live, an unreadable temp file)
        # — same "not an error, just unavailable" contract as the rest of
        # vision_grounding.py. Only the click below, once we HAVE a box,
        # is allowed to raise for real.
        try:
            with tempfile.TemporaryDirectory() as tmp:
                shot_path = Path(tmp) / "header.png"
                await self._page.screenshot(path=str(shot_path))
                box = locate_new_chat_button(shot_path)
        except Exception:
            return False

        if box is None:
            return False

        await self._page.mouse.click(box["x"] + box["w"] / 2, box["y"] + box["h"] / 2)
        return True

    async def navigate_to_new_chat(self) -> None:
        """Open the WhatsApp 'New chat' panel and wait for the contact list to appear.

        Real bug, 2026-08-26: _resolve_contact's refresh-on-no-match path
        calls this right after search_contacts() leaves text typed in the
        sidebar search box (never cleared) — with search active, WA hides
        the pencil/new-chat button, so it couldn't be found (true for vision
        too: the button just isn't rendered). Ensuring a clean sidebar state
        first fixes it for every caller, not just that one.
        """
        await self.ensure_chat_list()
        clicked = await self._click_new_chat_via_vision()
        if not clicked:
            clicked = await self._page.evaluate(_OPEN_NEW_CHAT_JS)
        if not clicked:
            raise RuntimeError("Could not find the 'new chat' button in WA Web (vision + DOM both failed)")
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
        """Snapshot every visible chat row in the main sidebar via DOM.

        Returns list of {name, last_message, timestamp, direction} per chat.
        direction is "outbound" when a delivery-tick icon is present in the
        preview row, "inbound" otherwise.
        """
        return await self._page.evaluate(_EXTRACT_SIDEBAR_UPDATES_JS)

    async def ensure_chat_list(self) -> None:
        """Navigate browser to the clean main chat list.

        Handles leftover states from previous commands:
        - "Nuevo chat" panel open → JS back-button click (_CLOSE_NEW_CHAT_JS)
        - Sidebar search bar filled → JS back-button / input clear (_CLEAR_SIDEBAR_SEARCH_JS)
        - Any other overlay → Escape as final safety net
        """
        await self._page.evaluate(_CLOSE_NEW_CHAT_JS)
        await self._page.wait_for_timeout(300)
        await self._page.evaluate(_CLEAR_SIDEBAR_SEARCH_JS)
        await self._page.wait_for_timeout(300)
        # Single Escape as safety net for any remaining overlay (e.g. a dialog).
        await self._page.keyboard.press("Escape")
        await self._page.wait_for_timeout(250)
        try:
            await self._page.wait_for_selector(
                '[data-testid="chat-list"], #pane-side', timeout=3_000
            )
        except Exception:
            pass


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
