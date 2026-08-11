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

The DCF's WACC is *computed* from its components (``cost_of_equity``,
``pretax_cost_of_debt``, the weights and the tax rate) by ``dcf._wacc``; there is
deliberately no resolved ``wacc`` assumption. Damodaran publishes a sector WACC and
an earlier version of this module carried it, but the DCF ignored it, so the report
printed two disagreeing numbers. The sector WACC still has one legitimate consumer:
the §6.4 ROIC-vs-WACC trap detector, which reads it from ``damodaran_industry``
directly.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any, TypeVar

import duckdb
import yaml

from bot.reference.regions import dataset_region
from bot.utils.logging import get_logger
from bot.valuator.dcf import Assumptions as DCFAssumptions
from bot.valuator.story_types import StoryType

log = get_logger(__name__)

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

# How far an explicitly overridden equity_weight + debt_weight may drift from 1.0
# before the pair is rejected. Only float representation error is tolerated: the
# two weights partition invested capital, so anything else is a user error.
_WEIGHT_PARTITION_TOLERANCE = 1e-9


class AssumptionSource(StrEnum):
    """Provenance of a resolved assumption (spec §7.3)."""

    MANUAL = "manual"
    SECTOR_DEFAULT_DAMODARAN = "sector_default_damodaran"
    #: The sector median came from a *different* Damodaran dataset region than the
    #: company's own, because the mapped region has no ingested rows. Disclosed so
    #: the report shows the substitution rather than passing it off as the
    #: company's own region.
    SECTOR_DEFAULT_DAMODARAN_CROSS_REGION = "sector_default_damodaran_cross_region"
    RULE_BASED = "rule_based"
    HISTORICAL_AVERAGE = "historical_average"
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
class Assumptions:
    """The six critical DCF assumptions, each carrying its provenance (§7.3).

    Attributes:
        revenue_growth: Year-by-year revenue-growth path (years 1..N).
        operating_margin: Steady-state EBIT / revenue ratio.
        sales_to_capital: Incremental sales per unit of reinvested capital.
        terminal_growth: Perpetual growth ``g`` past the horizon.
        probability_of_bankruptcy: Probability the firm fails (0 outside
            distressed stories).
        distress_value_per_share: Per-share value recovered in bankruptcy,
            paired with ``probability_of_bankruptcy`` to blend a going-concern
            and liquidation value (0 outside distressed stories). Never
            derived automatically — §7.3's rating/Altman-Z derivation is not
            implemented — so it comes from a manual override or stays 0.0.
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
            distress_value_per_share=self.distress_value_per_share.value,
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
    risk_free_rate: float | None
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
        historical_growth_path: The historical-average revenue-growth path, or
            ``None`` when there is too little history.
        sector_is_cross_region: Whether ``sector`` came from a different dataset
            region than the company's own (see
            :func:`_load_sector_with_fallback`). Every assumption drawn from that
            row is then labelled
            :attr:`AssumptionSource.SECTOR_DEFAULT_DAMODARAN_CROSS_REGION`.
    """

    company: _Company
    country: _CountryRow | None
    sector: _SectorRow | None
    historical_growth_path: tuple[float, ...] | None
    sector_is_cross_region: bool = False


def load_assumption_inputs(
    conn: duckdb.DuckDBPyConnection, ticker: str
) -> AssumptionInputs:
    """Load every DB row :func:`resolve_assumptions` needs for ``ticker``.

    Pure in the project sense (accepts the connection, reads only). The result
    can be reused across calls so the per-ticker reads happen exactly once.

    Raises:
        LookupError: If ``ticker`` is unknown.
    """
    company = _load_company(conn, ticker)
    country = _load_country(conn, company.country)
    region = dataset_region(company.country, country.region if country is not None else None)
    sector, cross_region = _load_sector_with_fallback(conn, company.industry_damodaran, region)
    historical_growth_path = _historical_growth_path(conn, ticker)
    return AssumptionInputs(
        company=company,
        country=country,
        sector=sector,
        historical_growth_path=historical_growth_path,
        sector_is_cross_region=cross_region,
    )


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
    if exact is not None or industry is None:
        return exact, False
    row = conn.execute(
        "SELECT wacc, cost_of_equity, cost_of_debt, op_margin, sales_to_capital, "
        "tax_rate, debt_to_equity, region FROM damodaran_industry "
        "WHERE industry = ? ORDER BY year DESC LIMIT 1",
        [industry],
    ).fetchone()
    if row is None:
        return None, False
    log.warning(
        "assumptions.sector.cross_region_substitution",
        industry=industry,
        requested_region=region,
        used_region=row[7],
    )
    return _SectorRow(*row[:7]), True


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
    }
)


def _load_override(override_path: Path | None) -> dict[str, Any]:
    if override_path is None or not override_path.exists():
        return {}
    loaded = yaml.safe_load(override_path.read_text())
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(f"override file {override_path} must contain a YAML mapping")
    unknown = sorted(set(loaded) - _OVERRIDE_KEYS)
    if unknown:
        valid = ", ".join(sorted(_OVERRIDE_KEYS))
        raise ValueError(
            f"{override_path}: unknown override key(s): {', '.join(unknown)}. "
            f"Valid keys: {valid}"
        )
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
    db_inputs: AssumptionInputs | None = None,
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
        db_inputs: Pre-loaded DB rows (see :func:`load_assumption_inputs`). When
            supplied, every per-ticker read is skipped and these rows are used
            verbatim, so a batched caller issues zero queries (the F7 N+1 fix,
            #53). When ``None`` (the default) the rows are loaded from ``conn``.

    Returns:
        An :class:`Assumptions` bundle where every field carries its source.

    Raises:
        LookupError: If ``ticker`` is unknown.
    """
    if db_inputs is None:
        db_inputs = load_assumption_inputs(conn, ticker)
    country = db_inputs.country
    sector = _SectorDefaults(
        row=db_inputs.sector, cross_region=db_inputs.sector_is_cross_region
    )
    override = _load_override(override_path)

    revenue_growth = _resolve_revenue_growth(
        db_inputs.historical_growth_path, override, gdp_nominal
    )
    operating_margin = _resolve_sector_scalar(
        override, sector, key="operating_margin", attr="op_margin"
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
    terminal_growth = _resolve_terminal_growth(override, country, gdp_nominal)
    probability_of_bankruptcy = _resolve_probability_of_bankruptcy(override)
    distress_value_per_share = _resolve_distress_value_per_share(override)
    tax_rate = _resolve_tax_rate(override, sector, country)

    return Assumptions(
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
    historical: tuple[float, ...] | None,
    override: dict[str, Any],
    gdp_nominal: float,
) -> Sourced[tuple[float, ...] | None]:
    """Resolve the revenue-growth path.

    Spec §7.3 wants analyst consensus for years 1-5 with convergence to nominal GDP by
    year 10. Neither is implemented: the path is the historical average repeated over a
    5-year horizon, sourced as HISTORICAL_AVERAGE. There is no ANALYST_CONSENSUS source
    because nothing can emit it — FMP's analyst-estimates endpoint is not wired.
    """
    manual = _override_path_field(override, "revenue_growth")
    if manual is not None:
        return manual
    # M1 universe: no analyst-consensus feed → historical average.
    if historical is not None:
        return Sourced(value=historical, source=AssumptionSource.HISTORICAL_AVERAGE)
    # No history at all: rule-based flat path anchored on nominal GDP.
    return Sourced(value=(gdp_nominal,) * _HORIZON, source=AssumptionSource.RULE_BASED)


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
    override: dict[str, Any],
    sector: _SectorDefaults,
    country: _CountryRow | None,
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
    if sector.row is not None and sector.row.tax_rate is not None:
        return Sourced(value=sector.row.tax_rate, source=sector.source)
    if country is not None and country.tax_rate is not None:
        return Sourced(value=country.tax_rate, source=AssumptionSource.SECTOR_DEFAULT_DAMODARAN)
    return Sourced(value=_DEFAULT_TAX_RATE, source=AssumptionSource.RULE_BASED)


def _resolve_probability_of_bankruptcy(override: dict[str, Any]) -> Sourced[float]:
    manual = _override_scalar(override, "probability_of_bankruptcy")
    if manual is not None and manual.value is not None:
        return Sourced(value=manual.value, source=AssumptionSource.MANUAL)
    # Default 0 outside distressed stories (spec §7.3).
    return Sourced(value=0.0, source=AssumptionSource.RULE_BASED)


def _resolve_distress_value_per_share(override: dict[str, Any]) -> Sourced[float]:
    """Per-share liquidation value, paired with ``probability_of_bankruptcy``.

    Spec §7.3's rating/Altman-Z derivation for distressed companies is not
    implemented, so this is never populated automatically: it comes from a
    manual override or stays at the neutral 0.0 default.
    """
    manual = _override_scalar(override, "distress_value_per_share")
    if manual is not None and manual.value is not None:
        return Sourced(value=manual.value, source=AssumptionSource.MANUAL)
    return Sourced(value=0.0, source=AssumptionSource.RULE_BASED)
