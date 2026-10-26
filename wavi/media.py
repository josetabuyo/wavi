"""media.py — download a chat's videos, photos and documents.

The chat's own bubbles only carry low-res thumbnails (data: URIs). The full
file is reachable once the media viewer is open:

  - photos: a blob: <img> holding the decrypted image;
  - videos: a <video> whose src is WA's service-worker stream endpoint
    (/stream/video?key=…), served in 206 chunks — fetched range by range.

The viewer walks the chat's media in order (ArrowLeft = older), and its header
names the sender and the day/time ("Hoy a la(s) 11:26 a. m."), so one open on
the newest media item plus ArrowLeft visits everything, newest → oldest.

Documents (zip, xlsx, pdf…) never reach that viewer's ArrowLeft walk. They
are read straight from the chat: each document bubble carries its file name,
size and message id, and the date pill above it gives the day. Clicking it
makes WA fetch + decrypt the file and hand Chrome a blob: download (PDFs open
a preview first, whose header has the download button). Chrome writes it to
disk itself via CDP Browser.setDownloadBehavior, so a 500 MB zip never
travels through Python.

DOM bridge (testids + viewer structure), same as audio's blob capture: there
is no vision path to a file's bytes.
"""

from __future__ import annotations

import base64
import contextlib
import hashlib
import json
import re
import sys
import time
from datetime import date as _Date
from datetime import datetime as _DateTime
from pathlib import Path

from wavi.vision import _date_from_pill_text, _parse_time_str

_MEDIA_IN_CHAT_JS = """
() => {
    const els = [...document.querySelectorAll(
        '#main [data-testid="image-thumb"], #main [data-testid="video-content"]')];
    return els.length;
}
"""

# Bring the newest (bottom-most) media bubble into view and return its centre.
_NEWEST_MEDIA_POS_JS = """
() => {
    const els = [...document.querySelectorAll(
        '#main [data-testid="image-thumb"], #main [data-testid="video-content"]')];
    if (!els.length) return null;
    const el = els[els.length - 1];
    el.scrollIntoView({block: 'center'});
    const r = el.getBoundingClientRect();
    return {x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2)};
}
"""

_VIEWER_STATE_JS = """
() => {
    const m = document.querySelector('[data-testid="media-viewer-modal"]');
    if (!m) return null;
    const v = m.querySelector('video');
    const video = v ? (v.currentSrc || v.src || null) : null;
    // Full-size photo: the widest rendered blob: <img> (avatars are ~40px,
    // the preview thumbnail is a data: URI).
    let image = null, best = 0;
    for (const i of m.querySelectorAll('img')) {
        const src = i.currentSrc || i.src || '';
        const w = i.getBoundingClientRect().width;
        if (src.startsWith('blob:') && w > best) { best = w; image = src; }
    }
    const header = (m.innerText || '').split('\\n').map(s => s.trim()).filter(Boolean).slice(0, 2);
    // A video WA hasn't fetched yet ("No se puede reproducir el video") has
    // no src, only its blurred thumbnail — which tells items apart.
    const mv = m.querySelector('[data-testid="media-video"] [style*="background-image"]');
    const thumb = mv ? mv.style.backgroundImage : null;
    return {header, video, image, thumb};
}
"""

# One ranged read of a URL (WA's stream endpoint answers 206 in ~1.5 MB slices).
_FETCH_RANGE_JS = """
async ([url, start]) => {
    try {
        const r = await fetch(url, {headers: {Range: 'bytes=' + start + '-'}});
        const buf = new Uint8Array(await r.arrayBuffer());
        let s = '';
        const CHUNK = 8192;
        for (let i = 0; i < buf.length; i += CHUNK)
            s += String.fromCharCode(...buf.subarray(i, i + CHUNK));
        return {status: r.status, range: r.headers.get('content-range'), b64: btoa(s)};
    } catch (e) { return {error: String(e)}; }
}
"""

# Every document bubble rendered in the chat, oldest → newest, with the date
# pill above it and who sent it: outgoing bubbles hug the right edge, and an
# incoming one takes the name its sender group is labelled with ("Name:").
_DOCUMENTS_JS = """
() => {
    const box = document.querySelector('#main [data-testid="conversation-panel-messages"]')
             || document.querySelector('#main');
    if (!box) return {docs: [], firstPill: null};
    const edge = box.getBoundingClientRect();
    const rows = [];
    let pill = null, firstPill = null;
    for (const el of box.querySelectorAll('[role="row"], span')) {
        if (el.getAttribute('role') !== 'row') {
            if (!el.closest('[role="row"]') && !el.children.length && el.innerText.trim()) {
                pill = el.innerText.trim();
                firstPill = firstPill || pill;
            }
            continue;
        }
        const pre = el.querySelector('[data-pre-plain-text]');
        const m = pre && pre.getAttribute('data-pre-plain-text').match(/\\]\\s*(.+?):\\s*$/);
        const label = [...el.querySelectorAll('[aria-label]')]
            .map(e => e.getAttribute('aria-label').trim()).find(a => /^[^,]+:$/.test(a));
        const bubble = (el.querySelector('[data-testid="msg-container"]') || el).getBoundingClientRect();
        const thumb = el.querySelector('[data-testid="document-thumb"]');
        const lines = thumb ? el.innerText.split('\\n').map(s => s.trim()).filter(Boolean) : [];
        const title = thumb && (thumb.getAttribute('title') || '').match(/"(.+)"/);
        rows.push({
            groupStart: !!el.querySelector('[data-testid="tail-in"], [data-testid="tail-out"]'),
            out: edge.right - bubble.right < bubble.left - edge.left,
            name: label ? label.slice(0, -1) : (m ? m[1] : null),
            doc: thumb ? {
                id: (el.querySelector('[data-id]') || el).getAttribute('data-id'),
                file: title ? title[1] : (lines[1] || ''),
                size: lines.find(s => s.includes('\u2022')) || '',
                time: lines[lines.length - 1] || '',
                pill,
            } : null,
        });
    }
    const docs = [];
    rows.forEach((r, i) => {
        if (!r.doc) return;
        let a = i, b = i;
        while (a > 0 && !rows[a].groupStart) a--;
        while (b + 1 < rows.length && !rows[b + 1].groupStart) b++;
        const named = r.name ? r : rows.slice(a, b + 1).find(x => x.name);
        docs.push({...r.doc, out: r.out, sender: named ? named.name : null});
    });
    return {docs, firstPill};
}
"""

# Scroll a document bubble into view; return its thumb's centre and the
# bubble's text (which changes while WA is fetching the file).
_DOCUMENT_POS_JS = """
(id) => {
    const t = document.querySelector(
        '#main [data-id="' + id + '"] [data-testid="document-thumb"]');
    if (!t) return null;
    t.scrollIntoView({block: 'center'});
    const r = t.getBoundingClientRect();
    return {x: Math.round(r.x + r.width / 2), y: Math.round(r.y + r.height / 2),
            text: (t.closest('[role="row"]') || t).innerText};
}
"""

# Press the media viewer's own download button — the viewer WA opens for a
# PDF instead of downloading it, or one showing a video WA hasn't fetched.
# Returns whether the viewer was there.
_VIEWER_DOWNLOAD_JS = """
() => {
    const m = document.querySelector('[data-testid="media-viewer-modal"]');
    if (!m) return false;
    const b = [...m.querySelectorAll('button')].find(
        b => /^(descargar|download)$/i.test(b.getAttribute('aria-label') || ''));
    if (b) b.click();
    return true;
}
"""

# A playable video gets its src within ~1-2s; one still without src after
# this long is a video WA hasn't fetched: saved through the viewer's button.
UNFETCHED_VIDEO_MS = 3_000

_HEADER_SPLIT_RE = re.compile(r"\s+(?:a\s+la\(s\)|a\s+las?|at)\s+", re.I)
_RANGE_TOTAL_RE = re.compile(r"/(\d+)\s*$")
_SIZE_RE = re.compile(r"([\d.,]+)\s*(B|KB|MB|GB)\b", re.I)
_SIZE_UNITS = {"B": 1, "KB": 1 << 10, "MB": 1 << 20, "GB": 1 << 30}

# WA fetches + decrypts the whole file before Chrome's download starts: allow
# a base wait plus time per MB (a 510 MB zip gets ~10 min). Once Chrome writes,
# a stall this long with no new bytes is a failure.
DOC_BEGIN_BASE_S = 90
DOC_BEGIN_PER_MB_S = 1.0
DOC_STALL_S = 60
# A click on a document WA hasn't prepared yet only prepares it (the bubble
# shows a busy state, then goes back to idle) — the save needs another click
# (seen 2026-10-21, 510 MB zip: every other click saved). Click again once
# the bubble is idle again; never while busy, which would cancel the fetch.
DOC_RECLICK_S = 5
DOC_MAX_CLICKS = 3


def parse_viewer_when(line: str, today: _Date) -> _DateTime | None:
    """'Hoy a la(s) 11:26 a. m.' / '5/10/2026 a la(s) 3:51 p. m.' /
    'Yesterday at 9:02 PM' → datetime. None if unrecognised."""
    parts = _HEADER_SPLIT_RE.split(line.strip(), maxsplit=1)
    if len(parts) != 2:
        return None
    day = _date_from_pill_text(parts[0], today)
    hhmm = _parse_time_str(parts[1])
    if day is None or hhmm is None:
        return None
    h, m = (int(x) for x in hhmm.split(":"))
    return _DateTime(day.year, day.month, day.day, h, m)


def _ext_for(data: bytes, kind: str) -> str:
    if data[4:8] == b"ftyp":
        return ".mp4"
    if data[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    return ".mp4" if kind == "video" else ".bin"


def parse_size(text: str) -> int | None:
    """'ZIP•510 MB' / 'PDF • 45 B' / '1,5 MB' → bytes (approximate)."""
    m = _SIZE_RE.search(text or "")
    if not m:
        return None
    return int(float(m.group(1).replace(",", ".")) * _SIZE_UNITS[m.group(2).upper()])


def _slug(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower() or "x"


async def _fetch_stream(page, url: str) -> bytes | None:
    """Read URL completely through ranged fetches inside the page."""
    out = bytearray()
    total: int | None = None
    while total is None or len(out) < total:
        r = await page.evaluate(_FETCH_RANGE_JS, [url, len(out)])
        if not r or r.get("error") or r.get("status") not in (200, 206):
            print(f"[wavi] media: stream read failed at {len(out)}: {r and (r.get('error') or r.get('status'))}",
                  file=sys.stderr)
            return None
        chunk = base64.b64decode(r["b64"])
        if not chunk:
            break
        out += chunk
        if r["status"] == 200:
            break
        m = _RANGE_TOTAL_RE.search(r.get("range") or "")
        total = int(m.group(1)) if m else len(out)
    return bytes(out)


async def _wait_viewer_item(page, prev_key: str | None, timeout_ms: int = 15_000) -> dict | None:
    """Poll the viewer until it shows a loaded item different from PREV_KEY.
    Returns the state (with "key", "kind", and "fetch": False for a video the
    browser can't stream yet), or None on timeout (= no newer item)."""
    waited = 0
    while waited < timeout_ms:
        st = await page.evaluate(_VIEWER_STATE_JS)
        if st:
            src = st.get("video") or st.get("image")
            unfetched = not src and st.get("thumb") and waited >= UNFETCHED_VIDEO_MS
            if src or unfetched:
                if st.get("video"):
                    key = st["video"]
                elif unfetched:
                    key = "thumb:" + hashlib.sha1(st["thumb"].encode()).hexdigest()[:16]
                else:
                    key = "|".join(st["header"]) + "|" + st["image"]
                if key != prev_key:
                    # Header and media swap at different moments: only trust
                    # a state that reads the same twice in a row.
                    await page.wait_for_timeout(500)
                    again = await page.evaluate(_VIEWER_STATE_JS)
                    if again != {k: st[k] for k in ("header", "video", "image", "thumb")}:
                        waited += 500
                        continue
                    st["key"] = key
                    st["kind"] = "video" if st.get("video") or unfetched else "image"
                    st["fetch"] = not unfetched
                    return st
        await page.wait_for_timeout(300)
        waited += 300
    return None


async def download_chat_media(
    session,
    out_dir: Path,
    *,
    kinds: tuple[str, ...] = ("video", "image"),
    from_date: _Date | None = None,
    limit: int | None = None,
    max_scrolls: int = 40,
    today: _Date | None = None,
) -> list[dict]:
    """Download the open chat's media, newest → oldest, into OUT_DIR.

    Stops at the first item older than FROM_DATE, after LIMIT downloads, or
    when the viewer has no older item. Items already in OUT_DIR/media.json
    are skipped (same video key or same photo bytes). Returns the entries
    written this run; media.json keeps the full manifest.
    """
    page = session._page
    today = today or _Date.today()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "media.json"
    manifest: list[dict] = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
    known_keys = {e.get("key") for e in manifest}
    known_hashes = {e.get("sha1") for e in manifest}

    # Find the newest media bubble — scroll up until one is loaded.
    pos = None
    for _ in range(max_scrolls):
        if await page.evaluate(_MEDIA_IN_CHAT_JS):
            pos = await page.evaluate(_NEWEST_MEDIA_POS_JS)
            break
        if await session.is_chat_at_top():
            break
        await session.scroll_chat_up()
        await page.wait_for_timeout(800)
    if pos is None:
        print("[wavi] media: no hay fotos ni videos en el chat", file=sys.stderr)
        return []

    await page.wait_for_timeout(600)
    pos = await page.evaluate(_NEWEST_MEDIA_POS_JS)
    await page.mouse.click(pos["x"], pos["y"])

    new_entries: list[dict] = []
    prev_key: str | None = None
    downloads = None             # opened on the first video WA hasn't fetched
    stack = contextlib.AsyncExitStack()
    try:
        while True:
            st = await _wait_viewer_item(page, prev_key)
            if st is None:
                if prev_key is None:
                    print("[wavi] media: el visor no abrió o no cargó el archivo", file=sys.stderr)
                break                                    # no older item
            prev_key = st["key"]
            sender = st["header"][0] if st["header"] else ""
            when = parse_viewer_when(st["header"][1], today) if len(st["header"]) > 1 else None
            if from_date and when and when.date() < from_date:
                break

            if st["kind"] in kinds and st["key"] not in known_keys:
                if not st["fetch"]:
                    downloads = downloads or await stack.enter_async_context(
                        _ChromeDownloads(page, out_dir / ".partial"))
                    data = await _download_from_viewer(page, downloads, f"video de {sender}")
                elif st["kind"] == "video":
                    data = await _fetch_stream(page, st["video"])
                else:
                    data = await session.fetch_blob(st["image"])
                if data:
                    sha1 = hashlib.sha1(data).hexdigest()
                    if sha1 not in known_hashes:
                        stamp = when.strftime("%Y-%m-%d_%H%M") if when else "sin_fecha"
                        name = f"{stamp}_{_slug(sender)}_{sha1[:6]}{_ext_for(data, st['kind'])}"
                        (out_dir / name).write_bytes(data)
                        entry = {
                            "file": name,
                            "kind": st["kind"],
                            "sender": sender,
                            "timestamp": when.isoformat(timespec="minutes") if when else None,
                            "bytes": len(data),
                            "sha1": sha1,
                            "key": st["key"] if st["kind"] == "video" else None,
                        }
                        manifest.append(entry)
                        new_entries.append(entry)
                        known_hashes.add(sha1)
                        known_keys.add(entry["key"])
                        print(f"[wavi] media: {name} ({len(data) // 1024} KB)", file=sys.stderr)
                else:
                    print(f"[wavi] media: no se pudo bajar {st['kind']} de {sender} {st['header'][1:]}",
                          file=sys.stderr)
                if limit and len(new_entries) >= limit:
                    break

            await page.keyboard.press("ArrowLeft")
            await page.wait_for_timeout(500)
    finally:
        await stack.aclose()
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)
        manifest.sort(key=lambda e: e.get("timestamp") or "", reverse=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    return new_entries


def _safe_filename(name: str) -> str:
    name = re.sub(r'[/\\:\x00-\x1f]+', "_", name).strip().strip(".")
    return name or "documento"


def document_when(doc: dict, today: _Date) -> _DateTime | None:
    day = _date_from_pill_text(doc.get("pill") or "", today)
    hhmm = _parse_time_str(doc.get("time") or "")
    if day is None or hhmm is None:
        return None
    h, m = (int(x) for x in hhmm.split(":"))
    return _DateTime(day.year, day.month, day.day, h, m)


class _ChromeDownloads:
    """Chrome saves downloads into DEST (named by guid) while active, via CDP;
    its default download behaviour is restored on exit."""

    def __init__(self, page, dest: Path):
        self.page, self.dest, self.state = page, Path(dest), {}

    async def __aenter__(self):
        self.dest.mkdir(parents=True, exist_ok=True)
        self.cdp = await self.page.context.browser.new_browser_cdp_session()
        await self.cdp.send("Browser.setDownloadBehavior", {
            "behavior": "allowAndName", "downloadPath": str(self.dest.resolve()), "eventsEnabled": True})
        self.cdp.on("Browser.downloadWillBegin", self._begin)
        self.cdp.on("Browser.downloadProgress", self._progress)
        return self

    async def __aexit__(self, *exc):
        await self.cdp.send("Browser.setDownloadBehavior", {"behavior": "default"})
        await self.cdp.detach()
        if not any(self.dest.iterdir()):
            self.dest.rmdir()

    def _begin(self, e):
        self.state.setdefault("guid", e["guid"])
        self.state["at"] = time.monotonic()

    def _progress(self, e):
        if e["guid"] == self.state.get("guid"):
            self.state.update(state=e["state"], got=e.get("receivedBytes", 0), at=time.monotonic())

    async def wait(self, label: str, begin_within_s: float, poke=None) -> Path | None:
        """Wait for the download started after the last start(). Until it
        begins, await POKE() every round (to click again, etc.). Returns the
        written file, or None (not delivered in time, stalled, canceled)."""
        dl, deadline = self.state, time.monotonic() + begin_within_s
        while True:
            await self.page.wait_for_timeout(500)
            if dl.get("state") == "completed":
                return self.dest / dl["guid"]
            if dl.get("state") == "canceled":
                print(f"[wavi] media: Chrome canceló la descarga de {label}", file=sys.stderr)
                return None
            if "guid" in dl:
                if time.monotonic() - dl["at"] > DOC_STALL_S:
                    print(f"[wavi] media: la descarga de {label} se trabó en "
                          f"{dl.get('got', 0) // (1 << 20)} MB", file=sys.stderr)
                    return None
                continue
            if time.monotonic() > deadline:
                print(f"[wavi] media: WA no entregó {label} a tiempo", file=sys.stderr)
                return None
            if poke:
                await poke()

    def start(self):
        self.state.clear()


async def _download_document(page, downloads: _ChromeDownloads, doc: dict) -> Path | None:
    """Click DOC and wait for Chrome to write it. Returns the file, or None."""
    downloads.start()
    pos = await page.evaluate(_DOCUMENT_POS_JS, doc["id"])
    if not pos:
        print(f"[wavi] media: no encuentro el documento {doc['file']} en el chat", file=sys.stderr)
        return None
    idle = pos["text"]
    await page.wait_for_timeout(300)
    await page.mouse.click(pos["x"], pos["y"])
    clicks, clicked_at, preview = 1, time.monotonic(), False

    async def poke():
        nonlocal clicks, clicked_at, preview
        if not preview:
            preview = await page.evaluate(_VIEWER_DOWNLOAD_JS)
        if preview or clicks >= DOC_MAX_CLICKS or time.monotonic() - clicked_at < DOC_RECLICK_S:
            return
        again = await page.evaluate(_DOCUMENT_POS_JS, doc["id"])
        if again and again["text"] == idle:
            await page.mouse.click(again["x"], again["y"])
            clicks, clicked_at = clicks + 1, time.monotonic()

    size_mb = (parse_size(doc.get("size")) or 0) / (1 << 20)
    try:
        return await downloads.wait(doc["file"], DOC_BEGIN_BASE_S + DOC_BEGIN_PER_MB_S * size_mb, poke)
    finally:
        if preview:
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(500)


async def _download_from_viewer(page, downloads: _ChromeDownloads, label: str) -> bytes | None:
    """Save the viewer's current item with its own download button."""
    downloads.start()
    await page.evaluate(_VIEWER_DOWNLOAD_JS)
    path = await downloads.wait(label, DOC_BEGIN_BASE_S)
    if path is None:
        return None
    data = path.read_bytes()
    path.unlink()
    return data


async def _save_document(page, downloads: _ChromeDownloads, doc: dict, when: _DateTime | None,
                         out_dir: Path, chat_name: str) -> dict | None:
    """Download DOC and move it to OUT_DIR under its final name.
    Returns its manifest entry, or None if it could not be downloaded."""
    got = await _download_document(page, downloads, doc)
    if got is None:
        return None
    sender = "Tú" if doc["out"] else (doc["sender"] or chat_name)
    stamp = when.strftime("%Y-%m-%d_%H%M") if when else "sin_fecha"
    path = out_dir / f"{stamp}_{_slug(sender)}_{_safe_filename(doc['file'])}"
    got.replace(path)
    entry = {
        "file": path.name,
        "kind": "document",
        "sender": sender,
        "timestamp": when.isoformat(timespec="minutes") if when else None,
        "bytes": path.stat().st_size,
        "sha1": _sha1_file(path),
        "key": doc["id"],
    }
    print(f"[wavi] media: {path.name} ({entry['bytes'] // 1024} KB)", file=sys.stderr)
    return entry


def _sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


async def download_chat_documents(
    session,
    out_dir: Path,
    *,
    from_date: _Date | None = None,
    limit: int | None = None,
    max_scrolls: int = 40,
    today: _Date | None = None,
    chat_name: str = "",
) -> list[dict]:
    """Download the open chat's documents (zip, xlsx, pdf…), newest → oldest,
    into OUT_DIR, keeping their original names. Same manifest (media.json) and
    skip-known rule as download_chat_media, keyed by message id."""
    page = session._page
    today = today or _Date.today()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "media.json"
    manifest: list[dict] = json.loads(manifest_path.read_text()) if manifest_path.exists() else []
    known_keys = {e.get("key") for e in manifest}

    # WA renders only the rows near the viewport: walk up from the bottom and
    # take each document while it is on screen, newest first.
    await page.wait_for_timeout(1500)
    new_entries: list[dict] = []
    seen: set[str] = set()
    scrolled = False
    try:
        async with _ChromeDownloads(page, out_dir / ".partial") as downloads:
            for _ in range(max_scrolls + 1):
                view = await page.evaluate(_DOCUMENTS_JS)
                at_top = await session.is_chat_at_top()
                done = False
                for doc in reversed(view["docs"]):
                    # No date pill rendered above it yet: take it after the next scroll.
                    if doc["id"] in seen or (doc["pill"] is None and not at_top):
                        continue
                    seen.add(doc["id"])
                    when = document_when(doc, today)
                    if from_date and when and when.date() < from_date:
                        done = True
                        break
                    if doc["id"] in known_keys:
                        continue
                    entry = await _save_document(page, downloads, doc, when, out_dir, chat_name)
                    if entry:
                        manifest.append(entry)
                        new_entries.append(entry)
                        known_keys.add(entry["key"])
                    if limit and len(new_entries) >= limit:
                        done = True
                        break
                top_day = _date_from_pill_text(view["firstPill"] or "", today)
                if done or (from_date and top_day and top_day < from_date) or at_top:
                    break
                await session.scroll_chat_up()
                scrolled = True
                await page.wait_for_timeout(800)
    finally:
        manifest.sort(key=lambda e: e.get("timestamp") or "", reverse=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    if not seen:
        print("[wavi] media: no hay documentos en el chat", file=sys.stderr)
    if scrolled:
        # Leave the chat at the bottom, where the viewer walk (wavi media
        # --type all) looks for the newest photo: WA unloads rows far from
        # the viewport (RuGIAR 2026-10-26: "no hay fotos ni videos").
        await _scroll_to_bottom(session)
    return new_entries


async def _scroll_to_bottom(session, max_steps: int = 80) -> None:
    for _ in range(max_steps):
        st = await session.get_chat_scroll_state()
        if not st or st["scrollTop"] + st["clientHeight"] >= st["scrollHeight"] - 20:
            return
        await session.scroll_chat_down(1800)
        await session._page.wait_for_timeout(300)
