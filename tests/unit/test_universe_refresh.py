"""Unit tests for the bulk universe refresh orchestrator (M2.6).

These exercise the orchestration logic — universe parsing, incremental skip via
``filings_log``, per-ticker error isolation, status thresholds, progress logging
and the ``refresh_log`` summary — against a :class:`FakeProvider` so no HTTP
happens.
"""

from __future__ import annotations

import inspect
from datetime import date
from pathlib import Path
from typing import Any, get_args

import duckdb
import pytest

from bot.ingest.provider import ProviderRateLimitError
from bot.ingest.universe import (
    TickerOutcome,
    TickerStatus,
    default_universe_path,
    latest_local_filing_date,
    load_universe,
    refresh_universe,
    upsert_prices_daily,
)
from bot.storage.db import apply_schema, connect
from bot.utils.fx import upsert_fx_rates
from tests.fake_provider import FakeProvider


def _db() -> duckdb.DuckDBPyConnection:
    conn = connect(":memory:")
    apply_schema(conn)
    return conn


# ---------- universe parsing ----------


def test_load_universe_parses_ticker_column(tmp_path: Path) -> None:
    f = tmp_path / "u.csv"
    f.write_text("ticker,name\nAAPL,Apple\nmsft,Microsoft\nNESN.SW,Nestle\n")
    assert load_universe(f) == ["AAPL", "MSFT", "NESN.SW"]


def test_load_universe_skips_blanks_dupes_and_comments(tmp_path: Path) -> None:
    f = tmp_path / "u.csv"
    f.write_text("# a comment\nticker\nAAPL\n\nAAPL\n  msft  \n")
    assert load_universe(f) == ["AAPL", "MSFT"]


def test_load_universe_first_column_without_header(tmp_path: Path) -> None:
    f = tmp_path / "u.csv"
    f.write_text("AAPL\nMSFT\n")
    assert load_universe(f) == ["AAPL", "MSFT"]


def test_default_universe_ships_and_is_sizeable() -> None:
    tickers = load_universe(default_universe_path())
    assert len(tickers) >= 400
    assert "AAPL" in tickers
    # US-only S&P 500 constituents in FMP format (hyphens, not dots).
    assert not any("." in t for t in tickers)
    assert len(set(tickers)) == len(tickers)  # de-duplicated


# ---------- incremental skip ----------


def test_skips_ticker_when_remote_filing_not_advanced() -> None:
    conn = _db()
    conn.execute(
        "INSERT INTO filings_log (ticker, filing_type, filing_date, source) "
        "VALUES ('AAPL', 'FY', '2023-11-03', 'fake')"
    )
    provider = FakeProvider(filing_dates={"AAPL": date(2023, 11, 3)})

    result = refresh_universe(conn, provider=provider, tickers=["AAPL"])

    assert ("fundamentals", "AAPL") not in provider.calls  # importer never invoked
    assert result.skipped == 1
    assert result.imported == 0
    assert result.status == "success"


def test_imports_when_remote_filing_advanced() -> None:
    conn = _db()
    conn.execute(
        "INSERT INTO filings_log (ticker, filing_type, filing_date, source) "
        "VALUES ('AAPL', 'FY', '2023-11-03', 'fake')"
    )
    provider = FakeProvider(filing_dates={"AAPL": date(2024, 11, 1)})

    result = refresh_universe(conn, provider=provider, tickers=["AAPL"])

    assert result.imported == 1
    assert result.skipped == 0


def test_imports_when_no_local_filing_history() -> None:
    conn = _db()
    # Probe would say "unchanged", but with no local history we must import.
    provider = FakeProvider(filing_dates={"AAPL": date(2020, 1, 1)})

    result = refresh_universe(conn, provider=provider, tickers=["AAPL"])

    assert result.imported == 1


def test_probe_failure_falls_through_to_import() -> None:
    conn = _db()
    conn.execute(
        "INSERT INTO filings_log (ticker, filing_type, filing_date, source) "
        "VALUES ('AAPL', 'FY', '2023-11-03', 'fake')"
    )

    class _BoomingProvider(FakeProvider):
        def latest_filing_date(self, ticker: str) -> date | None:
            raise RuntimeError("FMP down")

    provider = _BoomingProvider()

    result = refresh_universe(conn, provider=provider, tickers=["AAPL"])

    assert result.imported == 1
    assert result.failed == 0


def test_latest_local_filing_date_reads_max() -> None:
    conn = _db()
    for d in ("2022-11-01", "2023-11-03", "2021-10-29"):
        conn.execute(
            "INSERT INTO filings_log (ticker, filing_type, filing_date, source) "
            "VALUES ('AAPL', 'FY', ?, 'fmp')",
            [d],
        )
    assert latest_local_filing_date(conn, "aapl", "fmp") == date(2023, 11, 3)
    assert latest_local_filing_date(conn, "MSFT", "fmp") is None


# ---------- error isolation + status thresholds ----------


def test_per_ticker_error_is_isolated_not_fatal() -> None:
    conn = _db()
    provider = FakeProvider(fail_with={"BAD": ValueError("kaboom")})

    result = refresh_universe(conn, provider=provider, tickers=["AAPL", "BAD", "MSFT"])

    assert result.imported == 2
    assert result.failed == 1
    assert [o.ticker for o in result.failures] == ["BAD"]
    assert result.failures[0].error_message == "kaboom"


def test_non_success_result_counts_as_failure() -> None:
    conn = _db()

    class _NoProfileProvider(FakeProvider):
        def fundamentals(self, ticker: str) -> Any:
            self.calls.append(("fundamentals", ticker.upper()))
            raise ValueError("profile not found")

    provider = _NoProfileProvider()

    result = refresh_universe(conn, provider=provider, tickers=["NOPE"])

    assert result.failed == 1
    assert result.failures[0].error_message == "profile not found"


@pytest.mark.parametrize(
    ("n_fail", "n_total", "expected"),
    [
        (0, 20, "success"),
        (1, 20, "success"),  # 5% -> success boundary
        (2, 20, "partial"),  # 10% -> partial
        (5, 20, "partial"),  # 25% -> partial boundary
        (6, 20, "error"),  # 30% -> error
    ],
)
def test_status_thresholds(n_fail: int, n_total: int, expected: str) -> None:
    conn = _db()
    fail_with = {f"F{i}": ValueError("fail") for i in range(n_fail)}
    provider = FakeProvider(fail_with=fail_with)

    tickers = [f"F{i}" for i in range(n_fail)] + [f"OK{i}" for i in range(n_total - n_fail)]
    result = refresh_universe(conn, provider=provider, tickers=tickers)

    assert result.total == n_total
    assert result.failed == n_fail
    assert result.status == expected


def test_empty_universe_is_success_with_zero_total() -> None:
    conn = _db()
    provider = FakeProvider()

    result = refresh_universe(conn, provider=provider, tickers=[])

    assert result.total == 0
    assert result.status == "success"
    assert result.failure_rate == 0.0


# ---------- progress logging + refresh_log ----------


def test_progress_logged_every_n(monkeypatch: pytest.MonkeyPatch) -> None:
    conn = _db()
    events: list[tuple[str, dict[str, Any]]] = []

    import bot.ingest.universe as mod

    class _Recorder:
        def info(self, event: str, **kw: Any) -> None:
            events.append((event, kw))

        def warning(self, event: str, **kw: Any) -> None:
            events.append((event, kw))

        def exception(self, event: str, **kw: Any) -> None:
            events.append((event, kw))

    monkeypatch.setattr(mod, "log", _Recorder())

    provider = FakeProvider()
    refresh_universe(
        conn,
        provider=provider,
        tickers=[f"T{i}" for i in range(5)],
        progress_every=2,
    )
    progress = [e for e in events if e[0] == "universe.refresh.progress"]
    # 5 tickers, every 2 -> logged at 2 and 4.
    assert [e[1]["processed"] for e in progress] == [2, 4]


def test_writes_refresh_log_summary_row() -> None:
    conn = _db()
    provider = FakeProvider(fail_with={"BAD": ValueError("kaboom")})

    result = refresh_universe(conn, provider=provider, tickers=["AAPL", "BAD"])

    row = conn.execute(
        "SELECT source, run_id, status, rows_affected, error_message "
        "FROM refresh_log WHERE source = 'fake_universe'"
    ).fetchone()
    assert row is not None
    source, run_id, _status, rows_affected, error_message = row
    assert source == "fake_universe"
    assert run_id == result.run_id
    assert rows_affected == 1  # imported count (AAPL)
    assert error_message is not None
    assert "BAD" in error_message


def test_outcome_dataclass_shape() -> None:
    o = TickerOutcome(ticker="AAPL", status="imported", rows_affected=5)
    assert o.ticker == "AAPL"
    assert o.error_message is None


# ---------- rate limiting ----------


def test_rate_limit_defers_the_rest() -> None:
    conn = _db()
    provider = FakeProvider(rate_limit_after=1)

    result = refresh_universe(conn, provider=provider, tickers=["AAA", "BBB", "CCC"])

    statuses = {o.ticker: o.status for o in result.outcomes}
    assert statuses["BBB"] == "deferred" and statuses["CCC"] == "deferred"
    assert result.imported == 1
    assert result.deferred == 2
    assert result.failed == 0
    assert result.status == "success"


def test_rate_limit_raised_by_the_probe_stops_the_run_too(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A rate limit raised by the *probe* (not fundamentals) must still cut the
    run, not be swallowed as a generic ``probe_failed`` warning."""
    conn = _db()
    conn.execute(
        "INSERT INTO filings_log (ticker, filing_type, filing_date, source) "
        "VALUES ('CCC', 'FY', '2024-01-01', 'fake')"
    )

    class _ProbeRateLimitedProvider(FakeProvider):
        def latest_filing_date(self, ticker: str) -> date | None:
            self.calls.append(("latest_filing_date", ticker.upper()))
            if ticker.upper() == "CCC":
                raise ProviderRateLimitError("quota")
            return None

    provider = _ProbeRateLimitedProvider()

    result = refresh_universe(conn, provider=provider, tickers=["AAA", "BBB", "CCC", "DDD", "EEE"])

    probe_calls = [c for c in provider.calls if c[0] == "latest_filing_date"]
    assert probe_calls == [("latest_filing_date", "CCC")]  # AAA/BBB have no local filing
    imported_tickers = {o.ticker for o in result.outcomes if o.status == "imported"}
    assert imported_tickers == {"AAA", "BBB"}  # CCC's import is never reached
    assert result.imported == 2
    assert result.deferred == 3  # CCC (rate-limited) + DDD + EEE
    assert result.failed == 0
    assert result.status == "success"
    assert "universe.refresh.probe_failed" not in caplog.text


def test_ticker_status_names_the_four_outcomes() -> None:
    assert set(get_args(TickerStatus)) == {"imported", "skipped", "failed", "deferred"}


def test_provider_neutral_writers_require_an_explicit_source() -> None:
    for fn in (upsert_prices_daily, upsert_fx_rates, latest_local_filing_date):
        assert inspect.signature(fn).parameters["source"].default is inspect.Parameter.empty
