"""
vision_grounding.py — Cross-platform UI element grounding via OmniParser-v2.0.

First step of the DOM→vision migration tracked in docs/plan-mejoras.md (see
"DOM scraping inventory" table in wavi/session.py lines ~76-108 for the full
list of DOM signals this line of work is meant to eventually replace).

Unlike wavi/vision.py (Apple Vision OCR, macOS-only, text-only), this module
locates *UI elements* — icons and controls, not just text — from a plain
screenshot, using microsoft/OmniParser-v2.0 (YOLO icon detector + Florence-2
icon captioner + EasyOCR for text seeding). It works on any OS.

## ChatAppProfile — groundwork for more than WhatsApp

Every public function takes an optional `profile: ChatAppProfile` argument
(default `WHATSAPP_WEB`), bundling the chat-app-specific constants (sidebar
crop width, row-gap threshold, timestamp shape/regex, compose placeholder
text). WhatsApp Web is still the only profile that exists — this is not a
second chat app, just the seam that lets one be added later (a new
ChatAppProfile instance) without rewriting the detection functions, per
docs/plan-mejoras.md Fase 5.

## Why this isn't wired into session.py yet

This module only reads static screenshot files. It never opens a live
WhatsApp Web session or touches Playwright — on purpose. Wiring vision-based
element location into session.py's actual click/type actions is a separate,
higher-risk follow-up (touches an authenticated live session) and is out of
scope here. See tests/test_corpus_grounding.py for how this is validated
today: sanity-checked against static screenshots in tests/corpus/cases/.

## Dependencies — opt-in, heavy

Needs the `vision-omniparser` extra (torch, transformers, ultralytics —
~1.5GB installed): `uv sync --extra vision-omniparser`. wavi's core install
stays light; everything in this module is imported lazily inside functions
so importing wavi/vision_grounding.py itself never requires torch to be
installed. If the extra isn't installed, `locate_compose_area()` returns
None instead of raising.

Also needs the model weights (~1.5GB, not installed by the extra — see
`make omniparser-weights`), downloaded from
https://huggingface.co/microsoft/OmniParser-v2.0 into weights/ (gitignored).

## Licensing — read before shipping this anywhere beyond local/CLI use

This is NOT a clean MIT dependency like the rest of wavi:
  - wavi/_vendor/omniparser_utils.py and wavi/_vendor/box_annotator.py are
    vendored from the microsoft/OmniParser GitHub repo, licensed CC-BY-4.0
    (attribution required; not OSI-approved for software but permits reuse).
  - weights/icon_caption_florence (Florence-2) is MIT — clean.
  - weights/icon_detect (YOLO icon detector) is **AGPLv3**. AGPL's network-use
    clause can require releasing the combined work's source to any user who
    interacts with it over a network. wavi runs this locally as a CLI/harness
    today, which does not trigger that clause. If wavi/server.py or
    wavi/qr_server.py is ever used to expose this functionality as a network
    service to other users, this needs a fresh license review before that
    ships — do not assume the current "local use only" analysis still holds.

## Compatibility pins — do not bump casually

`transformers==4.49.0` is pinned exactly. `transformers>=5` breaks
Florence-2's custom remote code (`AttributeError: 'Florence2LanguageConfig'
object has no attribute 'forced_bos_token_id'`). Captioning auto-detects MPS
(Apple Silicon Metal GPU) and falls back to CPU otherwise — see
wavi/_vendor/omniparser_utils.py docstring for why the original OmniParser
code crashed on MPS (`RuntimeError: Input type (float) and bias type
(c10::Half) should be the same`) and how it's fixed here, plus the third pin
(the icon_caption_florence directory naming requirement).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, TypedDict

WEIGHTS_DIR = Path(__file__).parent.parent / "weights"


@dataclass(frozen=True)
class ChatAppProfile:
    """Bundles the chat-app-specific constants every function in this module
    needs (crop geometry, OCR text shapes) behind one parameter, instead of
    each function reaching for WA-specific module globals directly.

    Not a generalization to a second chat app yet — WHATSAPP_WEB below is
    still the only profile, and every function defaults to it, so behavior
    is unchanged. This exists so that adding Telegram/Slack/etc. later is a
    matter of writing a new ChatAppProfile instance and passing it in, not
    rewriting the detection functions — see docs/plan-mejoras.md Fase 5
    ("generalización... la 'gramática visual de chats' aplicable a
    Telegram/Slack"). Frozen: profiles are shared, read-only configuration,
    never mutated per-call.
    """
    name: str
    sidebar_px: int
    footer_band_frac: float
    compose_placeholder_re: re.Pattern[str]
    row_gap_px: int
    timestamp_re: re.Pattern[str]
    timestamp_gap_px: int


# Footer band where the compose input + send button live, as a fraction of
# image height from the bottom. WA Web's compose bar is consistently short
# (~70-90px on the corpus's 1280x1920 screenshots, ~5% of height); 15% gives
# headroom across window sizes without reaching into the message list.
FOOTER_BAND_FRAC = 0.15

# Tolerant on purpose: EasyOCR frequently drops short low-confidence words
# entirely rather than misreading them (confirmed on the corpus — "un" in
# "Escribe un mensaje" isn't merely split off, it's missing from the OCR
# output altogether), so this must not require an exact phrase match. ".*"
# between the anchor words absorbs whatever EasyOCR did or didn't catch
# between them, including nothing.
_COMPOSE_PLACEHOLDER_RE = re.compile(r"(escribe.*mensaj|type.*a.*messag)", re.I)

SIDEBAR_PX = 580  # matches wavi/vision.py's SIDEBAR_PX — kept independent
# on purpose (this module has no import-time dependency on wavi.vision) but
# should be updated alongside it if WA's sidebar width ever changes.

# Vertical gap (px) above which two OCR text lines are considered different
# sidebar rows rather than two lines of the same chat cell (name + preview).
# WA Web's cell height is ~72-90px with lines close together within a cell
# and a clearer gap between cells; 20px was picked empirically against the
# corpus and isn't first-principles derived — revisit if it misclusters on
# new screenshots (e.g. very long contact names that wrap to 3 lines).
SIDEBAR_ROW_GAP_PX = 20

# Broader than wavi/vision.py's RE_TIME on purpose: RE_TIME assumes a colon
# separator and a required am/pm suffix (true for in-bubble Apple Vision OCR
# text), but real EasyOCR output against a live sidebar showed WA rendering
# "11.27 a. m." (period separator) and, for the same session, bare "11.02"
# with the am/pm suffix silently dropped by OCR at this confidence threshold
# — confirmed 2026-09-18 against a live WhatsApp Web screenshot, not just the
# static corpus (the corpus's smoke test never asserted anything about
# `timestamp`, so this went unnoticed at first). am/pm is optional here for
# that reason. Still doesn't (and can't practically) match every locale's
# relative-day label ("Ayer", weekday names, absolute dates) — see the
# positional fallback in _split_row_fields for those.
_RE_TIMESTAMP = re.compile(r'\d{1,2}[:.]\d{2}(?:\s*(a|p)\.?\s*m\.?)?', re.I)

# Minimum horizontal gap (px) between the last name-column element and a
# candidate timestamp element for the positional fallback in
# _split_row_fields to trust it. Calibrated against real sidebar OCR output:
# words within the same phrase sit ~4-10px apart (e.g. "~Jorge" / "era
# penal ."), while the timestamp column (right-aligned near the crop's right
# edge) sits 190-350px away from the name text — this threshold sits
# comfortably between the two, not derived from first principles.
_TIMESTAMP_GAP_PX = 60

# The only profile in use today — see ChatAppProfile's docstring. Every
# function below defaults to this, so passing no `profile` argument keeps
# today's exact WA Web behavior.
WHATSAPP_WEB = ChatAppProfile(
    name="whatsapp_web",
    sidebar_px=SIDEBAR_PX,
    footer_band_frac=FOOTER_BAND_FRAC,
    compose_placeholder_re=_COMPOSE_PLACEHOLDER_RE,
    row_gap_px=SIDEBAR_ROW_GAP_PX,
    timestamp_re=_RE_TIMESTAMP,
    timestamp_gap_px=_TIMESTAMP_GAP_PX,
)


class ElementBox(TypedDict):
    x: int
    y: int
    w: int
    h: int


class ComposeArea(TypedDict):
    input_box: ElementBox | None
    send_button: ElementBox | None


_yolo_model = None
_caption_model_processor = None


def _models_available() -> bool:
    return (WEIGHTS_DIR / "icon_detect" / "model.pt").exists() and (
        WEIGHTS_DIR / "icon_caption_florence"
    ).exists()


def _load_models():
    """Lazily loads + caches the YOLO detector and Florence-2 captioner.
    Raises ImportError if the vision-omniparser extra isn't installed."""
    global _yolo_model, _caption_model_processor
    if _yolo_model is not None:
        return _yolo_model, _caption_model_processor

    from wavi._vendor.omniparser_utils import get_caption_model_processor, get_yolo_model

    _yolo_model = get_yolo_model(str(WEIGHTS_DIR / "icon_detect" / "model.pt"))
    _caption_model_processor = get_caption_model_processor(str(WEIGHTS_DIR / "icon_caption_florence"))
    return _yolo_model, _caption_model_processor


def _to_pixel_bbox(bbox_ratio: list[float], img_w: int, img_h: int) -> ElementBox:
    x0, y0, x1, y1 = bbox_ratio
    return {
        "x": int(x0 * img_w),
        "y": int(y0 * img_h),
        "w": int((x1 - x0) * img_w),
        "h": int((y1 - y0) * img_h),
    }


def parse_screen(screenshot_path: Path) -> list[dict] | None:
    """Runs the full OmniParser pipeline (OCR seed + YOLO icons + Florence-2
    captions) against a screenshot. Returns the raw element list (bbox in
    0-1 ratio coords, as OmniParser produces it) or None if the optional
    dependencies/weights aren't installed."""
    if not _models_available():
        return None
    try:
        from PIL import Image

        from wavi._vendor.omniparser_utils import check_ocr_box, get_som_labeled_img
    except ImportError:
        return None

    yolo_model, caption_model_processor = _load_models()

    image = Image.open(screenshot_path)
    text, ocr_bbox = check_ocr_box(
        image, output_bb_format="xyxy", easyocr_args={"paragraph": False, "text_threshold": 0.9}
    )
    _annotated_png_b64, parsed_content_list = get_som_labeled_img(
        image,
        yolo_model,
        BOX_TRESHOLD=0.05,
        ocr_bbox=ocr_bbox,
        caption_model_processor=caption_model_processor,
        ocr_text=text,
        iou_threshold=0.1,
        imgsz=640,
    )
    return parsed_content_list


def _cluster_by_y_overlap(elements: list[dict]) -> list[list[dict]]:
    """Groups elements into lines by y-overlap, each line's members sorted
    left-to-right. `elements` need only a `bbox` key ([x0,y0,x1,y1] — ratio
    or pixel, this is scale-agnostic since it only compares overlaps).

    Shared by `_group_text_lines` (compose-area OCR, ratio coords) and
    `_split_row_fields` (sidebar-row OCR, pixel coords) — both need to
    recover WA's actual line layout from OCR output that arrives as a flat,
    unordered bag of word/phrase boxes.
    """
    remaining = sorted(elements, key=lambda el: el["bbox"][0])
    lines: list[list[dict]] = []
    for el in remaining:
        _x0, y0, _x1, y1 = el["bbox"]
        placed = False
        for line in lines:
            _lx0, ly0, _lx1, ly1 = line[-1]["bbox"]
            overlap = min(y1, ly1) - max(y0, ly0)
            if overlap > 0.5 * min(y1 - y0, ly1 - ly0):
                line.append(el)
                placed = True
                break
        if not placed:
            lines.append([el])
    return lines


def _group_text_lines(text_elements: list[dict]) -> list[dict]:
    """Merges OCR text elements into lines by y-overlap, sorted left-to-right.

    EasyOCR frequently splits a single UI string into separate per-word
    boxes (e.g. "Escribe un mensaje" → "Escribe" + "mensaje", dropping short
    words like "un" entirely) — a single-element regex match against
    `content` misses these. Each returned line has a `content` (joined text)
    and a `bbox` (union of its members' bboxes, same [x0,y0,x1,y1] ratio
    format OmniParser uses elsewhere in this module).
    """
    result = []
    for line in _cluster_by_y_overlap(text_elements):
        xs0 = [el["bbox"][0] for el in line]
        ys0 = [el["bbox"][1] for el in line]
        xs1 = [el["bbox"][2] for el in line]
        ys1 = [el["bbox"][3] for el in line]
        result.append({
            "content": " ".join(el.get("content") or "" for el in line),
            "bbox": [min(xs0), min(ys0), max(xs1), max(ys1)],
        })
    return result


def locate_compose_area(
    screenshot_path: Path, profile: ChatAppProfile = WHATSAPP_WEB
) -> ComposeArea | None:
    """Locates the WhatsApp Web compose input box and send button in a
    screenshot via OmniParser, replacing the DOM signals documented for
    _FIND_COMPOSE_INPUT_JS / _CHECK_COMPOSE_EMPTY_JS / _CLICK_SEND_BTN_JS in
    wavi/session.py's DOM scraping inventory.

    Returns None if the vision-omniparser extra or weights aren't installed
    (never raises for that reason — callers should treat this as "vision
    grounding unavailable", not an error).
    """
    from PIL import Image

    elements = parse_screen(screenshot_path)
    if elements is None:
        return None

    with Image.open(screenshot_path) as img:
        img_w, img_h = img.size

    footer_y0 = img_h * (1 - profile.footer_band_frac)
    footer_elements = []
    for el in elements:
        _x0, y0, _x1, y1 = el["bbox"]
        cy = (y0 + y1) / 2 * img_h
        if cy >= footer_y0:
            footer_elements.append(el)

    input_box: ElementBox | None = None
    send_button: ElementBox | None = None
    # Narrow y-band (ratio coords) actually occupied by the compose row,
    # once we know it — set below when the placeholder text is found.
    row_y0: float | None = None
    row_y1: float | None = None

    # 1. Prefer matching the compose placeholder text ("Escribe un mensaje" /
    #    "Type a message"). Grouped into lines first because EasyOCR often
    #    splits this string across multiple word-level boxes.
    text_lines = _group_text_lines([el for el in footer_elements if el["type"] == "text"])
    for line in text_lines:
        if profile.compose_placeholder_re.search(line["content"]):
            input_box = _to_pixel_bbox(line["bbox"], img_w, img_h)
            row_y0, row_y1 = line["bbox"][1], line["bbox"][3]
            break

    # Once we've located the actual compose row, re-narrow the footer band
    # to it (+ padding) so unrelated floating UI in the generic 15% band —
    # e.g. a reaction-reactions popover overlapping the footer — can't be
    # picked up as the send button.
    if row_y0 is not None:
        pad = (row_y1 - row_y0) * 1.5
        band_elements = [
            el for el in footer_elements
            if row_y0 - pad <= (el["bbox"][1] + el["bbox"][3]) / 2 <= row_y1 + pad
        ]
    else:
        band_elements = footer_elements

    # 2. Fallback (no placeholder text found, e.g. compose box isn't empty):
    #    widest icon-typed element in the footer band.
    if input_box is None:
        icons = [el for el in band_elements if el["type"] == "icon"]
        if icons:
            widest = max(icons, key=lambda el: el["bbox"][2] - el["bbox"][0])
            input_box = _to_pixel_bbox(widest["bbox"], img_w, img_h)

    # Send button: icon-typed element in the (now-narrowed) band closest to
    # the right edge, excluding whatever we picked as the input box.
    icon_candidates = [
        el for el in band_elements
        if el["type"] == "icon" and _to_pixel_bbox(el["bbox"], img_w, img_h) != input_box
    ]
    if icon_candidates:
        rightmost = max(icon_candidates, key=lambda el: el["bbox"][2])
        send_button = _to_pixel_bbox(rightmost["bbox"], img_w, img_h)

    return {"input_box": input_box, "send_button": send_button}


# ── Sidebar chat list ─────────────────────────────────────────────────────────
# Replaces the DOM signal documented for _EXTRACT_SIDEBAR_UPDATES_JS in
# wavi/session.py's DOM scraping inventory. Text-only (EasyOCR via
# check_ocr_box) — sidebar rows are plain text, so this skips the YOLO +
# Florence-2 icon pipeline entirely and is correspondingly much faster than
# locate_compose_area() (no captioning pass).


class SidebarRow(TypedDict):
    bbox: ElementBox
    text: str  # every OCR line in the row, left-to-right, joined with " | ".
    name: str
    last_message: str
    timestamp: str
    # Always None in this cut: telling inbound from outbound needs the
    # delivery-tick icon (✓/✓✓), which this OCR-only pipeline can't see —
    # detecting it needs icon detection (YOLO), not just text. Deliberately
    # not adding Florence-2 captioning to get it, since that would erase this
    # function's speed advantage over locate_compose_area(). See
    # docs/plan-mejoras.md §4.8 for the planned follow-up (likely
    # predict_yolo() without captioning).
    direction: Literal["inbound", "outbound"] | None


def _split_row_fields(
    elements: list[dict], profile: ChatAppProfile = WHATSAPP_WEB
) -> tuple[str, str, str]:
    """Splits one sidebar row's OCR elements (already isolated to a single
    chat cell by profile.row_gap_px, but still a flat bag mixing every text
    line in that cell) into (name, last_message, timestamp).

    WA's cell layout is name + timestamp on the top line, message preview
    below (documented in wavi/session.py:447-451) — re-clusters the row back
    into visual lines by y-overlap, then pulls the timestamp out of the top
    line in two passes: regex first (right-aligned, so the rightmost regex
    match wins if more than one element happens to match — rare, but cheap
    to handle correctly), then a positional fallback — the rightmost element
    on the line, if it sits clearly apart from the rest (see
    profile.timestamp_gap_px) — for shapes no regex can enumerate:
    relative-day labels ("Ayer"), weekday names, absolute dates, all
    locale-dependent. There's no DOM structure to lean on here, so shape +
    position are the only signals available.
    """
    lines = sorted(
        _cluster_by_y_overlap(elements),
        key=lambda line: min(el["bbox"][1] for el in line),
    )
    if not lines:
        return "", "", ""

    top = sorted(lines[0], key=lambda el: el["bbox"][0])
    ts_idx: int | None = None
    for i, el in enumerate(top):
        if profile.timestamp_re.search(el.get("content") or ""):
            ts_idx = i  # keep overwriting: rightmost match wins

    if ts_idx is None and len(top) >= 2:
        gap = top[-1]["bbox"][0] - top[-2]["bbox"][2]
        if gap >= profile.timestamp_gap_px:
            ts_idx = len(top) - 1

    timestamp = (top[ts_idx].get("content") or "").strip() if ts_idx is not None else ""
    name = " ".join(el.get("content") or "" for i, el in enumerate(top) if i != ts_idx).strip()

    preview_words = [
        el.get("content") or ""
        for line in lines[1:]
        for el in sorted(line, key=lambda e: e["bbox"][0])
    ]
    last_message = " ".join(preview_words).strip()

    return name, last_message, timestamp


def _ocr_cell_rows(
    screenshot_path: Path, profile: ChatAppProfile = WHATSAPP_WEB
) -> list[list[tuple[str, tuple[int, int, int, int]]]] | None:
    """OCR-clusters the left column (width profile.sidebar_px) of a
    screenshot into rows by vertical gap (profile.row_gap_px) — one row per
    list cell. Shared by `parse_sidebar_rows` (chat list) and
    `parse_contacts_panel_rows` (the "Nuevo chat" contact list), which use
    the same left-column crop and the same row-boundary heuristic; they only
    differ in how they split fields *within* an already-isolated row.

    Returns None if the vision-omniparser extra isn't installed (never
    raises for that reason).
    """
    try:
        from PIL import Image

        from wavi._vendor.omniparser_utils import check_ocr_box
    except ImportError:
        return None

    image = Image.open(screenshot_path)
    img_w, _img_h = image.size
    column = image.crop((0, 0, min(profile.sidebar_px, img_w), image.size[1]))

    text, bboxes = check_ocr_box(
        column, output_bb_format="xyxy", easyocr_args={"paragraph": False, "text_threshold": 0.7}
    )
    elements = sorted(zip(text, bboxes, strict=False), key=lambda item: item[1][1])

    rows: list[list[tuple[str, tuple[int, int, int, int]]]] = []
    current: list[tuple[str, tuple[int, int, int, int]]] = []
    current_y1: int | None = None
    for content, bbox in elements:
        y0 = bbox[1]
        if current and current_y1 is not None and y0 - current_y1 > profile.row_gap_px:
            rows.append(current)
            current = []
        current.append((content, bbox))
        current_y1 = max(current_y1 or bbox[3], bbox[3])
    if current:
        rows.append(current)
    return rows


def _row_bbox(row: list[tuple[str, tuple[int, int, int, int]]]) -> ElementBox:
    xs0 = [b[0] for _c, b in row]
    ys0 = [b[1] for _c, b in row]
    xs1 = [b[2] for _c, b in row]
    ys1 = [b[3] for _c, b in row]
    return {"x": min(xs0), "y": min(ys0), "w": max(xs1) - min(xs0), "h": max(ys1) - min(ys0)}


def _row_elements(row: list[tuple[str, tuple[int, int, int, int]]]) -> list[dict]:
    return [{"content": content, "bbox": list(bbox)} for content, bbox in row]


def parse_sidebar_rows(
    screenshot_path: Path, profile: ChatAppProfile = WHATSAPP_WEB
) -> list[SidebarRow] | None:
    """OCR-clusters the WA Web sidebar (chat list) into rows, then splits
    each row into name / last_message / timestamp (see `_split_row_fields`).
    `direction` is always None here — see the SidebarRow docstring for why.

    Row boundaries (one row per chat cell) are the hard part of this
    function — arbitrary text layout, no DOM structure to lean on. Field
    splitting within an already-isolated row is comparatively cheap, since
    WA's two-line-per-cell layout and timestamp shape are consistent.

    Returns None if the vision-omniparser extra isn't installed (never
    raises for that reason).
    """
    rows = _ocr_cell_rows(screenshot_path, profile)
    if rows is None:
        return None

    result: list[SidebarRow] = []
    for row in rows:
        text = " | ".join(c for c, _b in sorted(row, key=lambda item: item[1][0]))
        name, last_message, timestamp = _split_row_fields(_row_elements(row), profile)
        result.append({
            "bbox": _row_bbox(row),
            "text": text,
            "name": name,
            "last_message": last_message,
            "timestamp": timestamp,
            "direction": None,
        })
    return result


# ── "Nuevo chat" contacts panel ─────────────────────────────────────────────
# Replaces the DOM signal documented for _EXTRACT_CONTACTS_JS /
# _EXTRACT_VISIBLE_CONTACTS_JS in wavi/session.py's DOM scraping inventory.
# Same left-column crop and row-clustering as parse_sidebar_rows (the panel
# occupies the same left column, replacing the chat list) — only the
# per-row field split differs: no timestamp, so the top line is the whole
# contact name and everything below it is the subtitle (phone number or
# WhatsApp "about" status), not a message preview.
#
# NOTE: no corpus case currently captures this panel open (see
# tests/corpus/cases/) — this function is validated by
# tests/test_vision_grounding.py against synthetic OCR output only. Add a
# real "Nuevo chat" screenshot case before relying on this beyond smoke use.


class ContactRow(TypedDict):
    bbox: ElementBox
    name: str
    subtitle: str


def _split_contact_fields(elements: list[dict]) -> tuple[str, str]:
    """Splits one contacts-panel row's OCR elements into (name, subtitle).

    Unlike sidebar chat rows, contact rows carry no timestamp — the top
    line is the full contact name, any line(s) below it are the subtitle.
    """
    lines = sorted(
        _cluster_by_y_overlap(elements),
        key=lambda line: min(el["bbox"][1] for el in line),
    )
    if not lines:
        return "", ""

    name = " ".join(
        el.get("content") or "" for el in sorted(lines[0], key=lambda e: e["bbox"][0])
    ).strip()
    subtitle_words = [
        el.get("content") or ""
        for line in lines[1:]
        for el in sorted(line, key=lambda e: e["bbox"][0])
    ]
    subtitle = " ".join(subtitle_words).strip()
    return name, subtitle


def parse_contacts_panel_rows(
    screenshot_path: Path, profile: ChatAppProfile = WHATSAPP_WEB
) -> list[ContactRow] | None:
    """OCR-clusters the WA Web "Nuevo chat" contacts panel into rows, then
    splits each row into name / subtitle (see `_split_contact_fields`).

    Returns None if the vision-omniparser extra isn't installed (never
    raises for that reason).
    """
    rows = _ocr_cell_rows(screenshot_path, profile)
    if rows is None:
        return None

    result: list[ContactRow] = []
    for row in rows:
        name, subtitle = _split_contact_fields(_row_elements(row))
        result.append({"bbox": _row_bbox(row), "name": name, "subtitle": subtitle})
    return result
