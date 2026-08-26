"""
cli.py — wavi command-line interface.

Commands:
  wavi connect   [session]            — start Chrome daemon, wait for WA auth
  wavi qr        [session]            — mini web app: fetch QR on demand, never stale
  wavi reload    [session]            — safe about:blank→WA cycle to flush/recover state
  wavi stop      [session]            — gracefully shut down Chrome daemon
  wavi events    [session]            — show the session lifecycle log (connects, QR, archives)
  wavi get       [session] <contact>  — capture full message history from a chat
  wavi status    [session]            — check if session daemon is alive + authenticated
  wavi bubbles   <screenshot>         — run vision pipeline on a local screenshot
  wavi alias     set/list/remove      — manage human-readable session aliases

Session model
─────────────
'wavi connect' tries headless first (optimistic strategy).  If WA loads
authenticated, the headless daemon keeps running — no visible window ever
appears.  Only if QR is needed does it kill the headless Chrome and open a
visible window for scanning.  After QR confirmation, it switches back to
headless.  All subsequent commands connect to the headless daemon via CDP.
'wavi stop' performs a graceful shutdown (navigates to about:blank, then SIGTERM).

Alias system
────────────
Session names can be human-readable aliases defined in data/sessions/aliases.json.
All commands accept an alias wherever a session argument is expected.
  wavi alias set pulpo-bot 5491155612767
  wavi alias set mateo 5491122608221
  wavi status pulpo-bot
  wavi get mateo "Contacto"

LID protection (--new)
──────────────────────
WhatsApp Web assigns a LID (Linked Device ID) to each new session registration.
'wavi connect --new' now validates that the detected phone looks like an E.164
number (7–15 digits, server==='c.us') and falls back to the SESSION argument if
the JS returns a WA-internal LID instead of the real phone number.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

import click
from dotenv import load_dotenv

from wavi.events import log_event
from wavi.session import CDP_PORT, PID_FILE, PORT_FILE, WINDOW_H, WINDOW_W

load_dotenv()

def _resolve_sessions_dir() -> Path:
    # 1. Explicit env var (pipx installs, CI, Pulpo, any non-repo context)
    if "WAVI_SESSIONS_DIR" in os.environ:
        return Path(os.environ["WAVI_SESSIONS_DIR"])
    # 2. Repo-relative path — only valid for editable/dev installs, i.e. when
    # __file__ actually sits inside the wavi git repo (pyproject.toml marker),
    # not a pipx/site-packages copy that happens to ship its own data/ dir.
    repo_root = Path(__file__).parent.parent
    repo_relative = repo_root / "data" / "sessions"
    if (repo_root / "pyproject.toml").exists():
        return repo_relative
    # 3. XDG fallback for pipx/system installs without env var
    xdg_data = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return xdg_data / "wavi" / "sessions"

DEFAULT_SESSIONS_DIR = _resolve_sessions_dir()
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
_ALIASES_FILE = DEFAULT_SESSIONS_DIR / "aliases.json"


def _load_aliases() -> dict[str, str]:
    """Load session aliases from aliases.json, migrating legacy .default if needed."""
    if _ALIASES_FILE.exists():
        try:
            return json.loads(_ALIASES_FILE.read_text())
        except Exception:
            pass
    # Migrate legacy .default → aliases.json
    if _DEFAULT_ALIAS_FILE.exists():
        target = _DEFAULT_ALIAS_FILE.read_text().strip()
        if target:
            return {"default": target}
    return {}


def _save_aliases(aliases: dict[str, str]) -> None:
    DEFAULT_SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    _ALIASES_FILE.write_text(json.dumps(aliases, indent=2, ensure_ascii=False) + "\n")


def _resolve_alias(name: str) -> str:
    """Resolve an alias to its session folder name. Returns name unchanged if not an alias."""
    return _load_aliases().get(name, name)


def _profile(session: str) -> Path:
    """Return the filesystem path for a session.

    Session can be an alias (defined in aliases.json) or a literal folder name.
    'default' always resolves via the alias table.
    """
    return DEFAULT_SESSIONS_DIR / _resolve_alias(session)


def _set_default_alias(session_name: str) -> None:
    """Point the 'default' alias to a specific session name."""
    aliases = _load_aliases()
    aliases["default"] = session_name
    _save_aliases(aliases)
    # Keep legacy .default in sync for external tools that may read it
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


async def _wait_cdp_ready(port: int, timeout_s: int = 20) -> bool:
    """Poll the CDP port directly until Chrome answers, or timeout_s elapses.

    Critical: call this BEFORE _check_session_status()/WASession.connect().
    WASession.connect() has its own fallback that spawns a *second* headless
    Chrome on the same profile+port the moment CDP doesn't answer instantly —
    if the daemon we just launched here hasn't finished booting yet, that
    fallback races it, leaving two live Chrome processes bound to the same
    profile (one via IPv4, one via IPv6) with no reliable way to kill the
    first later. Waiting here for the daemon we actually launched to become
    reachable avoids ever triggering that fallback.
    """
    from playwright.async_api import async_playwright

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        pw = await async_playwright().start()
        try:
            browser = await pw.chromium.connect_over_cdp(f"http://localhost:{port}", timeout=1_500)
            await browser.close()
            await pw.stop()
            return True
        except Exception:
            try:
                await pw.stop()
            except Exception:
                pass
            await asyncio.sleep(0.5)
    return False


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


# ── QR auth wait ──────────────────────────────────────────────────────────────
# The visible QR itself is never rendered here — 'wavi qr' (wavi/qr_server.py)
# owns that entirely, via its own on-demand, always-fresh mini web app. This
# module only needs to know whether WA is authenticated yet.

_AUTH_SEL = "[data-testid='chat-list'], #side, input[role='textbox']"


async def _wait_for_auth(profile: Path, timeout_s: int = 600) -> str:
    """Poll the running daemon over CDP (read-only) until WA is authenticated.

    Never navigates or writes to the tab — 'wavi qr' is what fetches/refreshes
    the QR the user scans. This just waits for the result. Returns
    'authenticated' or 'timeout'.
    """
    from playwright.async_api import async_playwright

    port = _session_port(profile)
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        pw = await async_playwright().start()
        try:
            browser = await pw.chromium.connect_over_cdp(
                f"http://localhost:{port}", timeout=5_000
            )
            ctx = browser.contexts[0] if browser.contexts else None
            page = ctx.pages[0] if ctx and ctx.pages else None
            if page and await page.query_selector(_AUTH_SEL):
                await browser.close()
                await pw.stop()
                click.echo("Autenticado correctamente.")
                return "authenticated"
            await browser.close()
        except Exception:
            pass
        finally:
            try:
                await pw.stop()
            except Exception:
                pass
        await asyncio.sleep(3)
    return "timeout"


# ── CLI root ──────────────────────────────────────────────────────────────────

@click.group()
def main():
    """wavi — WhatsApp automation via vision."""


# ── connect ───────────────────────────────────────────────────────────────────

@main.command()
@click.argument("session", default="default")
@click.option("--open", "open_browser", is_flag=True, help="Auto-launch 'wavi qr' for scanning.")
@click.option("--new", "force_new", is_flag=True, help="Force a fresh QR scan (creates a new profile, skips any existing session).")
def connect(session: str, open_browser: bool, force_new: bool):
    """Start the Chrome daemon and wait for WhatsApp authentication.

    Tries headless first — if WhatsApp loads authenticated no visible window
    ever opens. If a QR scan is needed, this command does NOT render or
    capture any QR itself: run 'wavi qr SESSION' (a small local web app,
    button-triggered, never a stale screenshot) to actually scan it. Pass
    --open here to launch that for you automatically. connect() then waits
    in the background until you've scanned.

    Use --new to register a fresh device without touching any existing
    session — the old profile is archived (renamed), never deleted. The
    session folder is automatically named after the phone number once
    scanned. See docs/adr/ADR-009-never-delete-session-profiles.md.

    SESSION is any name you choose (default: 'default').
    """
    if not REAL_CHROME.exists():
        click.echo(f"Chrome not found: {REAL_CHROME}", err=True)
        sys.exit(1)

    log_event(DEFAULT_SESSIONS_DIR, session, "connect_start", force_new=force_new)

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
                log_event(DEFAULT_SESSIONS_DIR, session, "connect_fastpath_restored", pid=pid, port=port)
                return
            click.echo(f"Daemon vivo pero sesión={status}. Relanzando...")
            log_event(DEFAULT_SESSIONS_DIR, session, "daemon_alive_but_unauth", status=status)

    # ── Claim a port from the society registry (or local fallback) ──────────
    port = _claim_port(str(profile))
    _kill_port_processes(port)
    time.sleep(1)

    # ── Launch headless Chrome ────────────────────────────────────────────────
    _set_chrome_prefs(profile)
    if not force_new:
        click.echo("Intentando restaurar sesión en modo headless...")
    headless_proc = _launch_headless_daemon(profile, port)
    if not asyncio.run(_wait_cdp_ready(port)):
        click.echo(f"Chrome no expuso CDP en el puerto {port} a tiempo.", err=True)
        _terminate_proc(headless_proc)
        sys.exit(1)

    status = asyncio.run(_check_session_status(profile))

    if not force_new and status == "restored":
        if session != "default":
            _set_default_alias(session)
        click.echo(f"Sesión restaurada — daemon headless activo (PID {headless_proc.pid}, CDP :{port}).")
        click.echo(f"Usá 'wavi get {session} <contacto>' para capturar mensajes.")
        click.echo(f"Usá 'wavi stop {session}' para cerrar Chrome de manera segura.")
        log_event(DEFAULT_SESSIONS_DIR, session, "connect_restored", pid=headless_proc.pid, port=port)
        return

    # ── QR needed ────────────────────────────────────────────────────────────
    # The QR itself is never captured or shown here — 'wavi qr' owns that via
    # its own on-demand, always-fresh mini web app (never a stale screenshot).
    if not force_new:
        click.echo(f"Sesión no encontrada (estado={status}) — QR requerido.")
    log_event(DEFAULT_SESSIONS_DIR, session, "qr_needed", status=status)
    click.echo("")
    click.echo(f"Corré 'wavi qr {session}' en otra terminal para escanear el QR")
    click.echo("(nunca vence: apretás el botón las veces que haga falta).")
    click.echo("")
    if open_browser:
        subprocess.Popen(["wavi", "qr", session])

    click.echo("Esperando a que escanees el QR...")
    auth_result = asyncio.run(_wait_for_auth(profile))
    log_event(DEFAULT_SESSIONS_DIR, session, "auth_wait_result", result=auth_result)

    if auth_result != "authenticated":
        click.echo(f"session={auth_result} — no se autenticó a tiempo.", err=True)
        _terminate_proc(headless_proc)
        sys.exit(1)

    # Give WhatsApp's backend time to durably commit the new device link
    # before we touch the tab at all. Our own AUTH_SEL check fires the
    # instant the *local* UI switches to the chat list, but the multi-device
    # link itself is still being confirmed with WA's servers for a few more
    # seconds — navigating away or killing the process during that window
    # reproducibly threw the session back to qr_needed (confirmed twice,
    # 2026-08-21: 'authenticated' logged, then 'qr_needed' ~9s later after
    # the flush+relaunch that used to happen immediately here).
    click.echo("Confirmando vínculo con WhatsApp (no cierres el teléfono)...")
    time.sleep(15)

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
                // WA now uses LIDs (Linked IDs) for privacy; server==='lid' means
                // id.user is an opaque internal ID, not the real phone number.
                // Only trust id.user when server==='c.us' (real phone) or undefined
                // (older WA versions that predate LIDs).
                if (id && id.user && id.server !== 'lid') return id.user;
                // Try serialized form: "1234567890@c.us" (never "@lid")
                if (id && id._serialized) {
                    const m = id._serialized.match(/^(\\d+)@c\\.us$/);
                    if (m) return m[1];
                }
                // Try explicit phone field
                const ph = Store.Me.get('phone');
                if (ph && typeof ph === 'string') {
                    const digits = ph.replace(/\\D/g, '');
                    if (digits.length >= 7) return digits;
                }
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

    # Validate: a real E.164-without-plus is 7–15 digits only.
    # If the JS returned something outside that range it's almost certainly a
    # WA-internal ID that slipped through (e.g. a LID from an older WA build
    # that doesn't expose id.server).  Discard it rather than naming the
    # session folder after an opaque ID.
    if detected_phone and not (detected_phone.isdigit() and 7 <= len(detected_phone) <= 15):
        click.echo(
            f"Advertencia: '{detected_phone}' no parece un número E.164 válido "
            f"({len(detected_phone)} dígitos) — descartando.", err=True
        )
        detected_phone = None

    if detected_phone:
        click.echo(f"Teléfono detectado: {detected_phone}")
    else:
        click.echo("No se pudo detectar el número de teléfono.", err=True)
        # --new with a phone-like session argument: use it as fallback so the
        # session doesn't end up named _tmp_<timestamp> or an opaque LID.
        if force_new and session != "default" and session.isdigit() and 7 <= len(session) <= 15:
            detected_phone = session
            click.echo(f"Usando el SESSION pasado como nombre de sesión: '{detected_phone}'")

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
            # Never delete an existing session profile — archive it instead.
            # A mistaken --new run must never destroy prior auth/browser state.
            archived = DEFAULT_SESSIONS_DIR / f"{detected_phone}_archived_{int(time.time())}"
            phone_profile.rename(archived)
            profile.rename(phone_profile)
            profile = phone_profile
            click.echo(f"Sesión '{detected_phone}' anterior archivada → '{archived.name}'")
            click.echo(f"Sesión '{detected_phone}' actualizada con nueva autenticación.")
            log_event(
                DEFAULT_SESSIONS_DIR, detected_phone, "profile_archived",
                archived_to=archived.name, reason="connect_new_collision",
            )
        else:
            click.echo(f"Sesión '{detected_phone}' ya existe.")
        if not force_new:
            _set_default_alias(detected_phone)
            click.echo(f"'default' ahora apunta a '{detected_phone}'")
    elif not detected_phone and force_new:
        click.echo(f"No se detectó el número. Sesión guardada como '{profile.name}'.", err=True)
        click.echo("AVISO: revisá 'wavi list' y renombrá la sesión manualmente.", err=True)
    elif session == "default" and not detected_phone:
        pass  # keep as-is, alias not updated
    else:
        _set_default_alias(session)

    click.echo("Iniciando daemon headless...")
    headless_proc = _launch_headless_daemon(profile, port)

    click.echo("Verificando sesión...")
    asyncio.run(_wait_cdp_ready(port))

    status = asyncio.run(_check_session_status(profile))
    final_name = detected_phone or profile.name
    if status == "restored":
        click.echo(f"Daemon headless activo (PID {headless_proc.pid}, CDP :{port}).")
        click.echo(f"Sesión: '{final_name}'")
    else:
        click.echo(f"Advertencia: sesión={status}. Puede requerir re-autenticación.", err=True)

    log_event(DEFAULT_SESSIONS_DIR, final_name, "connect_finished", status=status, pid=headless_proc.pid, port=port)
    click.echo(f"Usá 'wavi get {final_name} <contacto>' para capturar mensajes.")
    click.echo(f"Usá 'wavi stop {final_name}' para cerrar Chrome de manera segura.")


# ── reload ────────────────────────────────────────────────────────────────────

@main.command("reload")
@click.argument("session", default="default")
def reload_session(session: str):
    """Safely reload WhatsApp Web for SESSION without touching Chrome.

    Navigates to about:blank to let WA flush its IndexedDB state,
    waits for the flush, then navigates back to WhatsApp Web and
    verifies authentication.

    Use this when WA becomes unresponsive or throttled — NEVER use
    Page.reload via raw CDP, which interrupts in-flight IndexedDB
    writes and corrupts the session.

    \b
    Returns:
      session=restored  — WA loaded and authenticated
      session=qr_needed — WA loaded but auth lost (needs QR scan)
      session=timeout   — WA did not load within the timeout
      session=error     — daemon not running or CDP unreachable
    """
    profile = _profile(session)

    async def _go() -> str:
        from playwright.async_api import async_playwright
        port = _session_port(profile)
        pw = await async_playwright().start()
        try:
            browser = await pw.chromium.connect_over_cdp(
                f"http://localhost:{port}", timeout=5_000
            )
            ctx = browser.contexts[0] if browser.contexts else None
            if not ctx or not ctx.pages:
                await pw.stop()
                return "error"
            page = ctx.pages[0]

            # Step 1: flush — navigate away so WA commits all pending IndexedDB writes
            await page.goto("about:blank", timeout=8_000)
            await asyncio.sleep(3)

            # Step 2: reload WA
            await page.goto("https://web.whatsapp.com/", wait_until="domcontentloaded", timeout=30_000)

            # Step 3: wait for auth or QR
            QR = "[data-testid='qrcode'], div[data-ref], canvas"
            AUTH = "[data-testid='chat-list'], #side, input[role='textbox']"
            try:
                await page.wait_for_selector(f"{AUTH}, {QR}", timeout=60_000)
            except Exception:
                await browser.close()
                await pw.stop()
                return "timeout"

            result = "restored" if await page.query_selector(AUTH) else "qr_needed"
            await browser.close()
            await pw.stop()
            return result
        except Exception as e:
            click.echo(f"Error: {e}", err=True)
            try:
                await pw.stop()
            except Exception:
                pass
            return "error"

    from wavi.session import WASession
    s = WASession(profile)
    if not s.daemon_alive():
        click.echo(f"daemon=stopped — ejecutá 'wavi connect {session}' primero.", err=True)
        sys.exit(1)

    pid = s._load_pid()
    port = _session_port(profile)
    click.echo(f"Recargando WA para '{session}' (PID {pid}, CDP :{port})...")
    log_event(DEFAULT_SESSIONS_DIR, session, "reload_start", pid=pid, port=port)
    result = asyncio.run(_go())
    click.echo(f"session={result}")
    log_event(DEFAULT_SESSIONS_DIR, session, "reload_result", result=result)
    if result != "restored":
        sys.exit(1)


# ── qr ────────────────────────────────────────────────────────────────────────

@main.command("qr")
@click.argument("session", default="default")
@click.option("--no-open", "open_browser", is_flag=True, default=True, flag_value=False,
              help="No abrir el navegador automáticamente.")
def qr_cmd(session: str, open_browser: bool):
    """Open a local mini web app that vincula WhatsApp end-to-end.

    Self-contained: no separate 'wavi connect' step needed. The page opens
    immediately; pressing "Buscar QR" is what launches the session's Chrome
    daemon (if it isn't already running) and fetches whatever QR/auth state
    it shows. Never goes stale unnoticed — press the button again anytime
    for a fresh one. Closes itself once WhatsApp links successfully. Only
    reads the tab's DOM over CDP — never navigates or reloads it.
    """
    profile = _profile(session)
    log_event(DEFAULT_SESSIONS_DIR, session, "qr_web_started")
    from wavi.qr_server import serve
    serve(
        profile, open_browser=open_browser,
        on_event=lambda ev, **kw: log_event(DEFAULT_SESSIONS_DIR, session, ev, **kw),
    )


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
    log_event(DEFAULT_SESSIONS_DIR, session, "stop")


# ── events ────────────────────────────────────────────────────────────────────

@main.command("events")
@click.argument("session", default=None, required=False)
@click.option("-n", "limit", default=50, help="How many events to show (most recent).")
def events_cmd(session: str | None, limit: int):
    """Show the session lifecycle log — connects, QR fetches, archives, stops.

    Exists so a lost/qr_needed session is never a mystery again: every
    connect, archive, reload, and QR interaction is timestamped in
    <sessions_dir>/events.log. See docs/adr/ADR-009.
    """
    from wavi.events import read_events
    records = read_events(DEFAULT_SESSIONS_DIR, session=session, limit=limit)
    if not records:
        click.echo("Sin eventos registrados todavía.")
        return
    for r in records:
        extra = {k: v for k, v in r.items() if k not in ("ts", "session", "event")}
        extra_str = " ".join(f"{k}={v}" for k, v in extra.items() if v is not None)
        click.echo(f"{r['ts']}  {r['session']:<20}  {r['event']:<26}  {extra_str}")


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


# ── alias ─────────────────────────────────────────────────────────────────────

@main.group()
def alias():
    """Manage human-readable aliases for sessions.

    \b
    Examples:
      wavi alias set mateo 5491122608221
      wavi alias set pulpo-bot 5491155612767
      wavi alias list
      wavi alias remove mateo

    Once set, any command accepts the alias in place of the phone number:
      wavi get mateo "José"
      wavi status pulpo-bot
    """


@alias.command("set")
@click.argument("name")
@click.argument("session")
def alias_set(name: str, session: str):
    """Assign NAME as a friendly alias for SESSION (phone number or folder name)."""
    if name in ("default",) and not session:
        click.echo("Usá 'wavi connect' para cambiar el default.", err=True)
        sys.exit(1)
    profile = DEFAULT_SESSIONS_DIR / session
    if not profile.exists():
        click.echo(f"Sesión '{session}' no encontrada en {DEFAULT_SESSIONS_DIR}", err=True)
        sys.exit(1)
    aliases = _load_aliases()
    aliases[name] = session
    _save_aliases(aliases)
    if name == "default":
        _DEFAULT_ALIAS_FILE.write_text(session)
    click.echo(f"Alias '{name}' → '{session}'")


@alias.command("remove")
@click.argument("name")
def alias_remove(name: str):
    """Remove alias NAME (does not delete the session folder)."""
    if name == "default":
        click.echo("El alias 'default' no se puede eliminar.", err=True)
        sys.exit(1)
    aliases = _load_aliases()
    if name not in aliases:
        click.echo(f"Alias '{name}' no existe.", err=True)
        sys.exit(1)
    del aliases[name]
    _save_aliases(aliases)
    click.echo(f"Alias '{name}' eliminado.")


@alias.command("list")
def alias_list():
    """List all aliases and the session they point to."""
    aliases = _load_aliases()
    if not aliases:
        click.echo("No hay aliases definidos.")
        return
    for name, session in sorted(aliases.items()):
        profile = DEFAULT_SESSIONS_DIR / session
        marker = "✓" if profile.exists() else "✗ carpeta no encontrada"
        click.echo(f"  {name:<20} → {session}  {marker}")


# ── install-skill ─────────────────────────────────────────────────────────────

@main.command("install-skill")
def install_skill() -> None:
    """Install the wavi Claude Code skill to ~/.claude/skills/wavi/.

    Copies SKILL.md (session safety rules + command reference) to the location
    where Claude Code picks it up as the /wavi skill.  Run this after every
    'pip install --upgrade wavi-lib' to keep the skill in sync.

    \b
    After installing, restart Claude Code once to activate the skill.
    """
    skill_src = Path(__file__).parent / "skill" / "SKILL.md"
    if not skill_src.exists():
        click.echo(f"Skill source not found at {skill_src}", err=True)
        sys.exit(1)
    skill_dst = Path.home() / ".claude" / "skills" / "wavi"
    skill_dst.mkdir(parents=True, exist_ok=True)
    shutil.copy2(skill_src, skill_dst / "SKILL.md")
    click.echo(f"Skill installed → {skill_dst}/SKILL.md")
    click.echo("Restart Claude Code to activate /wavi.")


# ── serve ─────────────────────────────────────────────────────────────────────

@main.command("serve")
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind address.")
@click.option("--port", default=8900, show_default=True, help="Port to listen on.")
@click.option("--sessions-dir", default=None,
              help="Directory containing session profiles. Defaults to data/sessions/ or WAVI_SESSIONS_DIR env var.")
@click.option("--reload", is_flag=True, hidden=True, help="Enable uvicorn auto-reload (dev only).")
def serve(host: str, port: int, sessions_dir: str | None, reload: bool):
    """Start the wavi HTTP JSON API server.

    Exposes all wavi operations (get, send, check-updates, status, …) over HTTP
    so any language (Node.js, Ruby, Go, …) can integrate without calling the CLI
    as a subprocess.

    \b
    Examples:
      wavi serve                            # 127.0.0.1:8900
      wavi serve --port 9000
      wavi serve --host 0.0.0.0 --port 8900
      WAVI_SESSIONS_DIR=/data/sessions wavi serve

    API docs available at http://<host>:<port>/docs once running.
    """
    try:
        from wavi.server import serve as _serve
    except ImportError:
        click.echo(
            "FastAPI/uvicorn not installed.\n"
            "Run: pip install 'wavi[server]'  or  uv add 'wavi[server]'",
            err=True,
        )
        sys.exit(1)

    sd = Path(sessions_dir) if sessions_dir else None
    click.echo(f"wavi HTTP server → http://{host}:{port}")
    click.echo(f"Docs             → http://{host}:{port}/docs")
    click.echo(f"Sessions dir     → {sd or DEFAULT_SESSIONS_DIR}")
    _serve(host=host, port=port, sessions_dir=sd, reload=reload)
