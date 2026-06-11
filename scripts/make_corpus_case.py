#!/usr/bin/env python3
"""
make_corpus_case.py — create a golden-corpus case from a WA screenshot.

Usage:
    python scripts/make_corpus_case.py <screenshot.png> <case_name>

Runs the current vision pipeline on the screenshot and writes:
    tests/corpus/cases/<case_name>/screenshot.png
    tests/corpus/cases/<case_name>/expected.json   ← REVIEW THIS BY HAND

The generated expected.json is the *current pipeline output*, i.e. a baseline
that detects regressions. To turn it into real ground truth, open the
screenshot next to the JSON and fix any wrong sender/type/text/timestamp —
then the corpus also measures absolute quality, not just drift.

Cases are gitignored (real conversations — privacy).
"""
from __future__ import annotations

import json
import shutil
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from wavi.vision import analyze  # noqa: E402

CASES_DIR = ROOT / "tests" / "corpus" / "cases"


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__)
        return 1

    shot = Path(sys.argv[1]).resolve()
    case_name = sys.argv[2]
    if not shot.exists():
        print(f"screenshot not found: {shot}", file=sys.stderr)
        return 1

    case_dir = CASES_DIR / case_name
    if case_dir.exists():
        print(f"case already exists: {case_dir} — delete it first to regenerate", file=sys.stderr)
        return 1
    case_dir.mkdir(parents=True)

    shutil.copy2(shot, case_dir / "screenshot.png")
    bubbles = analyze(case_dir / "screenshot.png")

    spec = {
        "created": date.today().isoformat(),
        "source": str(shot),
        "reviewed": False,  # flip to true after hand-checking the bubbles below
        "bubbles": [
            {
                "sender": b.sender,
                "msg_type": b.msg_type,
                "timestamp": b.timestamp,
                "text": b.text,
                "bbox": b.bbox,
            }
            for b in bubbles
        ],
    }
    (case_dir / "expected.json").write_text(
        json.dumps(spec, indent=2, ensure_ascii=False)
    )

    # analyze() drops working files next to the screenshot — keep the case clean
    for leftover in case_dir.glob("screenshot_*.png"):
        leftover.unlink()
    for leftover in case_dir.glob("screenshot_*.json"):
        leftover.unlink()

    print(f"created {case_dir.relative_to(ROOT)} with {len(bubbles)} bubbles")
    print("→ review expected.json by hand and set \"reviewed\": true")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
