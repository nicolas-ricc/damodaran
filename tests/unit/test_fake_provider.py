"""The fake provider is a real adapter: it must satisfy the same Protocol."""

from __future__ import annotations

import pytest

from bot.ingest.provider import MarketDataProvider, ProviderRateLimitError
from tests.fake_provider import FakeProvider


def test_fake_satisfies_the_protocol() -> None:
    p: MarketDataProvider = FakeProvider()  # mypy checks structure
    assert isinstance(p, MarketDataProvider)
    assert p.name == "fake"
    assert p.lookup_company("ACME") is None
    assert p.daily_prices("ACME", since=None) == []
    assert p.fx_rates("EUR", since=None) == []
    assert p.latest_filing_date("ACME") is None
    p.close()


def test_rate_limit_after_fires_on_the_nth_fundamentals_call() -> None:
    p = FakeProvider(rate_limit_after=1)
    p.fundamentals("AAA")  # first call OK (empty bundle)
    with pytest.raises(ProviderRateLimitError):
        p.fundamentals("BBB")


def test_fail_with_raises_for_the_configured_ticker_only() -> None:
    p = FakeProvider(fail_with={"BAD": RuntimeError("boom")})
    p.fundamentals("GOOD")
    with pytest.raises(RuntimeError, match="boom"):
        p.fundamentals("BAD")
