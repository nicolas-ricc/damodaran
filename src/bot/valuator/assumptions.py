"""Resolve the six critical DCF assumptions with source tracking (spec §7.3).

A valuation is only as honest as its inputs, so every one of the six critical
assumptions from spec §7.3 carries its *provenance* — where the number came
from — alongside its value. The report (spec §7.7) shows that provenance for
each assumption so a human can see which figures are analyst-driven, which are
sector defaults, and which are pure rules.

Resolution order (highest-priority source wins, spec §7.3/§7.6)::

    1. Manual override    — config/assumptions/<TICKER>.yaml, if present
    2. Analyst consensus  — FMP (M2). There is no consensus feed, so revenue
                            growth starts at the company's own historical average
                            (HISTORICAL_AVERAGE) and fades to terminal growth over
                            ten years.
    3. Sector default     — medians from damodaran_industry; the country's tax
                            rate from damodaran_country is sourced
                            COUNTRY_DEFAULT_DAMODARAN.
    4. Rule-based         — e.g. terminal_growth = min(rfr_ccy, gdp_ccy), where
                            both come from the company's valuation currency in
                            ``config/currencies.yaml`` (#109), or a distressed
                            company's probability of bankruptcy from its interest
                            coverage via ``config/default_spreads.yaml`` (#213).

The valuation currency is the currency of the company's latest non-restated
``financials_annual`` row. A currency missing from the table (or a NULL one)
leaves the GDP-anchored assumptions ``UNRESOLVED``; there is no USD fallback.

This module is a pure function of ``(ticker, conn, override_path)`` plus a
currency table and a default-spread table: it reads, it does not write, and it
holds no global state.

The DCF's WACC is *computed* from its components (``cost_of_equity``,
``pretax_cost_of_debt``, the weights and the tax rate) by ``dcf._wacc``; there is
deliberately no resolved ``wacc`` assumption. Damodaran publishes a sector WACC and
an earlier version of this module carried it, but the DCF ignored it, so the report
printed two disagreeing numbers. The sector WACC still has one legitimate consumer:
the §6.4 ROIC-vs-WACC trap detector, which reads it from ``damodaran_industry``
directly.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, fields, replace
from datetime import date
from enum import StrEnum
from pathlib import Path
from statistics import fmean
from typing import Any, TypeVar

import duckdb
import yaml

from bot.reference.countries import damodaran_country_name
from bot.reference.currencies import (
    CurrencyRates,
    CurrencyTable,
    load_currency_table,
    normalize_currency,
)
from bot.reference.default_spreads import DefaultSpreadTable, load_default_spreads
from bot.reference.regions import dataset_region
from bot.utils.finance import cagr
from bot.utils.logging import get_logger
from bot.valuator.dcf import Assumptions as DCFAssumptions
from bot.valuator.hypergrowth import (
    STORY_TYPE,
    StoryInputs,
    apply_story,
    is_finite_number,
    story_from_override,
)
from bot.valuator.story_types import StoryType

log = get_logger(__name__)

T = TypeVar("T")

# Length of the explicit forecast horizon when a path is synthesised from a
# single scalar (sector/rule-based growth or margin), and the span over which
# revenue growth fades to terminal growth. Ten years gives a fast grower time to
# converge to the steady state instead of capitalising its growth into the terminal
# value; a richer year-by-year path comes from the analyst-consensus / story-type
# layer (M4.3+), which overrides this default.
_HORIZON = 10

# A cyclical company's "cycle average" margin is only meaningful once we hold at
# least one full business cycle of annual margins; fewer years fall back to the
# sector median rather than averaging a half-cycle.
_MIN_CYCLE_YEARS = 4

# Rule-based marginal tax rate used when neither a manual override nor a
# Damodaran sector/country tax rate is available. A neutral mid-rate so the DCF
# still produces a NOPAT rather than collapsing.
_DEFAULT_TAX_RATE = 0.25

# How far an explicitly overridden equity_weight + debt_weight may drift from 1.0
# before the pair is rejected. Only float representation error is tolerated: the
# two weights partition invested capital, so anything else is a user error.
_WEIGHT_PARTITION_TOLERANCE = 1e-9

# Every value StoryType can take, for validating a resolved story-type label
# (manual override or classifier verdict) before branching on it.
_STORY_TYPE_VALUES = {s.value for s in StoryType}


class AssumptionSource(StrEnum):
    """Provenance of a resolved assumption (spec §7.3)."""

    MANUAL = "manual"
    SECTOR_DEFAULT_DAMODARAN = "sector_default_damodaran"
    #: The sector median came from a *different* Damodaran dataset region than the
    #: company's own, because the mapped region has no ingested rows. Disclosed so
    #: the report shows the substitution rather than passing it off as the
    #: company's own region.
    SECTOR_DEFAULT_DAMODARAN_CROSS_REGION = "sector_default_damodaran_cross_region"
    #: The value is the Damodaran country row's figure for the company's country
    #: (tax rate only), taken when the sector row carries no tax rate.
    COUNTRY_DEFAULT_DAMODARAN = "country_default_damodaran"
    RULE_BASED = "rule_based"
    HISTORICAL_AVERAGE = "historical_average"
    #: The value sails from the archetype's projection pattern (spec §7.1): a path
    #: derived from the company's and the sector's data, not a scalar copied
    #: verbatim. Emitted by the story-type-branched growth and margin resolvers.
    STORY_PATTERN = "story_pattern"
    #: The value was set by the story section of the override file.
    STORY = "story"
    #: No layer produced a value. The report shows the gap instead of a number,
    #: and must not attribute the gap to a source it never came from.
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class Sourced[T]:
    """A resolved value together with the source it came from (spec §7.3).

    ``value`` is ``None`` when the assumption could not be resolved from any
    layer (e.g. the company's industry has no Damodaran row); the report shows
    the gap rather than inventing a number.
    """

    value: T
    source: AssumptionSource


@dataclass(frozen=True)
class BankruptcyDerivation:
    """How a distressed company's probability of bankruptcy was derived (#213).

    Attributes:
        interest_coverage: The coverage ratio the chain started from (``None``
            when it is unknown).
        rating: The rating the coverage maps to (``None`` when none was found).
        horizon_years: Horizon of the table's cumulative default probability
            (``None`` when the table was not read or is empty).
        probability: The probability the chain produced (0.0 on every fallback).
        reason: One line for the report: the chain, or why ``p`` stays 0.
    """

    interest_coverage: float | None
    rating: str | None
    horizon_years: int | None
    probability: float
    reason: str


@dataclass(frozen=True)
class Assumptions:
    """The six critical DCF assumptions, each carrying its provenance (§7.3).

    Attributes:
        revenue_growth: Year-by-year revenue-growth path (years 1..N).
        operating_margin: Year-by-year operating-margin path (years 1..N). Flat
            across the horizon for most archetypes, but a high-growth story ramps
            it, a cyclical story flattens it to the cycle average, a
            mature-decline story keeps the company's own latest margin
            (spec §7.1).
        sales_to_capital: Incremental sales per unit of reinvested capital.
        terminal_growth: Perpetual growth ``g`` past the horizon.
        probability_of_bankruptcy: Probability the firm fails (0 outside
            distressed stories). A distressed company's comes from its interest
            coverage via the default-spread table unless the override sets it.
        distress_value_per_share: Per-share value recovered in bankruptcy,
            paired with ``probability_of_bankruptcy`` to blend a going-concern
            and liquidation value (0 outside distressed stories). Never
            derived automatically, so it comes from a manual override or
            stays 0.0.
        cost_of_equity / pretax_cost_of_debt / equity_weight / debt_weight:
            The WACC components, kept so a downstream DCF can rebuild WACC from
            its parts and report the weights actually used.
        story_type: Optional Damodaran story type, sourced from a manual
            override (auto-assignment lives in story_types.py, M4.3).
        notes: Free-text override notes for the report's "manual overrides"
            section (spec §7.6).
        wacc_path: Per-year WACC path of a hypergrowth story (``None`` outside it).
        tax_rate_path: Per-year tax-rate path of a hypergrowth story (``None``
            outside it).
        terminal_roic: Terminal return on invested capital of a hypergrowth
            story (``None`` when the story gives none).
        distress_proceeds_pct: Share of value recovered on failure in a
            hypergrowth story (``None`` outside it).
        fixed_commitments: Present value of fixed commitments deducted from
            equity, from a hypergrowth story (``None`` outside it).
        extra_cash: Cash added to equity value, from a hypergrowth story
            (``None`` outside it).
        governance_discount: Fractional haircut on equity value for governance
            risk, from a hypergrowth story (``None`` outside it).
        story: The validated hypergrowth story behind the story fields
            (``None`` outside it).
        bankruptcy_derivation: The coverage → rating → probability chain behind
            ``probability_of_bankruptcy`` (``None`` unless the chain ran, i.e.
            a distressed story without a manual probability).
    """

    revenue_growth: Sourced[tuple[float, ...] | None]
    operating_margin: Sourced[tuple[float, ...] | None]
    sales_to_capital: Sourced[float | None]
    terminal_growth: Sourced[float | None]
    probability_of_bankruptcy: Sourced[float]
    distress_value_per_share: Sourced[float]
    cost_of_equity: Sourced[float | None]
    pretax_cost_of_debt: Sourced[float | None]
    equity_weight: Sourced[float | None]
    debt_weight: Sourced[float | None]
    tax_rate: Sourced[float | None]
    story_type: str | None = None
    notes: str | None = None
    wacc_path: Sourced[tuple[float, ...]] | None = None
    tax_rate_path: Sourced[tuple[float, ...]] | None = None
    terminal_roic: Sourced[float] | None = None
    distress_proceeds_pct: Sourced[float] | None = None
    fixed_commitments: Sourced[float] | None = None
    extra_cash: Sourced[float] | None = None
    governance_discount: Sourced[float] | None = None
    story: StoryInputs | None = None
    scenarios: Mapping[str, StoryInputs] | None = None
    bankruptcy_derivation: BankruptcyDerivation | None = None

    def to_dcf_assumptions(self) -> DCFAssumptions:
        """Project the resolved bundle onto the pure :class:`dcf.Assumptions`.

        Raises:
            ValueError: If a required assumption is still unresolved (``None``),
                so the caller cannot silently feed a half-built model into the
                DCF.
        """
        # terminal_growth first: an uncovered currency leaves it (and often the
        # no-history revenue path) unresolved, and it names the actual cause.
        terminal_growth = _require(self.terminal_growth, "terminal_growth")
        growth = _require(self.revenue_growth, "revenue_growth")
        margin_path = _require(self.operating_margin, "operating_margin")
        if len(margin_path) < len(growth):
            margin_path = margin_path + (margin_path[-1],) * (len(growth) - len(margin_path))
        return DCFAssumptions(
            revenue_growth=growth,
            operating_margin=margin_path[: len(growth)],
            tax_rate=_require(self.tax_rate, "tax_rate"),
            sales_to_capital=_require(self.sales_to_capital, "sales_to_capital"),
            terminal_growth=terminal_growth,
            cost_of_equity=_require(self.cost_of_equity, "cost_of_equity"),
            pretax_cost_of_debt=_require(self.pretax_cost_of_debt, "pretax_cost_of_debt"),
            equity_weight=_require(self.equity_weight, "equity_weight"),
            debt_weight=_require(self.debt_weight, "debt_weight"),
            probability_of_bankruptcy=self.probability_of_bankruptcy.value,
            distress_value_per_share=self.distress_value_per_share.value,
            wacc_path=None if self.wacc_path is None else self.wacc_path.value,
            tax_rate_path=None if self.tax_rate_path is None else self.tax_rate_path.value,
            terminal_roic=None if self.terminal_roic is None else self.terminal_roic.value,
            distress_proceeds_pct=(
                None if self.distress_proceeds_pct is None else self.distress_proceeds_pct.value
            ),
        )


def _require[T](sourced: Sourced[T | None], name: str) -> T:
    if sourced.value is None:
        raise ValueError(f"assumption {name!r} is unresolved (no value from any source)")
    return sourced.value


# --------------------------------------------------------------------------- #
# DB lookups                                                                   #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _Company:
    country: str | None
    industry_damodaran: str | None


@dataclass(frozen=True)
class _SectorRow:
    wacc: float | None
    cost_of_equity: float | None
    cost_of_debt: float | None
    op_margin: float | None
    sales_to_capital: float | None
    tax_rate: float | None
    debt_to_equity: float | None


#: The ``damodaran_industry`` columns behind :class:`_SectorRow`, in field order,
#: so every query can build the row positionally without the SELECT drifting
#: from the dataclass.
_SECTOR_COLUMNS = ", ".join(f.name for f in fields(_SectorRow))


@dataclass(frozen=True)
class _SectorDefaults:
    """The sector row a company's defaults come from, plus where it came from.

    The row and the cross-region flag are one fact, not two: every value drawn
    from ``row`` carries a provenance that depends on ``cross_region``, so the
    label is computed here rather than re-derived at each resolver from a
    boolean threaded alongside the row through every signature.
    """

    row: _SectorRow | None
    cross_region: bool = False

    @property
    def source(self) -> AssumptionSource:
        """The provenance label a value drawn from this row carries."""
        if self.cross_region:
            return AssumptionSource.SECTOR_DEFAULT_DAMODARAN_CROSS_REGION
        return AssumptionSource.SECTOR_DEFAULT_DAMODARAN


@dataclass(frozen=True)
class _CountryRow:
    region: str | None
    erp: float | None
    tax_rate: float | None


@dataclass(frozen=True)
class AssumptionInputs:
    """Pre-loaded DB rows :func:`resolve_assumptions` needs for one company.

    Threading a pre-built bundle into :func:`resolve_assumptions` lets a caller
    that already holds these rows (e.g. the screener's batched second pass) avoid
    re-issuing the per-ticker ``companies`` / ``damodaran_country`` /
    ``damodaran_industry`` / ``financials_annual`` reads — the deferred half of
    the F7 N+1 fix (#53). Build one with :func:`load_assumption_inputs`.

    Attributes:
        company: The ``companies`` row (country + Damodaran industry).
        country: The latest ``damodaran_country`` row, or ``None``.
        sector: The latest ``damodaran_industry`` row for the company's
            industry/region, or ``None``.
        historical_growth_path: The flat revenue-growth path at the historical
            revenue CAGR, or ``None`` when that CAGR is undefined.
        sector_is_cross_region: Whether ``sector`` came from a different dataset
            region than the company's own (see
            :func:`_load_sector_with_fallback`). Every assumption drawn from that
            row is then labelled
            :attr:`AssumptionSource.SECTOR_DEFAULT_DAMODARAN_CROSS_REGION`.
        company_operating_margin: The company's own most-recent EBIT / revenue
            ratio, used as the starting point of the high-growth margin ramp
            and as a mature-decline story's flat margin (spec §7.1). ``None``
            when there is no usable financials history.
        operating_margin_history: The company's own EBIT / revenue ratio for
            every year of financials history, used to average a cyclical
            story's own cycle (spec §7.1). Empty when there is no history.
        valuation_currency: The normalised currency of the latest non-restated
            ``financials_annual`` row, or ``None`` when there is none.
        currency_rates: That currency's risk-free rate and nominal-GDP growth
            from the currency table, or ``None`` when it is uncovered.
        latest_revenue: Revenue of the latest non-restated ``financials_annual``
            row, the base of a hypergrowth story's revenue path. ``None`` when
            there is no such row or its revenue is NULL.
    """

    company: _Company
    country: _CountryRow | None
    sector: _SectorRow | None
    historical_growth_path: tuple[float, ...] | None
    sector_is_cross_region: bool = False
    company_operating_margin: float | None = None
    operating_margin_history: tuple[float, ...] = ()
    valuation_currency: str | None = None
    currency_rates: CurrencyRates | None = None
    latest_revenue: float | None = None


def _currency_rates(
    currency: str | None, table: CurrencyTable
) -> tuple[str | None, CurrencyRates | None]:
    """Normalise a raw ``financials_annual.currency`` and look it up in ``table``."""
    code = normalize_currency(currency)
    return code, (table.get(code) if code is not None else None)


def _warn_uncovered(currency: str | None, warned: set[str | None] | None) -> None:
    """Log ``currency`` as uncovered unless the run-scoped ``warned`` set has it."""
    if warned is not None:
        if currency in warned:
            return
        warned.add(currency)
    log.warning("assumptions.currency_uncovered", currency=currency)


def load_assumption_inputs(
    conn: duckdb.DuckDBPyConnection,
    ticker: str,
    *,
    currencies: CurrencyTable | None = None,
    warned: set[str | None] | None = None,
) -> AssumptionInputs:
    """Load every DB row :func:`resolve_assumptions` needs for ``ticker``.

    Pure in the project sense (accepts the connection, reads only). The result
    can be reused across calls so the per-ticker reads happen exactly once.

    ``currencies`` is the table of per-currency rates; ``None`` loads the default
    file. An uncovered valuation currency is logged once as
    ``assumptions.currency_uncovered``; pass one ``warned`` set across calls to
    log each currency once per run (``None`` warns on every call).

    Raises:
        LookupError: If ``ticker`` is unknown.
    """
    table = currencies if currencies is not None else load_currency_table()
    company = _load_company(conn, ticker)
    country = _load_country(conn, company.country)
    region = dataset_region(company.country, country.region if country is not None else None)
    sector, cross_region = _load_sector_with_fallback(conn, company.industry_damodaran, region)
    historical_growth_path = _historical_growth_path(conn, ticker)
    margins = _operating_margin_history(conn, ticker)
    latest = conn.execute(
        "SELECT currency, revenue FROM financials_annual "
        "WHERE ticker = ? AND is_restated = FALSE ORDER BY fiscal_year DESC LIMIT 1",
        [ticker],
    ).fetchone()
    valuation_currency, rates = _currency_rates(latest[0] if latest else None, table)
    if rates is None:
        _warn_uncovered(valuation_currency, warned)
    return AssumptionInputs(
        company=company,
        country=country,
        sector=sector,
        historical_growth_path=historical_growth_path,
        sector_is_cross_region=cross_region,
        company_operating_margin=margins[-1] if margins else None,
        operating_margin_history=margins,
        valuation_currency=valuation_currency,
        currency_rates=rates,
        latest_revenue=float(latest[1]) if latest and latest[1] is not None else None,
    )


def bulk_load_assumption_inputs(
    conn: duckdb.DuckDBPyConnection,
    tickers: Iterable[str],
    *,
    currencies: CurrencyTable | None = None,
    warned: set[str | None] | None = None,
) -> dict[str, AssumptionInputs]:
    """Load :func:`load_assumption_inputs` for many tickers in four queries.

    Returns exactly what the per-ticker loader returns for each ticker, keyed by
    upper-cased ticker. Tickers absent from ``companies`` are omitted rather than
    raising, so a caller can pass a whole shortlist. Each distinct uncovered
    valuation currency is logged once, not once per company (and once per run
    when a shared ``warned`` set is passed).
    """
    table = currencies if currencies is not None else load_currency_table()
    wanted = sorted({t.upper() for t in tickers})
    if not wanted:
        return {}
    companies = {
        t: _Company(country=c, industry_damodaran=i)
        for t, c, i in conn.execute(
            "SELECT ticker, country, industry_damodaran FROM companies "
            "WHERE ticker IN (SELECT unnest(?::VARCHAR[]))",
            [wanted],
        ).fetchall()
    }
    # companies.country is ISO alpha-2; damodaran_country is keyed by Damodaran name.
    names = {
        code: damodaran_country_name(code)
        for code in {c.country for c in companies.values() if c.country is not None}
    }
    countries = sorted({n for n in names.values() if n is not None})
    country_rows = {
        r[0]: _CountryRow(region=r[1], erp=r[2], tax_rate=r[3])
        for r in conn.execute(
            "SELECT country, region, erp, tax_rate FROM damodaran_country "
            "WHERE country IN (SELECT unnest(?::VARCHAR[])) "
            "QUALIFY row_number() OVER (PARTITION BY country ORDER BY year DESC) = 1",
            [countries],
        ).fetchall()
    }
    industries = sorted(
        {c.industry_damodaran for c in companies.values() if c.industry_damodaran is not None}
    )
    # Rows arrive latest-year first, so the first seen per key is the latest one.
    exact: dict[tuple[str, str], _SectorRow] = {}
    fallback: dict[str, tuple[_SectorRow, str]] = {}
    for industry, region, *values in conn.execute(
        f"SELECT industry, region, {_SECTOR_COLUMNS} FROM damodaran_industry "
        "WHERE industry IN (SELECT unnest(?::VARCHAR[])) "
        "ORDER BY industry, year DESC, region",
        [industries],
    ).fetchall():
        row = _SectorRow(*values)
        exact.setdefault((industry, region), row)
        fallback.setdefault(industry, (row, region))
    history: dict[str, list[tuple[Any, Any]]] = {}
    latest_currency: dict[str, str | None] = {}
    latest_revenue: dict[str, float | None] = {}
    # Oldest first, so the last row seen per ticker is its latest non-restated year.
    for ticker, revenue, ebit, currency in conn.execute(
        "SELECT ticker, revenue, ebit, currency FROM financials_annual "
        "WHERE ticker IN (SELECT unnest(?::VARCHAR[])) AND is_restated = FALSE "
        "ORDER BY ticker, fiscal_year",
        [wanted],
    ).fetchall():
        history.setdefault(ticker, []).append((revenue, ebit))
        latest_currency[ticker] = currency
        latest_revenue[ticker] = float(revenue) if revenue is not None else None

    result: dict[str, AssumptionInputs] = {}
    uncovered: set[str | None] = set()
    for ticker, company in companies.items():
        name = names.get(company.country) if company.country is not None else None
        country = country_rows.get(name) if name is not None else None
        region = dataset_region(company.country, country.region if country is not None else None)
        industry = company.industry_damodaran
        sector, cross_region = _pick_sector(
            industry,
            region,
            exact.get((industry, region)) if industry is not None else None,
            fallback.get(industry) if industry is not None else None,
        )
        rows = history.get(ticker, [])
        margins = _margins_from_rows((e, r) for r, e in rows)
        valuation_currency, rates = _currency_rates(latest_currency.get(ticker), table)
        if rates is None:
            uncovered.add(valuation_currency)
        result[ticker] = AssumptionInputs(
            company=company,
            country=country,
            sector=sector,
            historical_growth_path=_growth_path_from_revenues(
                [float(r) for r, _ in rows if r is not None]
            ),
            sector_is_cross_region=cross_region,
            company_operating_margin=margins[-1] if margins else None,
            operating_margin_history=margins,
            valuation_currency=valuation_currency,
            currency_rates=rates,
            latest_revenue=latest_revenue.get(ticker),
        )
    for currency in sorted(uncovered, key=lambda c: c or ""):
        _warn_uncovered(currency, warned)
    return result


def _margins_from_rows(rows: Iterable[tuple[Any, Any]]) -> tuple[float, ...]:
    """EBIT / revenue per year; ``rows`` are ``(ebit, revenue)`` pairs, oldest first."""
    return tuple(
        float(e) / float(r) for e, r in rows if e is not None and r is not None and r != 0.0
    )


def _operating_margin_history(
    conn: duckdb.DuckDBPyConnection, ticker: str
) -> tuple[float, ...]:
    """The company's own EBIT / revenue ratio for every year of history.

    Feeds the high-growth margin ramp's starting point and the mature-decline
    flat margin (both the most recent year), and the cyclical margin's cycle
    average (spec §7.1).
    """
    rows = conn.execute(
        "SELECT ebit, revenue FROM financials_annual "
        "WHERE ticker = ? AND is_restated = FALSE ORDER BY fiscal_year",
        [ticker],
    ).fetchall()
    return _margins_from_rows(rows)


def _load_company(conn: duckdb.DuckDBPyConnection, ticker: str) -> _Company:
    row = conn.execute(
        "SELECT country, industry_damodaran FROM companies WHERE ticker = ?",
        [ticker],
    ).fetchone()
    if row is None:
        raise LookupError(f"company {ticker!r} not found in companies table")
    return _Company(country=row[0], industry_damodaran=row[1])


def _load_country(conn: duckdb.DuckDBPyConnection, country: str | None) -> _CountryRow | None:
    name = damodaran_country_name(country)
    if name is None:
        return None
    row = conn.execute(
        "SELECT region, erp, tax_rate FROM damodaran_country "
        "WHERE country = ? ORDER BY year DESC LIMIT 1",
        [name],
    ).fetchone()
    if row is None:
        return None
    return _CountryRow(region=row[0], erp=row[1], tax_rate=row[2])


def _load_sector(
    conn: duckdb.DuckDBPyConnection, industry: str | None, region: str | None
) -> _SectorRow | None:
    if industry is None or region is None:
        return None
    row = conn.execute(
        f"SELECT {_SECTOR_COLUMNS} FROM damodaran_industry "
        "WHERE industry = ? AND region = ? ORDER BY year DESC LIMIT 1",
        [industry, region],
    ).fetchone()
    if row is None:
        return None
    return _SectorRow(*row)


def _load_sector_with_fallback(
    conn: duckdb.DuckDBPyConnection, industry: str | None, region: str
) -> tuple[_SectorRow | None, bool]:
    """Load the sector row, substituting another region when the mapped one is absent.

    Returns ``(row, cross_region)``. Only the US dataset is ingested today, so a
    non-US company's mapped region has no rows; rather than resolving nothing, the
    most recent row for that industry in *any* region is used and the caller labels
    every assumption drawn from it ``sector_default_damodaran_cross_region`` so the
    report shows the substitution instead of hiding it.
    """
    exact = _load_sector(conn, industry, region)
    fallback: tuple[_SectorRow, str] | None = None
    if exact is None and industry is not None:
        row = conn.execute(
            f"SELECT {_SECTOR_COLUMNS}, region FROM damodaran_industry "
            "WHERE industry = ? ORDER BY year DESC, region LIMIT 1",
            [industry],
        ).fetchone()
        if row is not None:
            fallback = (_SectorRow(*row[:-1]), row[-1])
    return _pick_sector(industry, region, exact, fallback)


def _pick_sector(
    industry: str | None,
    region: str,
    exact: _SectorRow | None,
    fallback: tuple[_SectorRow, str] | None,
) -> tuple[_SectorRow | None, bool]:
    """Exact-region row, else the latest row for ``industry`` in any region (logged).

    Shared by the per-ticker and bulk loaders so both apply the same precedence
    and emit the same substitution warning. ``fallback`` is the row plus the
    region it came from.
    """
    if industry is None:
        return None, False
    if exact is not None:
        return exact, False
    if fallback is None:
        return None, False
    row, used_region = fallback
    log.warning(
        "assumptions.sector.cross_region_substitution",
        industry=industry,
        requested_region=region,
        used_region=used_region,
    )
    return row, True


def _growth_path_from_revenues(revenues: Sequence[float]) -> tuple[float, ...] | None:
    """Flat ``_HORIZON``-year path at the revenue CAGR (``bot.utils.finance.cagr``).

    ``None`` when the CAGR is undefined (< 2 years, or a first or last revenue ≤ 0).
    """
    rate = cagr(revenues)
    if rate is None:
        return None
    return (rate,) * _HORIZON


def _historical_growth_path(
    conn: duckdb.DuckDBPyConnection, ticker: str
) -> tuple[float, ...] | None:
    """Historical revenue CAGR from financials_annual.

    Returns a flat path of ``_HORIZON`` years at the historical revenue CAGR
    (_resolve_revenue_growth takes it as the fade start), or ``None`` when it is
    undefined (< 2 years of revenue, or a non-positive first or last revenue).
    """
    rows = conn.execute(
        "SELECT revenue FROM financials_annual "
        "WHERE ticker = ? AND revenue IS NOT NULL AND is_restated = FALSE "
        "ORDER BY fiscal_year",
        [ticker],
    ).fetchall()
    return _growth_path_from_revenues([float(r[0]) for r in rows])


# --------------------------------------------------------------------------- #
# Manual override                                                             #
# --------------------------------------------------------------------------- #


#: Every key a `config/assumptions/<TICKER>.yaml` may carry (spec §7.6). Anything
#: else is a typo: silently ignoring it would let a user believe an override
#: applied.
_OVERRIDE_KEYS: frozenset[str] = frozenset(
    {
        "revenue_growth",
        "operating_margin",
        "sales_to_capital",
        "terminal_growth",
        "cost_of_equity",
        "pretax_cost_of_debt",
        "equity_weight",
        "debt_weight",
        "tax_rate",
        "probability_of_bankruptcy",
        "distress_value_per_share",
        "story_type",
        "notes",
        "founded_year",
        "story",
        "scenarios",
    }
)

#: Override keys that take a number or a per-year list of numbers.
_OVERRIDE_PATH_KEYS: frozenset[str] = frozenset({"revenue_growth", "operating_margin"})


@dataclass(frozen=True)
class _Range:
    """An interval a numeric override value must lie in; ``None`` leaves a side open."""

    low: float | None = None
    high: float | None = None
    low_inclusive: bool = True
    high_inclusive: bool = True

    def contains(self, x: float) -> bool:
        if self.low is not None and (x < self.low or (x == self.low and not self.low_inclusive)):
            return False
        return not (
            self.high is not None
            and (x > self.high or (x == self.high and not self.high_inclusive))
        )

    def phrase(self) -> str:
        if (
            self.low is not None
            and self.high is not None
            and self.low_inclusive
            and self.high_inclusive
        ):
            return f"between {self.low:g} and {self.high:g}"
        parts = []
        if self.low is not None:
            parts.append(f"{'at least' if self.low_inclusive else 'greater than'} {self.low:g}")
        if self.high is not None:
            parts.append(f"{'at most' if self.high_inclusive else 'less than'} {self.high:g}")
        return " and ".join(parts)


#: The interval each numeric override key must lie in (every element, for the path
#: keys). Bounds are the ones the model breaks outside of: a rate above 100%, a
#: growth of -100% or less, a discount rate of 0 or below. ``tax_rate: 25`` (percent
#: typed as a whole number) is the mistake this catches.
_OVERRIDE_RANGES: dict[str, _Range] = {
    "tax_rate": _Range(0, 1),
    "probability_of_bankruptcy": _Range(0, 1),
    "equity_weight": _Range(0, 1),
    "debt_weight": _Range(0, 1),
    "cost_of_equity": _Range(0, 1, low_inclusive=False, high_inclusive=False),
    "pretax_cost_of_debt": _Range(0, 1, low_inclusive=False, high_inclusive=False),
    "terminal_growth": _Range(-1, 1, low_inclusive=False, high_inclusive=False),
    "sales_to_capital": _Range(low=0, low_inclusive=False),
    "distress_value_per_share": _Range(low=0),
    "operating_margin": _Range(high=1, high_inclusive=False),
    "revenue_growth": _Range(low=-1, low_inclusive=False),
}

#: Override keys that carry text, not a number.
_OVERRIDE_TEXT_KEYS: frozenset[str] = frozenset({"story_type", "notes"})

#: Override keys with their own validation in :func:`load_override` (an integer
#: year, and the story and scenarios mappings), so the generic numeric check skips them.
_OVERRIDE_STORY_KEYS: frozenset[str] = frozenset({"founded_year", "story", "scenarios"})

#: Earliest ``founded_year`` accepted: no listed company is older than the joint-stock
#: company era.
_FOUNDED_YEAR_MIN = 1600


def conventional_override_path(assumptions_dir: Path | None, ticker: str) -> Path | None:
    """Return ``<assumptions_dir>/<TICKER>.yaml`` when it exists (spec §7.6), else None.

    The single place that knows the convention: ``bot analyze`` and the
    screener's second-pass DCF both resolve overrides through here. A non-file at
    the path (a directory) is passed on as is; ``load_override`` refuses it.
    """
    if assumptions_dir is None:
        return None
    candidate = assumptions_dir / f"{ticker.upper()}.yaml"
    return candidate if candidate.exists() else None


def load_override(override_path: Path | None) -> dict[str, Any]:
    """Load and validate ``config/assumptions/<TICKER>.yaml``; return the raw mapping.

    Returns ``{}`` for no path, a missing file or an empty file. Refuses a file
    that exists but cannot be read (permissions, a directory, an I/O error), unknown
    keys, non-numeric or out-of-range values, a bad ``founded_year``, and an
    inconsistent story file (``story`` / ``scenarios`` / ``story_type: hypergrowth``),
    all as ``ValueError`` whose message starts with the path. The story section is
    parsed here only to validate it; the mapping is returned unchanged.
    """
    if override_path is None or not override_path.exists():
        return {}
    try:
        text = override_path.read_text()
    except OSError as exc:
        raise ValueError(
            f"override file {override_path} cannot be read: {exc.strerror or exc}"
        ) from exc
    try:
        loaded = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ValueError(f"override file {override_path} is not valid YAML: {exc}") from exc
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(f"override file {override_path} must contain a YAML mapping")
    unknown = sorted(set(loaded) - _OVERRIDE_KEYS, key=str)
    if unknown:
        valid = ", ".join(sorted(_OVERRIDE_KEYS))
        raise ValueError(
            f"{override_path}: unknown override key(s): {', '.join(str(k) for k in unknown)}. "
            f"Valid keys: {valid}"
        )
    _check_override_values(override_path, loaded)
    _check_story_file(override_path, loaded)
    return loaded


def _check_story_file(override_path: Path, loaded: dict[str, Any]) -> None:
    """Refuse a bad ``founded_year`` or an inconsistent ``story`` / ``scenarios`` set."""
    if "founded_year" in loaded:
        year = loaded["founded_year"]
        this_year = date.today().year
        if (
            not isinstance(year, int)
            or isinstance(year, bool)
            or not _FOUNDED_YEAR_MIN <= year <= this_year
        ):
            raise ValueError(
                f"{override_path}: founded_year must be an integer from "
                f"{_FOUNDED_YEAR_MIN} to {this_year}, got {year!r}"
            )
    for key in ("story", "scenarios"):
        if key in loaded and not isinstance(loaded[key], dict):
            raise ValueError(f"{override_path}: {key} must be a mapping, got {loaded[key]!r}")
    story_type = loaded.get("story_type")
    if story_type == STORY_TYPE and "story" not in loaded:
        raise ValueError(f"{override_path}: story_type {STORY_TYPE} requires a story section")
    if "story" in loaded and story_type != STORY_TYPE:
        raise ValueError(
            f"{override_path}: story requires story_type: {STORY_TYPE}, got {story_type!r}"
        )
    if "scenarios" in loaded and "story" not in loaded:
        raise ValueError(f"{override_path}: scenarios requires a story section")
    story_from_override(loaded, where=str(override_path))


def _check_override_values(override_path: Path, override: dict[str, Any]) -> None:
    """Refuse a numeric override value that is not a finite number or is outside its range.

    Raised here as ``ValueError`` so a malformed file fails its own ticker
    instead of surfacing later as a ``TypeError`` or a NaN in the valuation.
    """
    for key, value in override.items():
        if key in _OVERRIDE_TEXT_KEYS or key in _OVERRIDE_STORY_KEYS:
            continue
        if key in _OVERRIDE_PATH_KEYS:
            if isinstance(value, list):
                ok = bool(value) and all(is_finite_number(x) for x in value)
            else:
                ok = is_finite_number(value)
            expected = "a finite number or a non-empty list of finite numbers"
        else:
            ok = is_finite_number(value)
            expected = "a finite number"
        if not ok:
            raise ValueError(f"{override_path}: {key} must be {expected}, got {value!r}")
        numbers = value if isinstance(value, list) else [value]
        bounds = _OVERRIDE_RANGES[key]
        if not all(bounds.contains(float(x)) for x in numbers):
            every = " (every element)" if key in _OVERRIDE_PATH_KEYS else ""
            raise ValueError(
                f"{override_path}: {key} must be {bounds.phrase()}{every}, got {value!r}"
            )


def _override_scalar(override: dict[str, Any], key: str) -> Sourced[float | None] | None:
    if key not in override:
        return None
    return Sourced(value=float(override[key]), source=AssumptionSource.MANUAL)


def _override_path_field(
    override: dict[str, Any], key: str
) -> Sourced[tuple[float, ...] | None] | None:
    if key not in override:
        return None
    raw = override[key]
    if isinstance(raw, (list, tuple)):
        return Sourced(value=tuple(float(x) for x in raw), source=AssumptionSource.MANUAL)
    # A scalar override broadcasts to a flat path over the horizon.
    return Sourced(value=(float(raw),) * _HORIZON, source=AssumptionSource.MANUAL)


# --------------------------------------------------------------------------- #
# Public entry point                                                          #
# --------------------------------------------------------------------------- #


def resolve_assumptions(
    ticker: str,
    conn: duckdb.DuckDBPyConnection,
    override_path: Path | None = None,
    *,
    override: Mapping[str, Any] | None = None,
    auto_story_type: StoryType | None = None,
    db_inputs: AssumptionInputs | None = None,
    currencies: CurrencyTable | None = None,
    interest_coverage: float | None = None,
    default_spreads: DefaultSpreadTable | None = None,
) -> Assumptions:
    """Resolve the six critical DCF assumptions for ``ticker`` (spec §7.3).

    Args:
        ticker: Company ticker; must exist in the ``companies`` table.
        conn: Open DuckDB connection with the schema applied.
        override_path: Optional ``config/assumptions/<TICKER>.yaml``. A
            non-existent path is treated as "no overrides".
        override: Override mapping already returned by :func:`load_override`,
            so already validated. When not ``None`` it is used verbatim and
            ``override_path`` is not read.
        auto_story_type: The story type the classifier
            (:func:`bot.valuator.story_types.classify`) assigned this company.
            It fills ``story_type`` only when the override YAML does not set one
            — a manual ``story_type`` always wins (spec §7.6 override hook).
        db_inputs: Pre-loaded DB rows (see :func:`load_assumption_inputs`). When
            supplied, every per-ticker read is skipped and these rows are used
            verbatim, so a batched caller issues zero queries (the F7 N+1 fix,
            #53). When ``None`` (the default) the rows are loaded from ``conn``.
        currencies: Per-currency rates used when ``db_inputs`` is ``None``;
            ``None`` loads the default file. Ignored when ``db_inputs`` is given
            (its ``currency_rates`` already hold the lookup).
        interest_coverage: EBIT over interest expense, the start of a distressed
            company's coverage → rating → probability chain. ``None`` when
            unknown; the probability then stays 0.
        default_spreads: Coverage-to-rating and rating-to-probability tables;
            ``None`` loads the default file, and only when the chain needs it.

    Returns:
        An :class:`Assumptions` bundle where every field carries its source.
        For a ``hypergrowth`` story with a ``story`` section the generic bundle
        is overlaid by :func:`bot.valuator.hypergrowth.apply_story` (the story
        replaces the generic growth and margin keys, base revenue from
        ``db_inputs.latest_revenue``).

    Raises:
        LookupError: If ``ticker`` is unknown.
        ValueError: If a hypergrowth story is applied and the company has no
            latest revenue, or :func:`bot.valuator.hypergrowth.apply_story`
            refuses the story (unreachable revenue target, unresolved
            ``wacc_terminal``, ``terminal_growth`` or ``tax_rate``).
    """
    if db_inputs is None:
        db_inputs = load_assumption_inputs(conn, ticker, currencies=currencies)
    country = db_inputs.country
    sector = _SectorDefaults(
        row=db_inputs.sector, cross_region=db_inputs.sector_is_cross_region
    )
    override = dict(override) if override is not None else load_override(override_path)

    story_label = _resolve_story_type(override, auto_story_type, ticker=ticker)
    if story_label is not None and story_label not in _STORY_TYPE_VALUES:
        log.warning(
            "assumptions.story_type.invalid",
            story_type=story_label,
            valid_story_types=sorted(_STORY_TYPE_VALUES),
        )
    story_type = StoryType(story_label) if story_label in _STORY_TYPE_VALUES else None

    rates = db_inputs.currency_rates
    terminal_growth = _resolve_terminal_growth(override, rates)
    revenue_growth = _resolve_revenue_growth(
        db_inputs.historical_growth_path,
        override,
        rates.nominal_gdp_growth if rates is not None else None,
        terminal_growth=terminal_growth.value,
        story_type=story_type,
    )
    operating_margin = _resolve_operating_margin(
        override,
        sector,
        story_type=story_type,
        company_margin=db_inputs.company_operating_margin,
        margin_history=db_inputs.operating_margin_history,
    )
    sales_to_capital = _resolve_sector_scalar(
        override, sector, key="sales_to_capital", attr="sales_to_capital"
    )
    cost_of_equity = _resolve_sector_scalar(
        override, sector, key="cost_of_equity", attr="cost_of_equity"
    )
    pretax_cost_of_debt = _resolve_sector_scalar(
        override, sector, key="pretax_cost_of_debt", attr="cost_of_debt"
    )
    equity_weight, debt_weight = _resolve_weights(override, sector)
    probability_of_bankruptcy, bankruptcy_derivation = _resolve_probability_of_bankruptcy(
        override,
        story_type=story_type,
        interest_coverage=interest_coverage,
        default_spreads=default_spreads,
    )
    distress_value_per_share = _resolve_distress_value_per_share(override)
    tax_rate = _resolve_tax_rate(override, sector, country)

    bundle = Assumptions(
        revenue_growth=revenue_growth,
        operating_margin=operating_margin,
        sales_to_capital=sales_to_capital,
        terminal_growth=terminal_growth,
        probability_of_bankruptcy=probability_of_bankruptcy,
        distress_value_per_share=distress_value_per_share,
        cost_of_equity=cost_of_equity,
        pretax_cost_of_debt=pretax_cost_of_debt,
        equity_weight=equity_weight,
        debt_weight=debt_weight,
        tax_rate=tax_rate,
        story_type=story_label,
        notes=override.get("notes"),
        bankruptcy_derivation=bankruptcy_derivation,
    )
    if story_type is not StoryType.HYPERGROWTH:
        return bundle
    parsed = story_from_override(
        override, where=str(override_path) if override_path else ticker
    )
    if parsed is None:
        return bundle
    if db_inputs.latest_revenue is None:
        raise ValueError(
            f"{ticker}: hypergrowth story needs the latest revenue "
            "(none in financials_annual)"
        )
    story, scenarios = parsed
    return replace(
        apply_story(
            bundle,
            story,
            base_revenue=db_inputs.latest_revenue,
            sector_wacc=sector.row.wacc if sector.row is not None else None,
        ),
        scenarios=scenarios or None,
    )


def _resolve_story_type(
    override: dict[str, Any], auto_story_type: StoryType | None, *, ticker: str
) -> str | None:
    """Manual ``story_type`` wins; else the classifier's verdict (spec §7.6).

    A ``hypergrowth`` label without a ``story`` section falls back to
    ``high-growth`` (#195): the method is never applied without a story file.
    """
    manual = override.get("story_type")
    if manual is not None:
        label = str(manual)
    elif auto_story_type is not None:
        label = str(auto_story_type)
    else:
        return None
    if label == StoryType.HYPERGROWTH.value and "story" not in override:
        log.info("assumptions.story_type.hypergrowth_without_story", ticker=ticker)
        return StoryType.HIGH_GROWTH.value
    return label


def _linear_path(start: float, end: float, n: int = _HORIZON) -> tuple[float, ...]:
    """Interpolate linearly and inclusively from ``start`` to ``end`` over ``n`` steps.

    The last element is ``end`` itself, not ``start + step * (n - 1)``, so float
    rounding cannot leave the path off its target.
    """
    if n <= 1:
        return (end,) * n
    step = (end - start) / (n - 1)
    return (*(start + step * i for i in range(n - 1)), end)


def _resolve_revenue_growth(
    historical: tuple[float, ...] | None,
    override: dict[str, Any],
    gdp: float | None,
    *,
    terminal_growth: float | None,
    story_type: StoryType | None = None,
) -> Sourced[tuple[float, ...] | None]:
    """Resolve the revenue-growth path: ``_HORIZON`` (10) years fading to terminal growth.

    Spec §7.3 wants analyst consensus for years 1-5 with convergence to nominal GDP by
    year 10. Consensus is not implemented (FMP's analyst-estimates endpoint is not
    wired, so there is no ANALYST_CONSENSUS source). Every path instead starts at the
    company's own growth and fades linearly to the terminal growth rate, so the last
    explicit year already grows at the rate the terminal value assumes.

    With history the start is the historical revenue CAGR (the flat path's value; a
    high-growth story is sourced STORY_PATTERN, anything else HISTORICAL_AVERAGE). With
    no history the start is the valuation currency's nominal GDP (RULE_BASED). Without
    terminal growth there is no target, and with neither a history nor a GDP figure no
    start, so the path is ``UNRESOLVED``. ``gdp`` is only ever that no-history start,
    never the target.

    A manual override (scalar or list) always wins and keeps its own length.
    """
    manual = _override_path_field(override, "revenue_growth")
    if manual is not None:
        return manual
    if terminal_growth is None:
        return Sourced(value=None, source=AssumptionSource.UNRESOLVED)
    if historical is not None:
        source = (
            AssumptionSource.STORY_PATTERN
            if story_type is StoryType.HIGH_GROWTH
            else AssumptionSource.HISTORICAL_AVERAGE
        )
        return Sourced(value=_linear_path(fmean(historical), terminal_growth), source=source)
    if gdp is not None:
        return Sourced(
            value=_linear_path(gdp, terminal_growth), source=AssumptionSource.RULE_BASED
        )
    return Sourced(value=None, source=AssumptionSource.UNRESOLVED)


def _resolve_sector_scalar(
    override: dict[str, Any],
    sector: _SectorDefaults,
    *,
    key: str,
    attr: str,
) -> Sourced[float | None]:
    manual = _override_scalar(override, key)
    if manual is not None:
        return manual
    value = getattr(sector.row, attr) if sector.row is not None else None
    if value is None:
        return Sourced(value=None, source=AssumptionSource.UNRESOLVED)
    return Sourced(value=value, source=sector.source)


def _resolve_operating_margin(
    override: dict[str, Any],
    sector: _SectorDefaults,
    *,
    story_type: StoryType | None,
    company_margin: float | None,
    margin_history: tuple[float, ...],
) -> Sourced[tuple[float, ...] | None]:
    """Operating-margin path, branched by archetype (spec §7.1).

    high-growth: linear ramp from the company's own current margin to the
    sector median — margin improvement is half of a high-growth story. The
    ramp and the flat paths below all run over `_HORIZON` (10) years.
    cyclical: the cycle's own average margin, not the current year's, so a
    trough or peak year does not get projected forward as steady state,
    given at least `_MIN_CYCLE_YEARS` years of margin history.
    mature-decline: the company's own latest margin, flat — no convergence to
    the sector — falling back to the sector median when there is no own margin.
    Every other archetype keeps the previous behaviour: a flat sector median.
    A manual override (scalar or list) always wins.
    """
    manual = _override_path_field(override, "operating_margin")
    if manual is not None:
        return manual
    sector_margin = sector.row.op_margin if sector.row is not None else None
    if (
        story_type is StoryType.HIGH_GROWTH
        and company_margin is not None
        and sector_margin is not None
    ):
        return Sourced(
            value=_linear_path(company_margin, sector_margin),
            source=AssumptionSource.STORY_PATTERN,
        )
    if story_type is StoryType.CYCLICAL and len(margin_history) >= _MIN_CYCLE_YEARS:
        cycle_avg = fmean(margin_history)
        return Sourced(
            value=(cycle_avg,) * _HORIZON, source=AssumptionSource.HISTORICAL_AVERAGE
        )
    if story_type is StoryType.MATURE_DECLINE and company_margin is not None:
        return Sourced(
            value=(company_margin,) * _HORIZON,
            source=AssumptionSource.HISTORICAL_AVERAGE,
        )
    if sector_margin is None:
        return Sourced(value=None, source=AssumptionSource.UNRESOLVED)
    return Sourced(value=(sector_margin,) * _HORIZON, source=sector.source)


def _resolve_weights(
    override: dict[str, Any], sector: _SectorDefaults
) -> tuple[Sourced[float | None], Sourced[float | None]]:
    """Resolve the equity/debt split of the capital structure.

    The two weights partition invested capital, so either one determines the
    other: a manual override of just one is honoured and the complement is
    derived (both reported as MANUAL). With no override, the split comes from
    the sector's D/E.

    Raises:
        ValueError: If *both* weights are overridden and they do not sum to 1.0.
            Accepting a non-partition would feed the WACC a capital structure
            that does not exist, under a ``manual`` provenance label.
    """
    manual_equity = _override_scalar(override, "equity_weight")
    manual_debt = _override_scalar(override, "debt_weight")
    manual_src = AssumptionSource.MANUAL
    if (
        manual_equity is not None
        and manual_equity.value is not None
        and manual_debt is not None
        and manual_debt.value is not None
        and abs(manual_equity.value + manual_debt.value - 1.0) > _WEIGHT_PARTITION_TOLERANCE
    ):
        raise ValueError(
            "equity_weight and debt_weight must sum to 1.0 (they partition invested "
            f"capital); got equity_weight={manual_equity.value!r} + "
            f"debt_weight={manual_debt.value!r} = "
            f"{manual_equity.value + manual_debt.value!r}"
        )
    if manual_equity is not None and manual_equity.value is not None:
        equity = manual_equity.value
        debt = (
            manual_debt.value
            if manual_debt is not None and manual_debt.value is not None
            else 1.0 - equity
        )
        return Sourced(value=equity, source=manual_src), Sourced(value=debt, source=manual_src)
    if manual_debt is not None and manual_debt.value is not None:
        debt = manual_debt.value
        return (
            Sourced(value=1.0 - debt, source=manual_src),
            Sourced(value=debt, source=manual_src),
        )
    if sector.row is not None and sector.row.debt_to_equity is not None:
        d_to_e = sector.row.debt_to_equity
        debt_weight = d_to_e / (1.0 + d_to_e)
        src = sector.source
        equity_weight = 1.0 - debt_weight
        return Sourced(value=equity_weight, source=src), Sourced(value=debt_weight, source=src)
    unresolved = AssumptionSource.UNRESOLVED
    return Sourced(value=None, source=unresolved), Sourced(value=None, source=unresolved)


def _resolve_terminal_growth(
    override: dict[str, Any], rates: CurrencyRates | None
) -> Sourced[float | None]:
    manual = _override_scalar(override, "terminal_growth")
    if manual is not None:
        return manual
    # Rule-based cap: g = min(rfr_ccy, gdp_ccy) (spec §7.3). No currency, no cap.
    if rates is None:
        return Sourced(value=None, source=AssumptionSource.UNRESOLVED)
    return Sourced(
        value=min(rates.risk_free_rate, rates.nominal_gdp_growth),
        source=AssumptionSource.RULE_BASED,
    )


def _resolve_tax_rate(
    override: dict[str, Any],
    sector: _SectorDefaults,
    country: _CountryRow | None,
) -> Sourced[float | None]:
    """Marginal tax rate: manual → sector → country → rule-based default (§7.2).

    The DCF taxes EBIT to NOPAT, so a tax rate is always required. Damodaran
    publishes effective tax rates at both the industry and country level; the
    sector figure is the closer proxy and wins, falling back to the country
    figure (sourced COUNTRY_DEFAULT_DAMODARAN) and finally a neutral default so
    the model never collapses to a zero-NOPAT (100%-tax) degenerate case.
    """
    manual = _override_scalar(override, "tax_rate")
    if manual is not None:
        return manual
    if sector.row is not None and sector.row.tax_rate is not None:
        return Sourced(value=sector.row.tax_rate, source=sector.source)
    if country is not None and country.tax_rate is not None:
        return Sourced(value=country.tax_rate, source=AssumptionSource.COUNTRY_DEFAULT_DAMODARAN)
    return Sourced(value=_DEFAULT_TAX_RATE, source=AssumptionSource.RULE_BASED)


def _resolve_probability_of_bankruptcy(
    override: dict[str, Any],
    *,
    story_type: StoryType | None,
    interest_coverage: float | None,
    default_spreads: DefaultSpreadTable | None,
) -> tuple[Sourced[float], BankruptcyDerivation | None]:
    """Manual wins; a distressed story derives it from coverage; else 0 (spec §7.3).

    The chain is interest coverage → rating → cumulative default probability
    (#213). Every gap in it leaves ``p`` at 0 and says why in the derivation.
    """
    manual = _override_scalar(override, "probability_of_bankruptcy")
    if manual is not None and manual.value is not None:
        return Sourced(value=manual.value, source=AssumptionSource.MANUAL), None
    # Default 0 outside distressed stories (spec §7.3).
    if story_type is not StoryType.DISTRESSED:
        return Sourced(value=0.0, source=AssumptionSource.RULE_BASED), None

    def fallback(
        rating: str | None, horizon_years: int | None, reason: str
    ) -> tuple[Sourced[float], BankruptcyDerivation]:
        derivation = BankruptcyDerivation(interest_coverage, rating, horizon_years, 0.0, reason)
        return Sourced(value=0.0, source=AssumptionSource.RULE_BASED), derivation

    if interest_coverage is None:
        return fallback(
            None,
            None,
            "distressed, but interest coverage is unknown (no EBIT or no interest expense): "
            "p stays 0",
        )
    table = default_spreads if default_spreads is not None else load_default_spreads()
    if table.is_empty:
        return fallback(
            None,
            None,
            "distressed, but the default-spread table is empty "
            "(config/default_spreads.yaml absent or malformed): p stays 0",
        )
    rating = table.rating_for(interest_coverage)
    if rating is None:
        return fallback(
            None,
            table.horizon_years,
            f"distressed, but coverage {interest_coverage:.2f} has no rating in the "
            "default-spread table: p stays 0",
        )
    probability = table.probability_for(rating)
    if probability is None:
        return fallback(
            rating,
            table.horizon_years,
            f"distressed, but rating {rating} has no default probability in the table: "
            "p stays 0",
        )
    reason = (
        f"interest coverage {interest_coverage:.2f} → rating {rating} → "
        f"{table.horizon_years}-year cumulative default probability {probability:.1%}"
    )
    derivation = BankruptcyDerivation(
        interest_coverage, rating, table.horizon_years, probability, reason
    )
    return Sourced(value=probability, source=AssumptionSource.RULE_BASED), derivation


def _resolve_distress_value_per_share(override: dict[str, Any]) -> Sourced[float]:
    """Per-share liquidation value, paired with ``probability_of_bankruptcy``.

    Never populated automatically (only the probability has a derivation, from
    interest coverage): it comes from a manual override or stays at the neutral
    0.0 default.
    """
    manual = _override_scalar(override, "distress_value_per_share")
    if manual is not None and manual.value is not None:
        return Sourced(value=manual.value, source=AssumptionSource.MANUAL)
    return Sourced(value=0.0, source=AssumptionSource.RULE_BASED)
