"""pytest plugin: saves test results to docs/reports/test_results.js after each run."""
import json
import time
from pathlib import Path

_results: dict[str, dict] = {}
_start: float = 0.0


def pytest_sessionstart(session):
    global _start
    _start = time.time()


def pytest_runtest_logreport(report):
    if report.when not in ("call", "setup"):
        return
    nodeid = report.nodeid
    if nodeid not in _results:
        _results[nodeid] = {"nodeid": nodeid, "outcome": "passed", "duration": 0.0, "longrepr": None}
    if report.failed:
        _results[nodeid]["outcome"] = "failed"
        _results[nodeid]["longrepr"] = str(report.longrepr)[:500]
    elif report.skipped and _results[nodeid]["outcome"] != "failed":
        _results[nodeid]["outcome"] = "skipped"
    if report.when == "call":
        _results[nodeid]["duration"] = round(report.duration, 4)


def pytest_sessionfinish(session, exitstatus):
    tests = list(_results.values())
    data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "duration": round(time.time() - _start, 2),
        "total": len(tests),
        "passed": sum(1 for t in tests if t["outcome"] == "passed"),
        "failed": sum(1 for t in tests if t["outcome"] == "failed"),
        "skipped": sum(1 for t in tests if t["outcome"] == "skipped"),
        "exit_code": int(exitstatus),
        "tests": tests,
    }
    out = Path(__file__).parent.parent / "docs" / "reports" / "test_results.js"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        f"window.WAVI_TEST_RESULTS = {json.dumps(data, indent=2, ensure_ascii=False)};\n"
    )
