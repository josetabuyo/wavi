"""
Tests for the _lazy_session context manager.

Behavior:
- Contextualized invocation (daemon already running): no-op; daemon stays alive after command.
- Lazy invocation (no daemon): the command starts its own Chrome via WASession.connect()
  fallback; _lazy_session stops it afterward.
- If the command fails or Chrome was never started, cleanup is silent.
"""
from unittest.mock import patch

from wavi.cli import _lazy_session
from wavi.session import PID_FILE


class TestLazySessionAlreadyRunning:
    def test_no_stop_when_daemon_was_running(self, tmp_path):
        """If daemon was already running, _stop_daemon_for_profile is never called."""
        profile = tmp_path / "sess"
        profile.mkdir()

        with patch("wavi.session.WASession") as MockSession:
            MockSession.return_value.daemon_alive.return_value = True

            with patch("wavi.cli._stop_daemon_for_profile") as mock_stop:
                with patch("wavi.cli.asyncio.run") as mock_run:
                    with _lazy_session(profile):
                        pass

                    mock_stop.assert_not_called()
                    mock_run.assert_not_called()


class TestLazyInvocationStopsDaemon:
    def test_stops_daemon_started_by_command(self, tmp_path):
        """If daemon was NOT running before, and command left a PID file, stop it."""
        profile = tmp_path / "sess"
        profile.mkdir()
        pid_file = profile / PID_FILE

        with patch("wavi.session.WASession") as MockSession:
            MockSession.return_value.daemon_alive.return_value = False

            with patch("wavi.cli._stop_daemon_for_profile") as mock_stop:
                with patch("wavi.cli.asyncio.run") as mock_run:
                    mock_run.side_effect = lambda coro: None

                    with _lazy_session(profile):
                        # Simulate command creating a PID file
                        pid_file.write_text("99999")

                    # PID file exists → stop should be called
                    mock_stop.assert_called_once_with(profile)

    def test_no_stop_if_command_left_no_pid_file(self, tmp_path):
        """If daemon wasn't running and command left no PID file, no stop called."""
        profile = tmp_path / "sess"
        profile.mkdir()

        with patch("wavi.session.WASession") as MockSession:
            MockSession.return_value.daemon_alive.return_value = False

            with patch("wavi.cli._stop_daemon_for_profile") as mock_stop:
                with patch("wavi.cli.asyncio.run"):
                    with _lazy_session(profile):
                        pass  # No PID file created

                    mock_stop.assert_not_called()

    def test_stop_exception_is_swallowed(self, tmp_path):
        """Cleanup errors in finally block must not propagate."""
        profile = tmp_path / "sess"
        profile.mkdir()
        (profile / PID_FILE).write_text("1")

        with patch("wavi.session.WASession") as MockSession:
            MockSession.return_value.daemon_alive.return_value = False

            with patch("wavi.cli.asyncio.run", side_effect=RuntimeError("boom")):
                # Should not raise even when asyncio.run fails
                with _lazy_session(profile):
                    pass
