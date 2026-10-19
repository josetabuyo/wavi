"""'wavi send' argument checks — they fail before any session is touched."""
from click.testing import CliRunner

from wavi.cli import main


def test_send_needs_a_message_or_an_attachment():
    result = CliRunner().invoke(main, ["send", "default", "Familia"])
    assert result.exit_code == 2
    assert "Nada para enviar" in result.output


def test_attach_rejects_a_missing_file(tmp_path):
    missing = tmp_path / "no-existe.pdf"
    result = CliRunner().invoke(main, ["send", "default", "Familia", "hola", "--attach", str(missing)])
    assert result.exit_code == 2
    assert "does not exist" in result.output
