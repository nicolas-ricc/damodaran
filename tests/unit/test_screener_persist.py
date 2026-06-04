"""Unit tests for persisting a shortlist to ``screener_candidates`` (issue #9)."""

from __future__ import annotations

import duckdb

from bot.screener.engine import ScreenedCompany, ScreenResult
from bot.screener.persist import persist_candidates
from bot.storage.db import apply_schema


def _company(ticker: str, score: float) -> ScreenedCompany:
    return ScreenedCompany(
        ticker=ticker,
        name=f"{ticker} Corp",
        sector="Software",
        region="US",
        market_cap=1e9,
        pe=10.0,
        ev_ebitda=5.0,
        pbv=1.2,
        roe=0.2,
        roic=0.15,
        fcf_yield=0.1,
        passed=True,
        passed_gates=("min_market_cap", "pe_below_industry_multiple"),
        failed_gates=(),
        score=score,
        value_score=0.9,
        quality_score=0.8,
        growth_score=0.7,
        margin_of_safety=0.5,
    )


def test_persist_writes_rows_with_run_id() -> None:
    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    result = ScreenResult(
        preset="damodaran_value",
        shortlist=(_company("AAA", 90.0), _company("BBB", 80.0)),
        screened=10,
    )
    run_id = persist_candidates(conn, result)

    rows = conn.execute(
        "SELECT run_id, preset, ticker, rank, score, passed_gates "
        "FROM screener_candidates ORDER BY rank"
    ).fetchall()
    assert len(rows) == 2
    assert all(r[0] == run_id for r in rows)
    assert [r[2] for r in rows] == ["AAA", "BBB"]
    assert [r[3] for r in rows] == [1, 2]
    assert "min_market_cap" in list(rows[0][5])


def test_persist_accepts_explicit_run_id() -> None:
    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    result = ScreenResult(preset="p", shortlist=(_company("AAA", 1.0),), screened=1)
    run_id = persist_candidates(conn, result, run_id="fixed-run")
    assert run_id == "fixed-run"
    assert conn.execute(
        "SELECT run_id FROM screener_candidates"
    ).fetchone() == ("fixed-run",)


def test_persist_empty_shortlist() -> None:
    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    result = ScreenResult(preset="p", shortlist=(), screened=0)
    run_id = persist_candidates(conn, result)
    assert run_id
    assert conn.execute("SELECT COUNT(*) FROM screener_candidates").fetchone() == (0,)
