"""The one VCR configuration every cassette-backed test uses.

Replay only: a missing cassette raises instead of reaching the network. To
re-record against the live APIs, run
``uv run pytest -m integration --vcr-record=all``.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import pytest

DUMMY_FMP_KEY = "test-fmp-key"


class MissingFmpKeyError(RuntimeError):
    """Re-recording FMP cassettes needs a real key and none was supplied."""


def drop_error_response(response: dict[str, Any]) -> dict[str, Any] | None:
    """Keep 2xx responses only; ``None`` makes vcrpy skip recording the rest."""
    return response if 200 <= response["status"]["code"] < 300 else None


VCR_CONFIG: dict[str, object] = {
    # FMP authenticates with an ``apikey`` query param; SEC EDGAR wants a
    # contact User-Agent. Neither may land in a cassette.
    # The Flex Web Service token travels as ``t`` (#139).
    "filter_query_parameters": [("apikey", "SCRUBBED"), ("t", "SCRUBBED")],
    "filter_headers": [("User-Agent", "Tester t@example.com")],
    "record_mode": "none",
    # A 401/403 must never replace a cassette.
    "before_record_response": drop_error_response,
}


def vcr_kwargs(record: str | None = None) -> dict[str, object]:
    """``VCR_CONFIG`` with pytest-vcr's ``--vcr-record`` value applied, if any."""
    return VCR_CONFIG | {"record_mode": record} if record else dict(VCR_CONFIG)


def record_option(config: pytest.Config) -> str | None:
    """The record mode pytest-vcr was given, via the flag or its deprecated alias."""
    return config.getoption("--vcr-record") or config.getoption("--vcr-record-mode")


def fmp_test_key(record: str | None, environ: Mapping[str, str]) -> str:
    """The FMP key tests use: a dummy on replay, the real one when re-recording."""
    if record in (None, "none"):
        return DUMMY_FMP_KEY
    key = environ.get("BOT_FMP_API_KEY", "").strip()
    if not key or key == DUMMY_FMP_KEY:
        raise MissingFmpKeyError(
            f"BOT_FMP_API_KEY must hold a real FMP key to re-record (mode {record!r}); "
            "no FMP cassette was recorded"
        )
    return key


_CASSETTE_SUBDIRS = {
    "test_sec_edgar_": "sec_edgar",
    "test_fmp_": "fmp",
    "test_fx_": "fmp",
    "test_prices_": "fmp",
    "test_ibkr_flex_": "ibkr_flex",
}


def cassette_subdir(module_name: str) -> str:
    """The cassette folder for a test module; unknown modules fail loudly."""
    basename = module_name.rsplit(".", 1)[-1]
    for prefix, subdir in _CASSETTE_SUBDIRS.items():
        if basename.startswith(prefix):
            return subdir
    raise ValueError(f"no cassette folder mapped for test module {module_name!r}")
