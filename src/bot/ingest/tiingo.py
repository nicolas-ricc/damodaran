"""Tiingo EOD price adapter internals — the keyed free-tier alternative to Stooq.

Stooq's anti-bot wall and per-ticker daily cap make it unfit for bulk universe
refresh (ADR 0007). Tiingo's daily EOD endpoint is a plain keyed REST API
(https://api.tiingo.com/tiingo/daily/<ticker>/prices) whose free tier covers a
full S&P 500 refresh; a 429 becomes :class:`TiingoRateLimitError` so the same
defer/resume machinery cuts cleanly.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import httpx

from bot.ingest.base import coerce_date
from bot.ingest.provider import PriceBar, ProviderRateLimitError
from bot.utils.logging import get_logger

log = get_logger(__name__)

TIINGO_PRICES_URL = "https://api.tiingo.com/tiingo/daily/{symbol}/prices"


class TiingoRateLimitError(ProviderRateLimitError):
    """Tiingo returned HTTP 429; the hourly/daily/monthly quota is spent."""


def tiingo_symbol(ticker: str) -> str:
    """Map our ticker spelling to Tiingo's (lowercase, ``.`` -> ``-``)."""
    return ticker.strip().lower().replace(".", "-")


def parse_tiingo_prices(rows: list[dict[str, Any]]) -> list[PriceBar]:
    """Parse Tiingo's daily-price JSON rows into :class:`PriceBar` (no market cap).

    Tiingo dates are ISO datetimes (``2026-09-15T00:00:00.000Z``); the date
    portion is what a daily bar needs.
    """
    bars: list[PriceBar] = []
    for row in rows:
        raw = row.get("date")
        parsed = coerce_date(raw[:10] if isinstance(raw, str) else raw)
        if parsed is None:
            continue
        close = row.get("close")
        volume = row.get("volume")
        bars.append(
            PriceBar(
                date=parsed,
                close=float(close) if close is not None else None,
                volume=float(volume) if volume is not None else None,
                market_cap=None,
            )
        )
    return bars


class TiingoClient:
    """Thin HTTP client for Tiingo's daily EOD endpoint."""

    def __init__(
        self, api_key: str, timeout: float = 30.0, transport: httpx.BaseTransport | None = None
    ) -> None:
        self._client = httpx.Client(
            timeout=timeout,
            transport=transport,
            headers={"Authorization": f"Token {api_key}", "Content-Type": "application/json"},
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> TiingoClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def daily_prices(self, ticker: str, since: date | None) -> list[PriceBar]:
        params: dict[str, str] = {}
        if since is not None:
            params["startDate"] = since.isoformat()
        r = self._client.get(TIINGO_PRICES_URL.format(symbol=tiingo_symbol(ticker)), params=params)
        if r.status_code == 429:
            raise TiingoRateLimitError("Tiingo quota exceeded (HTTP 429); resume later")
        if r.status_code == 404:
            return []
        r.raise_for_status()
        body = r.json()
        return parse_tiingo_prices(body if isinstance(body, list) else [])
