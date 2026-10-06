"""pytest-vcr fixtures shared by every cassette-backed integration test."""

from __future__ import annotations

import pytest

from tests.vcr_settings import VCR_CONFIG, cassette_subdir


@pytest.fixture(scope="module")
def vcr_config() -> dict[str, object]:
    return dict(VCR_CONFIG)


@pytest.fixture(scope="module")
def vcr_cassette_dir(request: pytest.FixtureRequest) -> str:
    subdir = cassette_subdir(request.module.__name__)
    return str(request.config.rootpath / "tests" / "fixtures" / "cassettes" / subdir)
