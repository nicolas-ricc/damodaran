"""Integration test: seed 10 fixture companies, run screener, assert top-N.

Uses an in-memory DuckDB and a minimal custom config so no external
data (Damodaran benchmarks, prices_daily) is required.

Config rules chosen so each company passes or fails deterministically:
  Quality gates:
    - min_years_history(3)   — needs >= 3 rows in financials_annual
    - max_net_debt_to_ebitda(5.0) — net_debt / ebitda <= 5
    - positive_operating_cashflow(2, 3) — 2/3 years positive OCF

  Value indicators (min_pass=1):
    - fcf_yield_above(0.05) — free_cashflow / market_cap >= 5%

  Trap detection:
    - revenue_not_declining(-0.10) — avg revenue growth > -10%
    - share_count_not_diluting(0.10) — avg share growth < 10%

Fixture design - 10 companies labelled A-J:
  A-E: all gates pass, value indicator passes -> 5 expected finalists
  F: fails quality gate (net_debt/ebitda > 5)
  G: fails quality gate (only 2 years of history)
  H: fails value indicator (negative free cashflow -> fcf_yield < 0)
  I: fails trap - declining revenue
  J: fails trap - share dilution

Among A-E the composite ranking is determined by value_raw (fcf_yield
score), quality_raw, and growth_raw (trap scores).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from bot.screener.config import load_screener_config
from bot.screener.engine import run_screen
from bot.storage.db import apply_schema, connect

# ---------------------------------------------------------------------------
# Config fixture
# ---------------------------------------------------------------------------

_CONFIG_YAML = """\
quality_gates:
  rules:
    - name: min_years_history
      args:
        min_years: 3
    - name: max_net_debt_to_ebitda
      args:
        max_ratio: 5.0
    - name: positive_operating_cashflow
      args:
        min_positive_years: 2
        lookback_years: 3

value_indicators:
  min_pass: 1
  rules:
    - name: fcf_yield_above
      args:
        min_yield: 0.05

trap_detection:
  rules:
    - name: revenue_not_declining
      args:
        min_avg_growth: -0.10
    - name: share_count_not_diluting
      args:
        max_annual_growth: 0.10

ranking:
  weights:
    value: 0.40
    quality: 0.30
    growth: 0.20
    margin_of_safety: 0.10
"""

# ---------------------------------------------------------------------------
# DB seed helpers
# ---------------------------------------------------------------------------


def _seed(conn: object) -> None:
    import duckdb

    assert isinstance(conn, duckdb.DuckDBPyConnection)

    conn.execute(
        """
        INSERT INTO companies (ticker, name, status, source, market_cap)
        VALUES
          ('A', 'Alpha Corp',   'active', 'test', 2_000_000_000),
          ('B', 'Beta Inc',     'active', 'test', 1_500_000_000),
          ('C', 'Gamma Ltd',    'active', 'test', 1_000_000_000),
          ('D', 'Delta SA',     'active', 'test',   800_000_000),
          ('E', 'Epsilon PLC',  'active', 'test',   500_000_000),
          ('F', 'FailDebt Co',  'active', 'test', 1_000_000_000),
          ('G', 'FailHist Co',  'active', 'test', 1_000_000_000),
          ('H', 'FailFCF Co',   'active', 'test',   900_000_000),
          ('I', 'FailRev Co',   'active', 'test',   700_000_000),
          ('J', 'FailDil Co',   'active', 'test',   600_000_000)
        """
    )

    # Helper: insert 3 years of financials for a ticker.
    def _fins(
        ticker: str,
        *,
        revenues: tuple[float, float, float],
        ebitdas: tuple[float, float, float],
        ebits: tuple[float, float, float],
        ocfs: tuple[float, float, float],
        free_cfs: tuple[float, float, float],
        shares: tuple[float, float, float],
        net_debt: float = 0.0,
    ) -> None:
        for i, yr in enumerate((2022, 2023, 2024)):
            conn.execute(
                """
                INSERT INTO financials_annual
                  (ticker, fiscal_year, revenue, ebit, ebitda,
                   operating_cashflow, free_cashflow, shares_diluted,
                   total_debt, cash, net_income, total_assets,
                   total_equity, interest_expense, goodwill,
                   is_restated, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        FALSE, 'test')
                """,
                [
                    ticker,
                    yr,
                    revenues[i],
                    ebits[i],
                    ebitdas[i],
                    ocfs[i],
                    free_cfs[i],
                    shares[i],
                    net_debt,
                    0.0,  # total_debt, cash → net_debt = total_debt
                    ebits[i] * 0.75,  # net_income ≈ ebit * (1 - 0.25 tax)
                    ebitdas[i] * 10,  # total_assets
                    ebitdas[i] * 5,  # total_equity
                    0.0,  # interest_expense
                    0.0,  # goodwill
                ],
            )

    # ------------------------------------------------------------------
    # A — high FCF yield (20%), growing revenue, stable shares → top ranked
    # ------------------------------------------------------------------
    _fins(
        "A",
        revenues=(800e6, 900e6, 1_000e6),
        ebitdas=(200e6, 220e6, 240e6),
        ebits=(180e6, 200e6, 220e6),
        ocfs=(150e6, 160e6, 170e6),
        free_cfs=(400e6, 410e6, 420e6),  # FCF yield = 420M / 2B = 21%
        shares=(100e6, 100e6, 100e6),
        net_debt=100e6,
    )

    # B — FCF yield 13%, solid fundamentals
    _fins(
        "B",
        revenues=(600e6, 660e6, 720e6),
        ebitdas=(150e6, 165e6, 180e6),
        ebits=(130e6, 143e6, 156e6),
        ocfs=(120e6, 130e6, 140e6),
        free_cfs=(195e6, 200e6, 205e6),  # 205M / 1.5B = 13.7%
        shares=(80e6, 80e6, 80e6),
        net_debt=50e6,
    )

    # C — FCF yield 11%
    _fins(
        "C",
        revenues=(500e6, 530e6, 560e6),
        ebitdas=(120e6, 128e6, 136e6),
        ebits=(100e6, 108e6, 116e6),
        ocfs=(90e6, 95e6, 100e6),
        free_cfs=(110e6, 112e6, 114e6),  # 114M / 1B = 11.4%
        shares=(60e6, 60e6, 60e6),
        net_debt=30e6,
    )

    # D — FCF yield 8.75%
    _fins(
        "D",
        revenues=(400e6, 420e6, 440e6),
        ebitdas=(100e6, 106e6, 112e6),
        ebits=(80e6, 85e6, 90e6),
        ocfs=(70e6, 75e6, 80e6),
        free_cfs=(68e6, 70e6, 72e6),  # 72M / 800M = 9%
        shares=(50e6, 50e6, 50e6),
        net_debt=20e6,
    )

    # E — FCF yield 6%
    _fins(
        "E",
        revenues=(300e6, 315e6, 330e6),
        ebitdas=(80e6, 85e6, 90e6),
        ebits=(65e6, 70e6, 75e6),
        ocfs=(55e6, 60e6, 65e6),
        free_cfs=(28e6, 29e6, 30e6),  # 30M / 500M = 6%
        shares=(40e6, 40e6, 40e6),
        net_debt=10e6,
    )

    # F — fails quality gate: net_debt/ebitda = 800M/80M = 10 > 5.0
    _fins(
        "F",
        revenues=(300e6, 320e6, 340e6),
        ebitdas=(80e6, 84e6, 88e6),
        ebits=(60e6, 64e6, 68e6),
        ocfs=(55e6, 60e6, 65e6),
        free_cfs=(50e6, 52e6, 54e6),
        shares=(40e6, 40e6, 40e6),
        net_debt=800e6,  # ← kills this company (net_debt/ebitda ≈ 9)
    )

    # G — fails quality gate: only 2 years of history (min_years=3)
    conn.execute(
        """
        INSERT INTO financials_annual
          (ticker, fiscal_year, revenue, ebit, ebitda,
           operating_cashflow, free_cashflow, shares_diluted,
           total_debt, cash, net_income, total_assets, total_equity,
           interest_expense, goodwill, is_restated, source)
        VALUES
          ('G', 2023, 200e6, 40e6, 50e6, 45e6, 40e6, 30e6, 0, 0,
           30e6, 500e6, 250e6, 0, 0, FALSE, 'test'),
          ('G', 2024, 210e6, 42e6, 52e6, 47e6, 42e6, 30e6, 0, 0,
           31.5e6, 520e6, 260e6, 0, 0, FALSE, 'test')
        """
    )

    # H — fails value indicator: negative free cashflow → fcf_yield < 0 < 5%
    _fins(
        "H",
        revenues=(350e6, 370e6, 390e6),
        ebitdas=(90e6, 95e6, 100e6),
        ebits=(70e6, 75e6, 80e6),
        ocfs=(60e6, 65e6, 70e6),
        free_cfs=(-10e6, -5e6, -3e6),  # negative FCF
        shares=(45e6, 45e6, 45e6),
        net_debt=20e6,
    )

    # I - fails trap: revenue declining >10%  (-15% avg growth)
    _fins(
        "I",
        revenues=(500e6, 430e6, 365e6),  # approx -14% then -15%
        ebitdas=(100e6, 90e6, 80e6),
        ebits=(80e6, 72e6, 64e6),
        ocfs=(70e6, 65e6, 60e6),
        free_cfs=(35e6, 33e6, 31e6),
        shares=(40e6, 40e6, 40e6),
        net_debt=10e6,
    )

    # J — fails trap: share dilution avg 25% per year > 10%
    _fins(
        "J",
        revenues=(400e6, 420e6, 440e6),
        ebitdas=(100e6, 106e6, 112e6),
        ebits=(80e6, 85e6, 90e6),
        ocfs=(70e6, 75e6, 80e6),
        free_cfs=(40e6, 42e6, 44e6),
        shares=(40e6, 50e6, 62e6),  # +25% per year
        net_debt=20e6,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.fixture()
def db_conn():  # type: ignore[no-untyped-def]
    conn = connect(":memory:")
    apply_schema(conn)
    _seed(conn)
    yield conn
    conn.close()


@pytest.fixture()
def screener_config(tmp_path: Path):  # type: ignore[no-untyped-def]
    cfg_file = tmp_path / "test.yaml"
    cfg_file.write_text(_CONFIG_YAML)
    return load_screener_config(cfg_file)


def test_screen_returns_exactly_five_finalists(db_conn, screener_config) -> None:  # type: ignore[no-untyped-def]
    run = run_screen(db_conn, screener_config, preset_name="test", top_n=20)
    tickers = [c.ticker for c in run.candidates]
    assert set(tickers) == {"A", "B", "C", "D", "E"}


def test_screen_candidates_sorted_by_composite_score(db_conn, screener_config) -> None:  # type: ignore[no-untyped-def]
    """Composite scores must be non-increasing (best first)."""
    run = run_screen(db_conn, screener_config, preset_name="test", top_n=20)
    scores = [c.scored.composite_score for c in run.candidates]
    assert scores == sorted(scores, reverse=True)


def test_screen_top_n_limits_results(db_conn, screener_config) -> None:  # type: ignore[no-untyped-def]
    run = run_screen(db_conn, screener_config, preset_name="test", top_n=3)
    assert len(run.candidates) == 3


def test_screen_persists_candidates_to_db(db_conn, screener_config) -> None:  # type: ignore[no-untyped-def]
    run = run_screen(db_conn, screener_config, preset_name="test", top_n=5)
    rows = db_conn.execute(
        "SELECT ticker FROM screener_candidates WHERE run_id = ? ORDER BY rank",
        [run.run_id],
    ).fetchall()
    assert len(rows) == 5
    assert {r[0] for r in rows} == {"A", "B", "C", "D", "E"}


def test_screen_persists_correct_run_id(db_conn, screener_config) -> None:  # type: ignore[no-untyped-def]
    run = run_screen(db_conn, screener_config, preset_name="test", top_n=5, run_id="test-run-001")
    rows = db_conn.execute("SELECT DISTINCT run_id FROM screener_candidates").fetchall()
    assert rows == [("test-run-001",)]
    assert run.run_id == "test-run-001"


def test_screen_excludes_failing_companies(db_conn, screener_config) -> None:  # type: ignore[no-untyped-def]
    run = run_screen(db_conn, screener_config, preset_name="test", top_n=20)
    tickers = {c.ticker for c in run.candidates}
    assert "F" not in tickers  # fails debt gate
    assert "G" not in tickers  # fails history gate
    assert "H" not in tickers  # fails FCF yield
    assert "I" not in tickers  # fails revenue trap
    assert "J" not in tickers  # fails dilution trap


def test_screen_candidate_scores_in_range(db_conn, screener_config) -> None:  # type: ignore[no-untyped-def]
    run = run_screen(db_conn, screener_config, preset_name="test", top_n=20)
    for c in run.candidates:
        assert 0.0 <= c.scored.composite_score <= 1.0
        assert 0.0 <= c.scored.value_score <= 1.0
        assert 0.0 <= c.scored.quality_score <= 1.0


def test_screen_candidates_have_key_metrics(db_conn, screener_config) -> None:  # type: ignore[no-untyped-def]
    run = run_screen(db_conn, screener_config, preset_name="test", top_n=5)
    for c in run.candidates:
        assert "market_cap" in c.key_metrics
        assert c.key_metrics["market_cap"] is not None
        assert "fcf_yield" in c.key_metrics


def test_screen_run_date_format(db_conn, screener_config) -> None:  # type: ignore[no-untyped-def]
    run = run_screen(db_conn, screener_config, preset_name="test", top_n=5)
    parts = run.run_date.split("-")
    assert len(parts) == 3
    assert len(parts[0]) == 4  # YYYY


def test_screen_reports_written(db_conn, screener_config, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from bot.screener.reports import write_reports

    run = run_screen(db_conn, screener_config, preset_name="test", top_n=5)
    md_path, csv_path = write_reports(run, tmp_path)

    assert md_path.exists()
    assert csv_path.exists()

    md_text = md_path.read_text()
    csv_text = csv_path.read_text()

    assert "# Screener Report: test" in md_text
    assert "A" in md_text  # top ticker present in MD

    lines = csv_text.strip().splitlines()
    assert lines[0].startswith("rank,ticker,name")
    assert len(lines) == 6  # header + 5 candidates
