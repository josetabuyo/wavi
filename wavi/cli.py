"""
cli.py — wavi command-line interface.

Commands:
  wavi connect   [session]            — start Chrome daemon + QR scan (if needed)
  wavi stop      [session]            — gracefully shut down Chrome daemon
  wavi full-sync [session] <contact>  — capture messages + audio from a chat
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
import json
import shutil
import subprocess
import sys
import time
from pathlib import Path

import click
from dotenv import load_dotenv
load_dotenv()

DEFAULT_SESSIONS_DIR = Path(__file__).parent.parent / "data" / "sessions"
REAL_CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
from wavi.session import CDP_PORT, PID_FILE, WINDOW_W, WINDOW_H

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

def _kill_port_processes() -> None:
    result = subprocess.run(
        ["lsof", "-ti", f"tcp:{CDP_PORT}", "-sTCP:LISTEN"],
        capture_output=True, text=True,
    )
    for pid in result.stdout.strip().split("\n"):
        if pid.strip():
            subprocess.run(["kill", "-TERM", pid.strip()], capture_output=True)


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


def _launch_headless_daemon(profile: Path) -> subprocess.Popen:
    """Launch headless Chrome daemon, save PID, return the process."""
    (profile / "SingletonLock").unlink(missing_ok=True)
    proc = subprocess.Popen(
        ["arch", "-arm64", str(REAL_CHROME)]
        + [f"--user-data-dir={profile}", f"--remote-debugging-port={CDP_PORT}"]
        + _HEADLESS_CHROME_ARGS
        + [f"--headless=new", f"--window-size={WINDOW_W},{WINDOW_H}", "about:blank"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    (profile / PID_FILE).write_text(str(proc.pid))
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


# ── CLI root ──────────────────────────────────────────────────────────────────

@click.group()
def main():
    """wavi — WhatsApp automation via vision."""


# ── connect ───────────────────────────────────────────────────────────────────

@main.command()
@click.argument("session", default="default")
def connect(session: str):
    """Start Chrome daemon and authenticate (headless if session exists, QR if not).

    Tries headless first — if WhatsApp loads authenticated no visible window
    ever opens.  Only falls back to a visible window when QR scan is needed.

    SESSION is any name you choose (default: 'default').
    """
    if not REAL_CHROME.exists():
        click.echo(f"Chrome not found: {REAL_CHROME}", err=True)
        sys.exit(1)

    profile = _profile(session)
    profile.mkdir(parents=True, exist_ok=True)
    click.echo(f"Session '{session}' → {profile}")

    # ── Fast path: daemon already alive and authenticated ─────────────────────
    from wavi.session import WASession, _is_process_alive
    s = WASession(profile)
    if s.daemon_alive():
        click.echo("Daemon detectado, verificando sesión...")
        status = asyncio.run(_check_session_status(profile))
        if status == "restored":
            pid = s._load_pid()
            click.echo(f"Sesión '{session}' ya activa y autenticada (PID {pid}, CDP :{CDP_PORT}).")
            click.echo(f"Usá 'wavi full-sync {session} <contacto>' para capturar mensajes.")
            click.echo(f"Usá 'wavi stop {session}' para cerrar Chrome de manera segura.")
            return
        click.echo(f"Daemon vivo pero sesión={status}. Relanzando...")

    # ── Kill any existing process on CDP port ─────────────────────────────────
    _kill_port_processes()
    time.sleep(1)

    # ── Optimistic: try headless first ────────────────────────────────────────
    _set_chrome_prefs(profile)
    click.echo("Intentando restaurar sesión en modo headless...")
    headless_proc = _launch_headless_daemon(profile)
    time.sleep(3)  # Give Chrome time to start before CDP connect attempt

    status = asyncio.run(_check_session_status(profile))

    if status == "restored":
        # Keep default alias pointing to this session
        if session != "default":
            _set_default_alias(session)
        click.echo(f"Sesión restaurada — daemon headless activo (PID {headless_proc.pid}, CDP :{CDP_PORT}).")
        click.echo(f"Usá 'wavi full-sync {session} <contacto>' para capturar mensajes.")
        click.echo(f"Usá 'wavi stop {session}' para cerrar Chrome de manera segura.")
        return

    # ── QR needed: kill headless, open visible window ─────────────────────────
    click.echo(f"Sesión no encontrada (estado={status}) — QR requerido.")
    click.echo("Cerrando Chrome headless...")
    _terminate_proc(headless_proc)
    (profile / "SingletonLock").unlink(missing_ok=True)
    time.sleep(1)

    _cleanup_crash_files(profile)

    click.echo("Abriendo Chrome visible para escanear QR...")
    proc = subprocess.Popen(
        ["arch", "-arm64", str(REAL_CHROME)]
        + [f"--user-data-dir={profile}", f"--remote-debugging-port={CDP_PORT}"]
        + _VISIBLE_CHROME_ARGS
        + [f"--window-size={WINDOW_W},{WINDOW_H}", "https://web.whatsapp.com"],
    )
    (profile / PID_FILE).write_text(str(proc.pid))

    click.echo(f"Chrome abierto (PID {proc.pid}, CDP :{CDP_PORT}).")
    click.echo()
    click.echo("1. Escaneá el QR en WhatsApp Web")
    click.echo("2. Esperá que carguen tus chats")
    click.echo("3. Presioná Enter aquí — Chrome se cerrará y arrancará en modo headless")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass

    if proc.poll() is not None:
        click.echo("Error: Chrome se cerró antes de que confirmaras. Intentá de nuevo.", err=True)
        (profile / PID_FILE).unlink(missing_ok=True)
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
                f"http://localhost:{CDP_PORT}", timeout=5_000
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
    _terminate_proc(proc)
    (profile / "SingletonLock").unlink(missing_ok=True)
    time.sleep(1)

    # If we got the phone number, rename the session and update the alias
    if detected_phone and detected_phone != session:
        phone_profile = DEFAULT_SESSIONS_DIR / detected_phone
        if not phone_profile.exists():
            profile.rename(phone_profile)
            profile = phone_profile
            click.echo(f"Sesión renombrada → '{detected_phone}'")
        _set_default_alias(detected_phone)
        click.echo(f"'default' ahora apunta a '{detected_phone}'")
    elif session == "default" and not detected_phone:
        pass  # keep as-is, alias not updated
    else:
        _set_default_alias(session)

    click.echo("Iniciando daemon headless...")
    headless_proc = _launch_headless_daemon(profile)

    click.echo("Verificando sesión...")
    time.sleep(5)

    status = asyncio.run(_check_session_status(profile))
    final_name = detected_phone or session
    if status == "restored":
        click.echo(f"Daemon headless activo (PID {headless_proc.pid}, CDP :{CDP_PORT}).")
        click.echo(f"Sesión: '{final_name}'")
    else:
        click.echo(f"Advertencia: sesión={status}. Puede requerir re-autenticación.", err=True)

    click.echo(f"Usá 'wavi full-sync {final_name} <contacto>' para capturar mensajes.")
    click.echo(f"Usá 'wavi stop {final_name}' para cerrar Chrome de manera segura.")


# ── stop ──────────────────────────────────────────────────────────────────────

@main.command()
@click.argument("session", default="default")
def stop(session: str):
    """Gracefully shut down the Chrome daemon for SESSION.

    Navigates to about:blank first so WhatsApp can flush its state,
    then sends SIGTERM.  Never use kill -9 on a WA session directly.
    """
    from wavi.session import WASession

    profile = _profile(session)
    pid_file = profile / PID_FILE
    if not pid_file.exists():
        click.echo(f"No daemon PID file found for session '{session}'.", err=True)
        sys.exit(1)

    async def _run():
        s = WASession(profile)
        try:
            await s.connect()
        except Exception as e:
            click.echo(f"Could not connect to daemon: {e}", err=True)
        await s.stop_daemon()
        click.echo("Daemon stopped cleanly.")

    asyncio.run(_run())


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


# ── full-sync ─────────────────────────────────────────────────────────────────

@main.command("full-sync")
@click.argument("session", default="default")
@click.argument("contact")
@click.option("--assets", default=None, help="Directory to save screenshots and audio.")
@click.option("--headless/--no-headless", default=True, show_default=True,
              help="Headless fallback (ignored when daemon is running headful).")
@click.option("--json-out", is_flag=True, help="Output results as JSON.")
def full_sync(session: str, contact: str, assets: str | None, headless: bool, json_out: bool):
    """Capture messages + audio from CONTACT's chat (full pipeline)."""
    from wavi.runner import run_once

    assets_dir = Path(assets) if assets else Path("output") / contact.lower().replace(" ", "_")

    if assets_dir.exists():
        shutil.rmtree(assets_dir)

    async def _go():
        return await run_once(
            profile_dir=_profile(session),
            contact=contact,
            assets_dir=assets_dir,
            headless=headless,
        )

    try:
        result = asyncio.run(_go())
    except RuntimeError as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    bubbles = result["bubbles"]
    audios  = result["audios"]

    if json_out:
        output = {
            "bubbles": [b.as_dict() for b in bubbles],
            "audios": [
                {
                    "bubble_id": a["bubble"].id,
                    "blob_url": a["blob_url"],
                    "path": str(a["path"]) if a.get("path") else None,
                    "error": a.get("error"),
                }
                for a in audios
            ],
        }
        click.echo(json.dumps(output, indent=2, ensure_ascii=False))
        return

    click.echo(f"\n{len(bubbles)} mensaje(s) detectados:")
    for b in bubbles:
        ts = f" [{b.timestamp}]" if b.timestamp else ""
        click.echo(f"  #{b.id:02d} {b.sender:5s} {b.msg_type:6s}{ts}  {b.text[:80]}")

    if audios:
        click.echo(f"\n{len(audios)} audio(s) procesados:")
        for a in audios:
            if a.get("error"):
                click.echo(f"  bubble #{a['bubble'].id}: {a['error']}")
            else:
                size = len(a["data"]) if a.get("data") else 0
                path = a.get("path") or "(no guardado)"
                click.echo(f"  bubble #{a['bubble'].id}: {size} bytes → {path}")


# ── full-sync-enhanced ───────────────────────────────────────────────────────

@main.command("full-sync-enhanced")
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
def full_sync_enhanced(session: str, contact: str, assets: str | None, headless: bool, json_out: bool, max_iter: int, from_date: str | None):
    """Like full-sync but scrolls up to capture the full message history.

    iter_000/ holds the same initial capture that full-sync produces.
    Subsequent iterations scroll toward the past, each with its own debug image.
    history_bubbles.json aggregates all deduplicated messages.

    NOTE: photos and videos are not detected by the vision pipeline.
    """
    from wavi.runner import run_enhanced
    from datetime import date as _Date

    assets_dir = Path(assets) if assets else Path("output") / contact.lower().replace(" ", "_") / "history"

    from_date_obj: _Date | None = None
    if from_date:
        try:
            from_date_obj = _Date.fromisoformat(from_date)
        except ValueError:
            click.echo(f"Error: --from debe ser una fecha en formato YYYY-MM-DD, recibido: {from_date}", err=True)
            sys.exit(1)

    if assets_dir.exists():
        shutil.rmtree(assets_dir)

    async def _go():
        return await run_enhanced(
            profile_dir=_profile(session),
            contact=contact,
            assets_dir=assets_dir,
            headless=headless,
            max_iterations=max_iter,
            from_date=from_date_obj,
        )

    try:
        result = asyncio.run(_go())
    except RuntimeError as e:
        click.echo(str(e), err=True)
        sys.exit(1)

    bubbles = result["bubbles"]

    if json_out:
        click.echo(json.dumps([b.as_dict() for b in bubbles], indent=2, ensure_ascii=False))
        return

    click.echo(f"\n{len(bubbles)} mensaje(s) en el historial completo:")
    for b in bubbles:
        ts = f" [{b.timestamp}]" if b.timestamp else ""
        click.echo(f"  #{b.id:04d} {b.sender:5s} {b.msg_type:6s}{ts}  {b.text[:80]}")

    # Contar archivos .ogg descargados en todas las iteraciones
    import glob
    ogg_files = glob.glob(str(assets_dir / "iter_*" / "audio_*.ogg"))
    if ogg_files:
        click.echo(f"\n{len(ogg_files)} audio(s) descargados en iteraciones:")
        for f in sorted(ogg_files):
            size = Path(f).stat().st_size
            click.echo(f"  {Path(f).relative_to(assets_dir)}: {size} bytes")


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


