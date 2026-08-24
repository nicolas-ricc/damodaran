"""Integration test for the bulk universe refresh (M2.6).

Drives ``refresh_universe`` over a 5-ticker mini-universe with one VCR cassette
per ticker (US + international), through :class:`FmpProvider`. The cassettes are
SYNTHETIC (hand-authored, fabricated-but-realistic FMP JSON) so the suite runs
offline and deterministically; they MUST be re-recorded against the live FMP API
with a real BOT_FMP_API_KEY before production use.

The incremental-skip path and per-ticker error isolation are covered exhaustively
in ``tests/unit/test_universe_refresh.py`` against a :class:`FakeProvider`; this
test proves the orchestration drives the *real* FMP adapter end-to-end across the
mini-universe via replayed HTTP.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
import vcr

from bot.ingest.fmp import FmpProvider
from bot.ingest.provider import CompanyInfo, FundamentalsBundle, FxRate, PriceBar
from bot.ingest.universe import refresh_universe
from bot.storage.db import apply_schema, connect

API_KEY = "test-fmp-key"
MINI_UNIVERSE = ["AAPL", "MSFT", "NVDA", "NESN.SW", "SAP.DE"]


@pytest.fixture
def cassette_dir(request: pytest.FixtureRequest) -> Path:
    return Path(request.config.rootpath) / "tests" / "fixtures" / "cassettes" / "universe"


def _cassette_vcr() -> vcr.VCR:
    return vcr.VCR(
        filter_query_parameters=[("apikey", "SCRUBBED")],
        record_mode="none",
    )


class _CassetteFmpProvider:
    """Wraps a real :class:`FmpProvider`, replaying a VCR cassette scoped to
    each ticker (mirrors the old per-ticker ``_cassette_importer`` wrapper).

    ``filing_probe``, when given, replaces ``latest_filing_date`` with a canned
    function instead of replaying HTTP — the cassettes were recorded for the
    fundamentals fetch only (mirroring the old test's injected
    ``latest_filing_probe``), never for the probe's own request.
    """

    def __init__(
        self,
        cassette_dir: Path,
        api_key: str,
        filing_probe: object = None,
    ) -> None:
        self._provider = FmpProvider(api_key=api_key)
        self._cassette_dir = cassette_dir
        self._filing_probe = filing_probe

    @property
    def name(self) -> str:
        return self._provider.name

    def _use_cassette(self, key: str) -> object:
        return _cassette_vcr().use_cassette(str(self._cassette_dir / f"{key}.yaml"))

    def lookup_company(self, ticker: str) -> CompanyInfo | None:
        with self._use_cassette(ticker):
            return self._provider.lookup_company(ticker)

    def fundamentals(self, ticker: str) -> FundamentalsBundle:
        with self._use_cassette(ticker):
            return self._provider.fundamentals(ticker)

    def daily_prices(self, ticker: str, since: date | None) -> list[PriceBar]:
        with self._use_cassette(ticker):
            return self._provider.daily_prices(ticker, since)

    def fx_rates(self, currency: str, since: date | None) -> list[FxRate]:
        with self._use_cassette(currency):
            return self._provider.fx_rates(currency, since)

    def latest_filing_date(self, ticker: str) -> date | None:
        if self._filing_probe is not None:
            return self._filing_probe(ticker)  # type: ignore[operator]
        with self._use_cassette(ticker):
            return self._provider.latest_filing_date(ticker)

    def close(self) -> None:
        self._provider.close()


@pytest.mark.integration
def test_bulk_refresh_imports_full_mini_universe(cassette_dir: Path) -> None:
    conn = connect(":memory:")
    apply_schema(conn)

    provider = _CassetteFmpProvider(cassette_dir, API_KEY)
    result = refresh_universe(
        conn,
        provider=provider,  # type: ignore[arg-type]
        tickers=MINI_UNIVERSE,
        # First run: empty filings_log, so nothing is skipped -> the probe
        # (which would otherwise replay HTTP) is never reached.
    )

    assert result.total == 5
    assert result.imported == 5
    assert result.skipped == 0
    assert result.failed == 0
    assert result.status == "success"
    assert result.failure_rate == 0.0

    # Companies for every ticker, US + international currencies preserved.
    companies = dict(
        conn.execute("SELECT ticker, currency FROM companies").fetchall()
    )
    assert set(companies) == set(MINI_UNIVERSE)
    assert companies["AAPL"] == "USD"
    assert companies["NESN.SW"] == "CHF"
    assert companies["SAP.DE"] == "EUR"

    # filings_log populated for each ticker (drives the next run's incremental skip).
    filings = conn.execute(
        "SELECT ticker, COUNT(*) FROM filings_log GROUP BY ticker"
    ).fetchall()
    assert {t for t, _ in filings} == set(MINI_UNIVERSE)

    # A single fmp_universe summary row recorded the run.
    summary = conn.execute(
        "SELECT status, rows_affected, error_message "
        "FROM refresh_log WHERE source = 'fmp_universe'"
    ).fetchall()
    assert len(summary) == 1
    assert summary[0][0] == "success"
    assert summary[0][1] == 5  # imported count
    assert summary[0][2] is None  # no failures

    conn.close()


@pytest.mark.integration
def test_second_run_skips_unchanged_tickers(cassette_dir: Path) -> None:
    conn = connect(":memory:")
    apply_schema(conn)

    # First run imports everything and populates filings_log. The probe is
    # never reached (empty filings_log), so it needs no cassette of its own.
    refresh_universe(
        conn,
        provider=_CassetteFmpProvider(cassette_dir, API_KEY),  # type: ignore[arg-type]
        tickers=MINI_UNIVERSE,
    )

    # Second run: probe reports each ticker's newest filing has NOT advanced
    # (use a deliberately old date so every local latest is >= remote) -> all
    # skipped. A canned filing_probe stands in for the real probe request (no
    # cassette was recorded for it).
    result = refresh_universe(
        conn,
        provider=_CassetteFmpProvider(  # type: ignore[arg-type]
            cassette_dir, API_KEY, filing_probe=lambda _t: date(2000, 1, 1)
        ),
        tickers=MINI_UNIVERSE,
    )

    assert result.skipped == 5
    assert result.imported == 0
    assert result.status == "success"

    conn.close()
