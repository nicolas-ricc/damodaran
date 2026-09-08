"""The market-data provider port (spec 2026-08-24).

One seam between the ingest orchestration and any concrete data source.
Adapters (bot.ingest.fmp today, a fake in tests) implement
:class:`MarketDataProvider` and translate their source's wire format into the
canonical records below. Orchestration and the CLI may import this module and
never a concrete adapter's client.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Protocol, runtime_checkable


@dataclass
class ParsedCompanyData:
    """Fundamentals in DB-row shape: one company dict plus annual/quarterly/filings rows.

    The canonical record every adapter (SEC EDGAR, FMP, fakes) produces, so the
    importer never sees a source's wire format.
    """

    company: dict[str, Any]
    annual: list[dict[str, Any]] = field(default_factory=list)
    quarterly: list[dict[str, Any]] = field(default_factory=list)
    filings: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class CompanyInfo:
    """Normalized basic company info from a provider's profile lookup."""

    ticker: str
    name: str
    exchange: str | None
    exchange_short_name: str | None
    country: str | None
    currency: str | None
    sector: str | None
    industry: str | None
    is_actively_trading: bool
    ipo_date: date | None = None


@dataclass(frozen=True)
class FundamentalsBundle:
    """Everything the company importer needs for one ticker, in one fetch."""

    info: CompanyInfo | None
    annual: ParsedCompanyData
    quarterly: ParsedCompanyData
    filings: list[dict[str, Any]]  # filings_log row shape (upsert_filings)


@dataclass(frozen=True)
class PriceBar:
    """One daily EOD price row (prices_daily shape, sans ticker/currency)."""

    date: date
    close: float | None
    volume: float | None
    market_cap: float | None


@dataclass(frozen=True)
class FxRate:
    """One daily FX rate to USD (currencies table shape, sans currency)."""

    date: date
    rate_to_usd: float


class ProviderRateLimitError(RuntimeError):
    """The provider's quota is exhausted: stop the run cleanly, defer the rest.

    Not a per-ticker failure. Concrete adapters raise a subclass (e.g.
    FmpRateLimitError); orchestration catches only this base class.
    """


@runtime_checkable
class MarketDataProvider(Protocol):
    """Everything the pipeline may know about a fundamentals+prices source."""

    @property
    def name(self) -> str:
        """Short id ("fmp") — prefixes refresh_log sources, fills company.source."""
        ...

    def lookup_company(self, ticker: str) -> CompanyInfo | None: ...

    def fundamentals(self, ticker: str) -> FundamentalsBundle: ...

    def daily_prices(self, ticker: str, since: date | None) -> list[PriceBar]: ...

    def fx_rates(self, currency: str, since: date | None) -> list[FxRate]: ...

    def latest_filing_date(self, ticker: str) -> date | None: ...

    def close(self) -> None: ...
