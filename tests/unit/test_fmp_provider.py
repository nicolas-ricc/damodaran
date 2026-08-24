"""FmpProvider: FMP JSON in, canonical records out."""

from __future__ import annotations

from datetime import date
from typing import Any

from bot.ingest.fmp import FmpProvider
from bot.ingest.provider import FundamentalsBundle, FxRate, MarketDataProvider, PriceBar


class _StubClient:
    """Stands in for FmpClient; returns canned endpoint payloads."""

    def __init__(self) -> None:
        self.closed = False

    def historical_prices(
        self, ticker: str, *, start: date | None = None, end: date | None = None
    ) -> list[dict[str, Any]]:
        return [{"date": "2026-01-02", "close": 10.5, "volume": 900.0, "market_cap": None}]

    def historical_fx(
        self, currency: str, *, start: date | None = None, end: date | None = None
    ) -> list[dict[str, Any]]:
        return [{"date": "2026-01-02", "rate_to_usd": 1.08}]

    def income_statement(
        self, ticker: str, *, period: str, limit: int | None = None
    ) -> list[dict[str, Any]]:
        return []

    def balance_sheet(self, ticker: str, *, period: str) -> list[dict[str, Any]]:
        return []

    def cash_flow(self, ticker: str, *, period: str) -> list[dict[str, Any]]:
        return []

    def lookup_company(self, ticker: str) -> None:
        return None

    def close(self) -> None:
        self.closed = True


def _provider() -> FmpProvider:
    p = FmpProvider(api_key="test-key")
    p._client = _StubClient()  # type: ignore[assignment]
    return p


def test_fmp_provider_satisfies_the_protocol() -> None:
    p: MarketDataProvider = _provider()  # mypy enforces structural conformance
    assert p.name == "fmp"
    assert isinstance(p, MarketDataProvider)


def test_daily_prices_become_price_bars() -> None:
    bars = _provider().daily_prices("ACME", since=None)
    assert bars == [
        PriceBar(date=date(2026, 1, 2), close=10.5, volume=900.0, market_cap=None)
    ]


def test_fx_rates_become_fx_records() -> None:
    rates = _provider().fx_rates("EUR", since=None)
    assert rates == [FxRate(date=date(2026, 1, 2), rate_to_usd=1.08)]


def test_fundamentals_returns_a_bundle_even_when_empty() -> None:
    bundle = _provider().fundamentals("ACME")
    assert isinstance(bundle, FundamentalsBundle)
    assert bundle.info is None
    assert bundle.annual.annual == []
    assert bundle.filings == []


def test_close_closes_the_underlying_client() -> None:
    p = _provider()
    stub = p._client
    p.close()
    assert stub.closed  # type: ignore[union-attr]
    assert p._client is None


def test_lazily_opens_one_client_shared_across_many_calls(
    monkeypatch: Any,
) -> None:
    """One FmpProvider must open a single FmpClient (one connection pool) for
    its whole lifetime — not a fresh one per fundamentals/probe call — so a
    bulk universe refresh over hundreds of tickers reuses one TLS session."""
    instances: list[_StubClient] = []

    def _make_client(api_key: str, timeout: float = 30.0) -> _StubClient:
        stub = _StubClient()
        instances.append(stub)
        return stub

    monkeypatch.setattr("bot.ingest.fmp.FmpClient", _make_client)

    p = FmpProvider(api_key="test-key")
    p.fundamentals("AAA")
    p.latest_filing_date("AAA")
    p.fundamentals("BBB")

    assert len(instances) == 1, f"expected one shared client, got {len(instances)}"
