from typer.testing import CliRunner

from bot.cli import app


def test_cli_help_works():
    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "investment bot" in result.stdout.lower()


def test_cli_version_command():
    runner = CliRunner()
    result = runner.invoke(app, ["version"])
    assert result.exit_code == 0
    assert "0.1.0" in result.stdout
