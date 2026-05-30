"""
cli.py — wavi command-line interface.

Commands:
  wavi connect   [session]            — start Chrome daemon + QR scan
  wavi stop      [session]            — gracefully shut down Chrome daemon
  wavi full-sync [session] <contact>  — capture messages + audio from a chat
  wavi status    [session]            — check if session daemon is alive + authenticated
  wavi bubbles   <screenshot>         — run vision pipeline on a local screenshot

Session model
─────────────
'wavi connect' launches a real Chrome window with --remote-debugging-port so
the QR can be scanned without any automation signals.  Chrome is kept running
as a daemon after the QR scan (do not close it).  All subsequent commands
connect to that daemon via CDP and disconnect without killing Chrome.
'wavi stop' performs a graceful shutdown (navigates to about:blank, then SIGTERM).
"""
from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import sys
from pathlib import Path

import click

DEFAULT_SESSIONS_DIR = Path(__file__).parent.parent / "data" / "sessions"
REAL_CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
from wavi.session import CDP_PORT, PID_FILE


def _profile(session: str) -> Path:
    return DEFAULT_SESSIONS_DIR / session


# ── CLI root ──────────────────────────────────────────────────────────────────

@click.group()
def main():
    """wavi — WhatsApp automation via vision."""


# ── connect ───────────────────────────────────────────────────────────────────

@main.command()
@click.argument("session", default="default")
def connect(session: str):
    """Start Chrome daemon and authenticate via QR.

    Opens real Chrome (zero automation signals) with a CDP debug port so
    subsequent commands can connect without restarting the browser.
    Chrome MUST stay open after the QR scan — do not close it.

    SESSION is any name you choose (default: 'default').
    """
    if not REAL_CHROME.exists():
        click.echo(f"Chrome not found: {REAL_CHROME}", err=True)
        sys.exit(1)

    profile = _profile(session)
    profile.mkdir(parents=True, exist_ok=True)

    # Clear crash recovery state + session restoration files
    default_dir = profile / "Default"
    for crash_file in ("Last Session", "Last Tabs", "Last Browser State", "Current Session", "Current Tabs"):
        (default_dir / crash_file).unlink(missing_ok=True)

    # Clear session data directories that may contain restored tabs
    for sess_dir in ("Sessions", "SessionStorage"):
        sess_path = default_dir / sess_dir
        if sess_path.exists():
            shutil.rmtree(sess_path, ignore_errors=True)

    # Pre-set Chrome permissions in Preferences (no JS injection needed)
    import json as _json
    prefs_path = default_dir / "Preferences"
    prefs = {}
    if prefs_path.exists():
        try:
            prefs = _json.loads(prefs_path.read_text())
        except Exception:
            pass
    prefs.setdefault("profile", {}).setdefault("default_content_setting_values", {}).update({
        "media_stream_mic": 2,     # 2 = deny
        "media_stream_camera": 2,
        "notifications": 2,
    })
    prefs_path.write_text(_json.dumps(prefs))

    # Kill any existing daemon using our CDP port
    result = subprocess.run(
        ["lsof", "-ti", f"tcp:{CDP_PORT}", "-sTCP:LISTEN"],
        capture_output=True, text=True,
    )
    for pid in result.stdout.strip().split("\n"):
        if pid.strip():
            subprocess.run(["kill", "-TERM", pid.strip()], capture_output=True)
    (profile / "SingletonLock").unlink(missing_ok=True)

    proc = subprocess.Popen([
        "arch", "-arm64",  # Force ARM64 native on Apple Silicon (no Rosetta)
        str(REAL_CHROME),
        f"--user-data-dir={profile}",
        f"--remote-debugging-port={CDP_PORT}",
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
        "https://web.whatsapp.com",
    ])

    # Save daemon PID so other commands can find it
    (profile / PID_FILE).write_text(str(proc.pid))

    click.echo(f"Session '{session}' → {profile}")
    click.echo(f"Chrome abierto (PID {proc.pid}, CDP :{CDP_PORT}).")
    click.echo()
    click.echo("1. Escaneá el QR en WhatsApp Web")
    click.echo("2. Esperá que carguen tus chats")
    click.echo("3. Dejá Chrome abierto — NO lo cierres")
    click.echo()
    click.echo("Presioná Enter aquí cuando tus chats estén visibles.")
    try:
        input()
    except (EOFError, KeyboardInterrupt):
        pass

    if proc.poll() is not None:
        click.echo("Error: Chrome se cerró antes de que confirmaras. Intentá de nuevo.", err=True)
        (profile / PID_FILE).unlink(missing_ok=True)
        sys.exit(1)

    click.echo(f"Daemon activo. Usá 'wavi full-sync {session} <contacto>' para capturar mensajes.")
    click.echo(f"Usá 'wavi stop {session}' para cerrar Chrome de manera segura.")


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

    # Quick check: is the daemon process alive?
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
