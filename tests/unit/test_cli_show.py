from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from bot.cli import app
from bot.ingest.provider import CompanyInfo
from bot.storage.db import apply_schema, connect
from tests.fake_provider import FakeProvider


def test_show_existing_ticker(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    conn = connect(tmp_path / "x.duckdb")
    apply_schema(conn)
    conn.execute(
        "INSERT INTO companies (ticker, name, country, currency, source) VALUES (?, ?, ?, ?, ?)",
        ["FAKE", "Fake Co", "US", "USD", "sec_edgar"],
    )
    conn.execute(
        "INSERT INTO financials_annual (ticker, fiscal_year, revenue, source, currency) VALUES (?, ?, ?, ?, 'USD')",
        ["FAKE", 2023, 1_000_000_000, "sec_edgar"],
    )
    conn.close()

    runner = CliRunner()
    result = runner.invoke(app, ["show", "FAKE"])
    assert result.exit_code == 0
    assert "FAKE" in result.stdout
    assert "Fake Co" in result.stdout


def _fake_provider_with_new() -> FakeProvider:
    provider = FakeProvider(
        companies={
            "NEW": CompanyInfo(
                ticker="NEW",
                name="NEW Inc",
                exchange=None,
                exchange_short_name=None,
                country="US",
                currency="USD",
                sector=None,
                industry="Electronic Computers",
                is_actively_trading=True,
                ipo_date=None,
            )
        }
    )
    provider.industry_mapping_key = "edgar"
    return provider


def test_show_missing_ticker_triggers_sec_import(tmp_path, monkeypatch):
    """``show --fetch`` imports through the configured provider, so the row gets mapped."""
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    provider = _fake_provider_with_new()

    with patch("bot.cli._make_provider", return_value=provider):
        result = CliRunner().invoke(app, ["show", "NEW"])

    assert result.exit_code == 0, result.output
    assert "NEW Inc" in result.stdout
    assert provider.closed

    conn = connect(tmp_path / "x.duckdb")
    row = conn.execute(
        "SELECT industry, industry_damodaran, source FROM companies WHERE ticker = 'NEW'"
    ).fetchone()
    conn.close()
    assert row == ("Electronic Computers", "Computers/Peripherals", "fake")


def test_show_missing_ticker_reports_provider_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    provider = FakeProvider(fail_with={"NEW": ValueError("Ticker NEW not found")})

    with patch("bot.cli._make_provider", return_value=provider):
        result = CliRunner().invoke(app, ["show", "NEW"])

    assert result.exit_code == 1
    assert "Failed to import NEW: Ticker NEW not found" in result.output
    assert provider.closed


def test_show_no_fetch_does_not_build_provider(tmp_path, monkeypatch):
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    with patch("bot.cli._make_provider", MagicMock()) as make_provider:
        result = CliRunner().invoke(app, ["show", "NEW", "--no-fetch"])

    assert result.exit_code == 2
    assert "the configured data provider" in result.output
    make_provider.assert_not_called()


def test_show_help_names_the_configured_data_provider():
    result = CliRunner().invoke(app, ["show", "--help"], terminal_width=200)
    assert result.exit_code == 0
    assert "configured data provider" in result.output
    assert "SEC EDGAR" not in result.output
