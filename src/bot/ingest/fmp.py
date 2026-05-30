"""Financial Modeling Prep (FMP) adapter — HTTP client + auth + ticker lookup.

Thin client over the FMP REST API. Plays the same role as ``SecEdgarClient`` but
for global coverage (international fundamentals + EOD prices). The API key is read
from ``BOT_FMP_API_KEY`` (see :class:`bot.config.Settings`) and passed to FMP as
the ``apikey`` query parameter on every request.

Only the ticker lookup and exchange/country listing endpoints are implemented
here (M2.1). Fundamentals ingestion lands in a later slice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from bot.utils.logging import get_logger

log = get_logger(__name__)

BASE_URL = "https://financialmodelingprep.com/api/v3"


@dataclass(frozen=True)
class CompanyInfo:
    """Normalized basic company info from an FMP profile lookup."""

    ticker: str
    name: str
    exchange: str | None
    exchange_short_name: str | None
    country: str | None
    currency: str | None
    sector: str | None
    industry: str | None
    is_actively_trading: bool


class FmpClient:
    """Thin HTTP client for Financial Modeling Prep public endpoints.

    FMP authenticates via an ``apikey`` query parameter on every request. The key
    is required — there is no anonymous access — so construction fails fast on an
    empty key.
    """

    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        if not api_key:
            raise ValueError(
                "FMP API key is required. Set BOT_FMP_API_KEY (no default)."
            )
        self._api_key = api_key
        self._client = httpx.Client(
            base_url=BASE_URL,
            timeout=timeout,
            headers={"Accept": "application/json"},
            follow_redirects=True,
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> FmpClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        """GET ``path`` with the API key injected. Returns parsed JSON."""
        query: dict[str, Any] = dict(params or {})
        query["apikey"] = self._api_key
        r = self._client.get(path, params=query)
        r.raise_for_status()
        return r.json()

    def lookup_company(self, ticker: str) -> CompanyInfo | None:
        """Return normalized basic info for ``ticker``, or None if not found.

        FMP's ``/profile/{ticker}`` endpoint returns a JSON array: a single
        profile object for a known symbol, or an empty array for an unknown one.
        """
        data = self._get(f"/profile/{ticker.upper()}")
        if not isinstance(data, list) or not data:
            log.info("fmp.lookup_company.not_found", ticker=ticker)
            return None
        profile = data[0]
        info = CompanyInfo(
            ticker=str(profile.get("symbol", ticker)).upper(),
            name=str(profile.get("companyName", "")),
            exchange=_str_or_none(profile.get("exchange")),
            exchange_short_name=_str_or_none(profile.get("exchangeShortName")),
            country=_str_or_none(profile.get("country")),
            currency=_str_or_none(profile.get("currency")),
            sector=_str_or_none(profile.get("sector")),
            industry=_str_or_none(profile.get("industry")),
            is_actively_trading=bool(profile.get("isActivelyTrading", False)),
        )
        log.info("fmp.lookup_company.found", ticker=info.ticker, country=info.country)
        return info

    def available_exchanges(self) -> list[dict[str, Any]]:
        """Return FMP's list of available exchanges (for sanity checks)."""
        data = self._get("/available-exchanges")
        if not isinstance(data, list):
            return []
        return [e for e in data if isinstance(e, dict)]


def _str_or_none(value: Any) -> str | None:
    """Coerce to a non-empty string, mapping empty/None to None."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None
