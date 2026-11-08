"""ISO 3166 alpha-2 → Damodaran country name (#271)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from structlog.testing import capture_logs

from bot.ingest.damodaran import DEFAULT_COUNTRY_COLUMN_MAP, parse_country_xls
from bot.ingest.sec_edgar import parse_company_facts, parse_submissions_info
from bot.reference import countries
from bot.reference.countries import (
    ISO_TO_DAMODARAN_COUNTRY,
    SUBNATIONAL_SHEET_ROWS,
    damodaran_country_name,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CTRYPREM = FIXTURES / "damodaran" / "ctryprem_sample.xls"


@pytest.fixture(autouse=True)
def _fresh_warned(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(countries, "_warned", set())


def _sheet_countries() -> set[str]:
    rows = parse_country_xls(CTRYPREM, year=2026, column_map=DEFAULT_COUNTRY_COLUMN_MAP)
    return {str(r["country"]) for r in rows}


def test_us_maps_to_united_states() -> None:
    assert damodaran_country_name("US") == "United States"


def test_every_sheet_country_has_an_iso_code() -> None:
    assert _sheet_countries() == set(ISO_TO_DAMODARAN_COUNTRY.values()) | SUBNATIONAL_SHEET_ROWS


def test_every_mapping_value_is_a_sheet_country() -> None:
    assert set(ISO_TO_DAMODARAN_COUNTRY.values()) <= _sheet_countries()
    assert len(set(ISO_TO_DAMODARAN_COUNTRY.values())) == len(ISO_TO_DAMODARAN_COUNTRY)


def test_keys_are_upper_case_alpha_2() -> None:
    assert all(re.fullmatch(r"[A-Z]{2}", code) for code in ISO_TO_DAMODARAN_COUNTRY)


def test_no_damodaran_name_is_two_letters() -> None:
    names = set(ISO_TO_DAMODARAN_COUNTRY.values()) | SUBNATIONAL_SHEET_ROWS
    assert all(len(name) > 2 for name in names)


def _provider_codes() -> set[str]:
    """Every country code a known provider emitted in the recorded fixtures."""
    codes = {
        parse_submissions_info("AAPL", {"name": "Apple Inc."}).country,
        parse_company_facts("AAPL", {"entityName": "Apple Inc.", "facts": {}}).company["country"],
    }
    pattern = re.compile(r'\\?"country\\?":\s*\\?"([^"\\]*)\\?"')
    for cassette in (FIXTURES / "cassettes").rglob("*.yaml"):
        codes.update(pattern.findall(cassette.read_text(encoding="utf-8")))
    return {c for c in codes if c}


def test_every_known_provider_code_is_mapped() -> None:
    codes = _provider_codes()
    assert {"US", "CH", "JP"} <= codes
    assert {c: damodaran_country_name(c) for c in codes if c not in ISO_TO_DAMODARAN_COUNTRY} == {}


def test_normalises_case_and_whitespace() -> None:
    assert damodaran_country_name(" us ") == "United States"
    assert damodaran_country_name("ch") == "Switzerland"


def test_damodaran_names_pass_through_silently() -> None:
    with capture_logs() as logs:
        assert damodaran_country_name("United States") == "United States"
        assert damodaran_country_name(" Japan ") == "Japan"
        assert damodaran_country_name("Abu Dhabi") == "Abu Dhabi"
    assert logs == []


def test_none_and_blank_are_none() -> None:
    assert damodaran_country_name(None) is None
    assert damodaran_country_name("  ") is None


def test_unmapped_code_passes_through_and_logs_once() -> None:
    with capture_logs() as logs:
        assert damodaran_country_name("ZZ") == "ZZ"
        assert damodaran_country_name("zz") == "zz"
        assert damodaran_country_name(" ZZ") == "ZZ"
        assert damodaran_country_name("USA") == "USA"
    events = [(e["event"], e["country"]) for e in logs]
    assert events == [
        ("reference.country_unmapped", "ZZ"),
        ("reference.country_unmapped", "USA"),
    ]
