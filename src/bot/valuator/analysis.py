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

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date as _date
from pathlib import Path
from typing import Any

import duckdb

from bot.reference.countries import damodaran_country_name
from bot.reference.currencies import CurrencyTable, normalize_currency
from bot.reference.default_spreads import DefaultSpreadTable
from bot.reference.regions import dataset_region
from bot.reference.sectors import is_cyclical
from bot.utils.finance import cagr, latest_contiguous_run
from bot.utils.fx import ConvertedPrice, convert_price, get_fx_rate
from bot.utils.logging import get_logger
from bot.valuator.assumptions import (
    AssumptionInputs,
    bulk_load_assumption_inputs,
    load_assumption_inputs,
    load_override,
    resolve_assumptions,
)
from bot.valuator.assumptions import Assumptions as SourcedAssumptions
from bot.valuator.dcf import DCFResult, Financials, dcf
from bot.valuator.hypergrowth import scenario_cases
from bot.valuator.narrative_flags import (
    NarrativeContext,
    NarrativeFlag,
    hypergrowth_flags,
    narrative_flags,
)
from bot.valuator.sensitivity import (
    Grid2D,
    ScenarioResult,
    SensitivityAxis,
    TornadoEntry,
    grid_2d,
    scenario_range,
    tornado,
)
from bot.valuator.story_types import (
    ClassificationFinancials,
    SectorContext,
    StoryType,
    classify,
)

log = get_logger(__name__)

# Plausible range for a diluted share count (bounds inclusive). Outside it the
# figure is almost certainly mis-scaled (e.g. reported in millions), and a
# per-share value built on it would be silently wrong.
MIN_PLAUSIBLE_SHARES = 1_000_000.0
MAX_PLAUSIBLE_SHARES = 100_000_000_000.0


@dataclass(frozen=True)
class SanityCheck:
    """Implied valuation multiples vs the company's sector (spec §7.7).

    Attributes:
        implied_pe: The DCF's multiple: intrinsic value per share divided by
            EPS (net income / shares) of the latest fiscal year, or ``None``
            when EPS is non-positive or unavailable, or the intrinsic value is
            non-positive.
        market_pe: Current price divided by that same EPS, or ``None`` when
            the price is unavailable or EPS is non-positive or unavailable.
        sector_pe: Damodaran sector-median price/earnings multiple.
        implied_ev_sales: Enterprise value / trailing revenue from the DCF, or
            ``None`` when revenue is unavailable.
        sector_ev_sales: Damodaran sector-median EV/sales multiple.
    """

    implied_pe: float | None
    market_pe: float | None
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
            override or auto-classifier verdict; a ``hypergrowth`` verdict
            without a story file falls back to ``high-growth``).
        auto_story_type: The classifier's own verdict (``StoryType`` value),
            regardless of any override or the hypergrowth fallback.
        story_file_present: Whether the override file carries a ``story`` block.
        story_reasons: Human-readable reasons the story type was assigned.
        assumptions: The six critical assumptions, each carrying its source.
        financials: The current-year DCF inputs (revenue, net debt, shares).
        dcf_result: The two-stage DCF output (intrinsic value + projections).
        tornado: Per-axis impacts (±1pp on rate axes, ×0.8/×1.2 on
            sales-to-capital), descending by impact (spec §7.4).
        grid: 5x5 margin-of-safety grid over the two widest tornado axes.
        narrative_flags: The §7.5 consistency flags (four, plus ``story_margin``
            for a high-growth story), plus the ``hypergrowth_story`` flag when
            it applies.
        sanity_check: Implied vs sector multiples (spec §7.7).
        current_price: Latest close (on or before ``price_as_of`` when set) converted into
            the valuation currency (``None`` if absent or no exchange rate).
        margin_of_safety: ``intrinsic_value_after_governance / current_price``
            (``None`` if no price), i.e. measured on the value after the
            governance discount. > 1 means potentially undervalued (CONTEXT.md).
        override_notes: Free-text notes from the manual override (spec §7.6).
        scenarios: Base plus each story-file scenario run through a plain DCF
            (base first, then file order); ``()`` when the file has none.
        governance_discount: Fractional haircut on the intrinsic value for
            governance (``0.0`` when none). Tornado, grid and scenarios use
            the raw value.
        intrinsic_value_after_governance: ``dcf_result.intrinsic_value *
            (1 - governance_discount)``; equals the intrinsic value at ``0.0``.
        valuation_currency: Currency the DCF (and so ``current_price``) is in.
        listing_price: The newest close as listed, before conversion
            (``None`` without a close).
        price_currency: Currency of ``listing_price`` (normalised; ``None``
            when unknown or without a close).
        fx_rate: Multiplier taking the listing price into the valuation
            currency; ``None`` when no conversion applied or no rate was found.
        price_date: Date of the newest close (on or before ``price_as_of`` when set);
            ``None`` without a close.
    """

    ticker: str
    name: str
    country: str | None
    currency: str | None
    story_type: str | None
    auto_story_type: str
    story_file_present: bool
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
    scenarios: tuple[ScenarioResult, ...] = ()
    governance_discount: float = 0.0
    intrinsic_value_after_governance: float = 0.0
    valuation_currency: str | None = None
    listing_price: float | None = None
    price_currency: str | None = None
    fx_rate: float | None = None
    price_date: _date | None = None


# --------------------------------------------------------------------------- #
# DB loading                                                                   #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _CompanyRow:
    name: str
    country: str | None
    currency: str | None
    industry_damodaran: str | None
    ipo_date: _date | None


@dataclass(frozen=True)
class _LatestFinancials:
    revenue: float | None
    ebit: float | None
    net_income: float | None
    interest_expense: float | None
    net_debt: float | None
    shares_diluted: float | None
    total_debt: float | None
    total_equity: float | None


def _load_company(conn: duckdb.DuckDBPyConnection, ticker: str) -> _CompanyRow:
    row = conn.execute(
        "SELECT name, country, currency, industry_damodaran, ipo_date "
        "FROM companies WHERE ticker = ?",
        [ticker],
    ).fetchone()
    if row is None:
        raise LookupError(f"company {ticker!r} not found in companies table")
    return _CompanyRow(
        name=row[0],
        country=row[1],
        currency=row[2],
        industry_damodaran=row[3],
        ipo_date=row[4],
    )


def _latest_from_row(row: tuple[Any, ...]) -> _LatestFinancials:
    """Shape a ``financials_annual`` row.

    ``row`` is ``(revenue, ebit, net_income, interest_expense, total_debt, cash,
    shares_diluted, total_equity)``.
    """
    revenue, ebit, net_income, interest_expense, total_debt, cash, shares, total_equity = row
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
        total_debt=total_debt,
        total_equity=total_equity,
    )


def _load_latest_financials(
    conn: duckdb.DuckDBPyConnection, ticker: str
) -> _LatestFinancials:
    row = conn.execute(
        "SELECT revenue, ebit, net_income, interest_expense, total_debt, cash, "
        "shares_diluted, total_equity FROM financials_annual "
        "WHERE ticker = ? AND is_restated = FALSE "
        "ORDER BY fiscal_year DESC LIMIT 1",
        [ticker],
    ).fetchone()
    if row is None:
        raise LookupError(f"no financials_annual rows for {ticker!r}")
    return _latest_from_row(row)


def _load_history(
    conn: duckdb.DuckDBPyConnection, ticker: str
) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    """Revenue, net-income and EBIT histories, oldest first, in one scan."""
    rows = conn.execute(
        "SELECT fiscal_year, revenue, net_income, ebit FROM financials_annual "
        "WHERE ticker = ? AND is_restated = FALSE ORDER BY fiscal_year",
        [ticker],
    ).fetchall()
    return _histories_from_rows(rows)


def _histories_from_rows(
    rows: Iterable[tuple[Any, Any, Any, Any]],
) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    """Revenue, net-income and EBIT histories from ``(fiscal_year, revenue, net_income, ebit)`` rows.

    ``rows`` must be oldest first. Each series keeps only its latest run of
    consecutive fiscal years with values (see :func:`latest_contiguous_run`).
    """
    materialised = list(rows)
    return (
        latest_contiguous_run((r[0], r[1]) for r in materialised),
        latest_contiguous_run((r[0], r[2]) for r in materialised),
        latest_contiguous_run((r[0], r[3]) for r in materialised),
    )


@dataclass(frozen=True)
class LatestClose:
    """The newest non-null ``prices_daily`` row (on or before ``price_as_of`` when set).

    Holds the close, its listing currency and its date.

    ``currency`` is normalised (strip + upper, blank -> ``None``) like the
    valuation currency, so the two compare and key rate lookups in one spelling.
    """

    close: float
    currency: str | None
    date: _date


def _load_latest_close(
    conn: duckdb.DuckDBPyConnection,
    ticker: str,
    *,
    price_as_of: _date | None = None,
) -> LatestClose | None:
    """Newest non-null close for ``ticker``; on or before ``price_as_of`` when set."""
    sql = "SELECT close, currency, date FROM prices_daily WHERE ticker = ? AND close IS NOT NULL"
    params: list[Any] = [ticker]
    if price_as_of is not None:
        sql += " AND date <= ?"
        params.append(price_as_of)
    row = conn.execute(sql + " ORDER BY date DESC LIMIT 1", params).fetchone()
    if row is None:
        return None
    return LatestClose(float(row[0]), normalize_currency(row[1]), row[2])


def _needs_conversion(close: LatestClose | None, valuation: str | None) -> bool:
    return (
        close is not None
        and close.currency is not None
        and valuation is not None
        and close.currency != valuation
    )


def _warn_price_fx_missing(
    inputs: ValuationInput, warned: set[str | None] | None
) -> None:
    """Log a close that cannot be converted, once per currency pair per run."""
    close, rates = inputs.latest_close, inputs.close_rates
    valuation = inputs.assumption_inputs.valuation_currency
    if close is None or rates is None or price_in_valuation_currency(inputs).price is not None:
        return
    key = f"price_fx:{close.currency}/{valuation}"
    if warned is not None:
        if key in warned:
            return
        warned.add(key)
    log.warning(
        "analysis.price_fx_missing",
        listing=close.currency,
        valuation=valuation,
        date=close.date.isoformat(),
        listing_rate=rates[0],
        valuation_rate=rates[1],
    )


@dataclass(frozen=True)
class _SectorMultiples:
    region: str | None
    pe: float | None
    ev_sales: float | None
    op_margin: float | None
    beta_levered: float | None
    roic: float | None = None


def _sector_multiples_from(
    company: _CompanyRow,
    geographic_region: str | None,
    sector_row: tuple[Any, ...] | None,
) -> _SectorMultiples:
    """Shape the Damodaran rows into the company's sector multiples.

    ``geographic_region`` is ``damodaran_country.region`` for the company's
    country (or ``None``); ``sector_row`` is ``(pe, ev_sales,
    op_margin, beta_levered, roic)`` for the company's industry and dataset region.
    """
    # damodaran_country.region is a geographic grouping (e.g. "North America"),
    # not the damodaran_industry.region dataset key (e.g. "US") — the two
    # taxonomies share the name but not the values, so a raw join between them
    # never matches. Translate through the same reference mapping the assumptions
    # module uses.
    region = dataset_region(company.country, geographic_region)
    if sector_row is None:
        return _SectorMultiples(
            region=region, pe=None, ev_sales=None, op_margin=None, beta_levered=None
        )
    return _SectorMultiples(
        region=region,
        pe=sector_row[0],
        ev_sales=sector_row[1],
        op_margin=sector_row[2],
        beta_levered=sector_row[3],
        roic=sector_row[4],
    )


def _load_sector_multiples(
    conn: duckdb.DuckDBPyConnection, company: _CompanyRow
) -> _SectorMultiples:
    geographic_region: str | None = None
    name = damodaran_country_name(company.country)
    if name is not None:
        row = conn.execute(
            "SELECT region FROM damodaran_country WHERE country = ? "
            "ORDER BY year DESC LIMIT 1",
            [name],
        ).fetchone()
        geographic_region = row[0] if row is not None else None
    region = dataset_region(company.country, geographic_region)
    sector_row: tuple[Any, ...] | None = None
    if company.industry_damodaran is not None and region is not None:
        sector_row = conn.execute(
            "SELECT pe, ev_sales, op_margin, beta_levered, roic FROM damodaran_industry "
            "WHERE industry = ? AND region = ? ORDER BY year DESC LIMIT 1",
            [company.industry_damodaran, region],
        ).fetchone()
    return _sector_multiples_from(company, geographic_region, sector_row)


@dataclass(frozen=True)
class ValuationInput:
    """Every DB row :func:`analyze` needs for one company, pre-loaded.

    Threading a pre-built bundle into ``analyze(company=...)`` lets a caller that
    already holds these rows — e.g. the screener's batched second pass — value
    the company without re-issuing the per-ticker ``companies`` /
    ``financials_annual`` / ``prices_daily`` / Damodaran reads. This is the
    deferred valuator half of the F7 N+1 fix (#53). Build one with
    :func:`load_valuation_input`, or many at once with
    :func:`bulk_load_valuation_inputs`.

    Attributes:
        ticker: The (upper-cased) ticker these rows belong to.
        company: The ``companies`` row (name, country, currency, industry).
        latest: The latest non-restated annual financials.
        revenue_history / income_history / ebit_history: Oldest-first histories.
        sector: The Damodaran sector/country multiples.
        latest_close: Newest close (on or before ``price_as_of`` when set) with its
            currency and date, or ``None``.
        close_rates: ``(rate_to_usd(listing), rate_to_usd(valuation))`` on or
            before the close's date, only when the two currencies are known and
            differ; otherwise ``None``. A missing rate is ``None`` in the pair.
        assumption_inputs: The pre-loaded rows :func:`resolve_assumptions` needs.
    """

    ticker: str
    company: _CompanyRow
    latest: _LatestFinancials
    revenue_history: tuple[float, ...]
    income_history: tuple[float, ...]
    ebit_history: tuple[float, ...]
    sector: _SectorMultiples
    latest_close: LatestClose | None
    close_rates: tuple[float | None, float | None] | None
    assumption_inputs: AssumptionInputs


def price_in_valuation_currency(inputs: ValuationInput) -> ConvertedPrice:
    """The newest close converted into the valuation currency (``None`` if it cannot be)."""
    close = inputs.latest_close
    if close is None:
        return ConvertedPrice(None, None)
    rates = inputs.close_rates
    valuation = inputs.assumption_inputs.valuation_currency
    lookup: dict[str, float | None] = {}
    if rates is not None and close.currency is not None and valuation is not None:
        lookup = {close.currency: rates[0], valuation: rates[1]}
    return convert_price(close.close, close.currency, valuation, lookup.get)


def load_valuation_input(
    conn: duckdb.DuckDBPyConnection,
    ticker: str,
    *,
    currencies: CurrencyTable | None = None,
    warned: set[str | None] | None = None,
    price_as_of: _date | None = None,
) -> ValuationInput:
    """Load every DB row :func:`analyze` needs for ``ticker`` in one place.

    Pure in the project sense (accepts the connection, reads only). The result
    can be reused across calls so each company's per-ticker reads happen exactly
    once; :func:`bulk_load_valuation_inputs` builds the same bundles for many
    tickers in a constant number of queries. ``currencies`` is the per-currency
    rate table (``None`` loads the default file). ``price_as_of`` is the newest
    close on or before that date (inclusive); ``None`` = the newest close.

    Raises:
        LookupError: If ``ticker`` is unknown or has no annual financials.
    """
    ticker = ticker.upper()
    company = _load_company(conn, ticker)
    latest = _load_latest_financials(conn, ticker)
    revenue_history, income_history, ebit_history = _load_history(conn, ticker)
    sector = _load_sector_multiples(conn, company)
    latest_close = _load_latest_close(conn, ticker, price_as_of=price_as_of)
    assumption_inputs = load_assumption_inputs(
        conn, ticker, currencies=currencies, warned=warned
    )
    valuation = assumption_inputs.valuation_currency
    close_rates: tuple[float | None, float | None] | None = None
    if latest_close is not None and _needs_conversion(latest_close, valuation):
        assert latest_close.currency is not None and valuation is not None
        close_rates = (
            get_fx_rate(conn, latest_close.currency, latest_close.date),
            get_fx_rate(conn, valuation, latest_close.date),
        )
    result = ValuationInput(
        ticker=ticker,
        company=company,
        latest=latest,
        revenue_history=revenue_history,
        income_history=income_history,
        ebit_history=ebit_history,
        sector=sector,
        latest_close=latest_close,
        close_rates=close_rates,
        assumption_inputs=assumption_inputs,
    )
    _warn_price_fx_missing(result, warned)
    return result


def bulk_load_valuation_inputs(
    conn: duckdb.DuckDBPyConnection,
    tickers: Iterable[str],
    *,
    currencies: CurrencyTable | None = None,
    warned: set[str | None] | None = None,
    price_as_of: _date | None = None,
) -> dict[str, ValuationInput]:
    """Load :func:`load_valuation_input` for many tickers in a constant number of queries.

    Returns exactly what the per-ticker loader returns for each ticker, keyed by
    upper-cased ticker. Tickers for which the per-ticker loader would raise
    :class:`LookupError` (absent from ``companies``, or no non-restated annual
    financials) are omitted, so a caller can pass a whole shortlist. ``price_as_of``
    bounds each close like the per-ticker loader (newest close on or before it;
    ``None`` = newest close).
    """
    wanted = sorted({t.upper() for t in tickers})
    if not wanted:
        return {}
    companies = {
        t: _CompanyRow(name=n, country=c, currency=cur, industry_damodaran=i, ipo_date=d)
        for t, n, c, cur, i, d in conn.execute(
            "SELECT ticker, name, country, currency, industry_damodaran, ipo_date "
            "FROM companies WHERE ticker IN (SELECT unnest(?::VARCHAR[]))",
            [wanted],
        ).fetchall()
    }
    # Oldest first per ticker, so the last row is the latest fiscal year.
    financials: dict[str, list[tuple[Any, ...]]] = {}
    for ticker, *values in conn.execute(
        "SELECT ticker, revenue, ebit, net_income, interest_expense, total_debt, cash, "
        "shares_diluted, total_equity, fiscal_year FROM financials_annual "
        "WHERE ticker IN (SELECT unnest(?::VARCHAR[])) AND is_restated = FALSE "
        "ORDER BY ticker, fiscal_year",
        [wanted],
    ).fetchall():
        financials.setdefault(ticker, []).append(tuple(values))
    kept = [t for t in wanted if t in companies and t in financials]
    if not kept:
        return {}
    closes_sql = (
        "SELECT ticker, close, currency, date FROM prices_daily "
        "WHERE ticker IN (SELECT unnest(?::VARCHAR[])) AND close IS NOT NULL"
    )
    closes_params: list[Any] = [kept]
    if price_as_of is not None:
        closes_sql += " AND date <= ?"
        closes_params.append(price_as_of)
    closes = {
        t: LatestClose(float(c), normalize_currency(cur), d)
        for t, c, cur, d in conn.execute(
            closes_sql + " QUALIFY row_number() OVER (PARTITION BY ticker ORDER BY date DESC) = 1",
            closes_params,
        ).fetchall()
    }
    # companies.country is ISO alpha-2; damodaran_country is keyed by Damodaran name.
    names = {
        code: damodaran_country_name(code)
        for code in {companies[t].country for t in kept} - {None}
    }
    countries = sorted({n for n in names.values() if n is not None})
    country_rows: dict[str, str] = {
        r[0]: r[1]
        for r in conn.execute(
            "SELECT country, region FROM damodaran_country "
            "WHERE country IN (SELECT unnest(?::VARCHAR[])) "
            "QUALIFY row_number() OVER (PARTITION BY country ORDER BY year DESC) = 1",
            [countries],
        ).fetchall()
    }
    regions: dict[str, str] = {}
    for t in kept:
        company = companies[t]
        name = names.get(company.country) if company.country is not None else None
        geographic_region = country_rows.get(name) if name is not None else None
        regions[t] = dataset_region(company.country, geographic_region)
    industries = sorted({
        i for t in kept if (i := companies[t].industry_damodaran) is not None
    })
    sector_rows = {
        (r[0], r[1]): r[2:]
        for r in conn.execute(
            "SELECT industry, region, pe, ev_sales, op_margin, beta_levered, roic "
            "FROM damodaran_industry WHERE industry IN (SELECT unnest(?::VARCHAR[])) "
            "QUALIFY row_number() OVER (PARTITION BY industry, region ORDER BY year DESC) = 1",
            [industries],
        ).fetchall()
    }
    assumption_inputs = bulk_load_assumption_inputs(
        conn, kept, currencies=currencies, warned=warned
    )

    # Rates on or before each close's date, only for pairs that need converting.
    def _currencies_needed(t: str) -> tuple[str, ...]:
        close = closes.get(t)
        valuation = assumption_inputs[t].valuation_currency
        if close is None or not _needs_conversion(close, valuation):
            return ()
        assert close.currency is not None and valuation is not None
        return (close.currency, valuation)

    wanted_rates = sorted({
        (cur, closes[t].date)
        for t in kept
        for cur in _currencies_needed(t)
        if cur != "USD"
    })
    rate_at = {
        (cur, d): None if rate is None else float(rate)
        for cur, d, rate in conn.execute(
            "SELECT n.currency, n.date, c.rate_to_usd "
            "FROM (SELECT unnest(?::VARCHAR[]) AS currency, unnest(?::DATE[]) AS date) n "
            "ASOF LEFT JOIN currencies c ON c.currency = n.currency AND c.date <= n.date",
            [[w[0] for w in wanted_rates], [w[1] for w in wanted_rates]],
        ).fetchall()
    }

    def _rate(cur: str, d: _date) -> float | None:
        return 1.0 if cur == "USD" else rate_at.get((cur, d))

    result: dict[str, ValuationInput] = {}
    for t in kept:
        company = companies[t]
        pair = _currencies_needed(t)
        close_rates = (
            (_rate(pair[0], closes[t].date), _rate(pair[1], closes[t].date)) if pair else None
        )
        industry, region = company.industry_damodaran, regions[t]
        sector_row = sector_rows.get((industry, region)) if industry is not None else None
        name = names.get(company.country) if company.country is not None else None
        geographic_region = country_rows.get(name) if name is not None else None
        revenue_history, income_history, ebit_history = _histories_from_rows(
            (r[8], r[0], r[2], r[1]) for r in financials[t]
        )
        result[t] = ValuationInput(
            ticker=t,
            company=company,
            latest=_latest_from_row(financials[t][-1][:8]),
            revenue_history=revenue_history,
            income_history=income_history,
            ebit_history=ebit_history,
            sector=_sector_multiples_from(company, geographic_region, sector_row),
            latest_close=closes.get(t),
            close_rates=close_rates,
            assumption_inputs=assumption_inputs[t],
        )
    # One warning per missing (listing, valuation) pair, sorted.
    missing = {
        (str(v.latest_close.currency), str(v.assumption_inputs.valuation_currency)): v
        for v in reversed(result.values())
        if v.latest_close is not None
        and v.close_rates is not None
        and price_in_valuation_currency(v).price is None
    }
    for pair_key in sorted(missing):
        _warn_price_fx_missing(missing[pair_key], warned)
    return result


# --------------------------------------------------------------------------- #
# Derived signals                                                              #
# --------------------------------------------------------------------------- #


def _story_reasons(
    auto_story_type: StoryType,
    revenue_history: tuple[float, ...],
    age_years: int | None,
    *,
    overridden: bool,
    operating_margin: float | None = None,
    sector_operating_margin: float | None = None,
    founded_age_years: int | None = None,
    hypergrowth_fallback: bool = False,
) -> tuple[str, ...]:
    """Human-readable reasons for the story type shown in report §2.

    ``auto_story_type`` is always the classifier's verdict, not the effective story
    type — when ``overridden`` is set the two differ, and the reason line says so.

    When the type was manually overridden the auto-classification's reasons no
    longer explain it, so they are replaced by the override notice — otherwise the
    report states one type in its heading and justifies a different one below it.
    """
    if overridden:
        return (
            f"manually overridden in the assumptions file; the classifier would "
            f"have said {auto_story_type.value}",
        )
    if auto_story_type is StoryType.HYPERGROWTH:
        return _hypergrowth_reasons(
            revenue_history,
            operating_margin,
            sector_operating_margin,
            founded_age_years,
            hypergrowth_fallback,
        )
    reasons: list[str] = []
    rate = cagr(revenue_history)
    if rate is not None:
        periods = len(revenue_history) - 1
        reasons.append(f"historical revenue CAGR {rate:.1%} over {periods} years")
    else:
        reasons.append("too little revenue history for a reliable growth signal")
    if age_years is not None:
        reasons.append(f"company age {age_years} years")
    reasons.append(f"classified as {auto_story_type.value}")
    return tuple(reasons)


def _hypergrowth_reasons(
    revenue_history: tuple[float, ...],
    operating_margin: float | None,
    sector_operating_margin: float | None,
    founded_age_years: int | None,
    hypergrowth_fallback: bool,
) -> tuple[str, ...]:
    """Reasons for a ``hypergrowth`` verdict: the signals that fired (issue #195)."""
    growth = revenue_history[-1] / revenue_history[-2] - 1.0
    cagr_rate = cagr(revenue_history)
    periods = len(revenue_history) - 1
    reasons = [f"last-year revenue growth {growth:.1%}"]
    if cagr_rate is not None:
        reasons.append(f"revenue CAGR {cagr_rate:.1%} over {periods} years")
    else:
        reasons.append("too little revenue history for a reliable growth signal")
    if operating_margin is not None and sector_operating_margin is not None:
        reasons.append(
            f"operating margin {operating_margin:.1%} below sector {sector_operating_margin:.1%}"
        )
    reasons.append(
        f"founded {founded_age_years} years ago"
        if founded_age_years is not None
        else "founding year unknown"
    )
    reasons.append("classified as hypergrowth")
    if hypergrowth_fallback:
        reasons.append(
            "hypergrowth signals but no story file: valued as high-growth, "
            "see the hypergrowth_story flag"
        )
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
    intrinsic_value: float,
    enterprise_value: float,
    revenue: float | None,
    sector: _SectorMultiples,
) -> SanityCheck:
    implied_pe: float | None = None
    market_pe: float | None = None
    if net_income is not None and net_income > 0.0 and shares is not None and shares > 0.0:
        eps = net_income / shares
        if eps > 0.0:
            if intrinsic_value > 0.0:
                implied_pe = intrinsic_value / eps
            if current_price is not None:
                market_pe = current_price / eps
    implied_ev_sales: float | None = None
    if revenue is not None and revenue > 0.0:
        implied_ev_sales = enterprise_value / revenue
    return SanityCheck(
        implied_pe=implied_pe,
        market_pe=market_pe,
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
    is_cyclical_sector: bool | None = None,
    age_years: int | None = None,
    company: ValuationInput | None = None,
    currencies: CurrencyTable | None = None,
    warned: set[str | None] | None = None,
    price_as_of: _date | None = None,
    default_spreads: DefaultSpreadTable | None = None,
) -> Analysis:
    """Run the full §7.7 analysis pipeline for ``ticker``.

    Args:
        ticker: Company ticker; must exist in ``companies`` with at least one
            ``financials_annual`` row.
        conn: Open DuckDB connection with the schema applied.
        override_path: Optional ``config/assumptions/<TICKER>.yaml`` (spec §7.6).
        is_cyclical_sector: Whether the company's sector is structurally cyclical
            (feeds the story-type classifier's cyclical signal, spec §7.1).
            ``None`` (the default) derives the flag from the company's
            ``industry_damodaran`` label via :func:`bot.reference.sectors.is_cyclical`;
            pass ``True``/``False`` to force it regardless of the sector.
        age_years: Company age in years, if known (a high-growth signal).
        company: Pre-loaded DB rows for ``ticker`` (see
            :func:`load_valuation_input`). When supplied, every per-ticker read
            is skipped and these rows are used verbatim, so ``analyze`` itself
            issues zero DB queries; a batched caller builds the inputs with
            :func:`bulk_load_valuation_inputs` (the F7 N+1 fix, #53). When ``None`` (the
            default) the rows are loaded from ``conn``. ``ticker`` must match
            ``company.ticker``.
        currencies: Per-currency risk-free rate and GDP table used when ``company``
            is ``None`` (``None`` loads the default file). Ignored otherwise: the
            pre-loaded inputs already carry their currency rates.
        warned: Run-scoped set of currencies already logged as uncovered; share one
            across calls to warn once per currency per run. Used like ``currencies``.
        price_as_of: Price the company at the newest close on or before this date
            (``None`` = the newest close). Ignored when ``company`` is supplied,
            like ``currencies`` and ``warned``: the pre-loaded inputs already
            carry their close.
        default_spreads: Interest-coverage to rating to default-probability table
            that derives a distressed company's probability of bankruptcy (``None``
            loads the default file lazily, only when a distressed company needs it).
            Unlike ``currencies``, still used when ``company`` is supplied.

    A ``hypergrowth`` story file (resolved in :func:`resolve_assumptions`) also
    sets the DCF's ``fixed_commitments`` and ``extra_cash`` from the bundle; both
    are zero without one.

    Returns:
        An :class:`Analysis` carrying everything the §7.7 report renders.

    Raises:
        LookupError: If ``ticker`` is unknown or has no annual financials.
        ValueError: If the resolved assumptions are too incomplete to value the
            company (propagated from :meth:`Assumptions.to_dcf_assumptions` /
            :func:`bot.valuator.dcf.dcf`), or if the latest diluted share count
            is missing, non-positive, or outside the plausible range
            (``MIN_PLAUSIBLE_SHARES``..``MAX_PLAUSIBLE_SHARES``).
    """
    ticker = ticker.upper()
    if company is None:
        company = load_valuation_input(
            conn, ticker, currencies=currencies, warned=warned, price_as_of=price_as_of
        )
    inputs = company
    company_row = inputs.company
    latest = inputs.latest
    revenue_history = inputs.revenue_history
    income_history = inputs.income_history
    ebit_history = inputs.ebit_history
    sector = inputs.sector
    converted = price_in_valuation_currency(inputs)
    current_price = converted.price

    # Derive age from the company's ipoDate (FMP) when the caller didn't pass
    # one explicitly — an explicit age_years always wins.
    if age_years is None and company_row.ipo_date is not None:
        age_years = max(0, (_date.today() - company_row.ipo_date).days // 365)

    # Read the override once; resolve_assumptions reuses it instead of re-reading.
    override = load_override(override_path)
    founded_age_years = (
        _date.today().year - int(override["founded_year"]) if "founded_year" in override else None
    )

    # The company's *realised* operating margin, from its own income statement.
    # Deliberately not ``assumptions.operating_margin``: absent a manual override
    # that value is read from the same ``damodaran_industry`` row as
    # ``sector.op_margin``, so the story-margin flag would compare the sector
    # median against itself — the same vacuous comparison the ERP gap had.
    company_operating_margin: float | None = None
    if latest.revenue is not None and latest.revenue != 0.0 and latest.ebit is not None:
        company_operating_margin = latest.ebit / latest.revenue

    # Story type: classify, then let a manual override win inside resolve.
    interest_coverage = None
    if latest.ebit is not None and latest.interest_expense:
        interest_coverage = latest.ebit / latest.interest_expense
    classification = ClassificationFinancials(
        revenue_history=revenue_history,
        earnings_history=income_history,
        age_years=age_years,
        interest_coverage=interest_coverage,
        operating_margin=company_operating_margin,
        founded_age_years=founded_age_years,
    )
    # Derived from the company's Damodaran industry unless the caller forces it,
    # so StoryType.CYCLICAL is reachable from the CLI and the screener (§7.1).
    cyclical = (
        is_cyclical(company_row.industry_damodaran)
        if is_cyclical_sector is None
        else is_cyclical_sector
    )
    auto_story = classify(
        classification,
        SectorContext(is_cyclical=cyclical, operating_margin=sector.op_margin),
    )

    assumptions = resolve_assumptions(
        ticker,
        conn,
        override=override,
        auto_story_type=auto_story,
        db_inputs=inputs.assumption_inputs,
        interest_coverage=interest_coverage,
        default_spreads=default_spreads,
    )
    story_type = assumptions.story_type or auto_story.value
    manual = override.get("story_type")
    story_file_present = "story" in override
    hypergrowth_fallback = (
        auto_story is StoryType.HYPERGROWTH and manual is None and not story_file_present
    )
    overridden = manual is not None and str(manual) != auto_story.value

    if latest.revenue is None:
        raise ValueError(f"{ticker}: no revenue on the latest financials — cannot value")
    if latest.shares_diluted is None or latest.shares_diluted <= 0.0:
        raise ValueError(f"{ticker}: missing/non-positive diluted shares — cannot value")
    shares = latest.shares_diluted
    if not MIN_PLAUSIBLE_SHARES <= shares <= MAX_PLAUSIBLE_SHARES:
        raise ValueError(
            f"{ticker}: implausible diluted share count {shares:,.1f} "
            f"(outside {MIN_PLAUSIBLE_SHARES:,.0f} to {MAX_PLAUSIBLE_SHARES:,.0f}) — cannot value"
        )
    financials = Financials(
        revenue=latest.revenue,
        net_debt=latest.net_debt if latest.net_debt is not None else 0.0,
        shares_diluted=shares,
        # A hypergrowth story's balance-sheet items; None (no story) means zero.
        fixed_commitments=(
            assumptions.fixed_commitments.value
            if assumptions.fixed_commitments is not None
            else 0.0
        ),
        extra_cash=assumptions.extra_cash.value if assumptions.extra_cash is not None else 0.0,
    )

    dcf_assumptions = assumptions.to_dcf_assumptions()
    dcf_result = dcf(financials, dcf_assumptions)
    tornado_entries = tuple(tornado(financials, dcf_assumptions))
    axis_a, axis_b = _two_widest_axes(tornado_entries)
    grid = grid_2d(
        financials, dcf_assumptions, axis_a, axis_b, reference_price=current_price
    )

    # The company's own capital structure, not the sector's (which drives WACC).
    company_debt_weight: float | None = None
    if latest.total_debt is not None and latest.total_equity is not None:
        invested = latest.total_debt + latest.total_equity
        if invested > 0.0:
            company_debt_weight = latest.total_debt / invested

    context = NarrativeContext(
        story_type=story_type,
        hypergrowth_signals=auto_story is StoryType.HYPERGROWTH,
        story_file_present=story_file_present,
        company_operating_margin=company_operating_margin,
        sector_operating_margin=sector.op_margin,
        sector_beta=sector.beta_levered,
        operating_leverage=_operating_leverage(revenue_history, ebit_history),
        company_debt_weight=company_debt_weight,
        terminal_roic=(
            assumptions.terminal_roic.value if assumptions.terminal_roic is not None else None
        ),
        sector_roic=sector.roic,
        # erp_weighted / erp_listing deliberately unset: a revenue-weighted ERP
        # needs revenue by geography, which no ingest path supplies. Passing the
        # sector ERP as both made the gap identically zero — a fake calculation.
    )
    flags = narrative_flags(financials, dcf_assumptions, dcf_result, context) + hypergrowth_flags(
        financials, dcf_assumptions, dcf_result, context
    )

    governance_discount = (
        assumptions.governance_discount.value
        if assumptions.governance_discount is not None
        else 0.0
    )
    intrinsic_after_governance = dcf_result.intrinsic_value * (1.0 - governance_discount)
    scenario_results: tuple[ScenarioResult, ...] = ()
    if assumptions.scenarios:
        base_revenue = inputs.assumption_inputs.latest_revenue
        if base_revenue is None:  # resolve_assumptions already refused it; narrows the type
            raise ValueError(f"{ticker}: scenarios need the latest revenue — cannot value")
        assumption_sector = inputs.assumption_inputs.sector
        scenario_results = scenario_range(
            scenario_cases(
                assumptions,
                assumptions.scenarios,
                base_revenue=base_revenue,
                sector_wacc=assumption_sector.wacc if assumption_sector is not None else None,
                financials=financials,
            )
        )
    margin_of_safety = (
        intrinsic_after_governance / current_price
        if current_price is not None and current_price > 0.0
        else None
    )
    sanity = _sanity_check(
        current_price=current_price,
        net_income=latest.net_income,
        shares=latest.shares_diluted,
        intrinsic_value=dcf_result.intrinsic_value,
        enterprise_value=dcf_result.enterprise_value,
        revenue=latest.revenue,
        sector=sector,
    )

    close = inputs.latest_close
    return Analysis(
        ticker=ticker,
        name=company_row.name,
        country=company_row.country,
        currency=company_row.currency,
        story_type=story_type,
        auto_story_type=auto_story.value,
        story_file_present=story_file_present,
        story_reasons=_story_reasons(
            auto_story,
            revenue_history,
            age_years,
            overridden=overridden,
            operating_margin=company_operating_margin,
            sector_operating_margin=sector.op_margin,
            founded_age_years=founded_age_years,
            hypergrowth_fallback=hypergrowth_fallback,
        ),
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
        scenarios=scenario_results,
        governance_discount=governance_discount,
        intrinsic_value_after_governance=intrinsic_after_governance,
        valuation_currency=inputs.assumption_inputs.valuation_currency,
        listing_price=close.close if close else None,
        price_currency=close.currency if close else None,
        fx_rate=converted.fx_rate,
        price_date=close.date if close else None,
    )
