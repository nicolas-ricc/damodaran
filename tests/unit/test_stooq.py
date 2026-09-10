"""Stooq CSV client — symbol mapping, parsing, rate-limit detection."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import pytest

from bot.ingest.provider import ProviderRateLimitError
from bot.ingest.stooq import StooqClient, StooqRateLimitError, parse_stooq_csv, stooq_symbol

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "stooq"


def test_stooq_symbol_lowercases_and_appends_us_suffix() -> None:
    assert stooq_symbol("AAPL") == "aapl.us"


def test_stooq_symbol_maps_class_share_dot_to_dash() -> None:
    assert stooq_symbol("BRK.B") == "brk-b.us"


def test_parse_stooq_csv_yields_price_bars_without_market_cap() -> None:
    bars = parse_stooq_csv((FIXTURES / "aapl_daily.csv").read_text(encoding="utf-8"))
    assert len(bars) == 3
    assert bars[0].date == date(2026, 9, 3)
    assert bars[0].close == pytest.approx(229.87)
    assert bars[0].volume == pytest.approx(41250300)
    assert all(b.market_cap is None for b in bars)


def test_parse_stooq_csv_tolerates_empty_body_and_no_data_marker() -> None:
    assert parse_stooq_csv("") == []
    assert parse_stooq_csv("No data") == []


def _client_with(handler: httpx.MockTransport) -> StooqClient:
    return StooqClient(transport=handler)


def test_daily_prices_requests_symbol_and_since_and_parses() -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, text=(FIXTURES / "aapl_daily.csv").read_text(encoding="utf-8"))

    bars = _client_with(httpx.MockTransport(handler)).daily_prices("AAPL", since=date(2026, 9, 1))
    assert seen["s"] == "aapl.us"
    assert seen["i"] == "d"
    assert seen["d1"] == "20260901"
    assert len(bars) == 3


def test_daily_hit_limit_raises_rate_limit_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text="Exceeded the daily hits limit")

    with pytest.raises(StooqRateLimitError):
        _client_with(httpx.MockTransport(handler)).daily_prices("AAPL", since=None)


def test_stooq_rate_limit_is_a_provider_rate_limit() -> None:
    assert issubclass(StooqRateLimitError, ProviderRateLimitError)
