"""
vision.py — Pure vision pipeline: image → OCR → classified bubbles.

No Playwright, no DOM. Runs on a saved screenshot file.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image

SWIFT_OCR = Path(__file__).parent.parent / "swift" / "ocr_vision.swift"

# ── Regexes ───────────────────────────────────────────────────────────────────

RE_TIME          = re.compile(r'\d{1,2}:\d{2}\s*(a|p)\.?\s*m\.?', re.I)
RE_TIME_END      = re.compile(r'\d{1,2}:\d{2}\s*(a|p)\.?\s*m\.?\s*[JVjv/✓✔✗]*\s*$', re.I)
RE_CORE_TIME     = re.compile(r'(\d{1,2}:\d{2})\s*(a|p)', re.I)
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
    id: int                               # 1=newest, N=oldest
    sender: Literal["me", "other"]
    msg_type: Literal["text", "audio", "file", "media"]
    timestamp: str | None
    text: str
    bbox: dict                            # x,y,w,h in crop-panel coords
    raw_blocks: list[dict] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "sender": self.sender,
            "msg_type": self.msg_type,
            "timestamp": self.timestamp,
            "text": self.text,
            "bbox": self.bbox,
        }


# ── OCR ───────────────────────────────────────────────────────────────────────

def _run_ocr(img_path: Path) -> list[dict]:
    r = subprocess.run(["swift", str(SWIFT_OCR), str(img_path)],
                       capture_output=True, text=True, timeout=60)
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
    return None


def _classify_x(x: float, w: float) -> str:
    right_edge = x + w
    if right_edge > 0.75:
        return "me"
    if x < 0.15:
        return "other"
    return "me" if (x + w / 2) > 0.50 else "other"


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
    Full pipeline: screenshot → crop → OCR → classify bubbles.

    Returns list of Bubble objects sorted by id (1=newest, N=oldest).
    If assets_dir is given, saves bubbles.json there (and cropped.png/debug.png if save_debug=True).
    """
    from wavi.element_detector import detect_bubbles

    assets = assets_dir or screenshot_path.parent
    assets.mkdir(parents=True, exist_ok=True)

    cropped_path, _ = crop_chat_panel(screenshot_path)

    # Only save cropped.png to assets_dir if save_debug=True
    if save_debug and assets_dir:
        dest = assets / (screenshot_path.stem + "_cropped.png")
        if cropped_path != dest:
            shutil.copy2(cropped_path, dest)

    img = Image.open(cropped_path)
    img_w, img_h = img.size

    blocks = ocr_tiled(cropped_path)
    raw_bubbles = detect_bubbles(img, footer_px=70)

    split: list[dict] = []
    for b in raw_bubbles:
        split.extend(_split_bubbles_by_timestamps(b, blocks, img_h))

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
        results.append(Bubble(
            id          = len(split) - i,
            sender      = bubble["type"],
            msg_type    = classify_msg_type(text, raw_blocks),
            timestamp   = _extract_timestamp(raw_blocks),
            text        = text,
            bbox        = {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0},
            raw_blocks  = raw_blocks,
        ))

    if assets_dir:
        out = assets / (screenshot_path.stem + "_bubbles.json")
        out.write_text(json.dumps([b.as_dict() for b in results], indent=2, ensure_ascii=False))

        if save_debug:
            _save_debug_image(img, results, assets / (screenshot_path.stem + "_debug.png"))

    return results


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
