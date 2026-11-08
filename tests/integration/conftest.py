"""pytest-vcr fixtures shared by every cassette-backed integration test."""

from __future__ import annotations

import os

import pytest

from tests.vcr_settings import (
    VCR_CONFIG,
    MissingFmpKeyError,
    cassette_subdir,
    fmp_test_key,
    record_option,
)


@pytest.fixture(scope="module")
def vcr_config() -> dict[str, object]:
    return dict(VCR_CONFIG)


@pytest.fixture(scope="module")
def vcr_cassette_dir(request: pytest.FixtureRequest) -> str:
    subdir = cassette_subdir(request.module.__name__)
    return str(request.config.rootpath / "tests" / "fixtures" / "cassettes" / subdir)


@pytest.fixture(scope="session")
def fmp_api_key(pytestconfig: pytest.Config) -> str:
    """Dummy key on replay, the exported real one when recording.

    Session scope: it reads ``os.environ`` before the root autouse fixture
    overwrites ``BOT_FMP_API_KEY`` for each test.
    """
    try:
        return fmp_test_key(record_option(pytestconfig), os.environ)
    except MissingFmpKeyError as err:
        pytest.fail(str(err), pytrace=False)
