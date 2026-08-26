"""
qr_server.py — local mini web app for on-demand WhatsApp QR capture.

Single entry point by design: `wavi qr <session>` starts this page
immediately, with or without a daemon already running. Nothing happens
against Chrome/WhatsApp until the user presses "Buscar QR" — that's the
one and only trigger that launches the session's headless Chrome (if it
isn't already up) and asks it for whatever QR/auth state it currently
shows. No separate 'wavi connect' step required first.

Replaces the old flow of writing a single static QR HTML file, which
silently goes stale before the user manages to scan it (WA QR codes live
~60s): here, each button press pulls a fresh QR, and the page polls for
auth so it can close itself the moment linking succeeds.

Only ever reads DOM state from the WA tab once it's up. Never navigates
it, never touches storage — see .claude/skills/wa-session-guard.
"""
from __future__ import annotations

import asyncio
import base64
import json
import signal
import socket
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import click

_QR_SEL = "[data-testid='qrcode'], div[data-ref]"
_AUTH_SEL = "[data-testid='chat-list'], #side, input[role='textbox']"
_DATA_REF_JS = (
    "() => { const el = document.querySelector('div[data-ref]'); "
    "return el ? el.getAttribute('data-ref') : null; }"
)

_PAGE_HTML = """<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>wavi — Vincular WhatsApp</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: "Segoe UI", "Helvetica Neue", Helvetica, Arial, sans-serif;
    background: #f0f2f5; display: flex; flex-direction: column;
    align-items: center; justify-content: center;
    min-height: 100vh; padding: 24px; color: #111; text-align: center;
  }
  .card {
    background: #fff; border-radius: 16px; padding: 40px 48px;
    box-shadow: 0 2px 15px rgba(11,20,26,.15); max-width: 420px; width: 100%;
  }
  .logo { color: #00a884; font-size: 1.1rem; font-weight: 700;
           letter-spacing: .04em; margin-bottom: 20px; }
  h1 { font-size: 1.4rem; font-weight: 400; margin-bottom: 8px; }
  .sub { color: #667; font-size: .95rem; margin-bottom: 24px; line-height: 1.5; }
  button {
    background: #00a884; color: #fff; border: none; border-radius: 8px;
    padding: 14px 28px; font-size: 1rem; font-weight: 600; cursor: pointer;
    margin-bottom: 20px;
  }
  button:disabled { background: #9fd8c8; cursor: default; }
  #qrbox { min-height: 20px; margin-bottom: 16px; }
  #qrbox img { width: 280px; height: 280px; border: 1px solid #e9edef; border-radius: 4px; }
  #status { font-size: .95rem; color: #555; min-height: 1.3em; }
</style>
</head>
<body>
  <div class="card">
    <div class="logo">wavi</div>
    <h1>Vincular WhatsApp</h1>
    <p class="sub" id="hint">Presioná el botón para arrancar y pedir el QR.
      Podés volver a presionarlo tantas veces como haga falta — nunca queda vencido.</p>
    <button id="btn">Buscar QR</button>
    <div id="qrbox"></div>
    <p id="status"></p>
  </div>
<script>
function beep(freq, dur, type) {
  try {
    var ctx = beep._ctx || (beep._ctx = new (window.AudioContext || window.webkitAudioContext)());
    var osc = ctx.createOscillator(), gain = ctx.createGain();
    osc.frequency.value = freq; osc.type = type || 'sine';
    osc.connect(gain); gain.connect(ctx.destination);
    gain.gain.setValueAtTime(0.15, ctx.currentTime);
    osc.start();
    gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + dur);
    osc.stop(ctx.currentTime + dur);
  } catch (e) {}
}
window.addEventListener('load', function () { beep(660, 0.15); });

var btn = document.getElementById('btn');
var qrbox = document.getElementById('qrbox');
var status = document.getElementById('status');
var hint = document.getElementById('hint');
var pollTimer = null;
var currentRef = '';

function stopPolling() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }

function onLinked() {
  stopPolling();
  beep(880, 0.12); setTimeout(function () { beep(1046, 0.2); }, 140);
  status.textContent = 'Vinculado correctamente. Esta página ya se cierra sola — si no, cerrala vos.';
  hint.textContent = '';
  qrbox.innerHTML = '';
  btn.disabled = true;
  setTimeout(function () { try { window.close(); } catch (e) {} }, 1200);
}

function poll() {
  fetch('/api/status?ref=' + encodeURIComponent(currentRef))
    .then(function (r) { return r.json(); })
    .then(function (d) {
      if (d.state === 'restored') {
        onLinked();
      } else if (d.state === 'expired') {
        stopPolling();
        beep(220, 0.3, 'square');
        status.textContent = 'Ese QR expiró. Presioná el botón de nuevo para pedir uno nuevo.';
      }
    })
    .catch(function () {});
}

btn.addEventListener('click', function () {
  stopPolling();
  btn.disabled = true;
  status.textContent = 'Buscando QR...';
  qrbox.innerHTML = '';
  fetch('/api/qr').then(function (r) { return r.json(); }).then(function (d) {
    btn.disabled = false;
    if (!d.ok) {
      status.textContent = 'Error: ' + (d.error || 'desconocido');
      beep(220, 0.3, 'square');
      return;
    }
    if (d.state === 'restored') {
      onLinked();
      return;
    }
    currentRef = d.ref || '';
    qrbox.innerHTML = '<img src="data:image/png;base64,' + d.qr_b64 + '" alt="QR">';
    status.textContent = 'Escaneá desde WhatsApp → Dispositivos vinculados.';
    beep(523, 0.15);
    pollTimer = setInterval(poll, 3000);
  }).catch(function () {
    btn.disabled = false;
    status.textContent = 'Error de red buscando el QR.';
    beep(220, 0.3, 'square');
  });
});
</script>
</body>
</html>"""


_SOCIETY_URL = "http://localhost:8700"


def _claim_port(session_path: str) -> int:
    """Claim a port for this HTTP server from the Local Agent Society
    registry (see .agent.json, ADR-008), so 'las ports audit' can see it
    instead of it running invisibly. Falls back to a local OS-assigned
    ephemeral port if the society daemon isn't reachable."""
    import json as _json
    import urllib.error as _err
    import urllib.request as _req

    payload = _json.dumps({
        "app": "wavi QR mini web app",
        "local_agent": "Wavi",
        "path": session_path,
    }).encode()
    try:
        r = _req.urlopen(
            _req.Request(
                f"{_SOCIETY_URL}/ports/claim",
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=2,
        )
        return _json.loads(r.read())["port"]
    except _err.HTTPError:
        pass
    except Exception:
        pass

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _release_port(port: int) -> None:
    import urllib.request as _req
    try:
        _req.urlopen(
            _req.Request(f"{_SOCIETY_URL}/ports/{port}", method="DELETE"),
            timeout=2,
        )
    except Exception:
        pass


async def _ensure_daemon_ready(profile: Path) -> tuple[int | None, str | None]:
    """Launch the session's Chrome daemon if it isn't already running, then
    return its CDP port once reachable. This is the one thing that makes
    'Buscar QR' a self-contained entry point: no separate 'wavi connect'
    has to be run first — pressing the button is enough."""
    from wavi.cli import _check_session_status
    from wavi.session import WASession

    s = WASession(profile)
    if not s.daemon_alive():
        from wavi.cli import (
            _claim_port as _claim_cdp_port,
        )
        from wavi.cli import (
            _kill_port_processes,
            _launch_headless_daemon,
            _set_chrome_prefs,
            _wait_cdp_ready,
        )

        profile.mkdir(parents=True, exist_ok=True)
        port = _claim_cdp_port(str(profile))
        _kill_port_processes(port)
        _set_chrome_prefs(profile)
        _launch_headless_daemon(profile, port)
        if not await _wait_cdp_ready(port):
            return None, f"Chrome no expuso CDP en el puerto {port} a tiempo"

    # _launch_headless_daemon only opens about:blank — nothing navigates to
    # WhatsApp Web on its own, and a reused daemon might also be sitting at
    # about:blank from a previous run. _check_session_status does that
    # navigation (via WASession._setup_page) either way and leaves the tab
    # at "restored" or "qr_needed" — exactly what _fetch_qr expects.
    await _check_session_status(profile)

    from wavi.cli import _session_port
    return _session_port(profile), None


async def _with_page(cdp_port: int, fn):
    from playwright.async_api import async_playwright

    pw = await async_playwright().start()
    browser = None
    try:
        browser = await pw.chromium.connect_over_cdp(
            f"http://localhost:{cdp_port}", timeout=10_000
        )
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()
        return await fn(page)
    finally:
        if browser is not None:
            try:
                await browser.close()
            except Exception:
                pass
        await pw.stop()


async def _fetch_qr(cdp_port: int) -> dict:
    async def _go(page):
        try:
            await page.wait_for_selector(f"{_AUTH_SEL}, {_QR_SEL}", timeout=20_000)
        except Exception:
            return {"ok": False, "error": "timeout esperando WA Web"}

        if await page.query_selector(_AUTH_SEL):
            return {"ok": True, "state": "restored"}

        qr_el = await page.query_selector(
            "[data-testid='qrcode']"
        ) or await page.query_selector("div[data-ref]")
        if not qr_el:
            return {"ok": False, "error": "QR no encontrado en la página"}

        ref = await page.evaluate(_DATA_REF_JS) or ""
        qr_bytes = await qr_el.screenshot()
        return {
            "ok": True,
            "state": "qr",
            "qr_b64": base64.b64encode(qr_bytes).decode(),
            "ref": ref,
        }

    try:
        return await _with_page(cdp_port, _go)
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def _handle_qr_request(profile: Path) -> dict:
    port, err = await _ensure_daemon_ready(profile)
    if err:
        return {"ok": False, "error": err}
    return await _fetch_qr(port)


async def _check_status(cdp_port: int, ref: str) -> dict:
    async def _go(page):
        if await page.query_selector(_AUTH_SEL):
            return {"state": "restored"}
        curr_ref = (await page.evaluate(_DATA_REF_JS)) or ""
        if ref and curr_ref and curr_ref != ref:
            return {"state": "expired"}
        return {"state": "waiting"}

    try:
        return await _with_page(cdp_port, _go)
    except Exception as e:
        return {"state": "error", "error": str(e)}


async def _handle_status_request(profile: Path, ref: str) -> dict:
    from wavi.session import WASession

    if not WASession(profile).daemon_alive():
        return {"state": "waiting"}
    from wavi.cli import _session_port
    return await _check_status(_session_port(profile), ref)


def _make_handler(profile: Path, on_event, shutdown_event: threading.Event):
    page_bytes = _PAGE_HTML.encode("utf-8")

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # silence default request logging
            pass

        def _send_json(self, obj: dict, status: int = 200) -> None:
            body = json.dumps(obj).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):  # noqa: N802 — http.server API
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(page_bytes)))
                self.end_headers()
                self.wfile.write(page_bytes)
            elif parsed.path == "/api/qr":
                result = asyncio.run(_handle_qr_request(profile))
                on_event("qr_fetched", ok=result.get("ok"), state=result.get("state"), error=result.get("error"))
                self._send_json(result)
                if result.get("state") == "restored":
                    shutdown_event.set()
            elif parsed.path == "/api/status":
                ref = (parse_qs(parsed.query).get("ref") or [""])[0]
                result = asyncio.run(_handle_status_request(profile, ref))
                if result.get("state") in ("restored", "expired"):
                    on_event("qr_status_" + result["state"])
                self._send_json(result)
                if result.get("state") == "restored":
                    shutdown_event.set()
            else:
                self.send_response(404)
                self.end_headers()

    return Handler


def serve(profile: Path, open_browser: bool = True, on_event=None) -> None:
    """Serve the mini QR web app until WhatsApp links successfully or Ctrl-C.

    Starts immediately regardless of whether the session's Chrome daemon is
    running — pressing "Buscar QR" is what launches it if needed (see
    _ensure_daemon_ready). Closes itself automatically once /api/status (or
    /api/qr) observes the AUTH selector, releasing its claimed port back to
    the Local Agent Society registry either way (Ctrl-C, `kill`, or
    self-shutdown on success all go through the same cleanup path).

    `on_event(name, **fields)` is called for qr_fetched / qr_status_restored /
    qr_status_expired, so the caller can persist a forensic trail (see
    wavi/events.py) without this module needing to know about it.
    """
    if on_event is None:
        on_event = lambda *a, **k: None  # noqa: E731

    port = _claim_port(str(profile))
    shutdown_event = threading.Event()
    server = ThreadingHTTPServer(("127.0.0.1", port), _make_handler(profile, on_event, shutdown_event))
    url = f"http://127.0.0.1:{port}/"
    click.echo(f"wavi qr → {url}")
    click.echo("Se cierra sola al detectar que WhatsApp quedó vinculado, o con Ctrl-C.")
    if open_browser:
        webbrowser.open(url)

    server_thread = threading.Thread(target=server.serve_forever, daemon=True)
    server_thread.start()

    # `kill <pid>` (SIGTERM) does NOT raise KeyboardInterrupt — only Ctrl-C
    # (SIGINT) does. Without this handler, a plain `kill` bypasses cleanup
    # and leaks the port claim in the Society registry forever (shows up as
    # a GHOST in 'las ports audit').
    def _on_sigterm(signum, frame):
        shutdown_event.set()

    old_handler = signal.signal(signal.SIGTERM, _on_sigterm)
    try:
        while not shutdown_event.wait(timeout=1):
            pass
    except KeyboardInterrupt:
        pass
    finally:
        signal.signal(signal.SIGTERM, old_handler)
        server.shutdown()
        server_thread.join(timeout=5)
        _release_port(port)
