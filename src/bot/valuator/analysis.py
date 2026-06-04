"""End-to-end analysis pipeline (spec §7.7, issue #16).

This is the one impure-at-the-edges orchestrator that turns a ticker into a full
Damodaran-style analysis: it reads a company's data from the DB, resolves the six
critical assumptions (with provenance), runs the two-stage DCF, the sensitivity
views, and the narrative flags, and packages a :class:`Analysis` carrying
everything the §7.7 report renders. The arithmetic itself stays in the pure
valuator modules (``dcf``/``sensitivity``/``narrative_flags``/``story_types``);
this module only gathers inputs and wires them together.

It is a pure function of ``(ticker, conn, override_path)`` in the project sense:
it accepts the connection and never holds global state. It only reads from the
DB — writing the rendered report to disk is the CLI's job, not the pipeline's.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import duckdb

from bot.utils.finance import cagr
from bot.valuator.assumptions import Assumptions as SourcedAssumptions
from bot.valuator.assumptions import resolve_assumptions
from bot.valuator.dcf import DCFResult, Financials, dcf
from bot.valuator.narrative_flags import NarrativeContext, NarrativeFlag, narrative_flags
from bot.valuator.sensitivity import Grid2D, SensitivityAxis, TornadoEntry, grid_2d, tornado
from bot.valuator.story_types import (
    ClassificationFinancials,
    SectorContext,
    StoryType,
    classify,
)

#: Default nominal-GDP growth ceiling when a country row is missing (matches the
#: assumptions module default; roughly long-run US nominal GDP).
_DEFAULT_GDP_NOMINAL = 0.04


@dataclass(frozen=True)
class SanityCheck:
    """Implied valuation multiples vs the company's sector (spec §7.7).

    Attributes:
        implied_pe: Current price divided by trailing EPS (net income / shares),
            or ``None`` when EPS is non-positive or unavailable.
        sector_pe: Damodaran sector-median price/earnings multiple.
        implied_ev_sales: Enterprise value / trailing revenue from the DCF, or
            ``None`` when revenue is unavailable.
        sector_ev_sales: Damodaran sector-median EV/sales multiple.
    """

    implied_pe: float | None
    sector_pe: float | None
    implied_ev_sales: float | None
    sector_ev_sales: float | None


@dataclass(frozen=True)
class Analysis:
    """A complete §7.7 analysis of one company, ready to render.

    Every field the report needs is here so the renderer is a pure projection of
    this object — no DB access, no recomputation.

    Attributes:
        ticker / name / country / currency: Company identity.
        story_type: The story type that drove assumption resolution (manual
            override or auto-classifier verdict).
        story_reasons: Human-readable reasons the story type was assigned.
        assumptions: The six critical assumptions, each carrying its source.
        financials: The current-year DCF inputs (revenue, net debt, shares).
        dcf_result: The two-stage DCF output (intrinsic value + projections).
        tornado: Per-axis ±20% impacts, descending by impact (spec §7.4).
        grid: 5x5 margin-of-safety grid over the two widest tornado axes.
        narrative_flags: The five §7.5 consistency flags.
        sanity_check: Implied vs sector multiples (spec §7.7).
        current_price: Latest close in the listing currency (``None`` if absent).
        margin_of_safety: ``intrinsic_value / current_price`` (``None`` if no
            price). > 1 means potentially undervalued (CONTEXT.md).
        override_notes: Free-text notes from the manual override (spec §7.6).
    """

    ticker: str
    name: str
    country: str | None
    currency: str | None
    story_type: str | None
    story_reasons: tuple[str, ...]
    assumptions: SourcedAssumptions
    financials: Financials
    dcf_result: DCFResult
    tornado: tuple[TornadoEntry, ...]
    grid: Grid2D
    narrative_flags: tuple[NarrativeFlag, ...]
    sanity_check: SanityCheck
    current_price: float | None
    margin_of_safety: float | None
    override_notes: str | None


# --------------------------------------------------------------------------- #
# DB loading                                                                   #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _CompanyRow:
    name: str
    country: str | None
    currency: str | None
    industry_damodaran: str | None


@dataclass(frozen=True)
class _LatestFinancials:
    revenue: float | None
    ebit: float | None
    net_income: float | None
    interest_expense: float | None
    net_debt: float | None
    shares_diluted: float | None


def _load_company(conn: duckdb.DuckDBPyConnection, ticker: str) -> _CompanyRow:
    row = conn.execute(
        "SELECT name, country, currency, industry_damodaran "
        "FROM companies WHERE ticker = ?",
        [ticker],
    ).fetchone()
    if row is None:
        raise LookupError(f"company {ticker!r} not found in companies table")
    return _CompanyRow(
        name=row[0], country=row[1], currency=row[2], industry_damodaran=row[3]
    )


def _load_latest_financials(
    conn: duckdb.DuckDBPyConnection, ticker: str
) -> _LatestFinancials:
    row = conn.execute(
        "SELECT revenue, ebit, net_income, interest_expense, total_debt, cash, "
        "shares_diluted FROM financials_annual "
        "WHERE ticker = ? AND is_restated = FALSE "
        "ORDER BY fiscal_year DESC LIMIT 1",
        [ticker],
    ).fetchone()
    if row is None:
        raise LookupError(f"no financials_annual rows for {ticker!r}")
    revenue, ebit, net_income, interest_expense, total_debt, cash, shares = row
    net_debt = None
    if total_debt is not None or cash is not None:
        net_debt = (total_debt or 0.0) - (cash or 0.0)
    return _LatestFinancials(
        revenue=revenue,
        ebit=ebit,
        net_income=net_income,
        interest_expense=interest_expense,
        net_debt=net_debt,
        shares_diluted=shares,
    )


def _load_history(
    conn: duckdb.DuckDBPyConnection, ticker: str
) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    """Revenue, net-income and EBIT histories, oldest first, in one scan."""
    rows = conn.execute(
        "SELECT revenue, net_income, ebit FROM financials_annual "
        "WHERE ticker = ? AND is_restated = FALSE ORDER BY fiscal_year",
        [ticker],
    ).fetchall()
    revenues = tuple(float(r[0]) for r in rows if r[0] is not None)
    incomes = tuple(float(r[1]) for r in rows if r[1] is not None)
    ebits = tuple(float(r[2]) for r in rows if r[2] is not None)
    return revenues, incomes, ebits


def _load_latest_price(
    conn: duckdb.DuckDBPyConnection, ticker: str
) -> float | None:
    row = conn.execute(
        "SELECT close FROM prices_daily WHERE ticker = ? AND close IS NOT NULL "
        "ORDER BY date DESC LIMIT 1",
        [ticker],
    ).fetchone()
    return float(row[0]) if row is not None and row[0] is not None else None


@dataclass(frozen=True)
class _SectorMultiples:
    region: str | None
    pe: float | None
    ev_sales: float | None
    op_margin: float | None
    beta_levered: float | None
    erp: float | None


def _load_sector_multiples(
    conn: duckdb.DuckDBPyConnection, company: _CompanyRow
) -> _SectorMultiples:
    region: str | None = None
    erp: float | None = None
    if company.country is not None:
        country_row = conn.execute(
            "SELECT region, erp FROM damodaran_country WHERE country = ? "
            "ORDER BY year DESC LIMIT 1",
            [company.country],
        ).fetchone()
        if country_row is not None:
            region, erp = country_row[0], country_row[1]
    if company.industry_damodaran is None or region is None:
        return _SectorMultiples(
            region=region, pe=None, ev_sales=None, op_margin=None, beta_levered=None, erp=erp
        )
    sector_row = conn.execute(
        "SELECT pe, ev_sales, op_margin, beta_levered FROM damodaran_industry "
        "WHERE industry = ? AND region = ? ORDER BY year DESC LIMIT 1",
        [company.industry_damodaran, region],
    ).fetchone()
    if sector_row is None:
        return _SectorMultiples(
            region=region, pe=None, ev_sales=None, op_margin=None, beta_levered=None, erp=erp
        )
    return _SectorMultiples(
        region=region,
        pe=sector_row[0],
        ev_sales=sector_row[1],
        op_margin=sector_row[2],
        beta_levered=sector_row[3],
        erp=erp,
    )


# --------------------------------------------------------------------------- #
# Derived signals                                                              #
# --------------------------------------------------------------------------- #


def _story_reasons(
    story_type: StoryType,
    revenue_history: tuple[float, ...],
    age_years: int | None,
) -> tuple[str, ...]:
    """Human-readable explanation of the auto-assigned story type (spec §7.1)."""
    reasons: list[str] = []
    if len(revenue_history) >= 2 and revenue_history[0] > 0.0:
        periods = len(revenue_history) - 1
        rate = cagr(revenue_history)
        reasons.append(f"historical revenue CAGR {rate:.1%} over {periods} years")
    else:
        reasons.append("too little revenue history for a reliable growth signal")
    if age_years is not None:
        reasons.append(f"company age {age_years} years")
    reasons.append(f"classified as {story_type.value}")
    return tuple(reasons)


def _two_widest_axes(
    tornado_entries: tuple[TornadoEntry, ...],
) -> tuple[SensitivityAxis, SensitivityAxis]:
    """The two highest-impact axes for the 2-D grid (spec §7.4)."""
    if len(tornado_entries) >= 2:
        return tornado_entries[0].axis, tornado_entries[1].axis
    return SensitivityAxis.REVENUE_GROWTH, SensitivityAxis.OPERATING_MARGIN


def _operating_leverage(revenues: tuple[float, ...], ebits: tuple[float, ...]) -> float | None:
    """Rough operating leverage: %ΔEBIT / %ΔRevenue over the last two years."""
    if len(revenues) < 2 or len(ebits) < 2:
        return None
    rev_prev, rev_curr = revenues[-2], revenues[-1]
    ebit_prev, ebit_curr = ebits[-2], ebits[-1]
    if rev_prev == 0.0 or ebit_prev == 0.0:
        return None
    rev_change = (rev_curr - rev_prev) / rev_prev
    ebit_change = (ebit_curr - ebit_prev) / ebit_prev
    if rev_change == 0.0:
        return None
    return ebit_change / rev_change


def _sanity_check(
    current_price: float | None,
    net_income: float | None,
    shares: float | None,
    enterprise_value: float,
    revenue: float | None,
    sector: _SectorMultiples,
) -> SanityCheck:
    implied_pe: float | None = None
    if (
        current_price is not None
        and net_income is not None
        and net_income > 0.0
        and shares is not None
        and shares > 0.0
    ):
        eps = net_income / shares
        if eps > 0.0:
            implied_pe = current_price / eps
    implied_ev_sales: float | None = None
    if revenue is not None and revenue > 0.0:
        implied_ev_sales = enterprise_value / revenue
    return SanityCheck(
        implied_pe=implied_pe,
        sector_pe=sector.pe,
        implied_ev_sales=implied_ev_sales,
        sector_ev_sales=sector.ev_sales,
    )


# --------------------------------------------------------------------------- #
# Public entry point                                                           #
# --------------------------------------------------------------------------- #


def analyze(
    ticker: str,
    conn: duckdb.DuckDBPyConnection,
    override_path: Path | None = None,
    *,
    is_cyclical_sector: bool = False,
    age_years: int | None = None,
) -> Analysis:
    """Run the full §7.7 analysis pipeline for ``ticker``.

    Args:
        ticker: Company ticker; must exist in ``companies`` with at least one
            ``financials_annual`` row.
        conn: Open DuckDB connection with the schema applied.
        override_path: Optional ``config/assumptions/<TICKER>.yaml`` (spec §7.6).
        is_cyclical_sector: Whether the company's sector is structurally cyclical
            (feeds the story-type classifier's cyclical signal, spec §7.1).
        age_years: Company age in years, if known (a high-growth signal).

    Returns:
        An :class:`Analysis` carrying everything the §7.7 report renders.

    Raises:
        LookupError: If ``ticker`` is unknown or has no annual financials.
        ValueError: If the resolved assumptions are too incomplete to value the
            company (propagated from :meth:`Assumptions.to_dcf_assumptions` /
            :func:`bot.valuator.dcf.dcf`).
    """
    ticker = ticker.upper()
    company = _load_company(conn, ticker)
    latest = _load_latest_financials(conn, ticker)
    revenue_history, income_history, ebit_history = _load_history(conn, ticker)
    sector = _load_sector_multiples(conn, company)
    current_price = _load_latest_price(conn, ticker)

    # Story type: classify, then let a manual override win inside resolve.
    interest_coverage = None
    if latest.ebit is not None and latest.interest_expense:
        interest_coverage = latest.ebit / latest.interest_expense
    classification = ClassificationFinancials(
        revenue_history=revenue_history,
        earnings_history=income_history,
        age_years=age_years,
        interest_coverage=interest_coverage,
    )
    auto_story = classify(classification, SectorContext(is_cyclical=is_cyclical_sector))

    gdp_nominal = _DEFAULT_GDP_NOMINAL
    assumptions = resolve_assumptions(
        ticker,
        conn,
        override_path=override_path,
        gdp_nominal=gdp_nominal,
        auto_story_type=auto_story,
    )
    story_type = assumptions.story_type or auto_story.value

    if latest.revenue is None:
        raise ValueError(f"{ticker}: no revenue on the latest financials — cannot value")
    if latest.shares_diluted is None or latest.shares_diluted <= 0.0:
        raise ValueError(f"{ticker}: missing/non-positive diluted shares — cannot value")
    financials = Financials(
        revenue=latest.revenue,
        net_debt=latest.net_debt if latest.net_debt is not None else 0.0,
        shares_diluted=latest.shares_diluted,
    )

    dcf_assumptions = assumptions.to_dcf_assumptions()
    dcf_result = dcf(financials, dcf_assumptions)
    tornado_entries = tuple(tornado(financials, dcf_assumptions))
    axis_a, axis_b = _two_widest_axes(tornado_entries)
    grid = grid_2d(financials, dcf_assumptions, axis_a, axis_b)

    context = NarrativeContext(
        story_type=story_type,
        company_operating_margin=assumptions.operating_margin.value,
        sector_operating_margin=sector.op_margin,
        sector_beta=sector.beta_levered,
        operating_leverage=_operating_leverage(revenue_history, ebit_history),
        erp_weighted=sector.erp,
        erp_listing=sector.erp,
    )
    flags = narrative_flags(financials, dcf_assumptions, dcf_result, context)

    margin_of_safety = (
        dcf_result.intrinsic_value / current_price
        if current_price is not None and current_price > 0.0
        else None
    )
    sanity = _sanity_check(
        current_price=current_price,
        net_income=latest.net_income,
        shares=latest.shares_diluted,
        enterprise_value=dcf_result.enterprise_value,
        revenue=latest.revenue,
        sector=sector,
    )

    return Analysis(
        ticker=ticker,
        name=company.name,
        country=company.country,
        currency=company.currency,
        story_type=story_type,
        story_reasons=_story_reasons(auto_story, revenue_history, age_years),
        assumptions=assumptions,
        financials=financials,
        dcf_result=dcf_result,
        tornado=tornado_entries,
        grid=grid,
        narrative_flags=flags,
        sanity_check=sanity,
        current_price=current_price,
        margin_of_safety=margin_of_safety,
        override_notes=assumptions.notes,
    )
