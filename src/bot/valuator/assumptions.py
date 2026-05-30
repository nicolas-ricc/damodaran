"""Resolve the six critical DCF assumptions with source tracking (spec §7.3).

A valuation is only as honest as its inputs, so every one of the six critical
assumptions from spec §7.3 carries its *provenance* — where the number came
from — alongside its value. The report (spec §7.7) shows that provenance for
each assumption so a human can see which figures are analyst-driven, which are
sector defaults, and which are pure rules.

Resolution order (highest-priority source wins, spec §7.3/§7.6)::

    1. Manual override    — config/assumptions/<TICKER>.yaml, if present
    2. Analyst consensus  — FMP (M2). For the M1 universe there is no consensus
                            feed, so this layer falls back to the company's own
                            historical average (HISTORICAL_AVERAGE).
    3. Sector default     — medians from damodaran_industry (and the country's
                            risk-free rate / ERP from damodaran_country).
    4. Rule-based         — e.g. terminal_growth = min(risk_free_rate, GDP).

This module is a pure function of ``(ticker, conn, override_path)`` plus a
nominal-GDP scalar: it reads, it does not write, and it holds no global state.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, TypeVar

import duckdb
import yaml

from bot.valuator.dcf import Assumptions as DCFAssumptions
from bot.valuator.story_types import StoryType

T = TypeVar("T")

# Length of the explicit forecast horizon when a path is synthesised from a
# single scalar (sector/rule-based growth or margin). Spec §7.3 forecasts years
# 1-5 explicitly before convergence; a richer year-by-year path comes from the
# analyst-consensus / story-type layer (M4.3+), which overrides this default.
_HORIZON = 5

# Default nominal GDP growth used as the terminal-growth ceiling and the
# rule-based revenue-growth anchor when no better figure is supplied. Roughly
# long-run US nominal GDP; callers pass a country-specific value when known.
_DEFAULT_GDP_NOMINAL = 0.04

# Rule-based marginal tax rate used when neither a manual override nor a
# Damodaran sector/country tax rate is available. A neutral mid-rate so the DCF
# still produces a NOPAT rather than collapsing.
_DEFAULT_TAX_RATE = 0.25


class AssumptionSource(StrEnum):
    """Provenance of a resolved assumption (spec §7.3)."""

    MANUAL = "manual"
    ANALYST_CONSENSUS = "analyst_consensus"
    SECTOR_DEFAULT_DAMODARAN = "sector_default_damodaran"
    RULE_BASED = "rule_based"
    HISTORICAL_AVERAGE = "historical_average"


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
class Assumptions:
    """The six critical DCF assumptions, each carrying its provenance (§7.3).

    Attributes:
        revenue_growth: Year-by-year revenue-growth path (years 1..N).
        operating_margin: Steady-state EBIT / revenue ratio.
        sales_to_capital: Incremental sales per unit of reinvested capital.
        wacc: Weighted-average cost of capital.
        terminal_growth: Perpetual growth ``g`` past the horizon.
        probability_of_bankruptcy: Probability the firm fails (0 outside
            distressed stories).
        cost_of_equity / pretax_cost_of_debt / equity_weight / debt_weight:
            The WACC components, kept so a downstream DCF can rebuild WACC from
            its parts and report the weights actually used.
        story_type: Optional Damodaran story type, sourced from a manual
            override (auto-assignment lives in story_types.py, M4.3).
        notes: Free-text override notes for the report's "manual overrides"
            section (spec §7.6).
    """

    revenue_growth: Sourced[tuple[float, ...] | None]
    operating_margin: Sourced[float | None]
    sales_to_capital: Sourced[float | None]
    wacc: Sourced[float | None]
    terminal_growth: Sourced[float | None]
    probability_of_bankruptcy: Sourced[float]
    cost_of_equity: Sourced[float | None]
    pretax_cost_of_debt: Sourced[float | None]
    equity_weight: Sourced[float | None]
    debt_weight: Sourced[float | None]
    tax_rate: Sourced[float | None]
    story_type: str | None = None
    notes: str | None = None

    def to_dcf_assumptions(self) -> DCFAssumptions:
        """Project the resolved bundle onto the pure :class:`dcf.Assumptions`.

        Raises:
            ValueError: If a required assumption is still unresolved (``None``),
                so the caller cannot silently feed a half-built model into the
                DCF.
        """
        growth = _require(self.revenue_growth, "revenue_growth")
        margin = _require(self.operating_margin, "operating_margin")
        return DCFAssumptions(
            revenue_growth=growth,
            operating_margin=(margin,) * len(growth),
            tax_rate=_require(self.tax_rate, "tax_rate"),
            sales_to_capital=_require(self.sales_to_capital, "sales_to_capital"),
            terminal_growth=_require(self.terminal_growth, "terminal_growth"),
            cost_of_equity=_require(self.cost_of_equity, "cost_of_equity"),
            pretax_cost_of_debt=_require(self.pretax_cost_of_debt, "pretax_cost_of_debt"),
            equity_weight=_require(self.equity_weight, "equity_weight"),
            debt_weight=_require(self.debt_weight, "debt_weight"),
            probability_of_bankruptcy=self.probability_of_bankruptcy.value,
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


@dataclass(frozen=True)
class _CountryRow:
    region: str | None
    risk_free_rate: float | None
    erp: float | None
    tax_rate: float | None


def _load_company(conn: duckdb.DuckDBPyConnection, ticker: str) -> _Company:
    row = conn.execute(
        "SELECT country, industry_damodaran FROM companies WHERE ticker = ?",
        [ticker],
    ).fetchone()
    if row is None:
        raise LookupError(f"company {ticker!r} not found in companies table")
    return _Company(country=row[0], industry_damodaran=row[1])


def _load_country(conn: duckdb.DuckDBPyConnection, country: str | None) -> _CountryRow | None:
    if country is None:
        return None
    row = conn.execute(
        "SELECT region, risk_free_rate, erp, tax_rate FROM damodaran_country "
        "WHERE country = ? ORDER BY year DESC LIMIT 1",
        [country],
    ).fetchone()
    if row is None:
        return None
    return _CountryRow(region=row[0], risk_free_rate=row[1], erp=row[2], tax_rate=row[3])


def _load_sector(
    conn: duckdb.DuckDBPyConnection, industry: str | None, region: str | None
) -> _SectorRow | None:
    if industry is None or region is None:
        return None
    row = conn.execute(
        "SELECT wacc, cost_of_equity, cost_of_debt, op_margin, sales_to_capital, "
        "tax_rate, debt_to_equity FROM damodaran_industry "
        "WHERE industry = ? AND region = ? ORDER BY year DESC LIMIT 1",
        [industry, region],
    ).fetchone()
    if row is None:
        return None
    return _SectorRow(
        wacc=row[0],
        cost_of_equity=row[1],
        cost_of_debt=row[2],
        op_margin=row[3],
        sales_to_capital=row[4],
        tax_rate=row[5],
        debt_to_equity=row[6],
    )


def _historical_growth_path(
    conn: duckdb.DuckDBPyConnection, ticker: str
) -> tuple[float, ...] | None:
    """Average year-over-year revenue growth from financials_annual.

    Returns a flat path of ``_HORIZON`` years at the historical average growth
    rate, or ``None`` when there is too little history (< 2 years of revenue).
    """
    rows = conn.execute(
        "SELECT revenue FROM financials_annual "
        "WHERE ticker = ? AND revenue IS NOT NULL AND is_restated = FALSE "
        "ORDER BY fiscal_year",
        [ticker],
    ).fetchall()
    revenues = [float(r[0]) for r in rows]
    if len(revenues) < 2:
        return None
    growths = [
        (curr - prev) / prev
        for prev, curr in itertools.pairwise(revenues)
        if prev != 0.0
    ]
    if not growths:
        return None
    average = sum(growths) / len(growths)
    return (average,) * _HORIZON


# --------------------------------------------------------------------------- #
# Manual override                                                             #
# --------------------------------------------------------------------------- #


def _load_override(override_path: Path | None) -> dict[str, Any]:
    if override_path is None or not override_path.exists():
        return {}
    loaded = yaml.safe_load(override_path.read_text())
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(f"override file {override_path} must contain a YAML mapping")
    return loaded


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
    gdp_nominal: float = _DEFAULT_GDP_NOMINAL,
    auto_story_type: StoryType | None = None,
) -> Assumptions:
    """Resolve the six critical DCF assumptions for ``ticker`` (spec §7.3).

    Args:
        ticker: Company ticker; must exist in the ``companies`` table.
        conn: Open DuckDB connection with the schema applied.
        override_path: Optional ``config/assumptions/<TICKER>.yaml``. A
            non-existent path is treated as "no overrides".
        gdp_nominal: Country nominal-GDP growth used as the terminal-growth
            ceiling and the rule-based revenue-growth anchor.
        auto_story_type: The story type the classifier
            (:func:`bot.valuator.story_types.classify`) assigned this company.
            It fills ``story_type`` only when the override YAML does not set one
            — a manual ``story_type`` always wins (spec §7.6 override hook).

    Returns:
        An :class:`Assumptions` bundle where every field carries its source.

    Raises:
        LookupError: If ``ticker`` is unknown.
    """
    company = _load_company(conn, ticker)
    country = _load_country(conn, company.country)
    region = country.region if country is not None else None
    sector = _load_sector(conn, company.industry_damodaran, region)
    override = _load_override(override_path)

    revenue_growth = _resolve_revenue_growth(conn, ticker, override, gdp_nominal)
    operating_margin = _resolve_operating_margin(override, sector)
    sales_to_capital = _resolve_sales_to_capital(override, sector)
    cost_of_equity = _resolve_cost_of_equity(override, sector)
    pretax_cost_of_debt = _resolve_cost_of_debt(override, sector)
    equity_weight, debt_weight = _resolve_weights(override, sector)
    wacc = _resolve_wacc(override, sector)
    terminal_growth = _resolve_terminal_growth(override, country, gdp_nominal)
    probability_of_bankruptcy = _resolve_probability_of_bankruptcy(override)
    tax_rate = _resolve_tax_rate(override, sector, country)

    return Assumptions(
        revenue_growth=revenue_growth,
        operating_margin=operating_margin,
        sales_to_capital=sales_to_capital,
        wacc=wacc,
        terminal_growth=terminal_growth,
        probability_of_bankruptcy=probability_of_bankruptcy,
        cost_of_equity=cost_of_equity,
        pretax_cost_of_debt=pretax_cost_of_debt,
        equity_weight=equity_weight,
        debt_weight=debt_weight,
        tax_rate=tax_rate,
        story_type=_resolve_story_type(override, auto_story_type),
        notes=override.get("notes"),
    )


def _resolve_story_type(
    override: dict[str, Any], auto_story_type: StoryType | None
) -> str | None:
    """Manual ``story_type`` wins; else the classifier's verdict (spec §7.6)."""
    manual = override.get("story_type")
    if manual is not None:
        return str(manual)
    if auto_story_type is not None:
        return str(auto_story_type)
    return None


def _resolve_revenue_growth(
    conn: duckdb.DuckDBPyConnection,
    ticker: str,
    override: dict[str, Any],
    gdp_nominal: float,
) -> Sourced[tuple[float, ...] | None]:
    manual = _override_path_field(override, "revenue_growth")
    if manual is not None:
        return manual
    # M1 universe: no analyst-consensus feed → historical average.
    historical = _historical_growth_path(conn, ticker)
    if historical is not None:
        return Sourced(value=historical, source=AssumptionSource.HISTORICAL_AVERAGE)
    # No history at all: rule-based flat path anchored on nominal GDP.
    return Sourced(value=(gdp_nominal,) * _HORIZON, source=AssumptionSource.RULE_BASED)


def _resolve_operating_margin(
    override: dict[str, Any], sector: _SectorRow | None
) -> Sourced[float | None]:
    manual = _override_scalar(override, "operating_margin")
    if manual is not None:
        return manual
    if sector is not None and sector.op_margin is not None:
        return Sourced(value=sector.op_margin, source=AssumptionSource.SECTOR_DEFAULT_DAMODARAN)
    return Sourced(value=None, source=AssumptionSource.SECTOR_DEFAULT_DAMODARAN)


def _resolve_sales_to_capital(
    override: dict[str, Any], sector: _SectorRow | None
) -> Sourced[float | None]:
    manual = _override_scalar(override, "sales_to_capital")
    if manual is not None:
        return manual
    if sector is not None and sector.sales_to_capital is not None:
        return Sourced(
            value=sector.sales_to_capital, source=AssumptionSource.SECTOR_DEFAULT_DAMODARAN
        )
    return Sourced(value=None, source=AssumptionSource.SECTOR_DEFAULT_DAMODARAN)


def _resolve_cost_of_equity(
    override: dict[str, Any], sector: _SectorRow | None
) -> Sourced[float | None]:
    manual = _override_scalar(override, "cost_of_equity")
    if manual is not None:
        return manual
    if sector is not None and sector.cost_of_equity is not None:
        return Sourced(
            value=sector.cost_of_equity, source=AssumptionSource.SECTOR_DEFAULT_DAMODARAN
        )
    return Sourced(value=None, source=AssumptionSource.SECTOR_DEFAULT_DAMODARAN)


def _resolve_cost_of_debt(
    override: dict[str, Any], sector: _SectorRow | None
) -> Sourced[float | None]:
    manual = _override_scalar(override, "pretax_cost_of_debt")
    if manual is not None:
        return manual
    if sector is not None and sector.cost_of_debt is not None:
        return Sourced(
            value=sector.cost_of_debt, source=AssumptionSource.SECTOR_DEFAULT_DAMODARAN
        )
    return Sourced(value=None, source=AssumptionSource.SECTOR_DEFAULT_DAMODARAN)


def _resolve_weights(
    override: dict[str, Any], sector: _SectorRow | None
) -> tuple[Sourced[float | None], Sourced[float | None]]:
    manual_equity = _override_scalar(override, "equity_weight")
    manual_debt = _override_scalar(override, "debt_weight")
    if manual_equity is not None and manual_debt is not None:
        return manual_equity, manual_debt
    if sector is not None and sector.debt_to_equity is not None:
        d_to_e = sector.debt_to_equity
        debt_weight = d_to_e / (1.0 + d_to_e)
        equity_weight = 1.0 - debt_weight
        src = AssumptionSource.SECTOR_DEFAULT_DAMODARAN
        return Sourced(value=equity_weight, source=src), Sourced(value=debt_weight, source=src)
    src = AssumptionSource.SECTOR_DEFAULT_DAMODARAN
    return Sourced(value=None, source=src), Sourced(value=None, source=src)


def _resolve_wacc(
    override: dict[str, Any], sector: _SectorRow | None
) -> Sourced[float | None]:
    manual = _override_scalar(override, "wacc")
    if manual is not None:
        return manual
    if sector is not None and sector.wacc is not None:
        return Sourced(value=sector.wacc, source=AssumptionSource.SECTOR_DEFAULT_DAMODARAN)
    return Sourced(value=None, source=AssumptionSource.SECTOR_DEFAULT_DAMODARAN)


def _resolve_terminal_growth(
    override: dict[str, Any], country: _CountryRow | None, gdp_nominal: float
) -> Sourced[float | None]:
    manual = _override_scalar(override, "terminal_growth")
    if manual is not None:
        return manual
    # Rule-based cap: g = min(risk_free_rate, GDP nominal) (spec §7.3).
    rfr = country.risk_free_rate if country is not None else None
    if rfr is None:
        return Sourced(value=gdp_nominal, source=AssumptionSource.RULE_BASED)
    return Sourced(value=min(rfr, gdp_nominal), source=AssumptionSource.RULE_BASED)


def _resolve_tax_rate(
    override: dict[str, Any], sector: _SectorRow | None, country: _CountryRow | None
) -> Sourced[float | None]:
    """Marginal tax rate: manual → sector → country → rule-based default (§7.2).

    The DCF taxes EBIT to NOPAT, so a tax rate is always required. Damodaran
    publishes effective tax rates at both the industry and country level; the
    sector figure is the closer proxy and wins, falling back to the country
    figure and finally a neutral default so the model never collapses to a
    zero-NOPAT (100%-tax) degenerate case.
    """
    manual = _override_scalar(override, "tax_rate")
    if manual is not None:
        return manual
    if sector is not None and sector.tax_rate is not None:
        return Sourced(value=sector.tax_rate, source=AssumptionSource.SECTOR_DEFAULT_DAMODARAN)
    if country is not None and country.tax_rate is not None:
        return Sourced(value=country.tax_rate, source=AssumptionSource.SECTOR_DEFAULT_DAMODARAN)
    return Sourced(value=_DEFAULT_TAX_RATE, source=AssumptionSource.RULE_BASED)


def _resolve_probability_of_bankruptcy(override: dict[str, Any]) -> Sourced[float]:
    manual = _override_scalar(override, "probability_of_bankruptcy")
    if manual is not None and manual.value is not None:
        return Sourced(value=manual.value, source=AssumptionSource.MANUAL)
    # Default 0 outside distressed stories (spec §7.3).
    return Sourced(value=0.0, source=AssumptionSource.RULE_BASED)
