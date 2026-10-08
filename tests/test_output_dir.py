"""Default capture directory: central, never the caller's cwd (DataLake 2026-10-04:
a capture with plaintext credentials landed inside a client repo)."""
from pathlib import Path

from wavi.cli import _resolve_output_dir


def test_env_var_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("WAVI_OUTPUT_DIR", str(tmp_path))
    assert _resolve_output_dir() == tmp_path


def test_dev_install_uses_repo_output(monkeypatch):
    monkeypatch.delenv("WAVI_OUTPUT_DIR", raising=False)
    repo_root = Path(__file__).parent.parent
    assert _resolve_output_dir() == repo_root / "output"


def test_never_relative_to_cwd(monkeypatch, tmp_path):
    monkeypatch.delenv("WAVI_OUTPUT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    assert _resolve_output_dir().is_absolute()
