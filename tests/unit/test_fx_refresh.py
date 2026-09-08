"""Unit tests for the bulk FX refresh orchestrator (M2.5 CLI wiring).

Exercised against a :class:`FakeProvider` so no HTTP happens, mirroring
``test_universe_refresh.py`` / ``test_prices_refresh.py``.
"""

from __future__ import annotations

from datetime import date

import duckdb

from bot.ingest.provider import FxRate
from bot.ingest.universe import distinct_non_usd_currencies, refresh_fx
from bot.storage.db import apply_schema, connect
from tests.fake_provider import FakeProvider


def _db() -> duckdb.DuckDBPyConnection:
    conn = connect(":memory:")
    apply_schema(conn)
    return conn


def _company(conn: duckdb.DuckDBPyConnection, ticker: str, currency: str | None) -> None:
    conn.execute(
        "INSERT INTO companies (ticker, name, currency, source) VALUES (?, ?, ?, ?)",
        [ticker, f"{ticker} Corp", currency, "fmp"],
    )


def _fx(currency: str, rate: float = 1.1) -> list[FxRate]:
    return [FxRate(date=date(2026, 1, 2), rate_to_usd=rate)]


def test_distinct_non_usd_currencies_excludes_usd() -> None:
    conn = _db()
    _company(conn, "AAA", "USD")
    _company(conn, "NESN", "CHF")
    _company(conn, "SAP", "EUR")
    _company(conn, "BMW", "EUR")  # duplicate EUR
    _company(conn, "NIL", None)
    assert distinct_non_usd_currencies(conn) == ["CHF", "EUR"]


def test_fx_refresh_requests_each_distinct_non_usd_currency() -> None:
    conn = _db()
    _company(conn, "AAA", "USD")
    _company(conn, "NESN", "CHF")
    _company(conn, "SAP", "EUR")
    provider = FakeProvider(fx={"CHF": _fx("CHF"), "EUR": _fx("EUR")})

    result = refresh_fx(conn, provider=provider)

    seen = sorted(c for method, c in provider.calls if method == "fx_rates")
    assert seen == ["CHF", "EUR"]  # USD never requested
    assert result.imported == 2


def test_fx_refresh_all_usd_universe_is_success_with_zero_total() -> None:
    conn = _db()
    _company(conn, "AAA", "USD")
    provider = FakeProvider()

    result = refresh_fx(conn, provider=provider)

    assert result.total == 0
    assert result.status == "success"
    assert not provider.calls  # no provider calls for an all-USD universe


def test_fx_refresh_isolates_per_currency_errors() -> None:
    conn = _db()
    _company(conn, "A", "CHF")
    _company(conn, "B", "EUR")
    _company(conn, "C", "GBP")

    class _PartlyBoomingProvider(FakeProvider):
        def fx_rates(self, currency: str, since: date | None) -> list[FxRate]:
            self.calls.append(("fx_rates", currency.upper()))
            if currency.upper() == "EUR":
                raise ValueError("fx down")
            return _fx(currency)

    provider = _PartlyBoomingProvider()

    result = refresh_fx(conn, provider=provider)

    assert result.imported == 2
    assert result.failed == 1
    assert [o.ticker for o in result.failures] == ["EUR"]


def test_fx_refresh_writes_summary_row() -> None:
    conn = _db()
    _company(conn, "NESN", "CHF")
    provider = FakeProvider(fx={"CHF": _fx("CHF")})

    result = refresh_fx(conn, provider=provider)

    row = conn.execute(
        "SELECT source, run_id FROM refresh_log WHERE source = 'fake_fx_universe'"
    ).fetchone()
    assert row is not None
    assert row[0] == "fake_fx_universe"
    assert row[1] == result.run_id


def test_fx_refresh_uses_the_shared_provider_for_every_currency() -> None:
    """One ``provider`` instance is passed in and reused for the whole run — no
    per-currency client construction happens inside the orchestrator."""
    conn = _db()
    _company(conn, "NESN", "CHF")
    _company(conn, "SAP", "EUR")
    provider = FakeProvider(fx={"CHF": _fx("CHF"), "EUR": _fx("EUR")})

    result = refresh_fx(conn, provider=provider)

    assert result.imported == 2
    fx_calls = [c for c in provider.calls if c[0] == "fx_rates"]
    assert sorted(fx_calls) == [("fx_rates", "CHF"), ("fx_rates", "EUR")]
