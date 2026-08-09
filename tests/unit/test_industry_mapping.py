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
)


def _write(tmp_path: Path, body: str) -> Path:
    path = tmp_path / "industry_mapping.csv"
    path.write_text(body)
    return path


def test_normalize_collapses_case_whitespace_and_dashes() -> None:
    # FMP is inconsistent about the dash it emits between a family and a variant.
    assert normalize_industry_label("Banks—Diversified") == "banks-diversified"
    assert normalize_industry_label("Banks – Diversified") == "banks-diversified"  # noqa: RUF001
    assert normalize_industry_label("banks - diversified") == "banks-diversified"
    assert normalize_industry_label("  Software—Application  ") == "software-application"


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
