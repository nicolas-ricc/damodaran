"""Proves the re-record switch writes a scrubbed cassette, with no network."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest
import vcr

from bot.ingest.fmp import FmpClient, FmpProvider
from tests.vcr_settings import VCR_CONFIG

FAKE_KEY = "fake-key-do-not-record"

PROFILE = [
    {
        "symbol": "AAPL",
        "companyName": "Apple Inc.",
        "exchange": "NASDAQ",
        "exchangeShortName": "NASDAQ",
        "country": "US",
        "currency": "USD",
        "sector": "Technology",
        "industry": "Consumer Electronics",
        "isActivelyTrading": True,
        "ipoDate": "1980-12-12",
    }
]


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        body = json.dumps(PROFILE).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_: object) -> None:
        pass


@pytest.fixture
def stub_url() -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/stable"
    server.shutdown()
    server.server_close()


def test_record_all_writes_scrubbed_cassette(stub_url: str, tmp_path: Path) -> None:
    cassette = tmp_path / "recorded.yaml"
    recorder = vcr.VCR(**(VCR_CONFIG | {"record_mode": "all"}))
    with (
        recorder.use_cassette(str(cassette)),
        FmpClient(api_key=FAKE_KEY, base_url=stub_url) as client,
    ):
        info = client.lookup_company("AAPL")
    assert info is not None and info.ticker == "AAPL"
    text = cassette.read_text()
    assert "apikey=SCRUBBED" in text
    assert FAKE_KEY not in text


def test_provider_passes_base_url_through(stub_url: str) -> None:
    with FmpProvider(api_key=FAKE_KEY, base_url=stub_url) as provider:
        info = provider.lookup_company("AAPL")
    assert info is not None and info.name == "Apple Inc."
