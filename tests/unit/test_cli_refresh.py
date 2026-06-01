from datetime import datetime
from unittest.mock import patch

from typer.testing import CliRunner

from bot.cli import app
from bot.ingest.base import IngestResult
from bot.ingest.universe import UniverseRefreshResult


def test_refresh_damodaran_calls_importer(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "test.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))

    fake_result = IngestResult(
        source="damodaran",
        started_at=datetime(2026, 5, 25, 9, 0, 0),
        finished_at=datetime(2026, 5, 25, 9, 0, 10),
        status="success",
        rows_affected=237,
        details={"industry_rows": 100, "country_rows": 137},
    )
    with patch("bot.cli.import_damodaran", return_value=fake_result) as mock:
        runner = CliRunner()
        result = runner.invoke(app, ["refresh", "--damodaran"])
        assert result.exit_code == 0
        assert "237" in result.stdout
        assert mock.called


def test_refresh_runs_both_damodaran_and_fmp(tmp_path, monkeypatch):
    """Passing --damodaran and --fmp together must run BOTH sources, not
    short-circuit on --fmp."""
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "test.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))

    dam = IngestResult(
        source="damodaran",
        started_at=datetime(2026, 5, 25, 9, 0, 0),
        finished_at=datetime(2026, 5, 25, 9, 0, 5),
        status="success",
        rows_affected=10,
        details={"industry_rows": 5, "country_rows": 5},
    )
    uni = UniverseRefreshResult(
        run_id="r",
        started_at=datetime(2026, 5, 25, 9, 1, 0),
        finished_at=datetime(2026, 5, 25, 9, 1, 8),
        status="success",
        total=2,
        imported=2,
        skipped=0,
        failed=0,
        outcomes=[],
    )
    with (
        patch("bot.cli.import_damodaran", return_value=dam) as mdam,
        patch("bot.cli.refresh_universe_from_fmp", return_value=uni) as mfmp,
    ):
        runner = CliRunner()
        result = runner.invoke(app, ["refresh", "--damodaran", "--fmp"])

    assert mdam.called, "--damodaran must run even when --fmp is also passed"
    assert mfmp.called
    assert result.exit_code == 0


def test_refresh_worst_of_exit_code(tmp_path, monkeypatch):
    """A damodaran failure (1) plus an fmp data error (2) exits with the worst (2)."""
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "test.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))

    dam = IngestResult(
        source="damodaran",
        started_at=datetime(2026, 5, 25, 9, 0, 0),
        finished_at=datetime(2026, 5, 25, 9, 0, 5),
        status="error",
        rows_affected=0,
        error_message="boom",
    )
    uni = UniverseRefreshResult(
        run_id="r",
        started_at=datetime(2026, 5, 25, 9, 1, 0),
        finished_at=datetime(2026, 5, 25, 9, 1, 8),
        status="error",
        total=4,
        imported=1,
        skipped=0,
        failed=3,
        outcomes=[],
    )
    with (
        patch("bot.cli.import_damodaran", return_value=dam),
        patch("bot.cli.refresh_universe_from_fmp", return_value=uni),
    ):
        runner = CliRunner()
        result = runner.invoke(app, ["refresh", "--damodaran", "--fmp"])

    assert result.exit_code == 2


def test_refresh_prices_invokes_price_orchestrator(tmp_path, monkeypatch):
    """--prices runs the price refresh and maps its status to an exit code."""
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "test.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))

    prices = UniverseRefreshResult(
        run_id="p",
        started_at=datetime(2026, 5, 25, 9, 2, 0),
        finished_at=datetime(2026, 5, 25, 9, 2, 9),
        status="success",
        total=3,
        imported=3,
        skipped=0,
        failed=0,
        outcomes=[],
    )
    with patch("bot.cli.refresh_prices_from_fmp", return_value=prices) as mprices:
        runner = CliRunner()
        result = runner.invoke(app, ["refresh", "--prices"])

    assert mprices.called
    assert result.exit_code == 0


def _uni(run_id, status="success", total=1, imported=1, failed=0):
    return UniverseRefreshResult(
        run_id=run_id,
        started_at=datetime(2026, 5, 25, 9, 0, 0),
        finished_at=datetime(2026, 5, 25, 9, 0, 9),
        status=status,
        total=total,
        imported=imported,
        skipped=0,
        failed=failed,
        outcomes=[],
    )


def test_refresh_fx_invokes_fx_orchestrator(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "test.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))

    with patch("bot.cli.refresh_fx_from_fmp", return_value=_uni("fx")) as mfx:
        runner = CliRunner()
        result = runner.invoke(app, ["refresh", "--fx"])

    assert mfx.called
    assert result.exit_code == 0


def test_refresh_all_runs_every_source_in_order(tmp_path, monkeypatch):
    """--all runs damodaran → fmp → prices → fx in dependency order."""
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "test.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))

    calls = []
    dam = IngestResult(
        source="damodaran",
        started_at=datetime(2026, 5, 25, 9, 0, 0),
        finished_at=datetime(2026, 5, 25, 9, 0, 5),
        status="success",
        rows_affected=10,
        details={"industry_rows": 5, "country_rows": 5},
    )
    with (
        patch("bot.cli.import_damodaran", side_effect=lambda *a, **k: calls.append("dam") or dam),
        patch(
            "bot.cli.refresh_universe_from_fmp",
            side_effect=lambda *a, **k: calls.append("fmp") or _uni("u"),
        ),
        patch(
            "bot.cli.refresh_prices_from_fmp",
            side_effect=lambda *a, **k: calls.append("prices") or _uni("p"),
        ),
        patch(
            "bot.cli.refresh_fx_from_fmp",
            side_effect=lambda *a, **k: calls.append("fx") or _uni("f"),
        ),
    ):
        runner = CliRunner()
        result = runner.invoke(app, ["refresh", "--all"])

    assert calls == ["dam", "fmp", "prices", "fx"]
    assert result.exit_code == 0


def test_refresh_without_flags_shows_help(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "test.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    runner = CliRunner()
    result = runner.invoke(app, ["refresh"])
    assert result.exit_code != 0
    # The error message goes to stderr; CliRunner mixes_stderr=False by default? Check both.
    combined = (result.stdout + (result.stderr or "")).lower()
    assert "specify" in combined or "flag" in combined or "damodaran" in combined
