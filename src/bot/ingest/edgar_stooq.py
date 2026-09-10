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
from pathlib import Path

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
from bot.ingest.stooq import StooqClient, parse_stooq_csv
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
        stooq_dir: Path | None = None,
    ) -> None:
        self._sec_user_agent = sec_user_agent
        self._timeout = timeout
        self._sec_transport = sec_transport
        self._stooq_transport = stooq_transport
        self._stooq_dir = stooq_dir
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
        ``provider.name`` ("edgar_stooq"); leaving the raw stamp means the
        watermark query never finds a row and every fundamentals refresh
        re-imports the full universe.
        """
        return ParsedCompanyData(
            company={**parsed.company, "source": self.name},
            annual=[{**row, "source": self.name} for row in parsed.annual],
            quarterly=[{**row, "source": self.name} for row in parsed.quarterly],
            filings=[{**row, "source": self.name} for row in parsed.filings],
        )

    def _bars_from_dir(self, sym: str, since: date | None) -> list[PriceBar]:
        """Read ``<stooq_dir>/<TICKER>.csv`` (the browser recipe's output).

        Stooq's anti-bot wall blocks this adapter's HTTP path (ADR 0007);
        ``scripts/stooq_browser_fetch.mjs`` harvests the CSVs through a real
        browser instead. A missing file is a per-ticker failure that names the
        recipe — the run continues with the other tickers.
        """
        assert self._stooq_dir is not None
        path = self._stooq_dir / f"{sym}.csv"
        if not path.is_file():
            raise FileNotFoundError(
                f"{path}: no CSV for {sym} — harvest it first with "
                f"`node scripts/stooq_browser_fetch.mjs {sym}` (see ADR 0007)"
            )
        bars = parse_stooq_csv(path.read_text(encoding="utf-8"))
        if since is not None:
            bars = [b for b in bars if b.date >= since]
        return bars

    def daily_prices(self, ticker: str, since: date | None) -> list[PriceBar]:
        sym = ticker.upper()
        if self._stooq_dir is not None:
            bars = self._bars_from_dir(sym, since)
        else:
            bars = self._prices().daily_prices(sym, since)
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
                log.warning("edgar_stooq.market_cap.failed", ticker=sym, error=str(exc))
                shares = None
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
