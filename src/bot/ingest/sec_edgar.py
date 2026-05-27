"""SEC EDGAR adapter — fetch + parse + import US company fundamentals."""

from __future__ import annotations

from typing import Any

import httpx

from bot.utils.logging import get_logger

log = get_logger(__name__)

TICKER_LOOKUP_URL = "https://www.sec.gov/files/company_tickers.json"
COMPANY_FACTS_URL_TEMPLATE = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"


class SecEdgarClient:
    """Thin HTTP client for SEC EDGAR public endpoints.

    SEC requires every request to carry a User-Agent identifying the requester
    (per https://www.sec.gov/os/accessing-edgar-data).
    """

    def __init__(self, user_agent: str, timeout: float = 30.0) -> None:
        if not user_agent or "@" not in user_agent:
            raise ValueError(
                "SEC requires a User-Agent identifying you. "
                "Format: 'Your Name email@example.com'"
            )
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": user_agent, "Accept": "application/json"},
            follow_redirects=True,
        )
        self._ticker_table: dict[str, str] | None = None

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> SecEdgarClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _load_ticker_table(self) -> dict[str, str]:
        if self._ticker_table is not None:
            return self._ticker_table
        r = self._client.get(TICKER_LOOKUP_URL)
        r.raise_for_status()
        data = r.json()
        # File is { "0": {"cik_str": 320193, "ticker": "AAPL", ...}, ... }
        self._ticker_table = {
            entry["ticker"].upper(): str(entry["cik_str"]).zfill(10)
            for entry in data.values()
        }
        log.info("sec.ticker_table.loaded", count=len(self._ticker_table))
        return self._ticker_table

    def lookup_cik(self, ticker: str) -> str | None:
        """Return zero-padded 10-digit CIK for a ticker, or None if not found."""
        table = self._load_ticker_table()
        return table.get(ticker.upper())

    def fetch_company_facts(self, cik: str) -> dict[str, Any]:
        """Fetch XBRL company facts JSON for the given CIK (10-digit zero-padded)."""
        if len(cik) != 10 or not cik.isdigit():
            raise ValueError(f"CIK must be 10 digits zero-padded; got {cik!r}")
        url = COMPANY_FACTS_URL_TEMPLATE.format(cik=cik)
        r = self._client.get(url)
        r.raise_for_status()
        result: dict[str, Any] = r.json()
        return result
