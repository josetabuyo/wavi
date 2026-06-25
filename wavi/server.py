"""
wavi HTTP JSON API server.

Start with:
    wavi serve [--host 127.0.0.1] [--port 8900] [--sessions-dir /path/to/sessions]

Or programmatically:
    from wavi.server import create_app
    app = create_app(sessions_dir=Path("/my/sessions"))

Endpoints
─────────
GET  /health                          — liveness check
GET  /status/{session}                — daemon alive + auth status
GET  /queue/{session}                 — current queue status (idle or in-progress op)
POST /get                             — capture full message history
POST /send                            — send a message
POST /check-updates                   — check sidebar for new inbound messages
POST /list-contacts                   — list contacts from the New Chat panel

All errors return {"detail": "..."} with an appropriate HTTP status code.
"""
from __future__ import annotations

import os
from pathlib import Path

_DEFAULT_SESSIONS_DIR = Path(os.environ.get(
    "WAVI_SESSIONS_DIR",
    str(Path(__file__).parent.parent / "data" / "sessions"),
))


def create_app(sessions_dir: Path | None = None):
    try:
        from fastapi import FastAPI, HTTPException
        from pydantic import BaseModel
    except ImportError as e:
        raise ImportError(
            "FastAPI not installed. Run: pip install 'wavi[server]'"
        ) from e

    from wavi.queue import get_status, is_locked, session_lock
    from wavi.runner import WARunner, run_enhanced
    from wavi.session import WASession

    _sessions_dir = sessions_dir or _DEFAULT_SESSIONS_DIR

    app = FastAPI(title="wavi", version="0.2.0", description="WhatsApp automation API")

    # ── helpers ───────────────────────────────────────────────────────────────

    def _resolve(session: str) -> Path:
        alias_file = _sessions_dir / ".default"
        if session == "default" and alias_file.exists():
            target = alias_file.read_text().strip()
            if target:
                return _sessions_dir / target
        return _sessions_dir / session

    def _require_session(profile: Path) -> None:
        if not profile.exists():
            raise HTTPException(404, f"Session not found: {profile.name}")

    # ── models ────────────────────────────────────────────────────────────────

    class GetRequest(BaseModel):
        session: str = "default"
        contact: str
        assets_dir: str | None = None
        max_iter: int = 300
        from_date: str | None = None
        newest: bool = False
        grow: bool = False

    class SendRequest(BaseModel):
        session: str = "default"
        contact: str
        message: str

    class CheckUpdatesRequest(BaseModel):
        session: str = "default"
        reset: bool = False

    class ListContactsRequest(BaseModel):
        session: str = "default"

    # ── routes ────────────────────────────────────────────────────────────────

    @app.get("/health")
    def health():
        return {"status": "ok", "version": "0.2.0"}

    @app.get("/status/{session}")
    async def status(session: str):
        profile = _resolve(session)
        _require_session(profile)
        s = WASession(profile)
        pid = s._load_pid()
        from wavi.session import _is_process_alive
        daemon = bool(pid and _is_process_alive(pid))
        if not daemon:
            return {"session": session, "daemon": False, "authenticated": False}
        try:
            result = await s.connect()
            await s.close()
            return {"session": session, "daemon": True, "authenticated": result == "restored"}
        except Exception as exc:
            return {"session": session, "daemon": True, "authenticated": False, "error": str(exc)}

    @app.get("/queue/{session}")
    def queue(session: str):
        profile = _resolve(session)
        _require_session(profile)
        data = get_status(profile)
        if not data:
            return {"session": session, "status": "idle"}
        return {"session": session, "status": "busy", **data}

    @app.post("/get")
    async def get(req: GetRequest):
        from datetime import date as _Date
        profile = _resolve(req.session)
        _require_session(profile)

        if is_locked(profile):
            raise HTTPException(409, f"Session '{req.session}' is busy. Check /queue/{req.session}.")

        assets_dir = (
            Path(req.assets_dir)
            if req.assets_dir
            else Path("output") / profile.name / req.contact.lower().replace(" ", "_")
        )

        from_date = None
        if req.from_date:
            try:
                from_date = _Date.fromisoformat(req.from_date)
            except ValueError as exc:
                raise HTTPException(422, f"Invalid from_date '{req.from_date}'. Use YYYY-MM-DD.") from exc

        if req.grow and req.newest:
            raise HTTPException(422, "grow and newest are mutually exclusive.")

        with session_lock(profile, "get", contact=req.contact):
            result = await run_enhanced(
                profile_dir=profile,
                contact=req.contact,
                assets_dir=assets_dir,
                max_iterations=req.max_iter,
                from_date=from_date,
                newest=req.newest,
                grow=req.grow,
            )

        return {
            "contact": req.contact,
            "session": req.session,
            "count": len(result["bubbles"]),
            "bubbles": [b.as_dict() for b in result["bubbles"]],
        }

    @app.post("/send")
    async def send(req: SendRequest):
        profile = _resolve(req.session)
        _require_session(profile)

        if is_locked(profile):
            raise HTTPException(409, f"Session '{req.session}' is busy.")

        with session_lock(profile, "send", contact=req.contact):
            s = WASession(profile)
            try:
                st = await s.connect()
                if st != "restored":
                    raise HTTPException(401, "Session not authenticated. Run 'wavi connect' first.")
                await s.navigate_to_contact(req.contact)
                meta = await s.send_message(req.message)
            finally:
                await s.close()

        return {"ok": True, "contact": req.contact, "input_coords": meta}

    @app.post("/check-updates")
    async def check_updates(req: CheckUpdatesRequest):
        profile = _resolve(req.session)
        _require_session(profile)

        if is_locked(profile):
            raise HTTPException(409, f"Session '{req.session}' is busy.")

        assets_path = Path("output") / profile.name / "last-updates"
        runner = WARunner(profile)
        with session_lock(profile, "check-updates"):
            result = await runner.check_updates(assets_dir=assets_path, reset=req.reset)
        return result

    @app.post("/list-contacts")
    async def list_contacts(req: ListContactsRequest):
        profile = _resolve(req.session)
        _require_session(profile)

        if is_locked(profile):
            raise HTTPException(409, f"Session '{req.session}' is busy.")

        assets_path = Path("output") / profile.name / "contacts"
        runner = WARunner(profile)
        with session_lock(profile, "list-contacts"):
            result = await runner.list_contacts(assets_dir=assets_path)
        return result

    return app


# ── standalone entry point ────────────────────────────────────────────────────

def serve(
    host: str = "127.0.0.1",
    port: int = 8900,
    sessions_dir: Path | None = None,
    reload: bool = False,
) -> None:
    """Start the wavi HTTP server (blocking)."""
    try:
        import uvicorn
    except ImportError as e:
        raise ImportError(
            "uvicorn not installed. Run: pip install 'wavi[server]'"
        ) from e

    app = create_app(sessions_dir=sessions_dir)
    uvicorn.run(app, host=host, port=port, reload=reload)
