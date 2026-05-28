"""Screening engine — M3.8: runs rules, ranks, persists candidates."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import duckdb

from bot.screener.config import RuleConfig, ScreenerConfig
from bot.screener.ranking import Candidate, ScoredCandidate, rank
from bot.screener.rules import CompanyData, IndustryBenchmarks, RuleResult, get_rule


@dataclass
class ScreenCandidate:
    ticker: str
    name: str
    sector: str | None
    scored: ScoredCandidate
    key_metrics: dict[str, float | None] = field(default_factory=dict)
    passed_gates: list[str] = field(default_factory=list)
    failed_gates: list[str] = field(default_factory=list)


@dataclass
class ScreenRun:
    run_id: str
    preset: str
    run_date: str  # YYYY-MM-DD
    candidates: list[ScreenCandidate]


@dataclass
class _Meta:
    company_name: str
    sector: str | None
    passed_gates: list[str]
    failed_gates: list[str]
    key_metrics: dict[str, float | None]


def _fetch_latest_annual(conn: duckdb.DuckDBPyConnection, ticker: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT revenue, ebit, ebitda, interest_expense, net_income,
               total_assets, total_debt, cash, total_equity, goodwill,
               operating_cashflow, free_cashflow, shares_diluted, tax_expense
        FROM financials_annual
        WHERE ticker = ? AND is_restated = FALSE
        ORDER BY fiscal_year DESC
        LIMIT 1
        """,
        [ticker],
    ).fetchone()
    if row is None:
        return {}
    cols = [
        "revenue",
        "ebit",
        "ebitda",
        "interest_expense",
        "net_income",
        "total_assets",
        "total_debt",
        "cash",
        "total_equity",
        "goodwill",
        "operating_cashflow",
        "free_cashflow",
        "shares_diluted",
        "tax_expense",
    ]
    return dict(zip(cols, row, strict=True))


def _fetch_col_history(
    conn: duckdb.DuckDBPyConnection, ticker: str, col: str, years: int
) -> list[float]:
    rows = conn.execute(
        f"SELECT {col} FROM financials_annual "
        "WHERE ticker = ? AND is_restated = FALSE "
        f"AND {col} IS NOT NULL "
        "ORDER BY fiscal_year ASC",
        [ticker],
    ).fetchall()
    return [float(r[0]) for r in rows if r[0] is not None][-years:]


def _fetch_op_margin_history(
    conn: duckdb.DuckDBPyConnection, ticker: str, years: int
) -> list[float]:
    rows = conn.execute(
        "SELECT ebit, revenue FROM financials_annual "
        "WHERE ticker = ? AND is_restated = FALSE "
        "AND ebit IS NOT NULL AND revenue IS NOT NULL AND revenue > 0 "
        "ORDER BY fiscal_year ASC",
        [ticker],
    ).fetchall()
    return [float(r[0]) / float(r[1]) for r in rows][-years:]


def _build_company_data(
    conn: duckdb.DuckDBPyConnection,
    ticker: str,
    sector: str | None,
    market_cap: float | None,
) -> CompanyData:
    latest = _fetch_latest_annual(conn, ticker)
    if not latest:
        return CompanyData(ticker=ticker, sector=sector, market_cap=market_cap)

    count_row = conn.execute(
        "SELECT COUNT(DISTINCT fiscal_year) FROM financials_annual "
        "WHERE ticker = ? AND is_restated = FALSE",
        [ticker],
    ).fetchone()
    years_history: int | None = int(count_row[0]) if count_row and count_row[0] else None

    def _f(key: str) -> float | None:
        v: Any = latest.get(key)
        return float(v) if v is not None else None

    ebit = _f("ebit")
    ebitda = _f("ebitda")
    net_income = _f("net_income")
    total_assets = _f("total_assets")
    total_debt = _f("total_debt")
    cash = _f("cash")
    total_equity = _f("total_equity")
    goodwill = _f("goodwill")
    interest_expense = _f("interest_expense")
    operating_cashflow = _f("operating_cashflow")
    free_cashflow = _f("free_cashflow")
    tax_expense = _f("tax_expense")

    net_debt: float | None = (
        total_debt - cash if total_debt is not None and cash is not None else None
    )
    roe: float | None = (
        net_income / total_equity
        if net_income is not None and total_equity is not None and total_equity > 0
        else None
    )

    pe_ratio: float | None = None
    ev_ebitda_val: float | None = None
    pbv: float | None = None
    fcf_yield: float | None = None
    if market_cap is not None and market_cap > 0:
        if net_income is not None and net_income > 0:
            pe_ratio = market_cap / net_income
        if ebitda is not None and ebitda > 0 and net_debt is not None:
            ev_ebitda_val = (market_cap + net_debt) / ebitda
        if total_equity is not None and total_equity > 0:
            pbv = market_cap / total_equity
        if free_cashflow is not None:
            fcf_yield = free_cashflow / market_cap

    roic: float | None = None
    if ebit is not None and total_assets is not None and cash is not None:
        tax_rate = 0.21
        if tax_expense is not None and ebit > 0:
            tax_rate = min(max(tax_expense / ebit, 0.0), 0.5)
        ic = total_assets - cash
        if ic > 0:
            roic = ebit * (1.0 - tax_rate) / ic

    ocf_hist = _fetch_col_history(conn, ticker, "operating_cashflow", 5)
    rev_3y = _fetch_col_history(conn, ticker, "revenue", 3)
    op_margin_3y = _fetch_op_margin_history(conn, ticker, 3)
    shares_3y = _fetch_col_history(conn, ticker, "shares_diluted", 3)

    return CompanyData(
        ticker=ticker,
        market_cap=market_cap,
        years_history=years_history,
        sector=sector,
        net_debt=net_debt,
        ebitda=ebitda,
        ebit=ebit,
        interest_expense=interest_expense,
        operating_cashflow_history=ocf_hist,
        goodwill=goodwill,
        total_assets=total_assets,
        pe_ratio=pe_ratio,
        ev_ebitda=ev_ebitda_val,
        pbv=pbv,
        roe=roe,
        fcf_yield=fcf_yield,
        revenue_3y=rev_3y if len(rev_3y) >= 2 else None,
        op_margin_3y=op_margin_3y if len(op_margin_3y) >= 2 else None,
        roic=roic,
        net_income=net_income,
        operating_cashflow=operating_cashflow,
        shares_diluted_3y=shares_3y if len(shares_3y) >= 2 else None,
    )


def _build_benchmarks(conn: duckdb.DuckDBPyConnection, industry: str | None) -> IndustryBenchmarks:
    if industry is None:
        return IndustryBenchmarks()
    row = conn.execute(
        "SELECT pe, ev_ebitda, pbv, roe, wacc FROM damodaran_industry "
        "WHERE industry = ? AND region = 'US' ORDER BY year DESC LIMIT 1",
        [industry],
    ).fetchone()
    if row is None:
        return IndustryBenchmarks(industry=industry)

    def _cast(v: Any) -> float | None:
        return float(v) if v is not None else None

    return IndustryBenchmarks(
        industry=industry,
        pe=_cast(row[0]),
        ev_ebitda=_cast(row[1]),
        pbv=_cast(row[2]),
        roe=_cast(row[3]),
        wacc=_cast(row[4]),
    )


def _eval_rules(
    rules: list[RuleConfig],
    company: CompanyData,
    benchmarks: IndustryBenchmarks,
) -> list[tuple[str, RuleResult]]:
    results: list[tuple[str, RuleResult]] = []
    for rc in rules:
        rule_cls = get_rule(rc.name)
        rule = rule_cls(**rc.args)
        results.append((rc.name, rule.evaluate(company, benchmarks)))
    return results


def run_screen(
    conn: duckdb.DuckDBPyConnection,
    config: ScreenerConfig,
    preset_name: str,
    top_n: int = 20,
    run_id: str | None = None,
) -> ScreenRun:
    """Screen the universe, rank, persist top *top_n* to screener_candidates."""
    if run_id is None:
        run_id = str(uuid.uuid4())

    now = datetime.now(tz=UTC)
    run_date = now.strftime("%Y-%m-%d")

    universe = conn.execute(
        "SELECT ticker, name, industry_damodaran, market_cap "
        "FROM companies WHERE status = 'active' ORDER BY ticker"
    ).fetchall()

    ranking_candidates: list[Candidate] = []
    meta: dict[str, _Meta] = {}

    for uni_row in universe:
        ticker = str(uni_row[0])
        company_name = str(uni_row[1])
        sector = str(uni_row[2]) if uni_row[2] is not None else None
        market_cap: float | None = float(uni_row[3]) if uni_row[3] is not None else None

        company = _build_company_data(conn, ticker, sector, market_cap)
        benchmarks = _build_benchmarks(conn, sector)

        passed: list[str] = []
        failed: list[str] = []

        # Layer 1 — quality gates: all must pass
        gate_res = _eval_rules(config.quality_gates.rules, company, benchmarks)
        for rule_name, result in gate_res:
            (passed if result.passed else failed).append(rule_name)
        if not all(r.passed for _, r in gate_res):
            continue

        # Layer 2 — value indicators: min_pass must pass
        vi_res = _eval_rules(config.value_indicators.rules, company, benchmarks)
        for rule_name, result in vi_res:
            (passed if result.passed else failed).append(rule_name)
        vi_pass = [(n, r) for n, r in vi_res if r.passed]
        if len(vi_pass) < config.value_indicators.min_pass:
            continue

        # Layer 3 — trap detection: all must pass
        trap_res = _eval_rules(config.trap_detection.rules, company, benchmarks)
        for rule_name, result in trap_res:
            (passed if result.passed else failed).append(rule_name)
        if not all(r.passed for _, r in trap_res):
            continue

        quality_raw = sum(r.score for _, r in gate_res) / len(gate_res) if gate_res else 0.0
        value_raw = sum(r.score for _, r in vi_pass) / len(vi_pass) if vi_pass else 0.0
        growth_raw = sum(r.score for _, r in trap_res) / len(trap_res) if trap_res else 0.0

        ranking_candidates.append(
            Candidate(
                ticker=ticker,
                value_raw=value_raw,
                quality_raw=quality_raw,
                growth_raw=growth_raw,
            )
        )
        meta[ticker] = _Meta(
            company_name=company_name,
            sector=sector,
            passed_gates=passed,
            failed_gates=failed,
            key_metrics={
                "market_cap": company.market_cap,
                "pe_ratio": company.pe_ratio,
                "ev_ebitda": company.ev_ebitda,
                "pbv": company.pbv,
                "roe": company.roe,
                "fcf_yield": company.fcf_yield,
            },
        )

    scored = rank(ranking_candidates, weights=config.ranking.weights)
    top = scored[:top_n]

    for rank_pos, sc in enumerate(top, start=1):
        m = meta[sc.ticker]
        conn.execute(
            """
            INSERT INTO screener_candidates
              (run_id, preset, ticker, rank, score,
               score_value, score_quality, score_growth, score_mos,
               passed_gates, failed_gates, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                run_id,
                preset_name,
                sc.ticker,
                rank_pos,
                sc.composite_score,
                sc.value_score,
                sc.quality_score,
                sc.growth_score,
                sc.margin_of_safety,
                ",".join(m.passed_gates),
                ",".join(m.failed_gates),
                now,
            ],
        )

    return ScreenRun(
        run_id=run_id,
        preset=preset_name,
        run_date=run_date,
        candidates=[
            ScreenCandidate(
                ticker=sc.ticker,
                name=meta[sc.ticker].company_name,
                sector=meta[sc.ticker].sector,
                scored=sc,
                key_metrics=meta[sc.ticker].key_metrics,
                passed_gates=meta[sc.ticker].passed_gates,
                failed_gates=meta[sc.ticker].failed_gates,
            )
            for sc in top
        ],
    )
