"""CLI integration test for `bot analyze <TICKER>` (issue #16, spec §7.7).

Seeds an in-memory-equivalent DuckDB file with a fixture company, runs
``bot analyze``, then parses the written Markdown report and asserts the key
§7.7 sections are present.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
from typer.testing import CliRunner

from bot.cli import app
from bot.storage.db import apply_schema, connect


def _seed(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        "INSERT INTO companies "
        "(ticker, name, country, currency, industry_damodaran, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ["AAPL", "Apple Inc", "United States", "USD", "Computers/Peripherals", "sec_edgar"],
    )
    conn.execute(
        "INSERT INTO damodaran_country (country, year, erp, risk_free_rate, tax_rate, region) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ["United States", 2026, 0.045, 0.04, 0.21, "US"],
    )
    conn.execute(
        "INSERT INTO damodaran_industry "
        "(industry, region, year, wacc, cost_of_equity, cost_of_debt, beta_levered, "
        "debt_to_equity, op_margin, sales_to_capital, pe, ev_sales) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        ["Computers/Peripherals", "US", 2026, 0.085, 0.09, 0.045, 1.05, 0.20, 0.28,
         2.5, 22.0, 5.0],
    )
    for year, revenue in {2022: 380_000.0, 2023: 395_000.0, 2024: 410_000.0, 2025: 430_000.0}.items():
        conn.execute(
            "INSERT INTO financials_annual "
            "(ticker, fiscal_year, revenue, ebit, net_income, total_debt, cash, "
            "shares_diluted, is_restated, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            ["AAPL", year, revenue, revenue * 0.30, 100_000.0, 110_000.0, 60_000.0,
             15_500.0, False, "sec_edgar"],
        )
    conn.execute(
        "INSERT INTO prices_daily (ticker, date, close, currency, source) "
        "VALUES (?, ?, ?, ?, ?)",
        ["AAPL", "2026-05-29", 150.0, "USD", "fmp"],
    )


def test_analyze_writes_report(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "bot.duckdb"
    reports_dir = tmp_path / "reports"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    conn = connect(db_path)
    apply_schema(conn)
    _seed(conn)
    conn.close()

    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "AAPL"])
    assert result.exit_code == 0, result.stdout

    # Exactly one report under reports/<date>/analysis/AAPL.md.
    reports = list(reports_dir.glob("*/analysis/AAPL.md"))
    assert len(reports) == 1
    md = reports[0].read_text()

    for heading in (
        "# AAPL",
        "Executive summary",
        "Story type",
        "Assumptions",
        "DCF detail",
        "Sensitivity",
        "Narrative flags",
        "Sanity check",
    ):
        assert heading in md, f"missing section {heading!r}"
    # The CLI echoes the path it wrote to.
    assert "AAPL.md" in result.stdout


def test_analyze_unknown_ticker_exits_nonzero(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "bot.duckdb"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    conn = connect(db_path)
    apply_schema(conn)
    conn.close()

    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "NOPE"])
    assert result.exit_code != 0


def test_analyze_applies_override(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "bot.duckdb"
    reports_dir = tmp_path / "reports"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    conn = connect(db_path)
    apply_schema(conn)
    _seed(conn)
    conn.close()

    override = tmp_path / "AAPL.yaml"
    override.write_text(
        "operating_margin: 0.35\nnotes: Services mix lifts steady-state margin.\n"
    )

    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "AAPL", "--override", str(override)])
    assert result.exit_code == 0, result.stdout

    md = next(reports_dir.glob("*/analysis/AAPL.md")).read_text()
    assert "Services mix lifts steady-state margin." in md
    assert "manual" in md
