"""
Vision-grounding smoke test: can OmniParser locate the compose input box and
send button on real WA Web screenshots, cross-platform?

Unlike tests/test_corpus.py (bbox-precise regression against a reviewed
expected.json), this is a sanity/smoke check — there's no hand-labeled
ground truth for compose-area coordinates yet. It asserts the pipeline
*finds something plausible*, not pixel-perfect accuracy. See
wavi/vision_grounding.py for what's being tested and why.

Gated behind WAVI_CORPUS=1 (slow — CPU inference, ~1-3 min/case) AND
requires the vision-omniparser extra + weights (`make omniparser-weights`)
to be installed; skips cleanly otherwise instead of failing.

    make corpus-grounding   or
    WAVI_CORPUS=1 uv run --extra vision-omniparser pytest tests/test_corpus_grounding.py -v
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

CASES_DIR = Path(__file__).parent / "corpus" / "cases"

pytestmark = [
    pytest.mark.corpus,
    pytest.mark.skipif(
        not os.environ.get("WAVI_CORPUS"),
        reason="corpus eval is slow (CPU inference) — set WAVI_CORPUS=1 or run `make corpus-grounding`",
    ),
]


def _discover_cases() -> list[Path]:
    if not CASES_DIR.exists():
        return []
    return sorted(d for d in CASES_DIR.iterdir() if (d / "screenshot.png").exists())


CASES = _discover_cases()


@pytest.mark.skipif(not CASES, reason=f"no corpus cases in {CASES_DIR}")
@pytest.mark.parametrize("case_dir", CASES, ids=lambda d: d.name)
def test_locate_compose_area(case_dir: Path):
    from PIL import Image

    from wavi.vision_grounding import locate_compose_area

    result = locate_compose_area(case_dir / "screenshot.png")
    if result is None:
        pytest.skip("vision-omniparser extra or weights not installed — see make omniparser-weights")

    with Image.open(case_dir / "screenshot.png") as img:
        img_w, img_h = img.size
    footer_y0 = img_h * 0.85  # last 15% of the image, matches FOOTER_BAND_FRAC

    input_box = result["input_box"]
    send_button = result["send_button"]

    assert input_box is not None, f"{case_dir.name}: no compose input box found"
    assert send_button is not None, f"{case_dir.name}: no send button found"

    assert input_box["y"] >= footer_y0 - 20, (
        f"{case_dir.name}: input_box y={input_box['y']} is above the footer band "
        f"(expected >= {footer_y0 - 20:.0f})"
    )
    assert send_button["x"] >= input_box["x"], (
        f"{case_dir.name}: send_button (x={send_button['x']}) should be to the "
        f"right of input_box (x={input_box['x']})"
    )


@pytest.mark.skipif(not CASES, reason=f"no corpus cases in {CASES_DIR}")
@pytest.mark.parametrize("case_dir", CASES, ids=lambda d: d.name)
def test_parse_sidebar_rows(case_dir: Path):
    from wavi.vision_grounding import SIDEBAR_PX, parse_sidebar_rows

    rows = parse_sidebar_rows(case_dir / "screenshot.png")
    if rows is None:
        pytest.skip("vision-omniparser extra not installed")

    # Every corpus screenshot shows a populated chat list (see tests/corpus/README.md
    # coverage notes) — smoke-check that we find a plausible number of rows, not an
    # exact count (row clustering is a heuristic, not ground-truth-verified per case).
    assert len(rows) >= 5, f"{case_dir.name}: only found {len(rows)} sidebar rows, expected several"

    for row in rows:
        assert row["bbox"]["x"] < SIDEBAR_PX, f"{case_dir.name}: row bbox extends outside the sidebar crop"
        assert row["text"].strip(), f"{case_dir.name}: row with empty text"
