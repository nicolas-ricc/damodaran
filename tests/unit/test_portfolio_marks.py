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
    RedFlagBaseline,
    load_marks,
    load_red_flag_baselines,
    mark_holdings,
    persist_marks,
)
from bot.screener.engine import load_holding_inputs
from bot.screener.rules import MinMarketCap, ROICAboveSectorWACC
from bot.storage.db import apply_schema
from bot.valuator.narrative_flags import FlagColor, NarrativeFlag
from tests.unit.test_valuator_analysis import _seed as _seed_valuable

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
    def fn(
        ticker: str, _conn: duckdb.DuckDBPyConnection, *, price_as_of: date | None = None
    ) -> _Analysis:
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
            "free_cashflow, shares_diluted, is_restated, source, currency) "
            "VALUES (?, ?, 1000.0, 200.0, 300.0, 10.0, 150.0, 2000.0, 0.0, 100.0, "
            "1000.0, 100.0, 250.0, 200.0, 100.0, FALSE, 'fmp', 'USD')",
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
        ticker: str,
        _conn: duckdb.DuckDBPyConnection,
        override_path: Path | None = None,
        **_kwargs: object,
    ) -> _Analysis:
        seen[ticker] = override_path
        return _Analysis(ticker, _DCF(1.0), current_price=1.0)

    monkeypatch.setattr("bot.valuator.analysis.analyze", fake_analyze)
    _hold(conn, "AAPL")
    _hold(conn, "MSFT")

    mark_holdings(conn, DAY, assumptions_dir=tmp_path)

    assert seen == {"AAPL": override, "MSFT": None}


def test_mark_holdings_stores_the_converted_price(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    # #222: an EUR reporter trading at 110 USD, EUR rate 1.10 -> the mark's price is 100 EUR,
    # the currency its intrinsic value is in.
    _seed_valuable(conn)
    conn.execute("UPDATE financials_annual SET currency = 'EUR' WHERE ticker = 'AAPL'")
    conn.execute("UPDATE prices_daily SET close = 110.0 WHERE ticker = 'AAPL'")
    conn.execute(
        "INSERT INTO currencies (currency, date, rate_to_usd, source) "
        "VALUES ('EUR', '2026-05-29', 1.10, 'test')"
    )
    _hold(conn, "AAPL")

    marks = mark_holdings(conn, DAY, assumptions_dir=tmp_path)

    assert marks[0].intrinsic_value is not None
    assert marks[0].price == pytest.approx(100.0)
    assert load_marks(conn, DAY)["AAPL"].price == pytest.approx(100.0)


# --------------------------------------------------------------------------- #
# Last known red-flag set (#224)                                               #
# --------------------------------------------------------------------------- #

D1, D2, D3, D4 = (date(2026, 5, d) for d in (1, 2, 3, 4))
_RED = {"growth_reinvestment": "r"}


def test_baseline_skips_unknown_marks(conn: duckdb.DuckDBPyConnection) -> None:
    persist_marks(conn, D1, [HoldingMark("T", red_flags=_RED)])
    persist_marks(conn, D2, [HoldingMark("T", red_flags=None)])
    assert load_red_flag_baselines(conn, D3, ["T"]) == {"T": RedFlagBaseline(D1, _RED)}


def test_known_empty_set_is_a_baseline(conn: duckdb.DuckDBPyConnection) -> None:
    persist_marks(conn, D1, [HoldingMark("T", red_flags={})])
    assert load_red_flag_baselines(conn, D2, ["T"]) == {"T": RedFlagBaseline(D1, {})}


def test_no_known_mark_no_baseline(conn: duckdb.DuckDBPyConnection) -> None:
    assert load_red_flag_baselines(conn, D3, ["T"]) == {}
    persist_marks(conn, D1, [HoldingMark("T", red_flags=None)])
    persist_marks(conn, D2, [HoldingMark("T", red_flags=None)])
    assert load_red_flag_baselines(conn, D3, ["T"]) == {}


def test_baseline_ignores_current_and_later_marks(conn: duckdb.DuckDBPyConnection) -> None:
    persist_marks(conn, D1, [HoldingMark("T", red_flags=_RED)])
    persist_marks(conn, D3, [HoldingMark("T", red_flags={})])
    persist_marks(conn, D4, [HoldingMark("T", red_flags={})])
    assert load_red_flag_baselines(conn, D3, ["T"]) == {"T": RedFlagBaseline(D1, _RED)}


def test_baselines_are_per_ticker(conn: duckdb.DuckDBPyConnection) -> None:
    persist_marks(
        conn,
        D1,
        [HoldingMark("A", red_flags={}), HoldingMark("B", red_flags=_RED), HoldingMark("C", red_flags={})],
    )
    persist_marks(
        conn,
        D2,
        [HoldingMark("A", red_flags=_RED), HoldingMark("B", red_flags=None), HoldingMark("C", red_flags={})],
    )
    assert load_red_flag_baselines(conn, D3, ["A", "B"]) == {
        "A": RedFlagBaseline(D2, _RED),
        "B": RedFlagBaseline(D1, _RED),
    }


def test_baselines_empty_tickers(conn: duckdb.DuckDBPyConnection) -> None:
    persist_marks(conn, D1, [HoldingMark("T", red_flags=_RED)])
    assert load_red_flag_baselines(conn, D2, []) == {}


# --------------------------------------------------------------------------- #
# The mark's close is on or before the snapshot date (#225)                    #
# --------------------------------------------------------------------------- #


def _closes(conn: duckdb.DuckDBPyConnection, *rows: tuple[str, float]) -> None:
    """Replace AAPL's USD closes with ``(date, close)`` rows."""
    conn.execute("DELETE FROM prices_daily WHERE ticker = 'AAPL'")
    for day, close in rows:
        conn.execute(
            "INSERT INTO prices_daily (ticker, date, close, currency, source) "
            "VALUES ('AAPL', ?, ?, 'USD', 'fmp')",
            [day, close],
        )


def test_mark_holdings_prices_on_or_before_the_snapshot_date(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    # AC1: D-1 = 100, D+1 = 120 -> the mark for D stores 100.
    _seed_valuable(conn)
    _closes(conn, ("2026-05-31", 100.0), ("2026-06-02", 120.0))
    _hold(conn, "AAPL")

    marks = mark_holdings(conn, DAY, assumptions_dir=tmp_path)

    assert marks[0].price == pytest.approx(100.0)
    assert load_marks(conn, DAY)["AAPL"].price == pytest.approx(100.0)


def test_mark_holdings_rerun_of_an_old_snapshot_uses_that_dates_close(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    # AC2: re-marking an old snapshot reads that date's close, not today's.
    old = date(2026, 5, 4)
    _seed_valuable(conn)
    _closes(conn, ("2026-05-01", 90.0), ("2026-05-31", 100.0), ("2026-06-02", 120.0))
    conn.execute(
        "INSERT INTO portfolio_snapshots "
        "(snapshot_date, account, ticker, con_id, qty, market_value, currency) "
        "VALUES (?, 'DU1', 'AAPL', 1, 10.0, 900.0, 'USD')",
        [old],
    )

    marks = mark_holdings(conn, old, assumptions_dir=tmp_path)

    assert marks[0].price == pytest.approx(90.0)
    assert load_marks(conn, old)["AAPL"].price == pytest.approx(90.0)


def test_mark_holdings_no_close_before_snapshot_has_no_price(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    # Only a close after the snapshot date: the price is unknown, the value is not.
    _seed_valuable(conn)
    _closes(conn, ("2026-06-02", 120.0))
    _hold(conn, "AAPL")

    (mark,) = mark_holdings(conn, DAY, assumptions_dir=tmp_path)

    assert mark.price is None
    assert mark.intrinsic_value is not None


def test_mark_holdings_converts_the_bounded_close(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    # AC4: an EUR reporter; the bounded close (110 USD on 05-31) converts at that
    # date's EUR rate (1.10), not at the newer 1.20.
    _seed_valuable(conn)
    conn.execute("UPDATE financials_annual SET currency = 'EUR' WHERE ticker = 'AAPL'")
    _closes(conn, ("2026-05-31", 110.0), ("2026-06-02", 132.0))
    conn.execute(
        "INSERT INTO currencies (currency, date, rate_to_usd, source) VALUES "
        "('EUR', '2026-05-31', 1.10, 'test'), ('EUR', '2026-06-02', 1.20, 'test')"
    )
    _hold(conn, "AAPL")

    (mark,) = mark_holdings(conn, DAY, assumptions_dir=tmp_path)

    assert mark.price == pytest.approx(100.0)


def test_mark_holdings_passes_the_snapshot_date(conn: duckdb.DuckDBPyConnection) -> None:
    seen: list[date | None] = []

    def fn(
        ticker: str, _conn: duckdb.DuckDBPyConnection, *, price_as_of: date | None = None
    ) -> _Analysis:
        seen.append(price_as_of)
        return _Analysis(ticker, _DCF(1.0), current_price=1.0)

    _hold(conn, "AAPL")

    mark_holdings(conn, DAY, analyze_fn=cast(AnalyzeFn, fn))

    assert seen == [DAY]


def test_mark_holdings_forwards_the_default_spread_table(
    conn: duckdb.DuckDBPyConnection, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default valuator hands ``default_spreads`` to ``analyze`` (#246)."""
    from tests.unit.test_valuator_assumptions import _spreads

    table = _spreads()
    seen: dict[str, object] = {}

    def fake_analyze(ticker: str, _conn: duckdb.DuckDBPyConnection, *_args: object, **kwargs: object) -> _Analysis:
        seen[ticker] = kwargs.get("default_spreads")
        return _Analysis(ticker, _DCF(1.0), current_price=1.0)

    monkeypatch.setattr("bot.valuator.analysis.analyze", fake_analyze)
    _hold(conn, "AAPL")

    mark_holdings(conn, DAY, default_spreads=table)

    assert seen == {"AAPL": table}


def test_mark_holdings_unreadable_override_leaves_the_holding_unvalued(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    # #227: a directory named AAPL.yaml cannot be read; the holding is marked unvalued.
    _seed_valuable(conn)
    _hold(conn, "AAPL")
    (tmp_path / "AAPL.yaml").mkdir()

    (mark,) = mark_holdings(conn, DAY, assumptions_dir=tmp_path)

    assert mark.intrinsic_value is None
