"""Provider→Damodaran industry mapping (spec §4.3.1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bot.ingest.industry_mapping import (
    DAMODARAN_INDUSTRIES,
    IndustryMapping,
    default_mapping_path,
    load_industry_mapping,
    normalize_industry_label,
    resolve_mapping_path,
)


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "industry_mapping.csv"
    path.write_text(body)
    return path


def test_normalize_collapses_case_whitespace_and_dashes() -> None:
    # FMP is inconsistent about the dash it emits between a family and a variant.
    assert normalize_industry_label("Banks\u2014Diversified") == "banks-diversified"
    assert normalize_industry_label("Banks \u2013 Diversified") == "banks-diversified"
    assert normalize_industry_label("banks - diversified") == "banks-diversified"
    assert normalize_industry_label("  Software\u2014Application  ") == "software-application"


def test_normalize_collapses_runs_of_dash_characters() -> None:
    # A doubled separator (typo, bad copy/paste, future provider quirk) must still
    # converge to a single '-', not leak a run of dashes into the lookup key.
    assert normalize_industry_label("Banks\u2014\u2014Diversified") == "banks-diversified"
    assert (
        normalize_industry_label("Banks \u2014 \u2014 Diversified") == "banks-diversified"
    )
    assert normalize_industry_label("Banks\u2013\u2014Diversified") == "banks-diversified"
    assert normalize_industry_label("A -- B") == "a-b"


def test_normalize_leading_trailing_and_lone_dash() -> None:
    assert normalize_industry_label("-Banks") == "-banks"
    assert normalize_industry_label("Banks-") == "banks-"
    assert normalize_industry_label("-") == "-"


def test_normalize_dash_variants_resolve_to_the_same_key(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "provider,provider_industry,damodaran_industry\n"
        "fmp,Banks-Diversified,Bank (Money Center)\n",
    )
    mapping = load_industry_mapping(path)
    single = mapping.resolve("fmp", "Banks-Diversified")
    doubled = mapping.resolve("fmp", "Banks\u2014\u2014Diversified")
    spaced = mapping.resolve("fmp", "Banks \u2013 \u2013 Diversified")
    assert single == "Bank (Money Center)"
    assert doubled == single
    assert spaced == single


def test_resolve_exact_match(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "provider,provider_industry,damodaran_industry\n"
        "fmp,Semiconductors,Semiconductor\n",
    )
    mapping = load_industry_mapping(path)
    assert mapping.resolve("fmp", "Semiconductors") == "Semiconductor"


def test_resolve_is_dash_and_case_insensitive(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "provider,provider_industry,damodaran_industry\n"
        "fmp,Banks—Diversified,Bank (Money Center)\n",
    )
    mapping = load_industry_mapping(path)
    assert mapping.resolve("FMP", "banks - diversified") == "Bank (Money Center)"


def test_resolve_unmapped_returns_none(tmp_path: Path) -> None:
    path = _write(tmp_path, "provider,provider_industry,damodaran_industry\n")
    mapping = load_industry_mapping(path)
    assert mapping.resolve("fmp", "Blockchain Widgets") is None


def test_resolve_none_industry_returns_none(tmp_path: Path) -> None:
    path = _write(tmp_path, "provider,provider_industry,damodaran_industry\n")
    assert load_industry_mapping(path).resolve("fmp", None) is None


def test_missing_file_degrades_to_empty_mapping(tmp_path: Path) -> None:
    # Graceful degradation (spec §13.2): no mapping file must not break ingest.
    mapping = load_industry_mapping(tmp_path / "absent.csv")
    assert mapping.resolve("fmp", "Semiconductors") is None
    assert len(mapping) == 0


def test_rejects_unknown_damodaran_industry(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "provider,provider_industry,damodaran_industry\n"
        "fmp,Semiconductors,Semiconductorz\n",
    )
    with pytest.raises(ValueError, match="not a Damodaran industry"):
        load_industry_mapping(path)


def test_rejects_duplicate_provider_industry(tmp_path: Path) -> None:
    path = _write(
        tmp_path,
        "provider,provider_industry,damodaran_industry\n"
        "fmp,Semiconductors,Semiconductor\n"
        "fmp,semiconductors,Steel\n",
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_industry_mapping(path)


def test_rejects_missing_column(tmp_path: Path) -> None:
    path = _write(tmp_path, "provider,provider_industry\nfmp,Semiconductors\n")
    with pytest.raises(ValueError, match="damodaran_industry"):
        load_industry_mapping(path)


def test_shipped_mapping_loads_and_covers_the_cassette_industries() -> None:
    mapping = load_industry_mapping(default_mapping_path())
    # Every FMP industry string present in the committed VCR cassettes must map,
    # otherwise the integration tests screen against empty benchmarks.
    for fmp_industry in (
        "Consumer Electronics",
        "Semiconductors",
        "Software",
        "Packaged Foods",
        "Auto Manufacturers",
    ):
        assert mapping.resolve("fmp", fmp_industry) is not None, fmp_industry


def test_damodaran_industries_is_the_canonical_taxonomy() -> None:
    assert "Semiconductor" in DAMODARAN_INDUSTRIES
    assert "Financial Svcs. (Non-bank & Insurance)" in DAMODARAN_INDUSTRIES
    # The aggregate rows of wacc.xls are not industries a company belongs to.
    assert "Total Market" not in DAMODARAN_INDUSTRIES
    assert len(DAMODARAN_INDUSTRIES) == 94


def test_mapping_is_immutable() -> None:
    mapping = load_industry_mapping(default_mapping_path())
    with pytest.raises(AttributeError):
        mapping.foo = 1  # type: ignore[attr-defined]
    assert isinstance(mapping, IndustryMapping)


def test_default_mapping_path_returns_the_packaged_csv() -> None:
    # The docstring used to claim it returns config/industry_mapping.csv.
    assert default_mapping_path().name == "industry_mapping.csv"
    assert default_mapping_path().parent.name == "ingest"


def test_default_mapping_path_is_cwd_independent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # There used to be a repo-relative fallback to a second, byte-identical copy,
    # so which file was authoritative depended on the process CWD. This is the
    # fence that stops one being reintroduced.
    monkeypatch.chdir(tmp_path)
    resolved = default_mapping_path()
    assert resolved.is_absolute()
    assert "config" not in resolved.parts
    assert load_industry_mapping(resolved).resolve("fmp", "Semiconductors") == "Semiconductor"


def test_resolve_mapping_path_uses_the_configured_file(tmp_path: Path) -> None:
    configured = _write(
        tmp_path,
        "provider,provider_industry,damodaran_industry\nfmp,Widget Forges,Steel\n",
    )
    assert resolve_mapping_path(configured) == configured


def test_resolve_mapping_path_defaults_when_unset() -> None:
    assert resolve_mapping_path(None) == default_mapping_path()


def test_resolve_mapping_path_falls_back_when_the_configured_file_is_absent(
    tmp_path: Path,
) -> None:
    # A misconfigured path must not silently run with an empty mapping.
    assert resolve_mapping_path(tmp_path / "nope.csv") == default_mapping_path()


def test_settings_mapping_path_takes_effect(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """BOT_INDUSTRY_MAPPING_PATH must change what the ingest actually resolves."""
    from bot.config import Settings

    configured = _write(
        tmp_path,
        "provider,provider_industry,damodaran_industry\nfmp,Widget Forges,Steel\n",
    )
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_INDUSTRY_MAPPING_PATH", str(configured))
    settings = Settings()  # type: ignore[call-arg]  # values come from the env

    assert settings.industry_mapping_path == configured
    mapping = load_industry_mapping(resolve_mapping_path(settings.industry_mapping_path))
    # A label only the configured CSV knows about — the packaged one does not.
    assert mapping.resolve("fmp", "Widget Forges") == "Steel"
    assert load_industry_mapping(default_mapping_path()).resolve("fmp", "Widget Forges") is None


def test_settings_leaves_the_mapping_path_unset_by_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unset means "use the packaged CSV" — there is no committed second copy."""
    from bot.config import Settings

    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.delenv("BOT_INDUSTRY_MAPPING_PATH", raising=False)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]  # values come from the env

    assert settings.industry_mapping_path is None
    assert resolve_mapping_path(settings.industry_mapping_path) == default_mapping_path()


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_mapping_path_env_var_reads_as_unset(
    blank: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    # BOT_INDUSTRY_MAPPING_PATH="" used to coerce to Path("."), which exists, so
    # resolve_mapping_path handed load_industry_mapping a *directory* and the
    # open() blew up. A blank value means "not configured".
    from bot.config import Settings

    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_INDUSTRY_MAPPING_PATH", blank)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]  # values come from the env

    assert settings.industry_mapping_path is None
    assert load_industry_mapping(resolve_mapping_path(settings.industry_mapping_path)) is not None
    assert resolve_mapping_path(settings.industry_mapping_path).is_file()
