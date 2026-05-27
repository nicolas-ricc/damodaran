"""Financial Modeling Prep (FMP) adapter — company lookup."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from bot.utils.logging import get_logger

log = get_logger(__name__)

FMP_BASE_URL = "https://financialmodelingprep.com/api/v3"


class FmpError(Exception):
    """Raised when FMP returns an error payload (HTTP 200 with error body)."""


@dataclass
class CompanyInfo:
    """Normalized company data returned by FmpClient.lookup_company."""

    ticker: str
    name: str
    currency: str | None
    country: str | None
    exchange: str | None
    industry: str | None
    isin: str | None
    cik: str | None
    is_actively_trading: bool
    source: str = "fmp"

    @property
    def status(self) -> str:
        return "active" if self.is_actively_trading else "delisted"


class FmpClient:
    """Thin HTTP client over the Financial Modeling Prep v3 REST API.

    Authentication is via ``apikey`` query parameter on every request.
    API key is read from the ``api_key`` constructor argument; the caller
    should pass ``Settings().fmp_api_key``.
    """

    def __init__(self, api_key: str, timeout: float = 30.0) -> None:
        if not api_key:
            raise ValueError("FMP API key must not be empty")
        self._api_key = api_key
        self._client = httpx.Client(
            base_url=FMP_BASE_URL,
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

    def _get(self, path: str, **params: Any) -> Any:
        response = self._client.get(path, params={"apikey": self._api_key, **params})
        response.raise_for_status()
        return response.json()

    def lookup_company(self, ticker: str) -> CompanyInfo | None:
        """Return normalized company info for *ticker*, or ``None`` if FMP has no profile.

        Works for US (e.g. ``AAPL``), Swiss (``NESN.SW``), and Japanese (``7203.T``)
        tickers — any symbol accepted by the FMP ``/profile/{symbol}`` endpoint.
        """
        ticker = ticker.upper()
        data: Any = self._get(f"/profile/{ticker}")
        if isinstance(data, dict):
            msg = str(data.get("Error Message") or data)
            log.warning("fmp.lookup_company.error", ticker=ticker, error=msg)
            raise FmpError(msg)
        if not data:
            log.info("fmp.lookup_company.not_found", ticker=ticker)
            return None
        profile: dict[str, Any] = data[0]
        cik_raw = profile.get("cik")
        # Only US companies have a CIK; zero-pad to 10 digits when present.
        cik: str | None = None
        if cik_raw and str(cik_raw).strip():
            cik = str(cik_raw).strip().zfill(10)
        return CompanyInfo(
            ticker=ticker,
            name=profile.get("companyName") or ticker,
            currency=profile.get("currency") or None,
            country=profile.get("country") or None,
            exchange=profile.get("exchangeShortName") or None,
            industry=profile.get("industry") or None,
            isin=profile.get("isin") or None,
            cik=cik,
            is_actively_trading=bool(profile.get("isActivelyTrading", True)),
        )
