"""
corpus_utils.py — metrics for the golden-screenshot vision corpus.

Pure functions, no pytest dependency, reused by tests/test_corpus.py and
scripts/make_corpus_case.py.

A corpus case compares the pipeline's current output ("actual") against a
reviewed reference ("expected"). Bubbles are matched by bbox IoU; the matched
pairs then yield classification/OCR quality metrics.
"""
from __future__ import annotations

from difflib import SequenceMatcher


def iou(a: dict, b: dict) -> float:
    """Intersection-over-union of two {x, y, w, h} boxes."""
    ax0, ay0, ax1, ay1 = a["x"], a["y"], a["x"] + a["w"], a["y"] + a["h"]
    bx0, by0, bx1, by1 = b["x"], b["y"], b["x"] + b["w"], b["y"] + b["h"]
    ix = max(0, min(ax1, bx1) - max(ax0, bx0))
    iy = max(0, min(ay1, by1) - max(ay0, by0))
    inter = ix * iy
    union = a["w"] * a["h"] + b["w"] * b["h"] - inter
    return inter / union if union > 0 else 0.0


def match_bubbles(
    expected: list[dict], actual: list[dict], iou_threshold: float = 0.5
) -> list[tuple[dict, dict]]:
    """Greedy 1:1 matching by descending IoU. Returns matched (expected, actual) pairs."""
    candidates = [
        (iou(e["bbox"], a["bbox"]), ei, ai)
        for ei, e in enumerate(expected)
        for ai, a in enumerate(actual)
    ]
    candidates = [c for c in candidates if c[0] >= iou_threshold]
    candidates.sort(key=lambda c: -c[0])

    used_e: set[int] = set()
    used_a: set[int] = set()
    pairs: list[tuple[dict, dict]] = []
    for _score, ei, ai in candidates:
        if ei in used_e or ai in used_a:
            continue
        used_e.add(ei)
        used_a.add(ai)
        pairs.append((expected[ei], actual[ai]))
    return pairs


def _time_of_day(ts: str | None) -> str | None:
    """Extract 'HH:MM' from a timestamp for date-independent comparison.

    Day pills like 'Hoy'/'Ayer' resolve relative to date.today(), so the date
    part of a baseline drifts as days pass — only the time is stable.
    """
    if not ts:
        return None
    return ts.split("T")[-1] if "T" in ts else ts


def text_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.strip(), b.strip()).ratio()


def evaluate_case(expected: list[dict], actual: list[dict]) -> dict:
    """Compute all corpus metrics for one screenshot.

    Returns a flat dict: detection (precision/recall), classification accuracy
    over matched pairs (sender/msg_type), timestamp time-of-day accuracy, and
    mean OCR text similarity.
    """
    pairs = match_bubbles(expected, actual)
    n_exp, n_act, n_match = len(expected), len(actual), len(pairs)

    metrics = {
        "expected": n_exp,
        "actual": n_act,
        "matched": n_match,
        "precision": n_match / n_act if n_act else 1.0,
        "recall": n_match / n_exp if n_exp else 1.0,
    }

    if pairs:
        metrics["sender_acc"] = sum(
            1 for e, a in pairs if e["sender"] == a["sender"]
        ) / n_match
        metrics["type_acc"] = sum(
            1 for e, a in pairs if e["msg_type"] == a["msg_type"]
        ) / n_match
        ts_pairs = [(e, a) for e, a in pairs if e.get("timestamp")]
        metrics["timestamp_acc"] = (
            sum(
                1
                for e, a in ts_pairs
                if _time_of_day(e["timestamp"]) == _time_of_day(a.get("timestamp"))
            ) / len(ts_pairs)
            if ts_pairs
            else 1.0
        )
        metrics["text_sim"] = sum(
            text_similarity(e.get("text", ""), a.get("text", "")) for e, a in pairs
        ) / n_match
    else:
        metrics.update(sender_acc=0.0, type_acc=0.0, timestamp_acc=0.0, text_sim=0.0)

    return metrics


# Default minimums — overridable per case via "thresholds" in expected.json.
DEFAULT_THRESHOLDS = {
    "precision": 0.90,
    "recall": 0.90,
    "sender_acc": 0.95,
    "type_acc": 0.90,
    "timestamp_acc": 0.80,
    "text_sim": 0.85,
}


def check_thresholds(metrics: dict, overrides: dict | None = None) -> list[str]:
    """Return a list of human-readable failures (empty = all thresholds met)."""
    thresholds = {**DEFAULT_THRESHOLDS, **(overrides or {})}
    return [
        f"{key}={metrics[key]:.3f} < min {minimum:.2f}"
        for key, minimum in thresholds.items()
        if metrics.get(key, 0.0) < minimum
    ]
