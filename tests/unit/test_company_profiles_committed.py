"""The committed tag vocabulary and company profiles load and cover the universe (issue #333)."""

from __future__ import annotations

from pathlib import Path

from bot.reference.company_profiles import (
    COMPANY_PROFILES_PATH,
    INDUSTRY_TAGS_PATH,
    load_industry_tags,
    load_profiles,
)

_ROOT = Path(__file__).resolve().parents[2]
_UNIVERSE = _ROOT / "src" / "bot" / "ingest" / "universe_default.csv"

#: Universe tickers without a profile. The spec allows one only when no 10-K is
#: available; each entry names the missing filing.
PROFILE_EXCEPTIONS: frozenset[str] = frozenset()


def _universe() -> set[str]:
    lines = _UNIVERSE.read_text(encoding="utf-8").splitlines()
    return {
        line.strip()
        for line in lines
        if line.strip() and not line.startswith("#") and line.strip() != "ticker"
    }


def _profiles() -> dict[str, object]:
    return dict(load_profiles(_ROOT / COMPANY_PROFILES_PATH, _ROOT / INDUSTRY_TAGS_PATH))


def test_committed_vocabulary_loads() -> None:
    tags = load_industry_tags(_ROOT / INDUSTRY_TAGS_PATH)
    assert "cybersecurity" in tags
    assert 40 <= len(tags) <= 150


def test_committed_profiles_load() -> None:
    assert len(_profiles()) >= 1


def test_every_universe_ticker_has_a_profile() -> None:
    universe = _universe()
    profiles = set(_profiles())
    assert universe - PROFILE_EXCEPTIONS <= profiles, sorted(universe - PROFILE_EXCEPTIONS - profiles)
    assert not PROFILE_EXCEPTIONS & profiles
    assert universe >= PROFILE_EXCEPTIONS
    assert profiles <= universe, sorted(profiles - universe)


def test_cybersecurity_search_finds_pure_plays_not_sidelines() -> None:
    profiles = load_profiles(_ROOT / COMPANY_PROFILES_PATH, _ROOT / INDUSTRY_TAGS_PATH)

    def slugs(ticker: str) -> set[str]:
        return {t.tag.slug for t in profiles[ticker].tags}

    for ticker in ("CRWD", "PANW", "FTNT"):
        assert "cybersecurity" in slugs(ticker), ticker
    for ticker in ("MSFT", "CSCO"):
        assert "cybersecurity" not in slugs(ticker), ticker
