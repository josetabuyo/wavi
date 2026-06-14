"""
cli.py — wavi command-line interface.

Commands:
  wavi connect   [session]            — start Chrome daemon + QR scan (if needed)
  wavi stop      [session]            — gracefully shut down Chrome daemon
  wavi get       [session] <contact>  — capture full message history from a chat
  wavi status    [session]            — check if session daemon is alive + authenticated
  wavi bubbles   <screenshot>         — run vision pipeline on a local screenshot

Session model
─────────────
'wavi connect' tries headless first (optimistic strategy).  If WA loads
authenticated, the headless daemon keeps running — no visible window ever
appears.  Only if QR is needed does it kill the headless Chrome and open a
visible window for scanning.  After QR confirmation, it switches back to
headless.  All subsequent commands connect to the headless daemon via CDP.
'wavi stop' performs a graceful shutdown (navigates to about:blank, then SIGTERM).
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import click
from dotenv import load_dotenv

from wavi.session import CDP_PORT, PID_FILE, PORT_FILE, WINDOW_H, WINDOW_W

load_dotenv()

DEFAULT_SESSIONS_DIR = Path(__file__).parent.parent / "data" / "sessions"
REAL_CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")

_HEADLESS_CHROME_ARGS = [
    "--no-first-run",
    "--no-default-browser-check",
    "--disable-session-crashed-bubble",
    "--restore-last-session=false",
    "--disable-extensions",
    "--disable-default-apps",
    "--disable-component-update",
    "--disable-background-timer-throttling",
    "--disable-renderer-backgrounding",
    "--disable-backgrounding-occluded-windows",
    "--disable-features=CalculateNativeWinOcclusion",
    # ADR-002: force DPR=1 so --window-size=1280x1920 maps 1:1 to CSS pixels.
    # Without this, macOS Retina sets DPR=2 and the effective viewport is ~640x960,
    # producing "tiny" screenshots with few visible messages.
    "--force-device-scale-factor=1",
    # Silence: prevent any audio from reaching the system speakers when wavi
    # clicks play buttons to capture audio blobs. --headless=new suppresses
    # most audio on Linux but on macOS CoreAudio can still route sound through.
    "--mute-audio",
]

_VISIBLE_CHROME_ARGS = _HEADLESS_CHROME_ARGS  # same flags, no --headless=new


_DEFAULT_ALIAS_FILE = DEFAULT_SESSIONS_DIR / ".default"


def _profile(session: str) -> Path:
    """Return the filesystem path for a session.

    'default' is an alias: it resolves to whatever session name is stored in
    data/sessions/.default (written after QR scan or set manually).
    If the alias file doesn't exist, falls back to the literal 'default' dir.
    """
    if session == "default" and _DEFAULT_ALIAS_FILE.exists():
        target = _DEFAULT_ALIAS_FILE.read_text().strip()
        if target:
            return DEFAULT_SESSIONS_DIR / target
    return DEFAULT_SESSIONS_DIR / session


def _set_default_alias(session_name: str) -> None:
    """Point the 'default' alias to a specific session name."""
    DEFAULT_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    _DEFAULT_ALIAS_FILE.write_text(session_name)


# ── helpers ───────────────────────────────────────────────────────────────────

def _kill_port_processes(port: int) -> None:
    result = subprocess.run(
        ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
        capture_output=True, text=True,
    )
    for pid in result.stdout.strip().split("\n"):
        if pid.strip():
            subprocess.run(["kill", "-TERM", pid.strip()], capture_output=True)


_SOCIETY_URL    = "http://localhost:8700"
_WAVI_PORT_START = 9200
_WAVI_PORT_END   = 9249


def _claim_port(session_path: str) -> int:
    """
    Claim a CDP port from the Local Agent Society registry (atomic find+register).
    Falls back to GET /ports/free + POST /ports if /ports/claim not yet available.
    Final fallback: local socket scan.
    """
    import urllib.error as _err
    import urllib.request as _req

    payload = json.dumps({
        "app": "WhatsApp CDP daemon",
        "local_agent": "Wavi",
        "path": session_path,
        "start": _WAVI_PORT_START,
        "end": _WAVI_PORT_END,
    }).encode()

    # ── 1. Atomic claim (preferred) ───────────────────────────────────────────
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
        return json.loads(r.read())["port"]
    except _err.HTTPError as e:
        if e.code != 404:
            raise
    except Exception:
        pass

    # ── 2. Two-step fallback (GET free → POST register) ───────────────────────
    try:
        r = _req.urlopen(
            f"{_SOCIETY_URL}/ports/free?start={_WAVI_PORT_START}&end={_WAVI_PORT_END}",
            timeout=2,
        )
        port = json.loads(r.read())["port"]
        reg_payload = json.dumps({
            "port": port,
            "app": "WhatsApp CDP daemon",
            "local_agent": "Wavi",
            "path": session_path,
        }).encode()
        _req.urlopen(
            _req.Request(
                f"{_SOCIETY_URL}/ports",
                data=reg_payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            ),
            timeout=2,
        )
        return port
    except Exception:
        pass

    # ── 3. Last resort: local socket scan (no registry, no society) ───────────
    for port in range(_WAVI_PORT_START, _WAVI_PORT_END + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return _WAVI_PORT_START


def _release_port(port: int) -> None:
    """Release a CDP port back to the society registry."""
    import urllib.request as _req
    try:
        _req.urlopen(
            _req.Request(f"{_SOCIETY_URL}/ports/{port}", method="DELETE"),
            timeout=2,
        )
    except Exception:
        pass


def _pick_free_port(start: int = 9200, end: int = 9299) -> int:
    """Local socket scan fallback — prefer _claim_port() for new sessions."""
    for port in range(start, end + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    return start


def _session_port(profile: Path) -> int:
    """Read the CDP port for a session from disk, fallback to CDP_PORT."""
    try:
        return int((profile / PORT_FILE).read_text().strip())
    except Exception:
        return CDP_PORT


def _set_chrome_prefs(profile: Path) -> None:
    """Pre-set Chrome permissions in Preferences (deny mic/camera/notifications)."""
    import json as _json
    prefs_path = profile / "Default" / "Preferences"
    prefs = {}
    if prefs_path.exists():
        try:
            prefs = _json.loads(prefs_path.read_text())
        except Exception:
            pass
    prefs.setdefault("profile", {}).setdefault("default_content_setting_values", {}).update({
        "media_stream_mic": 2,
        "media_stream_camera": 2,
        "notifications": 2,
    })
    prefs_path.parent.mkdir(parents=True, exist_ok=True)
    prefs_path.write_text(_json.dumps(prefs))


def _cleanup_crash_files(profile: Path) -> None:
    """Remove Chrome crash-recovery files to avoid restore-session dialogs."""
    default_dir = profile / "Default"
    for f in ("Last Session", "Last Tabs", "Last Browser State", "Current Session", "Current Tabs"):
        (default_dir / f).unlink(missing_ok=True)
    for d in ("Sessions", "SessionStorage"):
        p = default_dir / d
        if p.exists():
            shutil.rmtree(p, ignore_errors=True)


def _launch_headless_daemon(profile: Path, port: int) -> subprocess.Popen:
    """Launch headless Chrome daemon on `port`, save PID and port, return the process."""
    (profile / "SingletonLock").unlink(missing_ok=True)
    proc = subprocess.Popen(
        ["arch", "-arm64", str(REAL_CHROME)]
        + [f"--user-data-dir={profile}", f"--remote-debugging-port={port}"]
        + _HEADLESS_CHROME_ARGS
        + ["--headless=new", f"--window-size={WINDOW_W},{WINDOW_H}", "about:blank"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    (profile / PID_FILE).write_text(str(proc.pid))
    (profile / PORT_FILE).write_text(str(port))
    return proc


def _terminate_proc(proc: subprocess.Popen, timeout: int = 8) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


async def _check_session_status(profile: Path) -> str:
    from wavi.session import WASession
    s = WASession(profile)
    try:
        status = await s.connect()
        await s.close()
        return status
    except Exception:
        return "error"


async def _stop_daemon_for_profile(profile: Path) -> None:
    """Stop the Chrome daemon for a profile without printing messages."""
    from wavi.session import WASession
    s = WASession(profile)
    port = s._load_port()
    try:
        await s.connect()
    except Exception:
        pass
    await s.stop_daemon()
    _release_port(port)


@contextlib.contextmanager
def _lazy_session(profile: Path):
    """Auto-stop Chrome after a command if it wasn't running beforehand.

    The commands' internal WASession.connect() already handles auto-start via
    its fallback Chrome path.  This context manager's only job is to track
    whether a daemon was alive *before* the command ran, and if not, stop
    whatever daemon the command may have started on exit.

    Contextualized invocation (daemon was already running): no-op on both
    enter and exit — the daemon outlives the command.

    Lazy invocation (no daemon before): command starts its own Chrome via the
    fallback path, runs, and on exit this manager stops it cleanly.
    """
    from wavi.session import WASession
    was_running = WASession(profile).daemon_alive()
    try:
        yield
    finally:
        if not was_running:
            try:
                if (profile / PID_FILE).exists():
                    asyncio.run(_stop_daemon_for_profile(profile))
            except Exception as e:
                import sys as _sys
                print(f"⚠️  Auto-stop failed: {e}", file=_sys.stderr)


# ── QR HTML helpers ───────────────────────────────────────────────────────────

def _write_qr_html(path: Path, qr_b64: str) -> None:
    html = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>wavi — Vincular WhatsApp</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: "Segoe UI", "Helvetica Neue", Helvetica, Lucida Grande, Arial, Ubuntu, Cantarell, "Fira Sans", sans-serif;
      background: #f0f2f5; display: flex; flex-direction: column;
      align-items: center; justify-content: center;
      min-height: 100vh; padding: 24px; color: #111; text-align: center;
    }}
    .card {{
      background: #fff; border-radius: 16px; padding: 40px 48px;
      box-shadow: 0 2px 15px rgba(11,20,26,.15); max-width: 480px; width: 100%;
    }}
    .logo {{ color: #00a884; font-size: 1.1rem; font-weight: 700;
             letter-spacing: .04em; margin-bottom: 20px; }}
    h1 {{ font-size: 1.5rem; font-weight: 400; margin-bottom: 8px; }}
    .sub {{ color: #667; font-size: 1rem; margin-bottom: 28px; line-height: 1.6; }}
    img.qr {{
      width: 320px; height: 320px; border: 1px solid #e9edef;
      border-radius: 4px; display: block; margin: 0 auto 28px;
    }}
    #status {{ font-size: 1rem; color: #667; margin-top: 4px; }}
    #status b {{ color: #111; font-size: 1.6rem; font-weight: 700; }}
    #status.expired {{ color: #e53935; font-weight: 600; font-size: 1.1rem; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="logo">wavi</div>
    <h1>Escaneá el código QR</h1>
    <p class="sub">
      Abrí WhatsApp en tu teléfono<br>
      <strong>Dispositivos vinculados → Vincular dispositivo</strong>
    </p>
    <img class="qr" src="data:image/png;base64,{qr_b64}" alt="WhatsApp QR">
    <p id="status">Este QR expira en <b id="sec">60</b> segundos</p>
  </div>
  <script>
    var sec = 60, el = document.getElementById('sec'), st = document.getElementById('status');
    var t = setInterval(function() {{
      sec--;
      if (sec <= 0) {{
        clearInterval(t);
        st.className = 'expired';
        st.textContent = 'QR expirado. Ejecutá wavi connect de nuevo.';
        setTimeout(function() {{ window.close(); }}, 1500);
      }} else {{
        el.textContent = sec;
      }}
    }}, 1000);
  </script>
</body>
</html>"""
    path.write_text(html, encoding="utf-8")


def _write_connected_html(path: Path) -> None:
    html = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>wavi — Vinculado</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #f0f2f5; display: flex; flex-direction: column;
      align-items: center; justify-content: center;
      min-height: 100vh; padding: 24px; text-align: center;
    }
    .card {
      background: white; border-radius: 16px; padding: 40px;
      box-shadow: 0 2px 16px rgba(0,0,0,.1); max-width: 360px; width: 100%;
    }
    .icon { font-size: 3rem; margin-bottom: 12px; }
    h1 { font-size: 1.3rem; color: #25d366; font-weight: 600; margin-bottom: 8px; }
    p { color: #667; font-size: .9rem; }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">&#10003;</div>
    <h1>&#161;WhatsApp vinculado!</h1>
    <p>wavi está conectado. Podés cerrar esta ventana.</p>
  </div>
</body>
</html>"""
    path.write_text(html, encoding="utf-8")


def _write_expired_html(path: Path) -> None:
    html = """<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8">
  <title>wavi — QR expirado</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #f0f2f5; display: flex; flex-direction: column;
      align-items: center; justify-content: center;
      min-height: 100vh; padding: 24px; text-align: center;
    }
    .card {
      background: white; border-radius: 16px; padding: 40px;
      box-shadow: 0 2px 16px rgba(0,0,0,.1); max-width: 360px; width: 100%;
    }
    .icon { font-size: 3rem; margin-bottom: 12px; }
    h1 { font-size: 1.3rem; color: #e53935; font-weight: 600; margin-bottom: 8px; }
    p { color: #667; font-size: .9rem; margin-bottom: 16px; }
    code {
      background: #f4f4f4; border-radius: 6px; padding: 10px 16px;
      display: block; font-size: .9rem; color: #333; text-align: left;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">&#9201;</div>
    <h1>QR expirado</h1>
    <p>El código expiró antes de ser escaneado.</p>
    <code>wavi connect</code>
  </div>
</body>
</html>"""
    path.write_text(html, encoding="utf-8")


_QR_HTML_PATH = (Path(__file__).parent.parent / "data" / "qr.html").resolve()

_QR_SEL  = "[data-testid='qrcode'], div[data-ref]"
_AUTH_SEL = "[data-testid='chat-list'], #side, input[role='textbox']"
_DATA_REF_JS = (
    "() => { const el = document.querySelector('div[data-ref]'); "
    "return el ? el.getAttribute('data-ref') : null; }"
)


async def _capture_qr(profile: Path, load_timeout_s: int = 60) -> str | None:
    """
    Connect to headless Chrome, wait for WA Web QR, screenshot it, write HTML.
    Returns the initial data-ref string (used by _poll_qr_auth to detect expiry),
    or None on failure.  Disconnects Playwright but leaves Chrome running.
    """
    import base64

    from playwright.async_api import async_playwright

    port = _session_port(profile)
    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.connect_over_cdp(
            f"http://localhost:{port}", timeout=10_000
        )
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        click.echo(f"Esperando QR en WA Web (URL: {page.url!r})...")
        try:
            await page.wait_for_selector(
                f"{_AUTH_SEL}, {_QR_SEL}", timeout=load_timeout_s * 1000
            )
        except Exception:
            click.echo(f"Timeout esperando QR/auth en {page.url!r}", err=True)
            await browser.close()
            await pw.stop()
            return None

        if await page.query_selector(_AUTH_SEL):
            await browser.close()
            await pw.stop()
            return "ALREADY_AUTHENTICATED"

        qr_el = (
            await page.query_selector("[data-testid='qrcode']")
            or await page.query_selector("div[data-ref]")
        )
        if not qr_el:
            click.echo("QR no encontrado para screenshot.", err=True)
            await browser.close()
            await pw.stop()
            return None

        initial_ref = await page.evaluate(_DATA_REF_JS)
        if not initial_ref:
            await asyncio.sleep(2)
            initial_ref = await page.evaluate(_DATA_REF_JS)

        qr_bytes = await qr_el.screenshot()
        qr_b64 = base64.b64encode(qr_bytes).decode()
        _QR_HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
        _write_qr_html(_QR_HTML_PATH, qr_b64)

        await browser.close()
        await pw.stop()
        return initial_ref or ""

    except Exception as e:
        click.echo(f"Error capturando QR: {e}", err=True)
        try:
            await pw.stop()
        except Exception:
            pass
        return None


async def _poll_qr_auth(profile: Path, initial_ref: str) -> str:
    """
    Reconnect to headless Chrome and poll every 2s until auth or QR expiry.
    Returns 'authenticated', 'expired', or 'timeout'.
    """
    from playwright.async_api import async_playwright

    port = _session_port(profile)
    pw = await async_playwright().start()
    try:
        browser = await pw.chromium.connect_over_cdp(
            f"http://localhost:{port}", timeout=10_000
        )
        ctx = browser.contexts[0] if browser.contexts else await browser.new_context()
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

        # Fallback timer when data-ref is unavailable (WA didn't expose it)
        qr_deadline = time.time() + 65  # ~60s WA QR lifetime + margin

        while True:
            await asyncio.sleep(2)

            if await page.query_selector(_AUTH_SEL):
                _write_connected_html(_QR_HTML_PATH)
                click.echo("Autenticado correctamente.")
                await browser.close()
                await pw.stop()
                return "authenticated"

            curr_ref = (await page.evaluate(_DATA_REF_JS)) or ""
            # Detect expiry via data-ref change (when available) or timer fallback
            if initial_ref and curr_ref and curr_ref != initial_ref:
                _write_expired_html(_QR_HTML_PATH)
                click.echo("QR expirado — ejecutá 'wavi connect' de nuevo para un QR fresco.")
                await browser.close()
                await pw.stop()
                return "expired"
            if not initial_ref and time.time() > qr_deadline:
                _write_expired_html(_QR_HTML_PATH)
                click.echo("QR expirado — ejecutá 'wavi connect' de nuevo para un QR fresco.")
                await browser.close()
                await pw.stop()
                return "expired"

    except Exception as e:
        click.echo(f"Error en bucle QR: {e}", err=True)
        try:
            await pw.stop()
        except Exception:
            pass
        return "timeout"


# ── CLI root ──────────────────────────────────────────────────────────────────

@click.group()
def main():
    """wavi — WhatsApp automation via vision."""


# ── connect ───────────────────────────────────────────────────────────────────

@main.command()
@click.argument("session", default="default")
@click.option("--open", "open_browser", is_flag=True, help="Open QR page in the default browser.")
@click.option("--new", "force_new", is_flag=True, help="Force a fresh QR scan (creates a new profile, skips any existing session).")
def connect(session: str, open_browser: bool, force_new: bool):
    """Start Chrome daemon and authenticate (headless + QR HTML if needed).

    Tries headless first — if WhatsApp loads authenticated no visible window
    ever opens.  If QR is needed, captures it headlessly and writes a local
    HTML file with a live countdown.  Pass --open to launch that page
    automatically.  The connect session closes when the QR is scanned or
    expires.

    Use --new to skip any existing session and force a fresh QR scan.  The
    session folder is automatically named after the phone number once scanned.

    SESSION is any name you choose (default: 'default').
    """
    if not REAL_CHROME.exists():
        click.echo(f"Chrome not found: {REAL_CHROME}", err=True)
        sys.exit(1)

    if force_new:
        profile = DEFAULT_SESSIONS_DIR / f"_tmp_{int(time.time())}"
        profile.mkdir(parents=True, exist_ok=True)
        click.echo(f"Perfil temporal (se renombrará al número detectado) → {profile}")
    else:
        profile = _profile(session)
        profile.mkdir(parents=True, exist_ok=True)
        click.echo(f"Session '{session}' → {profile}")

        # ── Fast path: daemon already alive and authenticated ─────────────────
        from wavi.session import WASession
        s = WASession(profile)
        if s.daemon_alive():
            click.echo("Daemon detectado, verificando sesión...")
            status = asyncio.run(_check_session_status(profile))
            if status == "restored":
                pid = s._load_pid()
                port = _session_port(profile)
                click.echo(f"Sesión '{session}' ya activa y autenticada (PID {pid}, CDP :{port}).")
                click.echo(f"Usá 'wavi get {session} <contacto>' para capturar mensajes.")
                click.echo(f"Usá 'wavi stop {session}' para cerrar Chrome de manera segura.")
                return
            click.echo(f"Daemon vivo pero sesión={status}. Relanzando...")

    # ── Claim a port from the society registry (or local fallback) ──────────
    port = _claim_port(str(profile))
    _kill_port_processes(port)
    time.sleep(1)

    # ── Launch headless Chrome ────────────────────────────────────────────────
    _set_chrome_prefs(profile)
    if not force_new:
        click.echo("Intentando restaurar sesión en modo headless...")
    headless_proc = _launch_headless_daemon(profile, port)
    time.sleep(3)

    status = asyncio.run(_check_session_status(profile))

    if not force_new and status == "restored":
        if session != "default":
            _set_default_alias(session)
        click.echo(f"Sesión restaurada — daemon headless activo (PID {headless_proc.pid}, CDP :{port}).")
        click.echo(f"Usá 'wavi get {session} <contacto>' para capturar mensajes.")
        click.echo(f"Usá 'wavi stop {session}' para cerrar Chrome de manera segura.")
        return

    # ── QR needed ────────────────────────────────────────────────────────────
    if not force_new:
        click.echo(f"Sesión no encontrada (estado={status}) — QR requerido.")
    click.echo("Capturando QR en modo headless...")

    initial_ref = asyncio.run(_capture_qr(profile))
    if initial_ref is None:
        _terminate_proc(headless_proc)
        sys.exit(1)

    click.echo(f"QR → {_QR_HTML_PATH}")
    if open_browser:
        subprocess.run(["open", "-n", f"file://{_QR_HTML_PATH}"])

    if initial_ref == "ALREADY_AUTHENTICATED":
        auth_result = "authenticated"
    else:
        auth_result = asyncio.run(_poll_qr_auth(profile, initial_ref))

    if auth_result != "authenticated":
        _terminate_proc(headless_proc)
        sys.exit(1)

    # ── Flush WA state and switch to headless daemon ──────────────────────────
    click.echo("Guardando sesión de WhatsApp...")

    _JS_READ_PHONE = """
    () => {
        try {
            // WA Web store — most reliable across versions
            const Store = window.require && (
                window.require('WAWebStorageLib/WAWebStorageLib') ||
                window.require('WAWebStoreLib/WAWebStoreLib')
            );
            if (Store && Store.Me) {
                const id = Store.Me.get('id');
                if (id && id.user) return id.user;
            }
        } catch(e) {}
        try {
            // Fallback: WA Web renders the phone in the profile drawer
            const spans = document.querySelectorAll('span[dir="ltr"]');
            for (const s of spans) {
                const t = s.textContent.trim().replace(/[^0-9]/g, '');
                if (t.length >= 10 && t.length <= 15) return t;
            }
        } catch(e) {}
        return null;
    }
    """

    detected_phone = None

    async def _flush_and_read_phone():
        nonlocal detected_phone
        from playwright.async_api import async_playwright
        try:
            pw = await async_playwright().start()
            browser = await pw.chromium.connect_over_cdp(
                f"http://localhost:{port}", timeout=5_000
            )
            if browser.contexts and browser.contexts[0].pages:
                page = browser.contexts[0].pages[0]
                try:
                    detected_phone = await page.evaluate(_JS_READ_PHONE)
                except Exception:
                    pass
                try:
                    await page.goto("about:blank", timeout=5_000)
                    await asyncio.sleep(2)
                except Exception:
                    pass
            await browser.close()
            await pw.stop()
        except Exception:
            pass

    asyncio.run(_flush_and_read_phone())
    if detected_phone:
        click.echo(f"Teléfono detectado: {detected_phone}")
    else:
        click.echo("No se pudo detectar el número de teléfono.", err=True)
    _terminate_proc(headless_proc)
    (profile / "SingletonLock").unlink(missing_ok=True)
    time.sleep(1)

    # Rename session folder to phone number
    if detected_phone and detected_phone != (profile.name if force_new else session):
        phone_profile = DEFAULT_SESSIONS_DIR / detected_phone
        if not phone_profile.exists():
            profile.rename(phone_profile)
            profile = phone_profile
            click.echo(f"Sesión creada → '{detected_phone}'")
        elif force_new:
            shutil.rmtree(phone_profile, ignore_errors=True)
            profile.rename(phone_profile)
            profile = phone_profile
            click.echo(f"Sesión '{detected_phone}' actualizada con nueva autenticación.")
        else:
            click.echo(f"Sesión '{detected_phone}' ya existe.")
        if not force_new:
            _set_default_alias(detected_phone)
            click.echo(f"'default' ahora apunta a '{detected_phone}'")
    elif not detected_phone and force_new:
        click.echo(f"No se detectó el número. Sesión guardada como '{profile.name}'.")
    elif session == "default" and not detected_phone:
        pass  # keep as-is, alias not updated
    else:
        _set_default_alias(session)

    click.echo("Iniciando daemon headless...")
    headless_proc = _launch_headless_daemon(profile, port)

    click.echo("Verificando sesión...")
    time.sleep(5)

    status = asyncio.run(_check_session_status(profile))
    final_name = detected_phone or profile.name
    if status == "restored":
        click.echo(f"Daemon headless activo (PID {headless_proc.pid}, CDP :{port}).")
        click.echo(f"Sesión: '{final_name}'")
    else:
        click.echo(f"Advertencia: sesión={status}. Puede requerir re-autenticación.", err=True)

    click.echo(f"Usá 'wavi get {final_name} <contacto>' para capturar mensajes.")
    click.echo(f"Usá 'wavi stop {final_name}' para cerrar Chrome de manera segura.")


# ── stop ──────────────────────────────────────────────────────────────────────

@main.command()
@click.argument("session", default="default")
def stop(session: str):
    """Gracefully shut down the Chrome daemon for SESSION.

    Navigates to about:blank first so WhatsApp can flush its state,
    then sends SIGTERM.  Never use kill -9 on a WA session directly.
    """
    profile = _profile(session)
    pid_file = profile / PID_FILE
    if not pid_file.exists():
        click.echo(f"No daemon PID file found for session '{session}'.", err=True)
        sys.exit(1)

    asyncio.run(_stop_daemon_for_profile(profile))
    click.echo("Daemon stopped cleanly.")


# ── status ────────────────────────────────────────────────────────────────────

@main.command()
@click.argument("session", default="default")
def status(session: str):
    """Check if SESSION daemon is alive and authenticated."""
    from wavi.session import WASession, _is_process_alive

    profile = _profile(session)
    if not profile.exists():
        click.echo(f"No profile found at {profile}", err=True)
        sys.exit(1)

    s = WASession(profile)

    pid = s._load_pid()
    if pid and _is_process_alive(pid):
        click.echo(f"daemon=running pid={pid}")
    else:
        click.echo("daemon=stopped")

    async def _run():
        result = await s.connect()
        await s.close()
        click.echo(f"session={result}")
        if result != "restored":
            sys.exit(1)

    asyncio.run(_run())


# ── get ───────────────────────────────────────────────────────────────────────

@main.command("get")
@click.argument("session", default="default")
@click.argument("contact")
@click.option("--assets", default=None, help="Directory to save screenshots and history.")
@click.option("--headless/--no-headless", default=True, show_default=True,
              help="Headless fallback (ignored when daemon is running headful).")
@click.option("--json-out", is_flag=True, help="Output results as JSON.")
@click.option("--max-iter", default=300, show_default=True,
              help="Max scroll iterations (use 3 for quick debug).")
@click.option("--from", "from_date", default=None,
              help="Stop scrolling at this date (YYYY-MM-DD). Captures messages on or after this date.")
@click.option("--newest", is_flag=True, help="Incremental update: stop when the first already-known message is found.")
@click.option("--grow", is_flag=True, help="Append older messages to existing history, block by block. Use with --max-iter to page through a long chat history in chunks.")
def get(session: str, contact: str, assets: str | None, headless: bool, json_out: bool, max_iter: int, from_date: str | None, newest: bool, grow: bool):
    """Capture the full message history from CONTACT's chat.

    Scrolls up from the most recent message, capturing all visible bubbles per
    iteration. iter_000/ holds the initial capture; subsequent iterations go
    toward the past. history_bubbles.json aggregates all deduplicated messages.

    NOTE: photos and videos are not detected by the vision pipeline.
    """
    from datetime import date as _Date

    from wavi.runner import run_enhanced

    profile_dir = _profile(session)
    assets_dir = Path(assets) if assets else Path("output") / profile_dir.name / contact.lower().replace(" ", "_")

    from_date_obj: _Date | None = None
    if from_date:
        try:
            from_date_obj = _Date.fromisoformat(from_date)
        except ValueError:
            click.echo(f"Error: --from debe ser una fecha en formato YYYY-MM-DD, recibido: {from_date}", err=True)
            sys.exit(1)

    if grow and newest:
        click.echo("Error: --grow y --newest son incompatibles (direcciones opuestas).", err=True)
        sys.exit(1)

    if assets_dir.exists() and not newest and not grow:
        shutil.rmtree(assets_dir)

    async def _go():
        return await run_enhanced(
            profile_dir=profile_dir,
            contact=contact,
            assets_dir=assets_dir,
            headless=headless,
            max_iterations=max_iter,
            from_date=from_date_obj,
            newest=newest,
            grow=grow,
        )

    from wavi.queue import is_locked, session_lock
    prof = _profile(session)
    if is_locked(prof):
        click.echo(f"Sesión '{session}' ocupada — esperando en cola...")

    with session_lock(prof, "get", contact=contact):
        with _lazy_session(prof):
            try:
                result = asyncio.run(_go())
            except RuntimeError as e:
                click.echo(str(e), err=True)
                sys.exit(1)

    bubbles = result["bubbles"]

    if json_out:
        click.echo(json.dumps([b.as_dict() for b in bubbles], indent=2, ensure_ascii=False))
        return

    click.echo(f"\n{len(bubbles)} mensaje(s) en el historial:")
    for b in bubbles:
        ts = f" [{b.timestamp}]" if b.timestamp else ""
        click.echo(f"  #{b.id:04d} {b.sender:5s} {b.msg_type:6s}{ts}  {b.text[:80]}")

    import glob
    ogg_files = glob.glob(str(assets_dir / "iter_*" / "audio_*.ogg"))
    if ogg_files:
        click.echo(f"\n{len(ogg_files)} audio(s) descargados:")
        for f in sorted(ogg_files):
            size = Path(f).stat().st_size
            click.echo(f"  {Path(f).relative_to(assets_dir)}: {size} bytes")


# ── send ──────────────────────────────────────────────────────────────────────

@main.command("send")
@click.argument("session", default="default")
@click.argument("contact")
@click.argument("message")
@click.option("--screenshot-out", default=None, help="Save a screenshot of the chat after sending.")
def send(session: str, contact: str, message: str, screenshot_out: str | None):
    """Send MESSAGE to CONTACT via WhatsApp.

    Opens the chat with CONTACT, types MESSAGE, and presses Enter.
    Use your own phone number as CONTACT to send a self-message for testing.

    Example:
      wavi send default "+54 9 11 5561 2767" "hola mundo"
    """
    profile = _profile(session)

    async def _go():
        from wavi.session import WASession
        s = WASession(profile)
        try:
            status = await s.connect()
            if status != "restored":
                raise RuntimeError(f"Sesión no autenticada (estado={status}). Ejecutá 'wavi connect' primero.")

            await s.navigate_to_contact(contact)
            meta = await s.send_message(message)
            click.echo(f"Mensaje enviado a '{contact}' (input @ {meta['x']},{meta['y']})")

            if screenshot_out:
                shot_path = Path(screenshot_out)
                await s.screenshot_to_file(shot_path)
                click.echo(f"Screenshot guardado: {shot_path}")
        finally:
            await s.close()

    from wavi.queue import is_locked, session_lock
    if is_locked(profile):
        click.echo(f"Sesión '{session}' ocupada — esperando en cola...")

    with session_lock(profile, "send", contact=contact):
        with _lazy_session(profile):
            try:
                asyncio.run(_go())
            except RuntimeError as e:
                click.echo(str(e), err=True)
                sys.exit(1)


# ── queue ─────────────────────────────────────────────────────────────────────

@main.command("queue")
@click.argument("session", default="default")
@click.option("--json-out", is_flag=True, help="Output status as JSON.")
def queue_status(session: str, json_out: bool):
    """Show the current operation queue status for SESSION.

    Prints 'idle' when no operation is running, or details of the in-progress
    operation (type, contact, PID, elapsed time).
    """
    from wavi.queue import get_status

    profile = _profile(session)
    status = get_status(profile)

    if json_out:
        click.echo(json.dumps(status or {}, indent=2, ensure_ascii=False))
        return

    if not status:
        click.echo(f"session={session} idle")
        return

    op      = status.get("operation", "?")
    pid     = status.get("pid", "?")
    started = status.get("started_at", "")
    contact = status.get("contact", "")

    elapsed = ""
    if started:
        try:
            from datetime import UTC, datetime
            delta = datetime.now(UTC) - datetime.fromisoformat(started)
            mins, secs = divmod(int(delta.total_seconds()), 60)
            elapsed = f" (running {mins}m{secs:02d}s)"
        except Exception:
            pass

    contact_str = f" contact={contact!r}" if contact else ""
    click.echo(f"session={session}")
    click.echo(f"operation={op}{contact_str} pid={pid} started={started}{elapsed}")


# ── bubbles ───────────────────────────────────────────────────────────────────

@main.command()
@click.argument("screenshot", type=click.Path(exists=True))
@click.option("--assets", default=None, help="Directory to save cropped image and bubbles.json.")
@click.option("--json-out", is_flag=True, help="Output results as JSON.")
@click.option("--debug/--no-debug", default=True, show_default=True, help="Save debug visualization image.")
def bubbles(screenshot: str, assets: str | None, json_out: bool, debug: bool):
    """Run vision pipeline on a local SCREENSHOT file (no browser needed)."""
    from wavi.vision import analyze

    shot = Path(screenshot)
    assets_dir = Path(assets) if assets else shot.parent

    result = analyze(shot, assets_dir=assets_dir, save_debug=debug)

    if json_out:
        click.echo(json.dumps([b.as_dict() for b in result], indent=2, ensure_ascii=False))
        return

    click.echo(f"{len(result)} mensaje(s) detectados:")
    for b in result:
        ts = f" [{b.timestamp}]" if b.timestamp else ""
        click.echo(f"  #{b.id:02d} {b.sender:5s} {b.msg_type:6s}{ts}  {b.text[:80]}")


# ── boarding ──────────────────────────────────────────────────────────────────

@main.command()
@click.option("--open", "open_browser", is_flag=True, help="Open in the default browser.")
def boarding(open_browser: bool):
    """Print the path to the wavi onboarding page.

    By default prints the file path (safe for agent/script use).
    Pass --open to launch the default browser.

    \b
    Examples:
      wavi boarding                  # print path
      wavi boarding --open           # open in browser
      open $(wavi boarding)          # shell one-liner
    """
    html_path = (Path(__file__).parent.parent / "docs" / "boarding.html").resolve()
    if not html_path.exists():
        click.echo(f"boarding.html not found at {html_path}", err=True)
        sys.exit(1)
    click.echo(str(html_path))
    if open_browser:
        import subprocess
        subprocess.run(["open", f"file://{html_path}"])


# ── check-updates ────────────────────────────────────────────────────────────

@main.command("check-updates")
@click.argument("session", default="default")
@click.option("--assets", "assets_dir", default=None,
              help="Directory to store snapshots and state. "
                   "Defaults to output/<session>/last-updates/.")
@click.option("--reset", is_flag=True,
              help="Ignore previous snapshot and treat this run as the first one.")
def check_updates(session: str, assets_dir: str | None, reset: bool):
    """Check WhatsApp sidebar for new inbound messages.

    Extracts every visible chat row (name, last message, timestamp, direction)
    via DOM and compares it against the previous saved state.  Saves
    updates.json and snapshot_current.png to the output directory.  On the
    first run (or with --reset) saves the baseline.  On subsequent runs returns
    'no_updates' when nothing changed, or 'updates' with the chats whose last
    message is new AND inbound.

    \b
    Examples:
      wavi check-updates
      wavi check-updates myphone
      wavi check-updates --reset
    """
    from wavi.runner import WARunner

    profile_dir = _profile(session)
    assets_path = (
        Path(assets_dir)
        if assets_dir
        else Path("output") / profile_dir.name / "last-updates"
    )
    from wavi.queue import is_locked, session_lock
    if is_locked(profile_dir):
        click.echo(f"Sesión '{session}' ocupada — esperando en cola...")

    runner = WARunner(profile_dir)
    with session_lock(profile_dir, "check-updates"):
        with _lazy_session(profile_dir):
            result = asyncio.run(runner.check_updates(assets_dir=assets_path, reset=reset))

    status = result["status"]
    new_inbound = result.get("new_inbound", [])
    checked_at = result.get("checked_at", "")

    if status == "no_updates":
        click.echo(f"no_updates  [{checked_at}]")
    elif status == "first_run":
        click.echo(f"first_run  baseline saved  [{checked_at}]")
    elif not new_inbound:
        click.echo(f"{status}  no new inbound messages  [{checked_at}]")
    else:
        click.echo(f"updates  {len(new_inbound)} new inbound message(s)  [{checked_at}]:")
        for c in new_inbound:
            msg = c.get("last_message", "")
            ts = c.get("timestamp", "")
            click.echo(f"  {c['name']}  {ts}  \"{msg}\"")

    if result.get("assets_dir"):
        click.echo(f"\n→ {result['assets_dir']}/")


# ── list-contacts ────────────────────────────────────────────────────────────

@main.command("list-contacts")
@click.argument("session", default="default")
@click.option("--json-out", is_flag=True, help="Output results as JSON.")
@click.option("--headless/--no-headless", default=True, show_default=True,
              help="Run Chrome headless (default) or visible.")
@click.option("--assets", "assets_dir", default=None,
              help="Directory to save contacts_list.json + screenshot.png. "
                   "Defaults to output/<session>/contacts/.")
def list_contacts(session: str, json_out: bool, headless: bool, assets_dir: str):
    """List all contacts available in the 'New chat' panel."""
    import json as _json

    from wavi.runner import WARunner

    profile_dir = _profile(session)
    assets_path = Path(assets_dir) if assets_dir else Path("output") / profile_dir.name / "contacts"
    from wavi.queue import is_locked, session_lock
    if is_locked(profile_dir):
        click.echo(f"Sesión '{session}' ocupada — esperando en cola...")

    runner = WARunner(profile_dir, headless=headless)
    with session_lock(profile_dir, "list-contacts"):
        with _lazy_session(profile_dir):
            result = asyncio.run(runner.list_contacts(assets_dir=assets_path))

    contacts = result.get("contacts", [])
    shot = result.get("screenshot")
    adir = result.get("assets_dir")

    if json_out:
        click.echo(_json.dumps(result, ensure_ascii=False, indent=2))
    else:
        click.echo(f"Found {len(contacts)} contacts:")
        for c in contacts:
            line = c["name"]
            if c.get("subtitle"):
                line += f"  ({c['subtitle']})"
            click.echo(f"  {line}")
        if adir:
            click.echo(f"\nOutput: {adir}/")
            if shot:
                click.echo(f"  screenshot.png  ← browser viewport at {shot}")


