"""The one VCR configuration every cassette-backed test uses.

Replay only: a missing cassette raises instead of reaching the network. To
re-record against the live APIs, run
``uv run pytest -m integration --vcr-record=all``.
"""

from __future__ import annotations

VCR_CONFIG: dict[str, object] = {
    # FMP authenticates with an ``apikey`` query param; SEC EDGAR wants a
    # contact User-Agent. Neither may land in a cassette.
    "filter_query_parameters": [("apikey", "SCRUBBED")],
    "filter_headers": [("User-Agent", "Tester t@example.com")],
    "record_mode": "none",
}


def vcr_kwargs(record: str | None = None) -> dict[str, object]:
    """``VCR_CONFIG`` with pytest-vcr's ``--vcr-record`` value applied, if any."""
    return VCR_CONFIG | {"record_mode": record} if record else dict(VCR_CONFIG)


# Test-module prefix -> cassette folder under ``tests/fixtures/cassettes``.
_CASSETTE_SUBDIRS = {
    "test_sec_edgar_": "sec_edgar",
    "test_fmp_": "fmp",
    "test_fx_": "fmp",
    "test_prices_": "fmp",
}


def cassette_subdir(module_name: str) -> str:
    """The cassette folder for a test module; unknown modules fail loudly."""
    basename = module_name.rsplit(".", 1)[-1]
    for prefix, subdir in _CASSETTE_SUBDIRS.items():
        if basename.startswith(prefix):
            return subdir
    raise ValueError(f"no cassette folder mapped for test module {module_name!r}")
