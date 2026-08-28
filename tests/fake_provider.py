"""In-memory MarketDataProvider adapter for tests — the seam's second adapter."""

from __future__ import annotations

from datetime import date

from bot.ingest.provider import (
    CompanyInfo,
    FundamentalsBundle,
    FxRate,
    ParsedCompanyData,
    PriceBar,
    ProviderRateLimitError,
)


def _empty_parsed(ticker: str) -> ParsedCompanyData:
    return ParsedCompanyData(
        company={
            "ticker": ticker.upper(),
            "name": ticker.upper(),
            "currency": None,
            "source": "fake",
            "status": "active",
        },
        annual=[],
        quarterly=[],
    )


class FakeProvider:
    """Serves canned records; records calls; can fail or rate-limit on demand."""

    def __init__(
        self,
        *,
        companies: dict[str, CompanyInfo] | None = None,
        bundles: dict[str, FundamentalsBundle] | None = None,
        prices: dict[str, list[PriceBar]] | None = None,
        fx: dict[str, list[FxRate]] | None = None,
        filing_dates: dict[str, date] | None = None,
        fail_with: dict[str, Exception] | None = None,
        rate_limit_after: int | None = None,
    ) -> None:
        self._companies = {k.upper(): v for k, v in (companies or {}).items()}
        self._bundles = {k.upper(): v for k, v in (bundles or {}).items()}
        self._prices = {k.upper(): v for k, v in (prices or {}).items()}
        self._fx = {k.upper(): v for k, v in (fx or {}).items()}
        self._filing_dates = {k.upper(): v for k, v in (filing_dates or {}).items()}
        self._fail_with = {k.upper(): v for k, v in (fail_with or {}).items()}
        self._rate_limit_after = rate_limit_after
        self._fundamentals_calls = 0
        self.calls: list[tuple[str, str]] = []
        self.closed = False

    @property
    def name(self) -> str:
        return "fake"

    def lookup_company(self, ticker: str) -> CompanyInfo | None:
        self.calls.append(("lookup_company", ticker.upper()))
        return self._companies.get(ticker.upper())

    def fundamentals(self, ticker: str) -> FundamentalsBundle:
        sym = ticker.upper()
        self.calls.append(("fundamentals", sym))
        if (
            self._rate_limit_after is not None
            and self._fundamentals_calls >= self._rate_limit_after
        ):
            raise ProviderRateLimitError("fake quota exhausted")
        self._fundamentals_calls += 1
        if sym in self._fail_with:
            raise self._fail_with[sym]
        if sym in self._bundles:
            return self._bundles[sym]
        return FundamentalsBundle(
            info=self._companies.get(sym),
            annual=_empty_parsed(sym),
            quarterly=_empty_parsed(sym),
            filings=[],
        )

    def daily_prices(self, ticker: str, since: date | None) -> list[PriceBar]:
        self.calls.append(("daily_prices", ticker.upper()))
        return self._prices.get(ticker.upper(), [])

    def fx_rates(self, currency: str, since: date | None) -> list[FxRate]:
        self.calls.append(("fx_rates", currency.upper()))
        return self._fx.get(currency.upper(), [])

    def latest_filing_date(self, ticker: str) -> date | None:
        self.calls.append(("latest_filing_date", ticker.upper()))
        return self._filing_dates.get(ticker.upper())

    def close(self) -> None:
        self.closed = True
