"""Tiingo EOD price client — symbol mapping, parsing, auth, rate-limit detection."""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from bot.ingest.provider import ProviderRateLimitError
from bot.ingest.tiingo import (
    TiingoClient,
    TiingoRateLimitError,
    parse_tiingo_prices,
    tiingo_symbol,
)

_SAMPLE = [
    {
        "date": "2026-09-14T00:00:00.000Z",
        "close": 229.87,
        "high": 230.44,
        "low": 227.51,
        "open": 228.10,
        "volume": 41250300,
    },
    {
        "date": "2026-09-15T00:00:00.000Z",
        "close": 231.42,
        "high": 232.18,
        "low": 229.94,
        "open": 230.60,
        "volume": 35520400,
    },
]


def test_tiingo_symbol_lowercases_and_maps_class_shares() -> None:
    assert tiingo_symbol("AAPL") == "aapl"
    assert tiingo_symbol("BRK.B") == "brk-b"


def test_parse_tiingo_prices_yields_bars_without_market_cap() -> None:
    bars = parse_tiingo_prices(_SAMPLE)
    assert [b.date for b in bars] == [date(2026, 9, 14), date(2026, 9, 15)]
    assert bars[0].close == pytest.approx(229.87)
    assert bars[0].volume == pytest.approx(41250300)
    assert all(b.market_cap is None for b in bars)


def test_parse_tiingo_prices_tolerates_empty_and_null_fields() -> None:
    assert parse_tiingo_prices([]) == []
    bars = parse_tiingo_prices([{"date": "2026-09-15T00:00:00.000Z", "close": None, "volume": None}])
    assert bars[0].close is None and bars[0].volume is None


def _client_with(handler: httpx.MockTransport, api_key: str = "tok") -> TiingoClient:
    return TiingoClient(api_key=api_key, transport=handler)


def test_daily_prices_sends_token_header_symbol_and_since() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization", "")
        seen["path"] = request.url.path
        seen["start"] = request.url.params.get("startDate", "")
        return httpx.Response(200, json=_SAMPLE)

    bars = _client_with(httpx.MockTransport(handler)).daily_prices("AAPL", since=date(2026, 9, 1))
    assert seen["auth"] == "Token tok"
    assert seen["path"] == "/tiingo/daily/aapl/prices"
    assert seen["start"] == "2026-09-01"
    assert len(bars) == 2


def test_daily_prices_unknown_ticker_404_returns_empty() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "Not found"})

    assert _client_with(httpx.MockTransport(handler)).daily_prices("NOPE", since=None) == []


def test_daily_prices_429_raises_rate_limit_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="Rate limit exceeded")

    with pytest.raises(TiingoRateLimitError):
        _client_with(httpx.MockTransport(handler)).daily_prices("AAPL", since=None)


def test_tiingo_rate_limit_is_a_provider_rate_limit() -> None:
    assert issubclass(TiingoRateLimitError, ProviderRateLimitError)
