"""End-to-end test for ``bot screen`` (issue #9, spec §6).

Seeds an in-memory-equivalent DuckDB file with 10 fixture companies spanning the
screener's pass/fail cases, runs ``bot screen --preset damodaran_value --top 5``,
and asserts the shortlist composition, the persisted ``screener_candidates`` rows,
and the Markdown + CSV report artefacts.
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import duckdb
import pytest
from typer.testing import CliRunner

from bot.cli import app
from bot.storage.db import apply_schema, connect

# Damodaran US medians: cheap thresholds at 0.7x → PE<15.4, EV/EBITDA<7, PBV<2.1.
_SECTOR = "Software (System & Application)"
_WACC = 0.085
_PE_MEDIAN = 22.0
_EV_EBITDA_MEDIAN = 12.0
_PBV_MEDIAN = 4.0
_ROE_MEDIAN = 0.15


def _seed_sector(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        "INSERT INTO damodaran_country (country, year, region) VALUES (?, ?, ?)",
        ["United States", 2026, "US"],
    )
    conn.execute(
        "INSERT INTO damodaran_industry "
        "(industry, region, year, wacc, roe, pe, pbv, ev_ebitda) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [_SECTOR, "US", 2026, _WACC, _ROE_MEDIAN, _PE_MEDIAN, _PBV_MEDIAN, _EV_EBITDA_MEDIAN],
    )


def _add_company(
    conn: duckdb.DuckDBPyConnection,
    ticker: str,
    *,
    industry: str = _SECTOR,
    country: str = "United States",
    market_cap: float = 5_000_000_000.0,
    close: float = 10.0,
    eps: float = 1.0,
    book_per_share: float = 2.0,
    ebitda: float = 1_000_000_000.0,
    net_debt: float = 0.0,
    ebit: float = 800_000_000.0,
    interest: float = 50_000_000.0,
    revenue_start: float = 1_000_000_000.0,
    revenue_growth: float = 0.10,
    op_margin: float = 0.20,
    fcf: float = 600_000_000.0,
    total_equity: float = 4_000_000_000.0,
    total_assets: float = 6_000_000_000.0,
    goodwill: float = 500_000_000.0,
    roic_invested: float = 4_000_000_000.0,
    years: int = 6,
    shares: float = 1_000_000_000.0,
) -> None:
    conn.execute(
        "INSERT INTO companies (ticker, name, country, industry, industry_damodaran, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [ticker, f"{ticker} Corp", country, industry, industry, "fmp"],
    )
    net_income = eps * shares
    total_debt = max(net_debt, 0.0)
    cash = max(-net_debt, 0.0)
    rev = revenue_start
    for offset in range(years):
        year = 2020 + offset
        rev = revenue_start * ((1.0 + revenue_growth) ** offset)
        conn.execute(
            "INSERT INTO financials_annual "
            "(ticker, fiscal_year, revenue, ebit, ebitda, interest_expense, net_income, "
            "total_assets, total_debt, cash, total_equity, goodwill, operating_cashflow, "
            "free_cashflow, shares_diluted, is_restated, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ticker, year, rev, rev * op_margin, ebitda, interest, net_income,
                total_assets, total_debt, cash, total_equity, goodwill,
                fcf + 100_000_000.0, fcf, shares, False, "fmp",
            ],
        )
    conn.execute(
        "INSERT INTO prices_daily (ticker, date, close, market_cap, currency, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [ticker, "2026-05-29", close, market_cap, "USD", "fmp"],
    )
    # Pin book-per-share by overriding equity to close/pbv-target * shares.
    conn.execute(
        "UPDATE financials_annual SET total_equity = ? WHERE ticker = ?",
        [book_per_share * shares, ticker],
    )


def _seed_universe(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_sector(conn)
    # Three clear winners: cheap (low PE) + quality + growing.
    _add_company(conn, "WINA", close=10.0, eps=1.2, revenue_growth=0.15, fcf=700_000_000.0)
    _add_company(conn, "WINB", close=11.0, eps=1.3, revenue_growth=0.13, fcf=900_000_000.0)
    _add_company(conn, "WINC", close=9.0, eps=1.0, revenue_growth=0.18, fcf=800_000_000.0)
    # Marginal passers: cheap enough but weaker metrics.
    _add_company(conn, "MIDA", close=14.0, eps=1.0, revenue_growth=0.06)
    _add_company(conn, "MIDB", close=13.0, eps=1.0, revenue_growth=0.05)
    _add_company(conn, "MIDC", close=14.0, eps=1.0, revenue_growth=0.04)
    # Fails: expensive (PE far above sector — no value indicator passes).
    _add_company(conn, "EXPN", close=40.0, eps=1.0, fcf=10_000_000.0)
    # Fails: financial-services sector excluded by a quality gate.
    _add_company(conn, "BANK", industry="Bank (Money Center)", close=8.0, eps=1.0)
    # Fails: too little history (<5 years).
    _add_company(conn, "YUNG", close=8.0, eps=1.2, years=2)
    # Fails: revenue declining (trap detector).
    _add_company(conn, "DECL", close=8.0, eps=1.2, revenue_growth=-0.20)


@pytest.fixture
def screened(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    db_path = tmp_path / "bot.duckdb"
    reports_dir = tmp_path / "reports"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    conn = connect(db_path)
    apply_schema(conn)
    _seed_universe(conn)
    conn.close()

    runner = CliRunner()
    result = runner.invoke(app, ["screen", "--preset", "damodaran_value", "--top", "5"])
    assert result.exit_code == 0, result.stdout
    return db_path, reports_dir


def test_shortlist_top_n_composition(screened: tuple[Path, Path]) -> None:
    db_path, _reports_dir = screened
    conn = connect(db_path)
    rows = conn.execute(
        "SELECT ticker, rank FROM screener_candidates ORDER BY rank"
    ).fetchall()
    conn.close()

    tickers = [r[0] for r in rows]
    # --top 5 caps the shortlist.
    assert len(tickers) == 5
    # The three engineered winners sit at the top; failures never appear.
    assert set(tickers[:3]) == {"WINA", "WINB", "WINC"}
    for failure in ("EXPN", "BANK", "YUNG", "DECL"):
        assert failure not in tickers
    # Ranks are 1..5 contiguous.
    assert [r[1] for r in rows] == [1, 2, 3, 4, 5]


def test_candidates_written_with_run_id(screened: tuple[Path, Path]) -> None:
    db_path, _ = screened
    conn = connect(db_path)
    run_ids = conn.execute("SELECT DISTINCT run_id FROM screener_candidates").fetchall()
    sub = conn.execute(
        "SELECT score, value_score, quality_score, growth_score, mos_score, "
        "passed_gates FROM screener_candidates WHERE rank = 1"
    ).fetchone()
    conn.close()

    assert len(run_ids) == 1
    assert run_ids[0][0]  # non-empty run_id
    assert sub is not None
    score, value_s, quality_s, growth_s, mos_s, passed_gates = sub
    assert score is not None and 0.0 <= score <= 100.0
    for sub_score in (value_s, quality_s, growth_s, mos_s):
        assert sub_score is not None
    assert "min_market_cap" in list(passed_gates)


def test_markdown_and_csv_reports_match(screened: tuple[Path, Path]) -> None:
    _, reports_dir = screened
    md_files = list(reports_dir.glob("*/screen/damodaran_value.md"))
    csv_files = list(reports_dir.glob("*/screen/damodaran_value.csv"))
    assert len(md_files) == 1
    assert len(csv_files) == 1

    md = md_files[0].read_text()
    assert "# Screen — damodaran_value" in md
    for header in ("ticker", "name", "score", "value_score", "sector", "roic"):
        assert header in md
    assert "WINA" in md

    rows = list(csv.DictReader(io.StringIO(csv_files[0].read_text())))
    assert len(rows) == 5
    # CSV columns are machine-readable and identical to the MD table columns.
    assert set(rows[0].keys()) == {
        "rank", "ticker", "name", "sector", "score", "value_score",
        "quality_score", "growth_score", "margin_of_safety", "market_cap",
        "pe", "ev_ebitda", "pbv", "roe", "roic", "fcf_yield",
    }
    assert rows[0]["ticker"] in {"WINA", "WINB", "WINC"}
    # Scores parse as floats (machine-readable).
    assert 0.0 <= float(rows[0]["score"]) <= 100.0


def test_config_path_flag(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "bot.duckdb"
    reports_dir = tmp_path / "reports"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    conn = connect(db_path)
    apply_schema(conn)
    _seed_universe(conn)
    conn.close()

    preset = (
        Path(__file__).resolve().parents[2]
        / "config"
        / "presets"
        / "damodaran_value.yaml"
    )
    runner = CliRunner()
    result = runner.invoke(app, ["screen", "--config", str(preset)])
    assert result.exit_code == 0, result.stdout
    assert (reports_dir).glob("*/screen/damodaran_value.md")
