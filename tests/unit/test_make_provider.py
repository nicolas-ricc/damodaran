"""The composition root selects the adapter from Settings.data_provider."""

from __future__ import annotations

import pytest
import typer

from bot.cli import _make_provider
from bot.config import Settings
from bot.ingest.edgar_stooq import EdgarStooqProvider  # noqa: F401 — seam: only cli names it
from bot.ingest.fmp import FmpProvider


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "sec_user_agent": "Test test@example.com",
        "_env_file": None,  # keep the developer's .env out of unit tests
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_default_provider_is_edgar_tiingo() -> None:
    settings = _settings()
    assert settings.data_provider == "edgar-tiingo"
    assert _make_provider(settings).name == "edgar_tiingo"


def test_edgar_tiingo_builds_without_a_key_so_fundamentals_still_run() -> None:
    # Only prices need the key; construction must not hard-fail without it.
    provider = _make_provider(_settings(tiingo_api_key=""))
    assert provider.name == "edgar_tiingo"


def test_edgar_stooq_selected_builds_stooq() -> None:
    provider = _make_provider(_settings(data_provider="edgar-stooq"))
    assert provider.name == "edgar_stooq"


def test_fmp_selected_with_key_builds_fmp() -> None:
    provider = _make_provider(_settings(data_provider="fmp", fmp_api_key="k"))
    assert isinstance(provider, FmpProvider)


def test_fmp_selected_without_key_exits_with_guidance() -> None:
    with pytest.raises(typer.Exit):
        _make_provider(_settings(data_provider="fmp", fmp_api_key=""))


def test_stooq_dir_setting_reaches_the_adapter(tmp_path: object) -> None:
    provider = _make_provider(_settings(data_provider="edgar-stooq", stooq_dir=str(tmp_path)))
    assert getattr(provider, "_stooq_dir", None) is not None
