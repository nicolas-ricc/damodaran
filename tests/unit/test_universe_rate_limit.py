"""FMP free-tier rate limiting: the HTTP client raises on 429.

The orchestrator-level "stop cleanly, defer the rest" behaviour is provider-
neutral and is covered against a :class:`FakeProvider` in
``tests/unit/test_universe_refresh.py`` (``test_rate_limit_defers_the_rest`` and
``test_rate_limit_raised_by_the_probe_stops_the_run_too``).
"""

import httpx
import pytest

from bot.ingest.fmp import FmpClient, FmpRateLimitError


def test_fmp_client_raises_rate_limit_on_429(monkeypatch: pytest.MonkeyPatch) -> None:
    client = FmpClient(api_key="k")

    def fake_get(path: str, params: object = None) -> httpx.Response:
        return httpx.Response(429, request=httpx.Request("GET", "https://x/"), json={"Error": "Limit"})

    monkeypatch.setattr(client._client, "get", fake_get)
    with pytest.raises(FmpRateLimitError):
        client.lookup_company("AAPL")
