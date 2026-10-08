"""media.py — download a chat's videos and photos through WA's media viewer.

The chat's own bubbles only carry low-res thumbnails (data: URIs). The full
file is reachable once the media viewer is open:

  - photos: a blob: <img> holding the decrypted image;
  - videos: a <video> whose src is WA's service-worker stream endpoint
    (/stream/video?key=…), served in 206 chunks — fetched range by range.

The viewer walks the chat's media in order (ArrowLeft = older), and its header
names the sender and the day/time ("Hoy a la(s) 11:26 a. m."), so one open on
the newest media item plus ArrowLeft visits everything, newest → oldest.

DOM bridge (testids + viewer structure), same as audio's blob capture: there
is no vision path to a file's bytes.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import sys
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
    return {header, video, image};
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

_HEADER_SPLIT_RE = re.compile(r"\s+(?:a\s+la\(s\)|a\s+las?|at)\s+", re.I)
_RANGE_TOTAL_RE = re.compile(r"/(\d+)\s*$")


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
    Returns the state (with "key"), or None on timeout (= no newer item)."""
    waited = 0
    while waited < timeout_ms:
        st = await page.evaluate(_VIEWER_STATE_JS)
        if st:
            src = st.get("video") or st.get("image")
            if src:
                key = st.get("video") or ("|".join(st["header"]) + "|" + st["image"])
                if key != prev_key:
                    # Header and media swap at different moments: only trust
                    # a state that reads the same twice in a row.
                    await page.wait_for_timeout(500)
                    again = await page.evaluate(_VIEWER_STATE_JS)
                    if again != {k: st[k] for k in ("header", "video", "image")}:
                        waited += 500
                        continue
                    st["key"] = key
                    st["kind"] = "video" if st.get("video") else "image"
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
                if st["kind"] == "video":
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
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(500)
        manifest.sort(key=lambda e: e.get("timestamp") or "", reverse=True)
        manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    return new_entries
