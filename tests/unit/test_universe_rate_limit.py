"""FMP free-tier rate limiting: stop cleanly, defer the rest, resume tomorrow."""

from datetime import datetime

import duckdb
import httpx
import pytest

from bot.ingest.base import IngestResult
from bot.ingest.fmp import FmpClient, FmpRateLimitError
from bot.ingest.universe import refresh_universe_from_fmp
from bot.storage.db import apply_schema


def test_fmp_client_raises_rate_limit_on_429(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FmpClient(api_key="k")

    def fake_get(path: str, params: object = None) -> httpx.Response:
        return httpx.Response(429, request=httpx.Request("GET", "https://x/"), json={"Error": "Limit"})

    monkeypatch.setattr(client._client, "get", fake_get)
    with pytest.raises(FmpRateLimitError):
        client.lookup_company("AAPL")


def _ok_result(source: str = "fmp") -> IngestResult:
    now = datetime.now()
    return IngestResult(source=source, started_at=now, finished_at=now, status="success", rows_affected=1)


def test_bulk_refresh_stops_on_rate_limit_and_defers_the_rest() -> None:
    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    calls: list[str] = []

    def importer(conn: object, *, ticker: str, api_key: str) -> IngestResult:
        calls.append(ticker)
        if ticker == "CCC":
            raise FmpRateLimitError("quota")
        return _ok_result()

    result = refresh_universe_from_fmp(
        conn,
        api_key="k",
        tickers=["AAA", "BBB", "CCC", "DDD", "EEE"],
        importer=importer,
        latest_filing_probe=lambda t: None,
    )
    assert calls == ["AAA", "BBB", "CCC"]  # DDD/EEE nunca se intentan
    assert result.imported == 2
    assert result.deferred == 3  # CCC (rate-limited) + DDD + EEE
    assert result.failed == 0
    assert result.status == "success"  # 0 fallas sobre lo intentado


def test_bulk_refresh_stops_when_the_probe_hits_the_rate_limit(caplog: pytest.LogCaptureFixture) -> None:
    """A 429 raised by the *probe* (not the importer) must still cut the run.

    ``_should_skip`` used to swallow every probe exception — including
    ``FmpRateLimitError`` — as a generic ``probe_failed`` warning and fall
    through to importing the ticker anyway. That wastes one more request
    against an already-exhausted quota and mislabels the cause in the logs.
    """
    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    # A local filings_log row is required so `_should_skip` actually calls the
    # probe for CCC (no local row -> local_latest is None -> probe is skipped).
    conn.execute(
        "INSERT INTO filings_log (ticker, filing_type, filing_date, source) "
        "VALUES ('CCC', 'FY', '2024-01-01', 'fmp')"
    )
    calls: list[str] = []
    imported: list[str] = []

    def importer(conn: object, *, ticker: str, api_key: str) -> IngestResult:
        imported.append(ticker)
        return _ok_result()

    def probe(ticker: str) -> None:
        calls.append(ticker)
        if ticker == "CCC":
            raise FmpRateLimitError("quota")
        return None

    result = refresh_universe_from_fmp(
        conn,
        api_key="k",
        tickers=["AAA", "BBB", "CCC", "DDD", "EEE"],
        importer=importer,
        latest_filing_probe=probe,
    )
    assert calls == ["CCC"]  # AAA/BBB have no local filing -> probe not called
    assert imported == ["AAA", "BBB"]  # CCC's importer is never reached
    assert result.imported == 2
    assert result.deferred == 3  # CCC (rate-limited) + DDD + EEE
    assert result.failed == 0
    assert result.status == "success"
    assert "universe.refresh.probe_failed" not in caplog.text
