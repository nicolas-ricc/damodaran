"""Screener engine — assemble the universe and run the three layers (spec §6).

This is the one impure-at-the-edges orchestrator of Capa B: it reads every
company from the DB (``companies`` + ``financials_annual`` + ``prices_daily`` +
the Damodaran sector medians), assembles a pure :class:`CompanyData` snapshot per
ticker, and runs the three eliminatory layers of the loaded screener config —
quality gates (§6.2), value indicators (§6.3, at least one must pass), trap
detection (§6.4) — keeping only the survivors. Survivors become ranking
:class:`~bot.screener.ranking.Candidate` rows whose value/quality/growth metrics
feed the §6.5 percentile blend.

The rule arithmetic stays in the pure :mod:`bot.screener.rules` classes; this
module only gathers inputs, wires the layers together, and projects the result
into a :class:`ScreenResult`. It accepts the connection and holds no global
state, and only reads from the DB — persisting the shortlist and writing reports
is the caller's job (``bot.screener.persist`` / ``bot.reporting.screen_report``).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import duckdb

from bot.screener.benchmarks import load_industry_benchmarks
from bot.screener.config import ScreenerConfig
from bot.screener.ranking import (
    PLACEHOLDER_MARGIN_OF_SAFETY,
    Candidate,
    RankingWeights,
    ScoredCandidate,
    rank,
    rescore_with_margins,
)
from bot.screener.rules import Rule
from bot.screener.types import CompanyData, IndustryBenchmarks
from bot.utils.finance import cagr
from bot.valuator.analysis import analyze

#: Damodaran region used when a company's country has no ``damodaran_country``
#: row (so a value indicator can still look its sector median up). The screener
#: targets the US-only universe in M1/M3, so US is the sensible default.
DEFAULT_REGION = "US"

#: Fallback NOPAT tax rate for ROIC when a company's country carries no Damodaran
#: tax rate (1 - 0.21 = 0.79, the prior hardcoded US-federal assumption).
DEFAULT_TAX_RATE = 0.21

#: A valuator: given an open connection and a ticker, return that company's
#: DCF-derived margin of safety (``intrinsic_value / price``), or ``None`` when it
#: cannot be valued. This is the seam M4.7 wires the Capa C valuator into the
#: screener through; the default :func:`_dcf_margin_of_safety` runs the real DCF
#: pipeline, but tests inject a deterministic stand-in. ``> 1`` is undervalued.
type Valuator = Callable[[duckdb.DuckDBPyConnection, str], float | None]


def _dcf_margin_of_safety(conn: duckdb.DuckDBPyConnection, ticker: str) -> float | None:
    """Real DCF margin of safety for ``ticker`` (spec §6.5/§7.2, M4.7).

    Runs the Capa C valuation pipeline (:func:`bot.valuator.analysis.analyze`) and
    returns its ``intrinsic_value / current_price`` ratio. A company that cannot be
    valued — unknown ticker, missing financials/price, or assumptions too
    incomplete for the DCF — yields ``None`` so the caller falls back to the
    neutral :data:`~bot.screener.ranking.PLACEHOLDER_MARGIN_OF_SAFETY` rather than
    dropping the candidate from the shortlist.
    """
    try:
        analysis = analyze(ticker, conn)
    except (LookupError, ValueError, ZeroDivisionError):
        return None
    return analysis.margin_of_safety


@dataclass(frozen=True)
class ScreenedCompany:
    """One company's screener outcome, carrying everything the report renders.

    Bundles the company identity, the metrics the report surfaces, and — for
    survivors — the ranking sub-scores. ``passed`` is ``True`` only when the
    company cleared all three layers; ``passed_gates`` / ``failed_gates`` record
    which rules it cleared or tripped (serialised into ``screener_candidates``).
    """

    ticker: str
    name: str
    sector: str | None
    region: str
    market_cap: float | None
    pe: float | None
    ev_ebitda: float | None
    pbv: float | None
    roe: float | None
    roic: float | None
    fcf_yield: float | None
    passed: bool
    passed_gates: tuple[str, ...]
    failed_gates: tuple[str, ...]
    score: float | None = None
    value_score: float | None = None
    quality_score: float | None = None
    growth_score: float | None = None
    margin_of_safety: float | None = None


@dataclass(frozen=True)
class ScreenResult:
    """The outcome of one screen run over a universe (spec §6.1).

    ``shortlist`` is the ranked survivors, best first, truncated to ``top`` when a
    cap was requested. ``screened`` is the count of companies actually evaluated
    (the universe minus those with too little data to assemble a snapshot).
    """

    preset: str
    shortlist: tuple[ScreenedCompany, ...]
    screened: int


# --------------------------------------------------------------------------- #
# DB loading                                                                   #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _CompanyRow:
    ticker: str
    name: str
    country: str | None
    industry: str | None
    industry_damodaran: str | None


@dataclass(frozen=True)
class _AnnualRow:
    revenue: float | None
    ebit: float | None
    ebitda: float | None
    interest_expense: float | None
    net_income: float | None
    total_assets: float | None
    total_debt: float | None
    cash: float | None
    total_equity: float | None
    goodwill: float | None
    operating_cashflow: float | None
    free_cashflow: float | None
    shares_diluted: float | None


def _load_companies(conn: duckdb.DuckDBPyConnection) -> list[_CompanyRow]:
    rows = conn.execute(
        "SELECT ticker, name, country, industry, industry_damodaran FROM companies ORDER BY ticker"
    ).fetchall()
    return [
        _CompanyRow(
            ticker=r[0],
            name=r[1],
            country=r[2],
            industry=r[3],
            industry_damodaran=r[4],
        )
        for r in rows
    ]


def _load_annual(conn: duckdb.DuckDBPyConnection, ticker: str) -> list[_AnnualRow]:
    """Annual financials, oldest first (so histories read most-recent-last)."""
    rows = conn.execute(
        "SELECT revenue, ebit, ebitda, interest_expense, net_income, total_assets, "
        "total_debt, cash, total_equity, goodwill, operating_cashflow, free_cashflow, "
        "shares_diluted FROM financials_annual "
        "WHERE ticker = ? AND is_restated = FALSE ORDER BY fiscal_year",
        [ticker],
    ).fetchall()
    return [_AnnualRow(*r) for r in rows]


def _latest_market_cap(conn: duckdb.DuckDBPyConnection, ticker: str) -> float | None:
    row = conn.execute(
        "SELECT market_cap FROM prices_daily "
        "WHERE ticker = ? AND market_cap IS NOT NULL "
        "ORDER BY date DESC LIMIT 1",
        [ticker],
    ).fetchone()
    return float(row[0]) if row is not None and row[0] is not None else None


def _latest_close(conn: duckdb.DuckDBPyConnection, ticker: str) -> float | None:
    row = conn.execute(
        "SELECT close FROM prices_daily WHERE ticker = ? AND close IS NOT NULL "
        "ORDER BY date DESC LIMIT 1",
        [ticker],
    ).fetchone()
    return float(row[0]) if row is not None and row[0] is not None else None


def _resolve_region(conn: duckdb.DuckDBPyConnection, country: str | None) -> str:
    """Map a company's country to its Damodaran region, defaulting to US."""
    if country is None:
        return DEFAULT_REGION
    row = conn.execute(
        "SELECT region FROM damodaran_country WHERE country = ? "
        "AND region IS NOT NULL ORDER BY year DESC LIMIT 1",
        [country],
    ).fetchone()
    return str(row[0]) if row is not None and row[0] is not None else DEFAULT_REGION


def _resolve_tax_rate(conn: duckdb.DuckDBPyConnection, country: str | None) -> float:
    """The company's marginal tax rate from Damodaran, defaulting to 21%.

    Used as the NOPAT factor for ROIC. The screener keys on country (it has no
    sector tax lookup); an unknown or NULL-tax country falls back to
    :data:`DEFAULT_TAX_RATE` so US/unknown companies keep their prior behaviour.

    Note: the current Damodaran country ingest (the ERP file) does not carry a
    tax rate, so ``damodaran_country.tax_rate`` is NULL in production today and
    every company falls back to the default. Wiring a country corporate-tax
    dataset (or keying tax off ``industry_damodaran`` like the valuator) is a
    follow-up; this just removes the hardcoded constant and the plumbing waits
    on the data. A rate outside ``[0, 1)`` (e.g. a percentage stored as ``30``
    instead of ``0.30``) is rejected back to the default rather than producing a
    negative NOPAT.
    """
    if country is None:
        return DEFAULT_TAX_RATE
    row = conn.execute(
        "SELECT tax_rate FROM damodaran_country WHERE country = ? "
        "AND tax_rate IS NOT NULL ORDER BY year DESC LIMIT 1",
        [country],
    ).fetchone()
    if row is None or row[0] is None:
        return DEFAULT_TAX_RATE
    tax_rate = float(row[0])
    if not 0.0 <= tax_rate < 1.0:
        return DEFAULT_TAX_RATE
    return tax_rate


# --------------------------------------------------------------------------- #
# Snapshot assembly                                                            #
# --------------------------------------------------------------------------- #


def _tuple(values: list[float | None]) -> tuple[float, ...]:
    """Drop ``None`` holes, preserving order (histories must stay contiguous)."""
    return tuple(float(v) for v in values if v is not None)


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator == 0.0:
        return None
    return numerator / denominator


def build_company_data(
    conn: duckdb.DuckDBPyConnection,
    company: _CompanyRow,
    annual: list[_AnnualRow],
    *,
    market_cap: float | None,
    close: float | None,
) -> CompanyData:
    """Assemble a pure :class:`CompanyData` snapshot for one company (spec §5/§6).

    Derives the screener-relevant ratios (PE, P/BV, EV/EBITDA, ROE, ROIC, FCF
    yield) and the histories the gates / trap detectors read, from the latest
    annual row and the price feed. Missing inputs stay ``None`` / empty so each
    rule can decide how to treat the gap.
    """
    latest = annual[-1] if annual else None

    revenue_history = _tuple([r.revenue for r in annual])
    ocf_history = _tuple([r.operating_cashflow for r in annual])
    share_history = _tuple([r.shares_diluted for r in annual])
    op_margin_history: tuple[float, ...] = tuple(
        r.ebit / r.revenue
        for r in annual
        if r.ebit is not None and r.revenue is not None and r.revenue != 0.0
    )

    net_debt: float | None = None
    pe = pbv = ev_ebitda = roe = roic = fcf_yield = None
    ebit = ebitda = interest_expense = goodwill = total_assets = None
    net_income = operating_cashflow = None
    if latest is not None:
        ebit = latest.ebit
        ebitda = latest.ebitda
        interest_expense = latest.interest_expense
        goodwill = latest.goodwill
        total_assets = latest.total_assets
        net_income = latest.net_income
        operating_cashflow = latest.operating_cashflow
        if latest.total_debt is not None or latest.cash is not None:
            net_debt = (latest.total_debt or 0.0) - (latest.cash or 0.0)
        roe = _ratio(latest.net_income, latest.total_equity)
        if (
            close is not None
            and latest.net_income is not None
            and latest.shares_diluted is not None
            and latest.shares_diluted != 0.0
        ):
            eps = latest.net_income / latest.shares_diluted
            pe = close / eps if eps > 0.0 else None
        if (
            close is not None
            and latest.total_equity is not None
            and latest.total_equity != 0.0
            and latest.shares_diluted is not None
            and latest.shares_diluted != 0.0
        ):
            book_per_share = latest.total_equity / latest.shares_diluted
            pbv = close / book_per_share if book_per_share > 0.0 else None
        if (
            market_cap is not None
            and net_debt is not None
            and latest.ebitda is not None
            and latest.ebitda != 0.0
        ):
            ev_ebitda = (market_cap + net_debt) / latest.ebitda
        # ROIC ≈ NOPAT / invested capital, with invested capital ≈ debt + equity.
        # NOPAT applies the company's country tax rate (not a flat US 21%).
        invested = None
        if latest.total_debt is not None or latest.total_equity is not None:
            invested = (latest.total_debt or 0.0) + (latest.total_equity or 0.0)
        if latest.ebit is not None and invested is not None and invested != 0.0:
            tax_rate = _resolve_tax_rate(conn, company.country)
            roic = (latest.ebit * (1.0 - tax_rate)) / invested
        fcf = latest.free_cashflow
        if fcf is not None and market_cap is not None and market_cap != 0.0:
            fcf_yield = fcf / market_cap

    industry = company.industry_damodaran or company.industry
    return CompanyData(
        ticker=company.ticker,
        name=company.name,
        industry=industry,
        region=_resolve_region(conn, company.country),
        market_cap=market_cap,
        years_of_financials=len(annual),
        net_debt=net_debt,
        ebitda=ebitda,
        ebit=ebit,
        interest_expense=interest_expense,
        goodwill=goodwill,
        total_assets=total_assets,
        operating_cashflow_history=ocf_history,
        pe=pe,
        pbv=pbv,
        ev_ebitda=ev_ebitda,
        roe=roe,
        roic=roic,
        fcf_yield=fcf_yield,
        revenue_history=revenue_history,
        operating_margin_history=op_margin_history,
        share_count_history=share_history,
        net_income=net_income,
        operating_cashflow=operating_cashflow,
    )


# --------------------------------------------------------------------------- #
# Layer evaluation                                                             #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _Verdict:
    """Per-company outcome of the three layers, before ranking."""

    passed: bool
    passed_gates: tuple[str, ...]
    failed_gates: tuple[str, ...]
    value_metric: float
    quality_metric: float
    growth_metric: float


_EMPTY_BENCHMARKS = IndustryBenchmarks(industry="", region="", year=0)


def _quality_metric(company: CompanyData, benchmarks: IndustryBenchmarks) -> float:
    """ROIC-over-sector-WACC spread blended with ROE (spec §6.5, higher better)."""
    spread = 0.0
    if company.roic is not None and benchmarks.wacc is not None:
        spread = company.roic - benchmarks.wacc
    roe = company.roe if company.roe is not None else 0.0
    return spread + roe


def _growth_metric(company: CompanyData) -> float:
    """Revenue CAGR over the available history (spec §6.5, higher better)."""
    return cagr(company.revenue_history)


def evaluate_company(
    company: CompanyData,
    benchmarks: IndustryBenchmarks | None,
    *,
    quality_gates: list[Rule],
    value_indicators: list[Rule],
    trap_detection: list[Rule],
) -> _Verdict:
    """Run the three eliminatory layers for one company (spec §6.2-§6.4).

    A company passes only when every quality gate passes, at least one value
    indicator passes, and every trap detector passes. Value indicators that skip
    for lack of data neither pass nor fail. The strongest value-indicator score
    becomes the candidate's value metric for ranking.
    """
    bench = benchmarks if benchmarks is not None else _EMPTY_BENCHMARKS
    passed_gates: list[str] = []
    failed_gates: list[str] = []
    passed = True

    for gate in quality_gates:
        result = gate.evaluate(company, bench)
        if result.passed:
            passed_gates.append(gate.name)
        else:
            failed_gates.append(gate.name)
            passed = False

    value_metric = 0.0
    any_value = False
    for indicator in value_indicators:
        result = indicator.evaluate(company, bench)
        if result.passed:
            any_value = True
            passed_gates.append(indicator.name)
            value_metric = max(value_metric, result.score)
        elif not result.skipped:
            failed_gates.append(indicator.name)
    if not any_value:
        passed = False

    for detector in trap_detection:
        result = detector.evaluate(company, bench)
        if result.passed or result.skipped:
            if result.passed:
                passed_gates.append(detector.name)
        else:
            failed_gates.append(detector.name)
            passed = False

    return _Verdict(
        passed=passed,
        passed_gates=tuple(passed_gates),
        failed_gates=tuple(failed_gates),
        value_metric=value_metric,
        quality_metric=_quality_metric(company, bench),
        growth_metric=_growth_metric(company),
    )


# --------------------------------------------------------------------------- #
# Public entry point                                                           #
# --------------------------------------------------------------------------- #


@dataclass
class _Pending:
    """A surviving company awaiting ranking (carries report-facing fields)."""

    company: CompanyData
    verdict: _Verdict = field(repr=False)


def run_screen(
    conn: duckdb.DuckDBPyConnection,
    config: ScreenerConfig,
    *,
    top: int | None = None,
    valuator: Valuator | None = _dcf_margin_of_safety,
) -> ScreenResult:
    """Screen the DB universe with ``config`` and return the ranked shortlist.

    Two passes (spec §6.5, M4.7). The **first pass** iterates every company in
    ``companies``, assembles its snapshot, runs the three eliminatory layers, and
    ranks the survivors with the §6.5 percentile blend carrying the *placeholder*
    margin of safety; ``top`` truncates that ranking to the best N. The **second
    pass** runs ``valuator`` on each of those top-N candidates to obtain the real
    DCF margin of safety (``intrinsic_value / price``) and **re-ranks** them with
    it — the moment Capa B (the screener) integrates with Capa C (the valuator).

    Args:
        conn: Open DuckDB connection with the schema applied.
        config: The loaded screener preset (layers + ranking weights).
        top: Cap on the shortlist; the valuator runs on at most this many
            candidates (``None`` keeps and values every survivor).
        valuator: The seam that yields each candidate's real margin of safety;
            defaults to the DCF pipeline. ``None`` skips valuation entirely and
            keeps the first-pass placeholder ranking (e.g. for a fast dry run). A
            candidate the valuator cannot value keeps the neutral placeholder.

    Returns:
        The re-ranked shortlist whose ``margin_of_safety`` reflects the real DCF
        ratio wherever the valuator could value the company.

    Pure in the project sense: accepts the connection, holds no global state, and
    only reads from the DB.
    """
    quality_gates = config.quality_gates.build()
    value_indicators = config.value_indicators.build()
    trap_detection = config.trap_detection.build()
    weights: RankingWeights = config.ranking.weights

    pending: list[_Pending] = []
    candidates: list[Candidate] = []
    screened = 0
    for row in _load_companies(conn):
        annual = _load_annual(conn, row.ticker)
        market_cap = _latest_market_cap(conn, row.ticker)
        close = _latest_close(conn, row.ticker)
        company = build_company_data(conn, row, annual, market_cap=market_cap, close=close)
        screened += 1
        region = company.region or DEFAULT_REGION
        benchmarks = load_industry_benchmarks(conn, industry=company.industry, region=region)
        verdict = evaluate_company(
            company,
            benchmarks,
            quality_gates=quality_gates,
            value_indicators=value_indicators,
            trap_detection=trap_detection,
        )
        if not verdict.passed:
            continue
        pending.append(_Pending(company=company, verdict=verdict))
        candidates.append(
            Candidate(
                ticker=company.ticker,
                value_metric=verdict.value_metric,
                quality_metric=verdict.quality_metric,
                growth_metric=verdict.growth_metric,
            )
        )

    # First pass: rank the FULL survivor universe so the value/quality/growth
    # percentiles mean "rank within the filtered universe", then truncate to the
    # shortlist the valuator runs on.
    first_pass = rank(candidates, weights)
    if top is not None:
        first_pass = first_pass[:top]

    # Second pass: value each shortlisted candidate and re-blend the composite
    # with the real MoS, keeping the full-universe percentiles (rescore does not
    # re-rank the sub-scores over the truncated subset).
    margins: dict[str, float] = {}
    for scored_candidate in first_pass:
        mos = valuator(conn, scored_candidate.ticker) if valuator is not None else None
        margins[scored_candidate.ticker] = mos if mos is not None else PLACEHOLDER_MARGIN_OF_SAFETY

    scored = rescore_with_margins(first_pass, margins, weights)
    by_ticker = {p.company.ticker: p for p in pending}
    shortlist = _project(scored, by_ticker)
    return ScreenResult(preset=config.name, shortlist=shortlist, screened=screened)


def _project(
    scored: list[ScoredCandidate], by_ticker: dict[str, _Pending]
) -> tuple[ScreenedCompany, ...]:
    """Join ranked sub-scores back onto each company's report-facing fields."""
    out: list[ScreenedCompany] = []
    for s in scored:
        pending = by_ticker[s.ticker]
        c = pending.company
        out.append(
            ScreenedCompany(
                ticker=c.ticker,
                name=c.name,
                sector=c.industry,
                region=c.region or DEFAULT_REGION,
                market_cap=c.market_cap,
                pe=c.pe,
                ev_ebitda=c.ev_ebitda,
                pbv=c.pbv,
                roe=c.roe,
                roic=c.roic,
                fcf_yield=c.fcf_yield,
                passed=True,
                passed_gates=pending.verdict.passed_gates,
                failed_gates=pending.verdict.failed_gates,
                score=s.score,
                value_score=s.value_score,
                quality_score=s.quality_score,
                growth_score=s.growth_score,
                margin_of_safety=s.margin_of_safety,
            )
        )
    return tuple(out)
