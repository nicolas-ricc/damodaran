"""Stooq EOD price adapter internals — free CSV endpoint, no API key.

Stooq serves plain-CSV daily history at ``https://stooq.com/q/d/l/``. There is
no auth and no documented quota; past a soft daily hit limit the body becomes
the plain-text marker ``Exceeded the daily hits limit`` (HTTP 200), which this
module converts into :class:`StooqRateLimitError` so the bulk refresh defers
the remaining tickers exactly like an FMP 429.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import cast

import httpx

from bot.ingest.base import coerce_date
from bot.ingest.provider import PriceBar, ProviderRateLimitError
from bot.utils.logging import get_logger

log = get_logger(__name__)

STOOQ_DAILY_URL = "https://stooq.com/q/d/l/"
_RATE_LIMIT_MARKER = "exceeded the daily hits limit"


class StooqRateLimitError(ProviderRateLimitError):
    """Stooq answered with its daily-hit-limit marker; retry tomorrow."""


def stooq_symbol(ticker: str) -> str:
    """Map our ticker spelling to Stooq's (lowercase, ``.`` -> ``-``, ``.us``)."""
    return ticker.strip().lower().replace(".", "-") + ".us"


def parse_stooq_csv(text: str) -> list[PriceBar]:
    """Parse a Stooq daily CSV body into :class:`PriceBar` rows (no market cap)."""
    body = text.strip()
    if not body or body.lower().startswith("no data"):
        return []
    bars: list[PriceBar] = []
    for row in csv.DictReader(io.StringIO(body)):
        parsed = coerce_date(cast(str | None, row.get("Date")))
        if parsed is None:
            continue
        close_raw = cast(str | None, row.get("Close"))
        volume_raw = cast(str | None, row.get("Volume"))
        close = float(close_raw) if (close_raw and close_raw != "") else None
        volume = float(volume_raw) if (volume_raw and volume_raw != "") else None
        bars.append(
            PriceBar(
                date=parsed,
                close=close,
                volume=volume,
                market_cap=None,
            )
        )
    return bars


class StooqClient:
    """Thin HTTP client for Stooq's daily CSV endpoint."""

    def __init__(self, timeout: float = 30.0, transport: httpx.BaseTransport | None = None) -> None:
        self._client = httpx.Client(timeout=timeout, follow_redirects=True, transport=transport)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> StooqClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def daily_prices(self, ticker: str, since: date | None) -> list[PriceBar]:
        params: dict[str, str] = {"s": stooq_symbol(ticker), "i": "d"}
        if since is not None:
            params["d1"] = since.strftime("%Y%m%d")
        r = self._client.get(STOOQ_DAILY_URL, params=params)
        r.raise_for_status()
        if _RATE_LIMIT_MARKER in r.text[:200].lower():
            raise StooqRateLimitError("Stooq daily hit limit reached; resume tomorrow")
        return parse_stooq_csv(r.text)
