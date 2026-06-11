"""
Golden-screenshot corpus: regression metrics for the vision pipeline.

Each case in tests/corpus/cases/<name>/ holds a real WA screenshot plus a
reviewed expected.json. The pipeline runs end-to-end (crop → detect → OCR →
classify) and the result is scored against the reference: bbox precision and
recall (IoU ≥ 0.5), sender/type accuracy, timestamp time-of-day accuracy, and
mean OCR text similarity. Thresholds live in corpus_utils.DEFAULT_THRESHOLDS
and can be overridden per case in expected.json["thresholds"].

Gated behind WAVI_CORPUS=1 because each case runs real Apple Vision OCR
(~5-10 s/case, macOS only). Run via:  make corpus   or
WAVI_CORPUS=1 pytest tests/test_corpus.py -v

Cases contain real conversations → tests/corpus/cases/ is gitignored.
New cases: python scripts/make_corpus_case.py <screenshot.png> <case_name>
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

from tests.corpus_utils import check_thresholds, evaluate_case

CASES_DIR = Path(__file__).parent / "corpus" / "cases"

pytestmark = [
    pytest.mark.corpus,
    pytest.mark.skipif(
        not os.environ.get("WAVI_CORPUS"),
        reason="corpus eval is slow (real OCR) — set WAVI_CORPUS=1 or run `make corpus`",
    ),
    pytest.mark.skipif(sys.platform != "darwin", reason="Apple Vision OCR requires macOS"),
]


def _discover_cases() -> list[Path]:
    if not CASES_DIR.exists():
        return []
    return sorted(
        d for d in CASES_DIR.iterdir()
        if (d / "screenshot.png").exists() and (d / "expected.json").exists()
    )


CASES = _discover_cases()


@pytest.mark.skipif(not CASES, reason=f"no corpus cases in {CASES_DIR}")
@pytest.mark.parametrize("case_dir", CASES, ids=lambda d: d.name)
def test_corpus_case(case_dir: Path):
    """Vision pipeline metrics on one golden screenshot must meet thresholds."""
    from wavi.vision import analyze

    spec = json.loads((case_dir / "expected.json").read_text())
    bubbles = analyze(case_dir / "screenshot.png")
    actual = [b.as_dict() for b in bubbles]

    metrics = evaluate_case(spec["bubbles"], actual)
    line = " ".join(
        f"{k}={v:.3f}" if isinstance(v, float) else f"{k}={v}"
        for k, v in metrics.items()
    )
    print(f"[corpus] {case_dir.name}: {line}", file=sys.stderr)

    failures = check_thresholds(metrics, spec.get("thresholds"))

    # Challenge cases: hand-labeled screenshots the pipeline can't solve yet
    # (dark theme, 24h locale, media bubbles…). Metrics are computed and
    # printed above, but an expected failure doesn't break the suite — remove
    # the "xfail" flag from expected.json when the capability lands.
    if failures and spec.get("xfail"):
        pytest.xfail(spec.get("xfail_reason", "known unsupported challenge case"))

    assert not failures, f"{case_dir.name}: " + "; ".join(failures)
