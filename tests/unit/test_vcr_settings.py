"""The shared VCR settings: replay-only by default, apikey scrubbed everywhere."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import httpx
import pytest
import vcr
from vcr.errors import CannotOverwriteExistingCassetteException

from tests.vcr_settings import (
    DUMMY_FMP_KEY,
    VCR_CONFIG,
    MissingFmpKeyError,
    cassette_subdir,
    drop_error_response,
    fmp_test_key,
    record_option,
    vcr_kwargs,
)


def test_missing_cassette_is_refused(tmp_path: Path) -> None:
    with (
        vcr.VCR(**VCR_CONFIG).use_cassette(str(tmp_path / "absent.yaml")),
        pytest.raises(CannotOverwriteExistingCassetteException),
    ):
        httpx.get("http://127.0.0.1:9/never")
    assert not (tmp_path / "absent.yaml").exists()


def test_apikey_is_scrubbed_by_default() -> None:
    assert ("apikey", "SCRUBBED") in VCR_CONFIG["filter_query_parameters"]


def test_vcr_kwargs_defaults_to_shared_config() -> None:
    assert vcr_kwargs() == VCR_CONFIG
    assert vcr_kwargs(None) == VCR_CONFIG


def test_vcr_kwargs_applies_override() -> None:
    before = dict(VCR_CONFIG)
    kwargs = vcr_kwargs("all")
    assert kwargs != VCR_CONFIG
    assert kwargs["filter_query_parameters"] == VCR_CONFIG["filter_query_parameters"]
    assert before == VCR_CONFIG


@pytest.mark.parametrize(
    ("module", "expected"),
    [
        ("tests.integration.test_fmp_client", "fmp"),
        ("tests.integration.test_fmp_import", "fmp"),
        ("tests.integration.test_fx_import", "fmp"),
        ("tests.integration.test_prices_import", "fmp"),
        ("tests.integration.test_sec_edgar_client", "sec_edgar"),
        ("tests.integration.test_sec_edgar_import", "sec_edgar"),
    ],
)
def test_cassette_subdir_follows_module_name(module: str, expected: str) -> None:
    assert cassette_subdir(module) == expected


def test_cassette_subdir_rejects_unmapped_module() -> None:
    with pytest.raises(ValueError, match="test_stooq_client"):
        cassette_subdir("tests.integration.test_stooq_client")


def _response(code: int) -> dict[str, Any]:
    return {"status": {"code": code, "message": ""}, "headers": {}, "body": {"string": b""}}


@pytest.mark.parametrize("code", [200, 204])
def test_drop_error_response_keeps_2xx(code: int) -> None:
    response = _response(code)
    assert drop_error_response(response) is response


@pytest.mark.parametrize("code", [301, 401, 403, 404, 429, 500])
def test_drop_error_response_drops_the_rest(code: int) -> None:
    assert drop_error_response(_response(code)) is None


def test_error_hook_is_shared() -> None:
    assert VCR_CONFIG["before_record_response"] is drop_error_response


@pytest.mark.parametrize("record", [None, "none"])
def test_replay_uses_dummy_key_even_with_real_one(record: str | None) -> None:
    assert fmp_test_key(record, {"BOT_FMP_API_KEY": "real"}) == DUMMY_FMP_KEY


@pytest.mark.parametrize("record", ["once", "new_episodes", "all"])
def test_recording_uses_real_key(record: str) -> None:
    assert fmp_test_key(record, {"BOT_FMP_API_KEY": " real-key "}) == "real-key"


def test_recording_without_key_raises() -> None:
    with pytest.raises(MissingFmpKeyError, match="BOT_FMP_API_KEY"):
        fmp_test_key("all", {})


def test_dummy_key_counts_as_missing() -> None:
    with pytest.raises(MissingFmpKeyError):
        fmp_test_key("all", {"BOT_FMP_API_KEY": DUMMY_FMP_KEY})


def test_blank_key_counts_as_missing() -> None:
    with pytest.raises(MissingFmpKeyError):
        fmp_test_key("all", {"BOT_FMP_API_KEY": "   "})


def _config(**options: str | None) -> pytest.Config:
    return cast(pytest.Config, SimpleNamespace(getoption=options.__getitem__))


def test_record_option_reads_deprecated_flag() -> None:
    assert record_option(_config(**{"--vcr-record": None, "--vcr-record-mode": "all"})) == "all"
    assert record_option(_config(**{"--vcr-record": "once", "--vcr-record-mode": "all"})) == "once"
    assert record_option(_config(**{"--vcr-record": None, "--vcr-record-mode": None})) is None


def test_real_key_repr_is_redacted() -> None:
    key = fmp_test_key("all", {"BOT_FMP_API_KEY": "real-key"})
    assert key == "real-key"
    assert "real-key" not in repr(key)
