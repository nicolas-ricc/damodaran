"""Unit tests for holding marks: the per-snapshot valuation facts the derived
§8.3 events diff (M5, #28)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import cast

import duckdb
import pytest

from bot.portfolio.marks import (
    AnalyzeFn,
    HoldingMark,
    load_marks,
    mark_holdings,
    persist_marks,
)
from bot.screener.engine import load_holding_inputs
from bot.screener.rules import MinMarketCap, ROICAboveSectorWACC
from bot.storage.db import apply_schema
from bot.valuator.narrative_flags import FlagColor, NarrativeFlag

DAY = date(2026, 6, 1)


@pytest.fixture
def conn() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    apply_schema(c)
    return c


@dataclass(frozen=True)
class _DCF:
    intrinsic_value: float


@dataclass(frozen=True)
class _Analysis:
    ticker: str
    dcf_result: _DCF
    current_price: float | None
    narrative_flags: tuple[NarrativeFlag, ...] = field(default_factory=tuple)


def _analyze_with(results: dict[str, _Analysis]) -> AnalyzeFn:
    def fn(ticker: str, _conn: duckdb.DuckDBPyConnection) -> _Analysis:
        if ticker not in results:
            raise LookupError(ticker)
        return results[ticker]

    return cast(AnalyzeFn, fn)


def _hold(conn: duckdb.DuckDBPyConnection, ticker: str, qty: float = 10.0) -> None:
    conn.execute(
        "INSERT INTO portfolio_snapshots "
        "(snapshot_date, account, ticker, con_id, qty, market_value, currency) "
        "VALUES (?, 'DU1', ?, ?, ?, 1000.0, 'USD')",
        [DAY, ticker, hash(ticker) & 0xFFFF, qty],
    )


def _seed_company(
    conn: duckdb.DuckDBPyConnection, ticker: str, industry: str = "Software"
) -> None:
    conn.execute(
        "INSERT INTO companies (ticker, name, country, industry, industry_damodaran, source) "
        "VALUES (?, ?, 'United States', ?, ?, 'fmp')",
        [ticker, f"{ticker} Corp", industry, industry],
    )
    for offset in range(6):
        conn.execute(
            "INSERT INTO financials_annual "
            "(ticker, fiscal_year, revenue, ebit, ebitda, interest_expense, net_income, "
            "total_assets, total_debt, cash, total_equity, goodwill, operating_cashflow, "
            "free_cashflow, shares_diluted, is_restated, source) "
            "VALUES (?, ?, 1000.0, 200.0, 300.0, 10.0, 150.0, 2000.0, 0.0, 100.0, "
            "1000.0, 100.0, 250.0, 200.0, 100.0, FALSE, 'fmp')",
            [ticker, 2020 + offset],
        )
    conn.execute(
        "INSERT INTO prices_daily (ticker, date, close, market_cap, currency, source) "
        "VALUES (?, '2026-05-29', 10.0, 1000.0, 'USD', 'fmp')",
        [ticker],
    )


def _seed_benchmarks(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        "INSERT INTO damodaran_country (country, year, region) "
        "VALUES ('United States', 2026, 'US')"
    )
    conn.execute(
        "INSERT INTO damodaran_industry (industry, region, year, wacc) VALUES "
        "('Software', 'US', 2025, 0.07), ('Software', 'US', 2026, 0.08)"
    )


# --------------------------------------------------------------------------- #
# Storage                                                                      #
# --------------------------------------------------------------------------- #


def test_marks_round_trip(conn: duckdb.DuckDBPyConnection) -> None:
    marks = [
        HoldingMark(
            ticker="AAPL",
            intrinsic_value=120.0,
            price=100.0,
            red_flags={"story_margin": "margin too high"},
            failed_gates=("max_net_debt_to_ebitda",),
            sector_wacc=0.08,
        ),
        HoldingMark(ticker="MSFT", red_flags={}, failed_gates=()),
        HoldingMark(ticker="GOOG"),
    ]
    assert persist_marks(conn, DAY, marks) == 3
    assert load_marks(conn, DAY) == {m.ticker: m for m in marks}


def test_persist_marks_replaces_the_date(conn: duckdb.DuckDBPyConnection) -> None:
    persist_marks(conn, DAY, [HoldingMark("AAPL", intrinsic_value=1.0)])
    persist_marks(conn, DAY, [HoldingMark("AAPL", intrinsic_value=2.0)])
    assert load_marks(conn, DAY) == {"AAPL": HoldingMark("AAPL", intrinsic_value=2.0)}
    (count,) = conn.execute("SELECT COUNT(*) FROM holding_marks").fetchone() or (0,)
    assert count == 1


def test_load_marks_empty_date(conn: duckdb.DuckDBPyConnection) -> None:
    assert load_marks(conn, DAY) == {}


# --------------------------------------------------------------------------- #
# load_holding_inputs                                                          #
# --------------------------------------------------------------------------- #


def test_load_holding_inputs_only_known_tickers(conn: duckdb.DuckDBPyConnection) -> None:
    _seed_benchmarks(conn)
    _seed_company(conn, "TST")
    _seed_company(conn, "OTHER")
    inputs = load_holding_inputs(conn, ["TST", "MISSING"])
    assert set(inputs) == {"TST"}
    company, benchmarks = inputs["TST"]
    assert company.ticker == "TST"
    assert company.years_of_financials == 6
    assert benchmarks is not None
    assert benchmarks.wacc == pytest.approx(0.08)  # latest year wins


# --------------------------------------------------------------------------- #
# mark_holdings                                                                #
# --------------------------------------------------------------------------- #


def test_mark_holdings_records_valuation_and_red_flags_only(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _hold(conn, "AAPL")
    analysis = _Analysis(
        "AAPL",
        _DCF(120.0),
        current_price=100.0,
        narrative_flags=(
            NarrativeFlag("story_margin", FlagColor.RED, "too high"),
            NarrativeFlag("beta_risk", FlagColor.GREEN, "ok"),
        ),
    )
    marks = mark_holdings(conn, DAY, analyze_fn=_analyze_with({"AAPL": analysis}))
    assert len(marks) == 1
    mark = marks[0]
    assert mark.ticker == "AAPL"
    assert mark.intrinsic_value == 120.0
    assert mark.price == 100.0
    assert mark.red_flags == {"story_margin": "too high"}
    assert load_marks(conn, DAY) == {"AAPL": mark}


def test_mark_holdings_unvaluable_ticker_gets_null_mark(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _hold(conn, "ZZZ")
    (mark,) = mark_holdings(conn, DAY, analyze_fn=_analyze_with({}))
    assert mark == HoldingMark(ticker="ZZZ")


def test_mark_holdings_skips_zero_qty(conn: duckdb.DuckDBPyConnection) -> None:
    _hold(conn, "AAPL")
    _hold(conn, "GONE", qty=0.0)
    marks = mark_holdings(conn, DAY, analyze_fn=_analyze_with({}))
    assert [m.ticker for m in marks] == ["AAPL"]


def test_mark_holdings_failed_gates_and_sector_wacc(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _seed_benchmarks(conn)
    _seed_company(conn, "TST")
    _hold(conn, "TST")
    (mark,) = mark_holdings(
        conn,
        DAY,
        analyze_fn=_analyze_with({}),
        quality_gates=[MinMarketCap(minimum_usd=1e12), ROICAboveSectorWACC()],
    )
    assert mark.failed_gates == ("min_market_cap",)
    assert mark.sector_wacc == pytest.approx(0.08)


def test_mark_holdings_skipped_gate_is_not_a_failure(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    # No benchmark for the company's industry: roic_above_sector_wacc skips.
    _seed_company(conn, "TST", industry="Nowhere")
    _hold(conn, "TST")
    (mark,) = mark_holdings(
        conn, DAY, analyze_fn=_analyze_with({}), quality_gates=[ROICAboveSectorWACC()]
    )
    assert mark.failed_gates == ()
    assert mark.sector_wacc is None


def test_mark_holdings_unknown_company_has_no_gate_verdict(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    _hold(conn, "NOPE")
    (mark,) = mark_holdings(
        conn, DAY, analyze_fn=_analyze_with({}), quality_gates=[MinMarketCap()]
    )
    assert mark.failed_gates is None


def test_mark_holdings_values_with_the_conventional_override(
    conn: duckdb.DuckDBPyConnection,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The same <TICKER>.yaml that `bot analyze` and `bot screen` pick up.
    override = tmp_path / "AAPL.yaml"
    override.write_text("story_type: mature-stable\n")
    seen: dict[str, Path | None] = {}

    def fake_analyze(
        ticker: str, _conn: duckdb.DuckDBPyConnection, override_path: Path | None = None
    ) -> _Analysis:
        seen[ticker] = override_path
        return _Analysis(ticker, _DCF(1.0), current_price=1.0)

    monkeypatch.setattr("bot.valuator.analysis.analyze", fake_analyze)
    _hold(conn, "AAPL")
    _hold(conn, "MSFT")

    mark_holdings(conn, DAY, assumptions_dir=tmp_path)

    assert seen == {"AAPL": override, "MSFT": None}
