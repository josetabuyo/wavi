"""
Tests de wavi/qr_server.py — el mini web app de 'wavi qr'.

Verifican que:
  - _fetch_qr / _check_status solo LEEN el DOM (query_selector, evaluate) y
    nunca llaman page.goto/page.reload — ver .claude/skills/wa-session-guard.
  - El HTTP handler expone /, /api/qr, /api/status y nada más.
  - La página incluye señales sonoras (Web Audio) en la carga y en los
    eventos de estado, como pidió el usuario.
"""
import inspect
from unittest.mock import AsyncMock, MagicMock

import pytest

from wavi.qr_server import (
    _PAGE_HTML,
    _check_status,
    _claim_port,
    _ensure_daemon_ready,
    _fetch_qr,
)


def _make_page(auth: bool = False, qr_present: bool = True, ref: str = "ref-1"):
    page = MagicMock()
    page.wait_for_selector = AsyncMock()
    if auth:
        page.query_selector = AsyncMock(return_value=MagicMock())
    else:
        async def _qs(sel):
            if "qrcode" in sel or "data-ref" in sel:
                return MagicMock() if qr_present else None
            return None
        page.query_selector = AsyncMock(side_effect=_qs)
    page.evaluate = AsyncMock(return_value=ref)
    qr_el = MagicMock()
    qr_el.screenshot = AsyncMock(return_value=b"\x89PNG\x00")
    return page, qr_el


class TestNeverNavigates:
    """wa-session-guard: el capturador de QR bajo demanda nunca debe navegar
    ni recargar la tab — solo lee su estado actual vía CDP."""

    def test_fetch_qr_never_calls_goto(self):
        source = inspect.getsource(_fetch_qr)
        assert ".goto(" not in source, (
            "_fetch_qr no debe navegar la tab de WA — solo debe leer su "
            "estado actual (query_selector/evaluate/screenshot)."
        )

    def test_check_status_never_calls_goto(self):
        source = inspect.getsource(_check_status)
        assert ".goto(" not in source

    def test_fetch_qr_never_calls_reload(self):
        source = inspect.getsource(_fetch_qr)
        assert "reload(" not in source


class TestFetchQr:
    @pytest.mark.asyncio
    async def test_returns_restored_when_authenticated(self, monkeypatch):
        page, _ = _make_page(auth=True)

        async def fake_with_page(cdp_port, fn):
            return await fn(page)

        monkeypatch.setattr("wavi.qr_server._with_page", fake_with_page)
        result = await _fetch_qr(9999)
        assert result == {"ok": True, "state": "restored"}

    @pytest.mark.asyncio
    async def test_returns_qr_b64_and_ref_when_qr_needed(self, monkeypatch):
        page, qr_el = _make_page(auth=False, qr_present=True, ref="abc123")
        page.query_selector = AsyncMock(side_effect=[None, qr_el])

        async def fake_with_page(cdp_port, fn):
            return await fn(page)

        monkeypatch.setattr("wavi.qr_server._with_page", fake_with_page)
        result = await _fetch_qr(9999)
        assert result["ok"] is True
        assert result["state"] == "qr"
        assert result["ref"] == "abc123"
        assert "qr_b64" in result and len(result["qr_b64"]) > 0

    @pytest.mark.asyncio
    async def test_returns_error_dict_on_exception(self, monkeypatch):
        async def fake_with_page(cdp_port, fn):
            raise RuntimeError("CDP unreachable")

        monkeypatch.setattr("wavi.qr_server._with_page", fake_with_page)
        result = await _fetch_qr(9999)
        assert result["ok"] is False
        assert "error" in result


class TestCheckStatus:
    @pytest.mark.asyncio
    async def test_restored_when_auth_selector_present(self, monkeypatch):
        page, _ = _make_page(auth=True)

        async def fake_with_page(cdp_port, fn):
            return await fn(page)

        monkeypatch.setattr("wavi.qr_server._with_page", fake_with_page)
        result = await _check_status(9999, "old-ref")
        assert result == {"state": "restored"}

    @pytest.mark.asyncio
    async def test_expired_when_ref_changed(self, monkeypatch):
        page, _ = _make_page(auth=False)
        page.query_selector = AsyncMock(return_value=None)
        page.evaluate = AsyncMock(return_value="new-ref")

        async def fake_with_page(cdp_port, fn):
            return await fn(page)

        monkeypatch.setattr("wavi.qr_server._with_page", fake_with_page)
        result = await _check_status(9999, "old-ref")
        assert result == {"state": "expired"}

    @pytest.mark.asyncio
    async def test_waiting_when_ref_unchanged(self, monkeypatch):
        page, _ = _make_page(auth=False)
        page.query_selector = AsyncMock(return_value=None)
        page.evaluate = AsyncMock(return_value="same-ref")

        async def fake_with_page(cdp_port, fn):
            return await fn(page)

        monkeypatch.setattr("wavi.qr_server._with_page", fake_with_page)
        result = await _check_status(9999, "same-ref")
        assert result == {"state": "waiting"}


class TestPortReleasedOnSigterm:
    """`kill <pid>` sends SIGTERM, which does NOT raise KeyboardInterrupt —
    only Ctrl-C (SIGINT) does. Without an explicit SIGTERM handler, serve()'s
    finally block (which releases the port) never runs, leaking a GHOST
    registration in 'las ports audit' forever. Found 2026-08-21 when three
    'wavi qr' processes killed via `kill` left three orphaned claims."""

    def test_serve_installs_a_sigterm_handler(self):
        import inspect

        from wavi.qr_server import serve
        source = inspect.getsource(serve)
        assert "SIGTERM" in source, (
            "serve() must install a SIGTERM handler that raises "
            "KeyboardInterrupt, so `kill <pid>` still releases the claimed "
            "port via the finally block."
        )


class TestPortClaimedFromSociety:
    """ADR-008 / .agent.json: cualquier puerto que este proceso escuche debe
    pasar por el registry de la Local Agent Society, para que 'las ports
    audit' lo vea — nunca un bind directo e invisible."""

    def test_claim_port_hits_society_registry_first(self, monkeypatch):
        calls = []

        class _FakeResp:
            def read(self):
                return b'{"port": 9012}'

        def fake_urlopen(req, timeout=2):
            calls.append(req.full_url)
            return _FakeResp()

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        port = _claim_port("some/session/path")
        assert port == 9012
        assert any("/ports/claim" in c for c in calls)

    def test_claim_port_falls_back_to_os_ephemeral_if_society_down(self, monkeypatch):
        def fake_urlopen(req, timeout=2):
            raise ConnectionRefusedError("society daemon not running")

        monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
        port = _claim_port("some/session/path")
        assert isinstance(port, int) and port > 0


class TestPageHasSoundCues:
    """El usuario pidió explícitamente señales sonoras al cargar la web."""

    def test_page_beeps_on_load(self):
        assert "window.addEventListener('load'" in _PAGE_HTML
        assert "beep(" in _PAGE_HTML

    def test_page_uses_web_audio_no_external_assets(self):
        assert "AudioContext" in _PAGE_HTML
        assert "<audio" not in _PAGE_HTML  # no external/embedded media files


class TestSelfContainedEntryPoint:
    """El usuario pidió que apretar 'Buscar QR' sea el único paso — que
    arranque el daemon si hace falta, sin exigir 'wavi connect' antes."""

    @pytest.mark.asyncio
    async def test_ensure_daemon_reuses_existing_daemon_without_relaunching(self, monkeypatch):
        launched = []
        fake_session = MagicMock()
        fake_session.daemon_alive.return_value = True
        monkeypatch.setattr("wavi.session.WASession", lambda profile: fake_session)
        monkeypatch.setattr("wavi.cli._session_port", lambda profile: 9236)
        monkeypatch.setattr("wavi.cli._launch_headless_daemon", lambda *a, **k: launched.append(1))

        async def fake_check_status(profile):
            return "restored"

        monkeypatch.setattr("wavi.cli._check_session_status", fake_check_status)

        port, err = await _ensure_daemon_ready(MagicMock())
        assert port == 9236
        assert err is None
        assert launched == []  # must not relaunch an already-alive daemon

    @pytest.mark.asyncio
    async def test_ensure_daemon_navigates_even_when_reusing_daemon(self, monkeypatch):
        """A reused daemon might be sitting at about:blank from a previous
        run — _check_session_status (which navigates to WA) must run either
        way, not just on a fresh launch."""
        fake_session = MagicMock()
        fake_session.daemon_alive.return_value = True
        monkeypatch.setattr("wavi.session.WASession", lambda profile: fake_session)
        monkeypatch.setattr("wavi.cli._session_port", lambda profile: 9236)

        calls = []

        async def fake_check_status(profile):
            calls.append(profile)
            return "qr_needed"

        monkeypatch.setattr("wavi.cli._check_session_status", fake_check_status)

        await _ensure_daemon_ready(MagicMock())
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_ensure_daemon_launches_when_not_alive(self, monkeypatch, tmp_path):
        fake_session = MagicMock()
        fake_session.daemon_alive.return_value = False
        monkeypatch.setattr("wavi.session.WASession", lambda profile: fake_session)

        launched = []
        monkeypatch.setattr("wavi.cli._claim_port", lambda path: 9240)
        monkeypatch.setattr("wavi.cli._kill_port_processes", lambda port: None)
        monkeypatch.setattr("wavi.cli._set_chrome_prefs", lambda profile: None)
        monkeypatch.setattr("wavi.cli._launch_headless_daemon", lambda profile, port: launched.append(port))

        async def fake_wait_cdp_ready(port, timeout_s=20):
            return True

        monkeypatch.setattr("wavi.cli._wait_cdp_ready", fake_wait_cdp_ready)

        async def fake_check_status(profile):
            return "qr_needed"

        monkeypatch.setattr("wavi.cli._check_session_status", fake_check_status)
        monkeypatch.setattr("wavi.cli._session_port", lambda profile: 9240)

        port, err = await _ensure_daemon_ready(tmp_path / "some-session")
        assert port == 9240
        assert err is None
        assert launched == [9240]  # button press is what triggered the launch

    @pytest.mark.asyncio
    async def test_ensure_daemon_reports_error_if_cdp_never_comes_up(self, monkeypatch, tmp_path):
        fake_session = MagicMock()
        fake_session.daemon_alive.return_value = False
        monkeypatch.setattr("wavi.session.WASession", lambda profile: fake_session)
        monkeypatch.setattr("wavi.cli._claim_port", lambda path: 9241)
        monkeypatch.setattr("wavi.cli._kill_port_processes", lambda port: None)
        monkeypatch.setattr("wavi.cli._set_chrome_prefs", lambda profile: None)
        monkeypatch.setattr("wavi.cli._launch_headless_daemon", lambda profile, port: None)

        async def fake_wait_cdp_ready(port, timeout_s=20):
            return False

        monkeypatch.setattr("wavi.cli._wait_cdp_ready", fake_wait_cdp_ready)

        port, err = await _ensure_daemon_ready(tmp_path / "some-session")
        assert port is None
        assert err is not None

    def test_qr_cmd_does_not_require_daemon_alive_upfront(self):
        """La regresión concreta: 'wavi qr' ya no debe cortar con sys.exit
        si el daemon está parado — eso ahora lo maneja el botón."""
        import inspect

        from wavi.cli import qr_cmd
        source = inspect.getsource(qr_cmd.callback)
        assert "daemon_alive" not in source
        assert "sys.exit" not in source

    def test_page_closes_itself_on_success(self):
        """El usuario aceptó window.close() como intento best-effort, con
        cierre manual como fallback aceptable si el navegador lo bloquea."""
        assert "window.close()" in _PAGE_HTML

    def test_handler_source_sets_shutdown_event_on_restored(self):
        import inspect

        from wavi.qr_server import _make_handler
        source = inspect.getsource(_make_handler)
        assert "shutdown_event.set()" in source
