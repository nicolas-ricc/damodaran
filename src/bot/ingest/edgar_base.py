"""Shared EDGAR half of the free-stack providers (ADR 0007).

Both free-stack adapters pair SEC EDGAR fundamentals with a US EOD price
source; only the price source differs. This base owns everything EDGAR —
company info (submissions), statements (company facts), the incremental-skip
source restamp, market-cap-from-shares, and the USD-no-op FX — and defers the
daily bars to a subclass via :meth:`_fetch_bars`.
"""

from __future__ import annotations

import dataclasses
from datetime import date

import httpx

from bot.ingest.provider import (
    CompanyInfo,
    FundamentalsBundle,
    FxRate,
    ParsedCompanyData,
    PriceBar,
    ProviderRateLimitError,
)
from bot.ingest.sec_edgar import (
    SecEdgarClient,
    latest_filing_date_from_submissions,
    parse_company_facts,
    parse_submissions_info,
)
from bot.utils.logging import get_logger

log = get_logger(__name__)

_FRESH_DAYS = 7


class EdgarPricedProvider:
    """EDGAR fundamentals + a subclass-supplied US EOD price source.

    Subclasses set :attr:`name`, implement :meth:`_fetch_bars`, and may override
    :meth:`_close_prices` to release their price client. One instance per bulk
    run; ``close()`` resets so post-close use reopens.
    """

    def __init__(
        self,
        sec_user_agent: str,
        timeout: float = 30.0,
        sec_transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._sec_user_agent = sec_user_agent
        self._timeout = timeout
        self._sec_transport = sec_transport
        self._sec: SecEdgarClient | None = None
        self._submissions_cache: dict[str, dict[str, object]] = {}

    @property
    def name(self) -> str:  # pragma: no cover - abstract
        raise NotImplementedError

    def _fetch_bars(self, sym: str, since: date | None) -> list[PriceBar]:  # pragma: no cover
        raise NotImplementedError

    def _close_prices(self) -> None:
        """Release the subclass's price client, if any (default: nothing)."""

    def _edgar(self) -> SecEdgarClient:
        if self._sec is None:
            self._sec = SecEdgarClient(
                user_agent=self._sec_user_agent,
                timeout=self._timeout,
                transport=self._sec_transport,
            )
        return self._sec

    def close(self) -> None:
        if self._sec is not None:
            self._sec.close()
            self._sec = None
        self._close_prices()
        self._submissions_cache.clear()

    def __enter__(self) -> EdgarPricedProvider:
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
        restamped = self._restamp(parsed)
        return FundamentalsBundle(
            info=self.lookup_company(sym),
            annual=dataclasses.replace(restamped, quarterly=[]),
            quarterly=dataclasses.replace(restamped, annual=[]),
            filings=restamped.filings,
        )

    def _restamp(self, parsed: ParsedCompanyData) -> ParsedCompanyData:
        """Re-stamp ``source`` as this provider's name (not the raw "sec_edgar").

        ``parse_company_facts`` always stamps "sec_edgar" so the ``bot show
        --fetch`` path keeps its own provenance. But the incremental-skip
        watermark (``universe.latest_local_filing_date``) is queried under
        ``provider.name``; leaving the raw stamp means the watermark query never
        finds a row and every fundamentals refresh re-imports the full universe.
        """
        return ParsedCompanyData(
            company={**parsed.company, "source": self.name},
            annual=[{**row, "source": self.name} for row in parsed.annual],
            quarterly=[{**row, "source": self.name} for row in parsed.quarterly],
            filings=[{**row, "source": self.name} for row in parsed.filings],
        )

    def _stamp_market_cap(self, bars: list[PriceBar], sym: str) -> list[PriceBar]:
        """Set market cap on the newest fresh bar as ``close x EDGAR shares``."""
        if not bars:
            return bars
        newest_idx = max(range(len(bars)), key=lambda i: bars[i].date)
        newest = bars[newest_idx]
        if newest.close is not None and (date.today() - newest.date).days <= _FRESH_DAYS:
            try:
                cik = self._cik(sym)
                shares = self._edgar().shares_outstanding(cik) if cik is not None else None
            except ProviderRateLimitError:
                raise
            except Exception as exc:
                log.warning("edgar.market_cap.failed", ticker=sym, error=str(exc))
                shares = None
            if shares is not None:
                bars[newest_idx] = dataclasses.replace(newest, market_cap=newest.close * shares)
        return bars

    def daily_prices(self, ticker: str, since: date | None) -> list[PriceBar]:
        sym = ticker.upper()
        return self._stamp_market_cap(self._fetch_bars(sym, since), sym)

    def fx_rates(self, currency: str, since: date | None) -> list[FxRate]:
        if currency.upper() != "USD":
            log.warning("edgar.fx.unsupported", currency=currency)
        return []

    def latest_filing_date(self, ticker: str) -> date | None:
        submissions = self._submissions(ticker)
        if submissions is None:
            return None
        return latest_filing_date_from_submissions(submissions)
