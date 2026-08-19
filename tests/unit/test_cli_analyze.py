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


def _seed(conn: duckdb.DuckDBPyConnection, ticker: str = "AAPL") -> None:
    conn.execute(
        "INSERT INTO companies "
        "(ticker, name, country, currency, industry_damodaran, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [ticker, f"{ticker} Inc", "United States", "USD", "Computers/Peripherals", "sec_edgar"],
    )
    conn.execute(
        "INSERT INTO damodaran_country (country, year, erp, risk_free_rate, tax_rate, region) "
        "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
        ["United States", 2026, 0.045, 0.04, 0.21, "US"],
    )
    conn.execute(
        "INSERT INTO damodaran_industry "
        "(industry, region, year, wacc, cost_of_equity, cost_of_debt, beta_levered, "
        "debt_to_equity, op_margin, sales_to_capital, pe, ev_sales) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
        ["Computers/Peripherals", "US", 2026, 0.085, 0.09, 0.045, 1.05, 0.20, 0.28,
         2.5, 22.0, 5.0],
    )
    for year, revenue in {2022: 380_000.0, 2023: 395_000.0, 2024: 410_000.0, 2025: 430_000.0}.items():
        conn.execute(
            "INSERT INTO financials_annual "
            "(ticker, fiscal_year, revenue, ebit, net_income, total_debt, cash, "
            "shares_diluted, is_restated, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [ticker, year, revenue, revenue * 0.30, 100_000.0, 110_000.0, 60_000.0,
             15_500.0, False, "sec_edgar"],
        )
    conn.execute(
        "INSERT INTO prices_daily (ticker, date, close, currency, source) "
        "VALUES (?, ?, ?, ?, ?)",
        [ticker, "2026-05-29", 150.0, "USD", "fmp"],
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


def test_analyze_writes_html_alongside_md(tmp_path: Path, monkeypatch) -> None:
    """The HTML report (M6.1) is produced next to the Markdown one."""
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

    md_reports = list(reports_dir.glob("*/analysis/AAPL.md"))
    html_reports = list(reports_dir.glob("*/analysis/AAPL.html"))
    assert len(md_reports) == 1
    assert len(html_reports) == 1
    # Same directory: the HTML sits right beside the Markdown.
    assert html_reports[0].parent == md_reports[0].parent

    html = html_reports[0].read_text()
    assert html.lstrip().lower().startswith("<!doctype html>")
    # Self-contained: the tornado chart is inlined, no external assets.
    assert "data:image/png;base64," in html
    assert "<h1" in html
    # The CLI echoes the HTML path it wrote to.
    assert "AAPL.html" in result.stdout


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


def test_analyze_picks_up_config_assumptions_by_convention(
    tmp_path: Path, monkeypatch
) -> None:
    """Without ``--override``, `analyze` looks for `<assumptions_dir>/<TICKER>.yaml`."""
    db_path = tmp_path / "bot.duckdb"
    reports_dir = tmp_path / "reports"
    assumptions_dir = tmp_path / "assumptions"
    assumptions_dir.mkdir()
    (assumptions_dir / "AAPL.yaml").write_text("notes: convention override\n")

    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_ASSUMPTIONS_DIR", str(assumptions_dir))

    conn = connect(db_path)
    apply_schema(conn)
    _seed(conn)
    conn.close()

    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "AAPL"])
    assert result.exit_code == 0, result.stdout

    md = next(reports_dir.glob("*/analysis/AAPL.md")).read_text()
    assert "convention override" in md


def test_analyze_accepts_multiple_tickers(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "bot.duckdb"
    reports_dir = tmp_path / "reports"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    conn = connect(db_path)
    apply_schema(conn)
    _seed(conn, "AAPL")
    _seed(conn, "MSFT")
    conn.close()

    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "AAPL", "MSFT"])
    assert result.exit_code == 0, result.stdout

    out_dir = next((reports_dir).glob("*/analysis"))
    assert (out_dir / "AAPL.md").exists()
    assert (out_dir / "MSFT.md").exists()


def test_analyze_from_screen_uses_the_latest_run(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "bot.duckdb"
    reports_dir = tmp_path / "reports"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    conn = connect(db_path)
    apply_schema(conn)
    _seed(conn, "AAPL")
    _seed(conn, "MSFT")

    # Older run: shortlist would be wrong if picked.
    conn.execute(
        "INSERT INTO screener_candidates (run_id, preset, ticker, rank, passed, created_at) "
        "VALUES (?, ?, ?, ?, TRUE, TIMESTAMP '2026-01-01 00:00:00')",
        ["old-run", "damodaran_value", "AAPL", 1],
    )
    # Latest run: MSFT ranked ahead of AAPL.
    conn.execute(
        "INSERT INTO screener_candidates (run_id, preset, ticker, rank, passed, created_at) "
        "VALUES (?, ?, ?, ?, TRUE, TIMESTAMP '2026-06-01 00:00:00')",
        ["new-run", "damodaran_value", "MSFT", 1],
    )
    conn.execute(
        "INSERT INTO screener_candidates (run_id, preset, ticker, rank, passed, created_at) "
        "VALUES (?, ?, ?, ?, TRUE, TIMESTAMP '2026-06-01 00:00:01')",
        ["new-run", "damodaran_value", "AAPL", 2],
    )
    conn.close()

    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "--from-screen"])
    assert result.exit_code == 0, result.stdout
    assert result.output.index("MSFT") < result.output.index("AAPL")


def test_analyze_from_screen_without_runs_fails_clearly(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "bot.duckdb"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    conn = connect(db_path)
    apply_schema(conn)
    conn.close()

    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "--from-screen"])
    assert result.exit_code == 2
    assert "bot screen" in result.output


def test_analyze_from_screen_with_empty_shortlist_says_so(
    tmp_path: Path, monkeypatch
) -> None:
    """The latest run persisted but shortlisted nothing (all rows failed).

    This must be reported differently from "no screen was ever persisted" —
    the run happened, it just did not pass anything.
    """
    db_path = tmp_path / "bot.duckdb"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    conn = connect(db_path)
    apply_schema(conn)
    conn.execute(
        "INSERT INTO screener_candidates (run_id, preset, ticker, rank, passed, created_at) "
        "VALUES (?, ?, ?, ?, FALSE, TIMESTAMP '2026-06-01 00:00:00')",
        ["new-run", "damodaran_value", "AAPL", 1],
    )
    conn.close()

    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "--from-screen"])
    assert result.exit_code == 2
    assert "No hay ningún screen persistido" not in result.output
    assert "no dejó ningún candidato" in result.output


def test_analyze_explicit_override_with_many_tickers_is_rejected(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "bot.duckdb"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    conn = connect(db_path)
    apply_schema(conn)
    _seed(conn, "AAPL")
    _seed(conn, "MSFT")
    conn.close()

    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "AAPL", "MSFT", "--override", "x.yaml"])
    assert result.exit_code == 2


def test_analyze_explicit_override_wins_over_convention(
    tmp_path: Path, monkeypatch
) -> None:
    """An explicit ``--override`` beats the conventional `<assumptions_dir>` file."""
    db_path = tmp_path / "bot.duckdb"
    reports_dir = tmp_path / "reports"
    assumptions_dir = tmp_path / "assumptions"
    assumptions_dir.mkdir()
    (assumptions_dir / "AAPL.yaml").write_text("notes: convention override\n")

    explicit_override = tmp_path / "explicit.yaml"
    explicit_override.write_text("notes: explicit override\n")

    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_ASSUMPTIONS_DIR", str(assumptions_dir))

    conn = connect(db_path)
    apply_schema(conn)
    _seed(conn)
    conn.close()

    runner = CliRunner()
    result = runner.invoke(
        app, ["analyze", "AAPL", "--override", str(explicit_override)]
    )
    assert result.exit_code == 0, result.stdout

    md = next(reports_dir.glob("*/analysis/AAPL.md")).read_text()
    assert "explicit override" in md
    assert "convention override" not in md
