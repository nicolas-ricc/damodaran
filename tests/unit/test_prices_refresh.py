"""Unit tests for the bulk price refresh orchestrator (M2.4 CLI wiring).

Exercised against a :class:`FakeProvider` so no HTTP happens, mirroring
``test_universe_refresh.py``.
"""

from __future__ import annotations

from datetime import date

import duckdb
import pytest

from bot.ingest.provider import PriceBar
from bot.ingest.universe import _last_weekday_before, refresh_prices
from bot.storage.db import apply_schema, connect
from tests.fake_provider import FakeProvider


def _db() -> duckdb.DuckDBPyConnection:
    conn = connect(":memory:")
    apply_schema(conn)
    return conn


def _seed_company(conn: duckdb.DuckDBPyConnection, ticker: str, currency: str | None) -> None:
    conn.execute(
        "INSERT INTO companies (ticker, name, currency, source) VALUES (?, ?, ?, ?)",
        [ticker, f"{ticker} Corp", currency, "fmp"],
    )


def _bar(day: date = date(2026, 1, 2), close: float = 10.5) -> list[PriceBar]:
    return [PriceBar(date=day, close=close, volume=900.0, market_cap=None)]


def test_refresh_prices_writes_bars_through_the_port() -> None:
    conn = _db()
    _seed_company(conn, "ACME", "USD")
    provider = FakeProvider(prices={"ACME": _bar()})

    result = refresh_prices(conn, provider=provider, tickers=["ACME"])

    assert result.imported == 1
    row = conn.execute(
        "SELECT close, currency FROM prices_daily WHERE ticker = 'ACME'"
    ).fetchone()
    assert row == (10.5, "USD")


def test_price_refresh_passes_each_tickers_currency() -> None:
    conn = _db()
    _seed_company(conn, "AAA", "USD")
    _seed_company(conn, "NESN", "CHF")
    provider = FakeProvider(prices={"AAA": _bar(), "NESN": _bar()})

    result = refresh_prices(conn, provider=provider, tickers=["AAA", "NESN"])

    assert result.imported == 2
    assert result.failed == 0
    currencies = dict(
        conn.execute("SELECT ticker, currency FROM prices_daily").fetchall()
    )
    assert currencies == {"AAA": "USD", "NESN": "CHF"}


def test_price_refresh_ticker_without_company_uses_none_currency() -> None:
    conn = _db()
    provider = FakeProvider(prices={"NOPE": _bar()})

    # No companies row for NOPE -> currency None, still imported (not a failure).
    result = refresh_prices(conn, provider=provider, tickers=["NOPE"])

    currency = conn.execute(
        "SELECT currency FROM prices_daily WHERE ticker = 'NOPE'"
    ).fetchone()
    assert currency == (None,)
    assert result.imported == 1
    assert result.failed == 0


def test_price_refresh_isolates_per_ticker_errors() -> None:
    conn = _db()
    for t in ("AAA", "BBB"):
        _seed_company(conn, t, "USD")

    class _PartlyBoomingProvider(FakeProvider):
        def daily_prices(self, ticker: str, since: date | None) -> list[PriceBar]:
            self.calls.append(("daily_prices", ticker.upper()))
            if ticker.upper() == "BAD":
                raise ValueError("kaboom")
            return _bar()

    provider = _PartlyBoomingProvider()

    result = refresh_prices(conn, provider=provider, tickers=["AAA", "BAD", "BBB"])

    assert result.imported == 2
    assert result.failed == 1
    assert [o.ticker for o in result.failures] == ["BAD"]
    assert result.failures[0].error_message == "kaboom"


def test_price_refresh_writes_summary_row() -> None:
    conn = _db()
    _seed_company(conn, "AAA", "USD")
    provider = FakeProvider(prices={"AAA": _bar()})

    result = refresh_prices(conn, provider=provider, tickers=["AAA"])

    row = conn.execute(
        "SELECT source, run_id, rows_affected FROM refresh_log WHERE source = 'fake_prices_universe'"
    ).fetchone()
    assert row is not None
    assert row[0] == "fake_prices_universe"
    assert row[1] == result.run_id
    assert row[2] == result.imported


def test_price_refresh_empty_universe_is_success() -> None:
    conn = _db()
    result = refresh_prices(conn, provider=FakeProvider(), tickers=[])
    assert result.total == 0
    assert result.status == "success"


def test_price_refresh_derives_since_from_max_price_date_plus_one_day() -> None:
    """When ``since_date`` is omitted, each ticker's fetch starts the day *after*
    the latest date already stored for it (via ``_max_price_date``, moved
    alongside ``upsert_prices_daily``) — matching the pre-port incremental
    semantics exactly."""
    conn = _db()
    _seed_company(conn, "ACME", "USD")
    conn.execute(
        "INSERT INTO prices_daily (ticker, date, close, source) "
        "VALUES ('ACME', '2026-01-05', 100.0, 'fmp')"
    )
    seen_since: list[date | None] = []

    class _RecordingProvider(FakeProvider):
        def daily_prices(self, ticker: str, since: date | None) -> list[PriceBar]:
            self.calls.append(("daily_prices", ticker.upper()))
            seen_since.append(since)
            return []

    result = refresh_prices(conn, provider=_RecordingProvider(), tickers=["ACME"])

    assert seen_since == [date(2026, 1, 6)]
    assert result.imported == 1


def test_price_refresh_since_date_wins_when_later_than_max_price_date() -> None:
    """``since_date`` overrides the derived +1-day bound only when it is later."""
    conn = _db()
    _seed_company(conn, "ACME", "USD")
    conn.execute(
        "INSERT INTO prices_daily (ticker, date, close, source) "
        "VALUES ('ACME', '2026-01-05', 100.0, 'fmp')"
    )
    seen_since: list[date | None] = []

    class _RecordingProvider(FakeProvider):
        def daily_prices(self, ticker: str, since: date | None) -> list[PriceBar]:
            self.calls.append(("daily_prices", ticker.upper()))
            seen_since.append(since)
            return []

    refresh_prices(
        conn, provider=_RecordingProvider(), tickers=["ACME"], since_date=date(2026, 1, 10)
    )
    assert seen_since == [date(2026, 1, 10)]  # later than max+1 (2026-01-06) -> wins

    seen_since.clear()
    refresh_prices(
        conn, provider=_RecordingProvider(), tickers=["ACME"], since_date=date(2026, 1, 1)
    )
    assert seen_since == [date(2026, 1, 6)]  # earlier than max+1 -> max+1 wins


def test_price_refresh_drops_bars_at_or_before_the_last_stored_date() -> None:
    """Defensive post-filter: even if the provider returns overlapping/duplicate
    dates, only bars strictly after the last stored date are upserted."""
    conn = _db()
    _seed_company(conn, "ACME", "USD")
    conn.execute(
        "INSERT INTO prices_daily (ticker, date, close, source) "
        "VALUES ('ACME', '2026-01-05', 100.0, 'fmp')"
    )
    provider = FakeProvider(
        prices={
            "ACME": [
                PriceBar(date=date(2026, 1, 4), close=1.0, volume=None, market_cap=None),
                PriceBar(date=date(2026, 1, 5), close=2.0, volume=None, market_cap=None),
                PriceBar(date=date(2026, 1, 6), close=3.0, volume=None, market_cap=None),
            ]
        }
    )

    result = refresh_prices(conn, provider=provider, tickers=["ACME"])

    assert result.outcomes[0].rows_affected == 1
    rows = conn.execute(
        "SELECT date, close FROM prices_daily WHERE ticker = 'ACME' ORDER BY date"
    ).fetchall()
    assert [(str(d), c) for d, c in rows] == [("2026-01-05", 100.0), ("2026-01-06", 3.0)]


def test_price_refresh_uses_the_shared_provider_for_every_ticker() -> None:
    """One ``provider`` instance is passed in and reused for the whole run — no
    per-ticker client construction happens inside the orchestrator."""
    conn = _db()
    for t in ("AAA", "BBB"):
        _seed_company(conn, t, "USD")
    provider = FakeProvider(prices={"AAA": _bar(), "BBB": _bar()})

    result = refresh_prices(conn, provider=provider, tickers=["AAA", "BBB"])

    assert result.imported == 2
    price_calls = [c for c in provider.calls if c[0] == "daily_prices"]
    assert sorted(price_calls) == [("daily_prices", "AAA"), ("daily_prices", "BBB")]


def test_only_missing_skips_tickers_that_already_have_prices() -> None:
    conn = _db()
    _seed_company(conn, "HAVE", "USD")
    _seed_company(conn, "MISS", "USD")
    conn.execute(
        "INSERT INTO prices_daily (ticker, date, close, source) VALUES ('HAVE', ?, 5.0, 'x')",
        [date(2026, 1, 2)],
    )

    class _RecordingProvider(FakeProvider):
        def __init__(self) -> None:
            super().__init__(prices={"MISS": _bar()})
            self.requested: list[str] = []

        def daily_prices(self, ticker, since):  # type: ignore[no-untyped-def]
            self.requested.append(ticker.upper())
            return super().daily_prices(ticker, since)

    provider = _RecordingProvider()
    result = refresh_prices(
        conn, provider=provider, tickers=["HAVE", "MISS"], only_missing=True
    )

    assert provider.requested == ["MISS"]
    assert result.imported == 1
    assert result.total == 1


# --- #136: stale-first ordering, up-to-date skip --------------------------------

_TODAY = date(2026, 10, 28)  # a Wednesday
_LAST_WEEKDAY = date(2026, 10, 27)


def _seed_price(conn: duckdb.DuckDBPyConnection, ticker: str, day: date) -> None:
    conn.execute(
        "INSERT INTO prices_daily (ticker, date, close, source) VALUES (?, ?, 1.0, 'fake')",
        [ticker, day.isoformat()],
    )


def _price_calls(provider: FakeProvider) -> list[str]:
    return [ticker for kind, ticker in provider.calls if kind == "daily_prices"]


def _priced(conn: duckdb.DuckDBPyConnection) -> set[str]:
    return {r[0] for r in conn.execute("SELECT DISTINCT ticker FROM prices_daily").fetchall()}


def test_two_rate_limited_runs_import_distinct_tickers() -> None:
    conn = _db()
    tickers = [f"T{i}" for i in range(1, 7)]
    bars = {t: _bar(_LAST_WEEKDAY) for t in tickers}

    first = refresh_prices(
        conn,
        provider=FakeProvider(prices=bars, prices_rate_limit_after=2),
        tickers=tickers,
        today=_TODAY,
    )
    second = refresh_prices(
        conn,
        provider=FakeProvider(prices=bars, prices_rate_limit_after=2),
        tickers=tickers,
        today=_TODAY,
    )

    assert (first.imported, first.deferred) == (2, 4)
    assert (second.imported, second.skipped, second.deferred) == (2, 2, 2)
    imported = {
        o.ticker for r in (first, second) for o in r.outcomes if o.status == "imported"
    }
    assert imported == {"T1", "T2", "T3", "T4"}


def test_never_priced_before_stale_before_fresh() -> None:
    conn = _db()
    _seed_price(conn, "TODAY", _TODAY)
    _seed_price(conn, "FRESHER", date(2026, 10, 20))
    _seed_price(conn, "STALE", date(2026, 9, 17))
    provider = FakeProvider()

    result = refresh_prices(
        conn, provider=provider, tickers=["TODAY", "FRESHER", "STALE", "NEW"], today=_TODAY
    )

    assert _price_calls(provider) == ["NEW", "STALE", "FRESHER"]
    assert [o.ticker for o in result.outcomes] == ["NEW", "STALE", "FRESHER", "TODAY"]
    assert result.outcomes[-1].status == "skipped"


def test_stale_first_orders_oldest_first_and_keeps_csv_order_on_ties() -> None:
    conn = _db()
    _seed_price(conn, "B", date(2026, 9, 17))
    _seed_price(conn, "A", date(2026, 9, 17))
    _seed_price(conn, "D", date(2026, 10, 1))
    _seed_price(conn, "C", date(2026, 8, 1))
    provider = FakeProvider()

    refresh_prices(conn, provider=provider, tickers=["B", "A", "D", "C", "Y", "X"], today=_TODAY)

    assert _price_calls(provider) == ["Y", "X", "C", "B", "A", "D"]


def test_stale_first_matches_tickers_case_insensitively() -> None:
    conn = _db()
    _seed_price(conn, "AAPL", date(2026, 10, 1))
    provider = FakeProvider()

    refresh_prices(conn, provider=provider, tickers=["aapl", "MSFT"], today=_TODAY)

    assert _price_calls(provider) == ["MSFT", "AAPL"]


def test_unpriceable_ticker_does_not_starve_the_rest() -> None:
    conn = _db()
    tickers = ["GONE", "A", "B", "C"]
    bars = {t: _bar(_LAST_WEEKDAY) for t in ("A", "B", "C")}

    runs = []
    for _ in range(2):
        provider = FakeProvider(prices=bars, prices_rate_limit_after=2)
        result = refresh_prices(conn, provider=provider, tickers=tickers, today=_TODAY)
        runs.append((_price_calls(provider), result.status))

    assert runs == [(["GONE", "A", "B"], "success"), (["GONE", "B", "C"], "success")]
    assert _priced(conn) == {"A", "B"}


def test_up_to_date_tickers_are_skipped_without_a_request() -> None:
    conn = _db()
    _seed_price(conn, "UP", _LAST_WEEKDAY)
    _seed_price(conn, "OLD", date(2026, 10, 23))
    provider = FakeProvider()

    result = refresh_prices(conn, provider=provider, tickers=["UP", "OLD"], today=_TODAY)

    assert _price_calls(provider) == ["OLD"]
    assert (result.skipped, result.imported) == (1, 1)


def test_run_over_an_up_to_date_universe_defers_nothing() -> None:
    conn = _db()
    for t in ("A", "B", "C"):
        _seed_price(conn, t, _LAST_WEEKDAY)
    provider = FakeProvider(prices_rate_limit_after=0)

    result = refresh_prices(conn, provider=provider, tickers=["A", "B", "C"], today=_TODAY)

    assert _price_calls(provider) == []
    assert result.deferred == 0
    assert result.skipped == 3
    assert result.status == "success"


def test_fully_rate_limited_run_is_a_success() -> None:
    conn = _db()
    for t in ("A", "B"):
        _seed_price(conn, t, date(2026, 9, 17))
    provider = FakeProvider(prices_rate_limit_after=0)

    result = refresh_prices(conn, provider=provider, tickers=["A", "B", "NEW"], today=_TODAY)

    assert result.deferred == 3
    assert result.failed == 0
    assert result.status == "success"


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 10, 26), date(2026, 10, 23)),  # Mon -> Fri
        (date(2026, 10, 28), date(2026, 10, 27)),  # Wed -> Tue
        (date(2026, 10, 25), date(2026, 10, 23)),  # Sun -> Fri
        (date(2026, 10, 24), date(2026, 10, 23)),  # Sat -> Fri
    ],
)
def test_last_weekday_before(day: date, expected: date) -> None:
    assert _last_weekday_before(day) == expected


def test_only_missing_still_drops_priced_tickers() -> None:
    conn = _db()
    _seed_price(conn, "P", date(2026, 9, 17))
    provider = FakeProvider()

    refresh_prices(
        conn, provider=provider, tickers=["P", "N1", "N2"], only_missing=True, today=_TODAY
    )

    assert _price_calls(provider) == ["N1", "N2"]
