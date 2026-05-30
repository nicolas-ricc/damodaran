"""Input types consumed by screener rules (Capa B).

A rule reads a single company's snapshot (``CompanyData``) and the matching
industry benchmarks (``IndustryBenchmarks``, sourced from Damodaran datasets)
and returns a verdict. Both types are plain immutable dataclasses so rules stay
pure and trivially testable against fixtures — no DB connection required at
evaluation time.

Fields are optional (``None``) when a datum is unavailable; rules decide how to
treat missing data (typically: fail the gate, since the screener cannot vouch
for a company it cannot measure).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class CompanyData:
    """A single company's screener-relevant snapshot.

    Assembled by the screener engine from ``companies`` + ``financials_annual``
    (spec §5). Monetary values are in USD unless otherwise noted.
    """

    ticker: str
    name: str
    industry: str | None = None
    region: str | None = None
    market_cap: float | None = None
    years_of_financials: int = 0
    is_financial_services: bool = False
    net_debt: float | None = None
    ebitda: float | None = None
    ebit: float | None = None
    interest_expense: float | None = None
    goodwill: float | None = None
    total_assets: float | None = None
    operating_cashflow_history: tuple[float, ...] = field(default_factory=tuple)
    """Operating cashflow per fiscal year, most recent last (spec §6.2)."""
    pe: float | None = None
    pbv: float | None = None
    ev_ebitda: float | None = None
    roe: float | None = None
    roic: float | None = None
    fcf_yield: float | None = None


@dataclass(frozen=True)
class IndustryBenchmarks:
    """Damodaran industry-level medians for one (industry, region, year).

    Mirrors the numeric columns of ``damodaran_industry`` (schema.sql). Used by
    value-indicator and trap-detection rules that compare a company against its
    sector (spec §6.3/§6.4).
    """

    industry: str
    region: str
    year: int
    wacc: float | None = None
    roic: float | None = None
    roe: float | None = None
    pe: float | None = None
    pbv: float | None = None
    ev_ebitda: float | None = None
    op_margin: float | None = None
    net_margin: float | None = None
