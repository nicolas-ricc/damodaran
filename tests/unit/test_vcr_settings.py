"""The shared VCR settings: replay-only by default, apikey scrubbed everywhere."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import vcr
from vcr.errors import CannotOverwriteExistingCassetteException

from tests.vcr_settings import VCR_CONFIG, cassette_subdir, vcr_kwargs


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
