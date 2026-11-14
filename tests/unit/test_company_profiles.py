"""Company profiles and the industry tag vocabulary (issue #333)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from bot.reference.company_profiles import (
    ProfileError,
    load_company_profiles,
    load_industry_tags,
    load_profiles,
)

_VOCABULARY: list[dict[str, str]] = [
    {"slug": "cybersecurity", "label": "Cybersecurity", "description": "Security software."},
    {"slug": "smartphones", "label": "Smartphones", "description": "Phones."},
    {"slug": "digital-services", "label": "Digital services", "description": "App stores."},
]


def _profile(**overrides: Any) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "description": "Sells endpoint security software to companies.",
        "fiscal_year": 2026,
        "accession": "0001535527-26-000012",
        "tags": [{"tag": "cybersecurity", "share": 0.95, "source": "segment"}],
    }
    entry.update(overrides)
    return entry


def _write(tmp_path: Path, tags: Any, profiles: Any) -> tuple[Path, Path]:
    tags_path = tmp_path / "industry_tags.yaml"
    profiles_path = tmp_path / "company_profiles.yaml"
    tags_path.write_text(yaml.safe_dump(tags), encoding="utf-8")
    profiles_path.write_text(yaml.safe_dump(profiles), encoding="utf-8")
    return profiles_path, tags_path


def test_loads_a_valid_profile(tmp_path: Path) -> None:
    profiles = load_profiles(*_write(tmp_path, _VOCABULARY, {"CRWD": _profile()}))
    profile = profiles["CRWD"]
    assert profile.ticker == "CRWD"
    assert profile.fiscal_year == 2026
    assert profile.accession == "0001535527-26-000012"
    assert profile.description == "Sells endpoint security software to companies."
    assert len(profile.tags) == 1
    assert profile.tags[0].tag.slug == "cybersecurity"
    assert profile.tags[0].tag.label == "Cybersecurity"
    assert profile.tags[0].share == 0.95
    assert profile.tags[0].source == "segment"


def test_tags_sorted_by_share_descending(tmp_path: Path) -> None:
    tags = [
        {"tag": "cybersecurity", "share": 0.10, "source": "judgment"},
        {"tag": "smartphones", "share": 0.51, "source": "disaggregation"},
        {"tag": "digital-services", "share": 0.25, "source": "disaggregation"},
    ]
    profiles = load_profiles(*_write(tmp_path, _VOCABULARY, {"AAPL": _profile(tags=tags)}))
    assert [t.share for t in profiles["AAPL"].tags] == [0.51, 0.25, 0.10]


@pytest.mark.parametrize(
    "tags",
    [
        [
            {"tag": "cybersecurity", "share": 0.7, "source": "segment"},
            {"tag": "smartphones", "share": 0.2, "source": "segment"},
            {"tag": "digital-services", "share": 0.1, "source": "segment"},
        ],
        [
            {"tag": "cybersecurity", "share": 0.34, "source": "segment"},
            {"tag": "smartphones", "share": 0.33, "source": "segment"},
            {"tag": "digital-services", "share": 0.33, "source": "segment"},
        ],
    ],
)
def test_share_sum_tolerates_float_noise(tmp_path: Path, tags: list[dict[str, Any]]) -> None:
    profiles = load_profiles(*_write(tmp_path, _VOCABULARY, {"X": _profile(tags=tags)}))
    assert len(profiles["X"].tags) == 3


def test_a_ticker_key_keeps_the_universe_format(tmp_path: Path) -> None:
    profiles = load_profiles(*_write(tmp_path, _VOCABULARY, {"BRK-B": _profile()}))
    assert set(profiles) == {"BRK-B"}


_TWO = [
    {"tag": "cybersecurity", "share": 0.6, "source": "segment"},
    {"tag": "smartphones", "share": 0.5, "source": "segment"},
]
_TWICE = [
    {"tag": "cybersecurity", "share": 0.4, "source": "segment"},
    {"tag": "cybersecurity", "share": 0.3, "source": "segment"},
]


@pytest.mark.parametrize(
    ("entry", "match"),
    [
        (_profile(tags=[{"tag": "infosec", "share": 0.5, "source": "segment"}]), "unknown tag"),
        (_profile(tags=[{"tag": "cybersecurity", "share": 0.09, "source": "segment"}]), "share"),
        (_profile(tags=[{"tag": "cybersecurity", "share": 1.01, "source": "segment"}]), "share"),
        (_profile(tags=[{"tag": "cybersecurity", "share": "high", "source": "segment"}]), "share"),
        (_profile(tags=[{"tag": "cybersecurity", "share": True, "source": "segment"}]), "share"),
        (_profile(tags=_TWO), "sum"),
        (_profile(tags=[{"tag": "cybersecurity", "share": 0.5, "source": "guess"}]), "source"),
        (_profile(tags=[{"tag": "cybersecurity", "share": 0.5}]), "source"),
        (_profile(tags=[]), "tags"),
        (_profile(tags=None), "tags"),
        (_profile(description="  "), "description"),
        (_profile(description=None), "description"),
        (_profile(accession="0001535527-26-12"), "accession"),
        (_profile(accession="000153552726000012"), "accession"),
        (_profile(tags=_TWICE), "duplicate"),
        ({k: v for k, v in _profile().items() if k != "fiscal_year"}, "fiscal_year"),
        (_profile(fiscal_year="2026"), "fiscal_year"),
        ("not a mapping", "CRWD"),
    ],
)
def test_rejects_bad_profile(tmp_path: Path, entry: Any, match: str) -> None:
    paths = _write(tmp_path, _VOCABULARY, {"CRWD": entry})
    with pytest.raises(ProfileError, match=match) as raised:
        load_profiles(*paths)
    assert "CRWD" in str(raised.value)


def test_rejects_a_profiles_file_that_is_not_a_mapping(tmp_path: Path) -> None:
    with pytest.raises(ProfileError):
        load_profiles(*_write(tmp_path, _VOCABULARY, ["CRWD"]))


@pytest.mark.parametrize(
    "vocabulary",
    [
        [{"slug": "Cyber Security", "label": "Cybersecurity", "description": "x"}],
        [{"slug": "cyber_security", "label": "Cybersecurity", "description": "x"}],
        [{"slug": "cybersecurity", "label": "", "description": "x"}],
        [{"slug": "cybersecurity", "label": "Cybersecurity", "description": " "}],
        [{"slug": "cybersecurity", "label": "Cybersecurity"}],
        [
            {"slug": "cybersecurity", "label": "Cybersecurity", "description": "x"},
            {"slug": "cybersecurity", "label": "Cyber", "description": "y"},
        ],
        {"cybersecurity": {"label": "Cybersecurity", "description": "x"}},
        ["cybersecurity"],
        [],
    ],
)
def test_rejects_bad_vocabulary(tmp_path: Path, vocabulary: Any) -> None:
    _, tags_path = _write(tmp_path, vocabulary, {})
    with pytest.raises(ProfileError):
        load_industry_tags(tags_path)


def test_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ProfileError):
        load_industry_tags(tmp_path / "nope.yaml")
    vocabulary = load_industry_tags(_write(tmp_path, _VOCABULARY, {})[1])
    with pytest.raises(ProfileError):
        load_company_profiles(tmp_path / "nope.yaml", vocabulary)


def test_malformed_yaml_raises(tmp_path: Path) -> None:
    profiles_path, tags_path = _write(tmp_path, _VOCABULARY, {})
    profiles_path.write_text("CRWD: [unclosed\n", encoding="utf-8")
    with pytest.raises(ProfileError):
        load_profiles(profiles_path, tags_path)
