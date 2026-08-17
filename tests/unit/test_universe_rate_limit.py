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
