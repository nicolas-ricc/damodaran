"""The free-stack adapter: SEC EDGAR fundamentals + Stooq EOD prices (ADR 0007).

Composes the two free sources behind :class:`bot.ingest.provider
.MarketDataProvider`. EDGAR supplies company info (submissions), statements
(company facts) and shares outstanding; Stooq supplies daily closes. Market
cap is computed on the newest fresh bar as ``close x shares`` — mirroring the
FMP adapter's profile-onto-newest-bar behavior. FX is a USD no-op: this
adapter exists only under the US-only scope (listing = reporting = USD).
"""

from __future__ import annotations

import dataclasses
from datetime import date

import httpx

from bot.ingest.provider import CompanyInfo, FundamentalsBundle, FxRate, PriceBar
from bot.ingest.sec_edgar import (
    SecEdgarClient,
    latest_filing_date_from_submissions,
    parse_company_facts,
    parse_submissions_info,
)
from bot.ingest.stooq import StooqClient
from bot.utils.logging import get_logger

log = get_logger(__name__)

_FRESH_DAYS = 7


class EdgarStooqProvider:
    """EDGAR + Stooq behind the provider port. One instance per bulk run."""

    def __init__(
        self,
        sec_user_agent: str,
        timeout: float = 30.0,
        sec_transport: httpx.BaseTransport | None = None,
        stooq_transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._sec_user_agent = sec_user_agent
        self._timeout = timeout
        self._sec_transport = sec_transport
        self._stooq_transport = stooq_transport
        self._sec: SecEdgarClient | None = None
        self._stooq: StooqClient | None = None
        self._submissions_cache: dict[str, dict[str, object]] = {}

    @property
    def name(self) -> str:
        return "edgar_stooq"

    def _edgar(self) -> SecEdgarClient:
        if self._sec is None:
            self._sec = SecEdgarClient(
                user_agent=self._sec_user_agent,
                timeout=self._timeout,
                transport=self._sec_transport,
            )
        return self._sec

    def _prices(self) -> StooqClient:
        if self._stooq is None:
            self._stooq = StooqClient(timeout=self._timeout, transport=self._stooq_transport)
        return self._stooq

    def close(self) -> None:
        if self._sec is not None:
            self._sec.close()
            self._sec = None
        if self._stooq is not None:
            self._stooq.close()
            self._stooq = None
        self._submissions_cache.clear()

    def __enter__(self) -> EdgarStooqProvider:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _cik(self, ticker: str) -> str | None:
        return self._edgar().lookup_cik(ticker)

    def _submissions(self, ticker: str) -> dict[str, object] | None:
        sym = ticker.upper()
        if sym in self._submissions_cache:
            return self._submissions_cache[sym]
        cik = self._cik(sym)
        if cik is None:
            return None
        data = self._edgar().fetch_submissions(cik)
        self._submissions_cache[sym] = data
        return data

    def lookup_company(self, ticker: str) -> CompanyInfo | None:
        submissions = self._submissions(ticker)
        if submissions is None:
            return None
        return parse_submissions_info(ticker, submissions)

    def fundamentals(self, ticker: str) -> FundamentalsBundle:
        sym = ticker.upper()
        cik = self._cik(sym)
        if cik is None:
            raise LookupError(f"{sym}: not in EDGAR's ticker table")
        parsed = parse_company_facts(sym, self._edgar().fetch_company_facts(cik))
        return FundamentalsBundle(
            info=self.lookup_company(sym),
            annual=dataclasses.replace(parsed, quarterly=[]),
            quarterly=dataclasses.replace(parsed, annual=[]),
            filings=parsed.filings,
        )

    def daily_prices(self, ticker: str, since: date | None) -> list[PriceBar]:
        sym = ticker.upper()
        bars = self._prices().daily_prices(sym, since)
        if not bars:
            return bars
        newest_idx = max(range(len(bars)), key=lambda i: bars[i].date)
        newest = bars[newest_idx]
        if newest.close is not None and (date.today() - newest.date).days <= _FRESH_DAYS:
            cik = self._cik(sym)
            shares = self._edgar().shares_outstanding(cik) if cik is not None else None
            if shares is not None:
                bars[newest_idx] = dataclasses.replace(
                    newest, market_cap=newest.close * shares
                )
        return bars

    def fx_rates(self, currency: str, since: date | None) -> list[FxRate]:
        if currency.upper() != "USD":
            log.warning("edgar_stooq.fx.unsupported", currency=currency)
        return []

    def latest_filing_date(self, ticker: str) -> date | None:
        submissions = self._submissions(ticker)
        if submissions is None:
            return None
        return latest_filing_date_from_submissions(submissions)
