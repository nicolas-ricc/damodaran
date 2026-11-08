"""Proves the re-record switch writes a scrubbed cassette, with no network."""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx
import pytest
import vcr
import yaml

from bot.ingest.fmp import FmpClient, FmpProvider
from tests.vcr_settings import VCR_CONFIG, fmp_test_key

FAKE_KEY = "fake-key-do-not-record"
CASSETTES = Path(__file__).resolve().parents[1] / "fixtures" / "cassettes"

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


class _ProfileOnlyHandler(BaseHTTPRequestHandler):
    """200 with ``PROFILE`` on ``/stable/profile``, 401 on every other path."""

    def do_GET(self) -> None:
        if self.path.startswith("/stable/profile"):
            code, payload = 200, json.dumps(PROFILE).encode()
        else:
            code, payload = 401, json.dumps({"Error Message": "Invalid API KEY."}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_: object) -> None:
        pass


def _serve(handler: type[BaseHTTPRequestHandler]) -> Iterator[str]:
    server = HTTPServer(("127.0.0.1", 0), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_address[1]}/stable"
    server.shutdown()
    server.server_close()


@pytest.fixture
def stub_url() -> Iterator[str]:
    yield from _serve(_Handler)


@pytest.fixture
def profile_only_url() -> Iterator[str]:
    yield from _serve(_ProfileOnlyHandler)


def _recorder() -> vcr.VCR:
    return vcr.VCR(**(VCR_CONFIG | {"record_mode": "all"}))


def test_record_all_writes_scrubbed_cassette(stub_url: str, tmp_path: Path) -> None:
    cassette = tmp_path / "recorded.yaml"
    recorder = vcr.VCR(**(VCR_CONFIG | {"record_mode": "all"}))
    with (
        recorder.use_cassette(str(cassette)),
        FmpClient(api_key=fmp_test_key("all", {"BOT_FMP_API_KEY": FAKE_KEY}), base_url=stub_url) as client,
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


def test_error_response_is_not_recorded(profile_only_url: str, tmp_path: Path) -> None:
    cassette = tmp_path / "new.yaml"
    with (
        _recorder().use_cassette(str(cassette)),
        FmpClient(api_key=FAKE_KEY, base_url=profile_only_url) as client,
        pytest.raises(httpx.HTTPStatusError),
    ):
        client.available_exchanges()
    assert not cassette.exists()


def test_error_response_leaves_existing_cassette_untouched(
    profile_only_url: str, tmp_path: Path
) -> None:
    cassette = tmp_path / "test_available_exchanges.yaml"
    original = (CASSETTES / "fmp" / "test_available_exchanges.yaml").read_bytes()
    cassette.write_bytes(original)
    with (
        _recorder().use_cassette(str(cassette)),
        FmpClient(api_key=FAKE_KEY, base_url=profile_only_url) as client,
        pytest.raises(httpx.HTTPStatusError),
    ):
        client.available_exchanges()
    assert cassette.read_bytes() == original


def test_mixed_rerecord_keeps_only_2xx(profile_only_url: str, tmp_path: Path) -> None:
    cassette = tmp_path / "mixed.yaml"
    with (
        _recorder().use_cassette(str(cassette)),
        FmpClient(api_key=FAKE_KEY, base_url=profile_only_url) as client,
    ):
        assert client.lookup_company("AAPL") is not None
        with pytest.raises(httpx.HTTPStatusError):
            client.available_exchanges()
    interactions = yaml.safe_load(cassette.read_text())["interactions"]
    assert [i["response"]["status"]["code"] for i in interactions] == [200]
    assert "Invalid API KEY" not in cassette.read_text()
