"""
cli.py — wavi command-line interface.

Commands:
  wavi connect  <phone>              — authenticate via QR (first time)
  wavi run      <phone> <contact>    — capture messages + audio from a chat
  wavi status   <phone>              — check if session is still valid
  wavi bubbles  <screenshot>         — run vision pipeline on a local screenshot
"""
from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import click

DEFAULT_SESSIONS_DIR = Path(__file__).parent.parent / "data" / "sessions"


def _profile(phone: str) -> Path:
    return DEFAULT_SESSIONS_DIR / phone


# ── CLI root ──────────────────────────────────────────────────────────────────

@click.group()
def main():
    """wavi — WhatsApp automation via vision."""


# ── connect ───────────────────────────────────────────────────────────────────

@main.command()
@click.argument("phone")
@click.option("--timeout", default=120, show_default=True, help="Seconds to wait for QR scan.")
def connect(phone: str, timeout: int):
    """Authenticate PHONE via QR code (opens a visible browser)."""
    from wavi.session import WASession

    profile = _profile(phone)
    click.echo(f"Profile: {profile}")

    async def _run():
        session = WASession(profile, headless=False)
        status = await session.connect()
        if status == "restored":
            click.echo("Session already active — no QR needed.")
            await session.close()
            return
        click.echo("Waiting for QR scan...")
        ok = await session.wait_for_auth(timeout_s=timeout)
        if ok:
            click.echo("Authenticated successfully.")
        else:
            click.echo("Timeout — QR not scanned in time.", err=True)
            sys.exit(1)
        await session.close()

    asyncio.run(_run())


# ── status ────────────────────────────────────────────────────────────────────

@main.command()
@click.argument("phone")
def status(phone: str):
    """Check if PHONE session is still valid (no browser window)."""
    from wavi.session import WASession

    profile = _profile(phone)
    if not profile.exists():
        click.echo(f"No profile found at {profile}", err=True)
        sys.exit(1)

    async def _run():
        session = WASession(profile, headless=True)
        result = await session.connect()
        await session.close()
        click.echo(result)
        if result != "restored":
            sys.exit(1)

    asyncio.run(_run())


# ── run ───────────────────────────────────────────────────────────────────────

@main.command()
@click.argument("phone")
@click.argument("contact")
@click.option("--assets", default=None, help="Directory to save screenshots and audio.")
@click.option("--headless/--no-headless", default=True, show_default=True)
@click.option("--json-out", is_flag=True, help="Output results as JSON.")
def run(phone: str, contact: str, assets: str | None, headless: bool, json_out: bool):
    """Open CONTACT's chat for PHONE and capture messages + audio."""
    from wavi.runner import run_once

    assets_dir = Path(assets) if assets else None

    async def _run():
        result = await run_once(
            profile_dir=_profile(phone),
            contact=contact,
            assets_dir=assets_dir,
            headless=headless,
        )
        return result

    try:
        result = asyncio.run(_run())
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
def bubbles(screenshot: str, assets: str | None, json_out: bool):
    """Run vision pipeline on a local SCREENSHOT file (no browser needed)."""
    from wavi.vision import analyze

    shot = Path(screenshot)
    assets_dir = Path(assets) if assets else shot.parent

    result = analyze(shot, assets_dir=assets_dir)

    if json_out:
        click.echo(json.dumps([b.as_dict() for b in result], indent=2, ensure_ascii=False))
        return

    click.echo(f"{len(result)} mensaje(s) detectados:")
    for b in result:
        ts = f" [{b.timestamp}]" if b.timestamp else ""
        click.echo(f"  #{b.id:02d} {b.sender:5s} {b.msg_type:6s}{ts}  {b.text[:80]}")
