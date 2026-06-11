"""
vision.py — Pure vision pipeline: image → OCR → classified bubbles.

No Playwright, no DOM. Runs on a saved screenshot file.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from PIL import Image

SWIFT_OCR = Path(__file__).parent.parent / "swift" / "ocr_vision.swift"
# Compiled binary (make ocr) — ~6x less startup overhead than interpreting the
# script, and runs Vision natively on arm64 instead of under Rosetta.
OCR_BIN = Path(__file__).parent.parent / "bin" / "ocr_vision"

# ── Timing instrumentation (WAVI_TIMING=1) ────────────────────────────────────
# Cumulative OCR stats are always collected (cost is negligible); the per-stage
# breakdown is printed by analyze() only when WAVI_TIMING is set.

_TIMING = bool(os.environ.get("WAVI_TIMING"))
_ocr_stats = {"calls": 0, "secs": 0.0}

# ── Regexes ───────────────────────────────────────────────────────────────────

RE_TIME          = re.compile(r'\d{1,2}:\d{2}\s*(a|p)\.?\s*m\.?', re.I)
RE_TIME_END      = re.compile(r'\d{1,2}:\d{2}\s*(a|p)\.?\s*m\.?\s*[JVjv/✓✔✗]*\s*$', re.I)
RE_CORE_TIME     = re.compile(r'(\d{1,2}:\d{2})\s*(a|p)', re.I)
# Cyrillic OCR artifact: Apple Vision OCR misreads "p." as "р." (Cyrillic р looks like Latin p).
# Pattern is specific to "р." so it doesn't fire on ordinary Russian/Bulgarian text.
# Known edge case: a 1:30-min audio whose duration block fuses with the timestamp ("1:30 р.")
# is ambiguous; we accept "1:30" as the best-effort result since it's rare in practice.
RE_TIME_CYRILLIC = re.compile(r'([1-9]\d?:\d{2})\s+р\.')
RE_DURATION      = re.compile(r'^\d+:\d{2}$')
RE_AUDIO_LOOSE   = re.compile(r'^0[\s\-\.]?\d{2}$')
RE_FILE_EXT      = re.compile(r'\.(xlsx?|docx?|pdf|csv|pptx?|txt|zip|rar|mov|mp4|png|jpg|jpeg)\b', re.I)
RE_SCREEN_REC    = re.compile(r'Screen Recording', re.I)
RE_SIZE          = re.compile(r'\d+[\.,]?\d*\s*(kB|MB|GB|k8|M8)\b', re.I)
RE_AUDIO_DUR     = re.compile(r'\b\d{1,2}:\d{2}\b(?!\s*[ap])', re.I)
RE_NOISE         = re.compile(r'^(\+|\s*Escribe un mensaje.*|.*filtrados.*|.*encriptados.*|\d{3,}/\d{3,})', re.I)

SIDEBAR_PX = 580
HEADER_PX  = 60


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class Bubble:
    # Both ID fields share the same convention:  1 = newest,  N = oldest.
    #   id        → global rank across the full history (set by capture_full_history).
    #               For single-screenshot use this equals screen_id.
    #   screen_id → rank within the snapshot returned by analyze().
    #               Mirrors WA Web's bottom-anchored layout (newest at bottom = id 1).
    id: int
    sender: Literal["me", "other"]
    msg_type: Literal["text", "audio", "file", "media"]
    timestamp: str | None
    text: str
    bbox: dict                            # x,y,w,h in crop-panel coords
    screen_id: int = 0                    # 1=newest in snapshot, N=oldest (see note above)
    raw_blocks: list[dict] = field(default_factory=list)
    dom_id: str | None = None             # WA DOM data-id attribute — stable across screenshots
    transcript: str | None = None        # Groq/whisper transcription for audio bubbles
    audio_path: str | None = None        # relative path to .ogg within history_dir (e.g. "iter_002/audio_17.ogg")

    def as_dict(self) -> dict:
        d = {
            "id": self.id,            # 1=newest overall (both fields share this convention)
            "screen_id": self.screen_id,  # 1=newest in this snapshot
            "sender": self.sender,
            "msg_type": self.msg_type,
            "timestamp": self.timestamp,
            "text": self.text,
            "bbox": self.bbox,
            "dom_id": self.dom_id,
        }
        if self.transcript is not None:
            d["transcript"] = self.transcript
        if self.audio_path is not None:
            d["audio_path"] = self.audio_path
        return d


# ── OCR ───────────────────────────────────────────────────────────────────────

def _ocr_cmd() -> list[str]:
    """Prefer the compiled binary; fall back to interpreting the script.

    The binary is only used when it is at least as new as the .swift source,
    so editing the source never silently runs a stale binary.
    """
    if OCR_BIN.exists() and OCR_BIN.stat().st_mtime >= SWIFT_OCR.stat().st_mtime:
        return [str(OCR_BIN)]
    return ["swift", str(SWIFT_OCR)]


def _run_ocr(img_path: Path) -> list[dict]:
    t0 = time.perf_counter()
    r = subprocess.run(_ocr_cmd() + [str(img_path)],
                       capture_output=True, text=True, timeout=60)
    _ocr_stats["calls"] += 1
    _ocr_stats["secs"] += time.perf_counter() - t0
    if r.returncode != 0:
        return []
    return json.loads(r.stdout)


def ocr_tiled(img_path: Path, tile_h: int = 500, overlap: int = 50, scale: float = 2.5) -> list[dict]:
    img = Image.open(img_path)
    w, h = img.size
    all_blocks: list[dict] = []
    y = 0
    while y < h:
        y_end = min(y + tile_h, h)
        tile = img.crop((0, y, w, y_end))
        tile_up = tile.resize((int(w * scale), int((y_end - y) * scale)), Image.LANCZOS)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp = Path(f.name)
        tile_up.save(tmp)
        blocks = _run_ocr(tmp)
        tmp.unlink()
        frac_start = y / h
        frac_h = (y_end - y) / h
        for b in blocks:
            b["y"] = frac_start + b["y"] * frac_h
            b["h"] = b["h"] * frac_h
        all_blocks.extend(blocks)
        y += tile_h - overlap

    seen, deduped = set(), []
    for b in sorted(all_blocks, key=lambda x: (round(x["y"], 3), x["text"][:10])):
        key = (b["text"][:20], round(b["y"] * h / 10) * 10)
        if key not in seen:
            seen.add(key)
            deduped.append(b)
    return deduped


# ── Crop ──────────────────────────────────────────────────────────────────────

def crop_chat_panel(img_path: Path) -> tuple[Path, int]:
    """
    Crop the WA Web sidebar and header from a full screenshot.
    Returns (cropped_path, sidebar_x).
    """
    img = Image.open(img_path)
    w, h = img.size
    sidebar_x = int(w * (SIDEBAR_PX / 1280))
    chat = img.crop((sidebar_x, HEADER_PX, w, h))
    out = img_path.parent / (img_path.stem + "_cropped.png")
    chat.save(out)
    return out, sidebar_x


# ── Parse helpers ─────────────────────────────────────────────────────────────

def _is_noise(text: str) -> bool:
    t = text.strip()
    if not t or len(t) < 2:
        return True
    if RE_NOISE.match(t):
        return True
    if len(t) <= 4 and not re.search(r'[a-záéíóú]', t, re.I):
        if not RE_DURATION.match(t) and not RE_AUDIO_LOOSE.match(t):
            return True
    if re.match(r'^[А-ЯЁа-яё\s\-]+$', t):
        return True
    return False


def _is_waveform_garbage(text: str) -> bool:
    if len(text) < 5:
        return False
    if RE_TIME.search(text):  # timestamps ("10:17 a. m.") are not waveforms
        return False
    noise = sum(1 for c in text if c in '|•01-[]lL ')
    return noise / len(text) > 0.45


def classify_msg_type(text: str, raw_blocks: list[dict]) -> str:
    if RE_SIZE.search(text) or RE_FILE_EXT.search(text) or RE_SCREEN_REC.search(text):
        return "file"
    if RE_AUDIO_DUR.search(text) or any(_is_waveform_garbage(b["text"]) for b in raw_blocks):
        return "audio"
    if not text.strip():
        return "media"
    return "text"


def _parse_time_str(raw: str) -> str | None:
    """Convert OCR time string to 24-h 'HH:MM'.

    '9:43 a. m.' → '09:43'   '7:44 p.m.' → '19:44'
    Bare 'H:MM' (Cyrillic fallback) is returned zero-padded as-is.
    """
    m = RE_CORE_TIME.search(raw)
    if m:
        h, mn = map(int, m.group(1).split(":"))
        if m.group(2).lower() == "p" and h != 12:
            h += 12
        elif m.group(2).lower() == "a" and h == 12:
            h = 0
        return f"{h:02d}:{mn:02d}"
    # Bare H:MM with no am/pm marker (Cyrillic OCR artifact)
    m2 = re.match(r"^(\d{1,2}):(\d{2})$", raw.strip())
    if m2:
        return f"{int(m2.group(1)):02d}:{m2.group(2)}"
    return None


def _build_timestamp(date_str: str | None, raw_time: str | None) -> str | None:
    """Combine ISO date and raw OCR time into 'YYYY-MM-DDTHH:MM'.

    Falls back to bare 'HH:MM' when date is unknown, and to the raw string
    when the time cannot be parsed (should not happen in practice).
    """
    if raw_time is None:
        return None
    time_24 = _parse_time_str(raw_time)
    if time_24 is None:
        return raw_time          # unparseable edge case — keep raw
    if date_str is None:
        return time_24           # no date context yet (e.g. wavi bubbles on a single shot)
    return f"{date_str}T{time_24}"


def _extract_timestamp(raw_blocks: list[dict]) -> str | None:
    for b in raw_blocks:
        t = b["text"].strip()
        if len(t) < 25 and RE_TIME.search(t):
            m = RE_TIME.search(t)
            return t[m.start():m.end()].strip()
    for b in raw_blocks:
        t = b["text"].strip()
        if RE_TIME_END.search(t):
            m = RE_TIME.search(t)
            if m:
                return t[m.start():m.end()].strip()
    # Third pass: Cyrillic OCR artifact ("р." read as "p.") — returns bare "H:MM" without am/pm.
    # Note: this differs from passes 1-2 which return the full "H:MM p. m." string.
    # Downstream (dedup key, display) tolerates both formats.
    for b in raw_blocks:
        t = b["text"].strip()
        if len(t) < 25:
            m = RE_TIME_CYRILLIC.search(t)
            if m:
                return m.group(1)
    return None


# ── Bubble detection ──────────────────────────────────────────────────────────

def _split_bubbles_by_timestamps(bubble: dict, blocks: list[dict], img_h: int) -> list[dict]:
    b_y0 = bubble["y"] / img_h
    b_y1 = (bubble["y"] + bubble["h"]) / img_h
    inner = [b for b in blocks if b_y0 <= b["y"] <= b_y1]

    def _core_time(t: str) -> str | None:
        m = RE_CORE_TIME.search(t)
        return (m.group(1) + m.group(2).lower()) if m else None

    standalone = [b for b in inner if RE_TIME.search(b["text"]) and len(b["text"]) < 25]
    embedded = [
        b for b in inner
        if b not in standalone and RE_TIME_END.search(b["text"].strip())
    ]
    # Duraciones de audio (m:ss) también son puntos de corte (separan audios de texto)
    audio_duration = [
        b for b in inner
        if b not in standalone and b not in embedded and RE_AUDIO_DUR.search(b["text"].strip())
    ]

    def has_same_standalone(emb: dict) -> bool:
        emb_core = _core_time(emb["text"])
        emb_bot  = (emb["y"] + emb.get("h", 0.015)) * img_h
        return any(
            0 < s["y"] * img_h - emb_bot <= 80 and _core_time(s["text"]) == emb_core
            for s in standalone
        )

    cut_blocks = standalone + [e for e in embedded if not has_same_standalone(e)] + audio_duration
    if len(cut_blocks) <= 1:
        return [bubble]

    subs, y_start = [], bubble["y"]
    for b in sorted(cut_blocks, key=lambda b: b["y"]):
        y_bot = min(int((b["y"] + b.get("h", 0.015)) * img_h) + 6,
                    bubble["y"] + bubble["h"])
        if y_bot - y_start >= 12:
            subs.append({"x": bubble["x"], "y": y_start,
                         "w": bubble["w"], "h": y_bot - y_start,
                         "type": bubble["type"]})
        y_start = y_bot
    remaining = (bubble["y"] + bubble["h"]) - y_start
    if subs and remaining > 0:
        subs[-1]["h"] += remaining
    return subs or [bubble]


# ── Main pipeline entry point ─────────────────────────────────────────────────

def analyze(screenshot_path: Path, assets_dir: Path | None = None, save_debug: bool = False) -> list[Bubble]:
    """
    Full pipeline: screenshot → detect elements visually → per-element OCR + action.

    Returns list of Bubble objects sorted by id (1=newest, N=oldest).
    If assets_dir is given, saves bubbles.json there (and cropped.png/debug.png if save_debug=True).
    """
    from wavi.element_detector import detect_bubbles

    _t0 = time.perf_counter()
    _ocr0 = dict(_ocr_stats)
    _stages: dict[str, float] = {}

    assets = assets_dir or screenshot_path.parent
    assets.mkdir(parents=True, exist_ok=True)

    _t = time.perf_counter()
    cropped_path, _ = crop_chat_panel(screenshot_path)
    _stages["crop"] = time.perf_counter() - _t

    # Only save cropped.png to assets_dir if save_debug=True
    if save_debug and assets_dir:
        dest = assets / (screenshot_path.stem + "_cropped.png")
        if cropped_path != dest:
            shutil.copy2(cropped_path, dest)

    img = Image.open(cropped_path)
    img_w, img_h = img.size

    # Auxiliary structural scan — one OCR pass over the full panel, used only to:
    #   (a) locate date-separator pills, and
    #   (b) decide whether a color-detected region spans multiple messages.
    # The canonical text for each element comes from the per-bubble OCR below.
    _t = time.perf_counter()
    _structural_scan = ocr_tiled(cropped_path)
    _stages["structural_scan"] = time.perf_counter() - _t

    # Build date map from day-separator pills BEFORE processing bubbles.
    # Each pill marks the date of everything below it; a bubble at y gets the
    # date of the pill with the largest pill_y that is still <= bubble_y.
    _pills = extract_day_pills(cropped_path, blocks=_structural_scan)
    _pill_map: list[tuple[int, str]] = []  # [(y_px, "YYYY-MM-DD"), ...]
    if _pills:
        from datetime import date as _Date
        _today = _Date.today()
        for _p in _pills:
            _pd = _date_from_pill_text(_p["text"], _today)
            if _pd is not None:
                _pill_map.append((_p["y"], _pd.isoformat()))
        _pill_map.sort(key=lambda x: x[0])

    def _date_for_y(y: int) -> str | None:
        if not _pill_map:
            return None
        chosen = _pill_map[0][1]
        for pill_y, pill_date in _pill_map:
            if pill_y <= y:
                chosen = pill_date
            else:
                break
        return chosen

    _t = time.perf_counter()
    raw_bubbles = detect_bubbles(img, footer_px=70)
    _stages["detect_bubbles"] = time.perf_counter() - _t

    split: list[dict] = []
    for b in raw_bubbles:
        split.extend(_split_bubbles_by_timestamps(b, _structural_scan, img_h))

    _t = time.perf_counter()
    results: list[Bubble] = []
    for i, bubble in enumerate(split):
        x0 = max(0, bubble["x"])
        y0 = max(0, bubble["y"])
        x1 = min(img_w, bubble["x"] + bubble["w"])
        y1 = min(img_h, bubble["y"] + bubble["h"])
        crop = img.crop((x0, y0, x1, y1))
        cw, ch = crop.size

        if ch < 12:
            scale = 2.0
        elif ch < 40:
            scale = 5.0
        else:
            scale = 3.0
        crop_up = crop.resize((int(cw * scale), int(ch * scale)), Image.LANCZOS)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            tmp = Path(f.name)
        crop_up.save(tmp)
        raw_blocks = _run_ocr(tmp)
        tmp.unlink()

        text = " ".join(b["text"].strip() for b in raw_blocks if b["text"].strip())
        local_id = len(split) - i
        results.append(Bubble(
            id          = local_id,
            screen_id   = local_id,
            sender      = bubble["type"],
            msg_type    = classify_msg_type(text, raw_blocks),
            timestamp   = _build_timestamp(_date_for_y(y0), _extract_timestamp(raw_blocks)),
            text        = text,
            bbox        = {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0},
            raw_blocks  = raw_blocks,
        ))

    _stages["bubble_ocr"] = time.perf_counter() - _t

    if assets_dir:
        out = assets / (screenshot_path.stem + "_bubbles.json")
        out.write_text(json.dumps([b.as_dict() for b in results], indent=2, ensure_ascii=False))

        if save_debug:
            _save_debug_image(img, results, assets / (screenshot_path.stem + "_debug.png"))

    if _TIMING:
        ocr_calls = _ocr_stats["calls"] - _ocr0["calls"]
        ocr_secs = _ocr_stats["secs"] - _ocr0["secs"]
        total = time.perf_counter() - _t0
        breakdown = " ".join(f"{k}={v:.2f}s" for k, v in _stages.items())
        print(
            f"[wavi-timing] analyze total={total:.2f}s {breakdown} "
            f"ocr_calls={ocr_calls} ocr_total={ocr_secs:.2f}s "
            f"bubbles={len(results)} engine={'bin' if _ocr_cmd()[0].endswith('ocr_vision') else 'swift-script'}",
            file=sys.stderr,
        )

    return results


def _date_from_pill_text(text: str, today) -> object | None:
    """Parse a WA day-separator pill text into a datetime.date. Returns None if unrecognised."""
    import re as _re
    from datetime import date as _D
    from datetime import timedelta as _td

    _MONTHS: dict[str, int] = {
        "ene": 1, "enero": 1, "feb": 2, "febrero": 2, "mar": 3, "marzo": 3,
        "abr": 4, "abril": 4, "may": 5, "mayo": 5, "jun": 6, "junio": 6,
        "jul": 7, "julio": 7, "ago": 8, "agosto": 8, "sep": 9, "septiembre": 9,
        "oct": 10, "octubre": 10, "nov": 11, "noviembre": 11, "dic": 12, "diciembre": 12,
        "jan": 1, "january": 1, "february": 2, "march": 3, "apr": 4, "april": 4,
        "june": 6, "july": 7, "aug": 8, "august": 8, "september": 9,
        "october": 10, "november": 11, "dec": 12, "december": 12,
    }
    _WDAYS_ES = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]
    _WDAYS_EN = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

    t = text.strip().lower()
    if t in ("hoy", "today"):
        return today
    if t in ("ayer", "yesterday"):
        return today - _td(days=1)
    for names in (_WDAYS_ES, _WDAYS_EN):
        for i, name in enumerate(names):
            if t == name:
                days_back = (today.weekday() - i) % 7 or 7
                return today - _td(days=days_back)
    m = _re.match(r'^(\d{1,2})[/\-\.](\d{1,2})[/\-\.](\d{2,4})$', t)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        try:
            return _D(y if y > 100 else 2000 + y, mo, d)
        except ValueError:
            pass
    m = _re.match(r'^(\d{1,2})\s+de\s+(\w+)(?:\s+de\s+(\d{4}))?$', t)
    if m:
        d, month_s = int(m.group(1)), m.group(2)
        y = int(m.group(3)) if m.group(3) else today.year
        mo = _MONTHS.get(month_s)
        if mo:
            try:
                return _D(y, mo, d)
            except ValueError:
                pass
    m = _re.match(r'^(\w+)\s+(\d{1,2})(?:,?\s*(\d{4}))?$', t)
    if m:
        month_s, d = m.group(1), int(m.group(2))
        y = int(m.group(3)) if m.group(3) else today.year
        mo = _MONTHS.get(month_s)
        if mo:
            try:
                return _D(y, mo, d)
            except ValueError:
                pass
    return None


_RE_PILL = re.compile(
    r"^(hoy|ayer|today|yesterday"
    r"|lunes|martes|mi[eé]rcoles|jueves|viernes|s[aá]bado|domingo"
    r"|monday|tuesday|wednesday|thursday|friday|saturday|sunday"
    r"|\d{1,2}\s+de\s+\w+(?:\s+de\s+\d{4})?"   # "3 de junio [de 2025]"
    r"|\w+\s+\d{1,2}(?:,?\s*\d{4})?"            # "June 1[, 2025]"
    r"|\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}"    # "01/05/2025"
    r")$",
    re.I,
)


def extract_day_pills(cropped_path: Path, blocks: list[dict] | None = None) -> list[dict]:
    """
    Detect WA date-separator pills by OCR on the cropped chat panel.

    blocks: pre-computed structural scan (ocr_tiled output). If None, runs OCR
            internally — used when called standalone, e.g. from runner.py.

    Returns [{"text": str, "y": int}] sorted by y (crop-panel pixels).
    """
    img = Image.open(cropped_path)
    img_h = img.size[1]

    if blocks is None:
        blocks = ocr_tiled(cropped_path)

    results = []
    for b in blocks:
        text = b["text"].strip()
        if not text or len(text) > 30:
            continue
        if not _RE_PILL.match(text):
            continue
        # Pills are centered: x_center between 0.20 and 0.80 (fractional)
        x_center = b["x"] + b.get("w", 0.1) / 2
        if not (0.20 < x_center < 0.80):
            continue
        results.append({"text": text, "y": int(b["y"] * img_h)})

    results.sort(key=lambda d: d["y"])

    # Deduplicate: OCR tiling may return the same pill twice at nearly the same y
    deduped: list[dict] = []
    for r in results:
        if not deduped or abs(r["y"] - deduped[-1]["y"]) > 20:
            deduped.append(r)

    return deduped


def _save_debug_image(
    img: Image.Image,
    bubbles: list[Bubble],
    out_path: Path,
    play_positions: dict[int, tuple[int, int]] | None = None,
) -> None:
    """
    Draw bounding boxes on all bubbles + a click cross on audio/file bubbles.

    play_positions: maps bubble.id → (crop_x, crop_y) of the actual DOM play button.
                    When None, the cross is estimated: near the play button — left edge
                    for incoming ("other"), right of the avatar for outgoing ("me") —
                    bottom-anchored to the audio control row.
    Green = me, blue = other. Red cross = where wavi clicks to play/open.
    """
    from PIL import ImageDraw

    debug = img.copy().convert("RGBA")
    overlay = Image.new("RGBA", debug.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    FILL   = {"me": (72, 199, 116, 55),  "other": (66, 153, 225, 55)}
    BORDER = {"me": (34, 139, 34, 230),  "other": (30, 100, 200, 230)}
    CROSS_COLOR = (220, 40, 40, 230)
    ARM = 8

    for b in bubbles:
        x, y, w, h = b.bbox["x"], b.bbox["y"], b.bbox["w"], b.bbox["h"]
        fill   = FILL.get(b.sender,   (180, 180, 180, 55))
        border = BORDER.get(b.sender, (100, 100, 100, 230))

        draw.rectangle([x, y, x + w, y + h], fill=fill, outline=border, width=2)

        label = f"#{b.id} {b.sender} {b.msg_type}"
        tag_w = len(label) * 6 + 6
        draw.rectangle([x, max(0, y - 17), x + tag_w, y], fill=border)
        draw.text((x + 3, max(0, y - 16)), label, fill=(255, 255, 255, 255))

        if b.msg_type in ("audio", "file"):
            if play_positions and b.id in play_positions:
                cx, cy = play_positions[b.id]        # exact DOM position
            else:
                cx = x + 93 if b.sender == "me" else x + 38
                cy = y + h - 37
            draw.line([cx - ARM, cy, cx + ARM, cy], fill=CROSS_COLOR, width=3)
            draw.line([cx, cy - ARM, cx, cy + ARM], fill=CROSS_COLOR, width=3)

    combined = Image.alpha_composite(debug, overlay).convert("RGB")
    combined.save(out_path)
