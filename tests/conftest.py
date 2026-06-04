"""pytest plugin: embeds test results into boarding.html after each run."""
import json
import re
import time
from pathlib import Path

_results: dict[str, dict] = {}
_start: float = 0.0


def pytest_sessionstart(session):
    global _start
    _start = time.time()


def pytest_runtest_logreport(report):
    if report.when not in ("setup", "call", "teardown"):
        return
    nodeid = report.nodeid
    if nodeid not in _results:
        _results[nodeid] = {"nodeid": nodeid, "outcome": "passed", "duration": 0.0, "longrepr": None}
    if report.failed:
        _results[nodeid]["outcome"] = "failed"
        _results[nodeid]["longrepr"] = str(report.longrepr)[:3000]
    elif report.skipped and _results[nodeid]["outcome"] != "failed":
        _results[nodeid]["outcome"] = "skipped"
        if report.longrepr:
            _results[nodeid]["longrepr"] = str(report.longrepr)
    # Accumulate duration across setup + call + teardown phases
    _results[nodeid]["duration"] = round(
        (_results[nodeid].get("duration") or 0.0) + (report.duration or 0.0), 6
    )


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
    root = Path(__file__).parent.parent

    # 1. Sidecar .js for machine/API use
    js_out = root / "docs" / "reports" / "test_results.js"
    js_out.parent.mkdir(parents=True, exist_ok=True)
    js_out.write_text(
        f"window.WAVI_TEST_RESULTS = {json.dumps(data, indent=2, ensure_ascii=False)};\n"
    )

    # 2. Embed JSON inline in boarding.html (works on file:// — no CORS issues)
    html_path = root / "docs" / "boarding.html"
    if html_path.exists():
        html = html_path.read_text()
        json_str = json.dumps(data, ensure_ascii=False)
        html = re.sub(
            r'(<script id="wavi-test-results" type="application/json">).*?(</script>)',
            rf'\g<1>{json_str}\g<2>',
            html,
            flags=re.DOTALL,
        )
        html_path.write_text(html)
