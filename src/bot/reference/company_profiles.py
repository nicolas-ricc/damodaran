"""Company profiles and the industry tag vocabulary (issue #333, spec §6.2).

``config/industry_tags.yaml`` is the closed vocabulary of industry tags and
``config/company_profiles.yaml`` maps each ticker to a plain-language
description, the filing it was read from, and weighted tags drawn from that
vocabulary. Unlike ``default_spreads.py`` nothing degrades silently: a missing
file or any defect raises :class:`ProfileError` naming the ticker (or slug) and
the reason, so a bad commit fails the build instead of shipping a wrong viewer.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

INDUSTRY_TAGS_PATH = Path("config/industry_tags.yaml")
COMPANY_PROFILES_PATH = Path("config/company_profiles.yaml")

SOURCES: tuple[str, ...] = ("segment", "disaggregation", "judgment")

_MIN_SHARE = 0.10
_MAX_SHARE = 1.0
_SUM_TOLERANCE = 1e-9
_SLUG = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
_ACCESSION = re.compile(r"^\d{10}-\d{2}-\d{6}$")


class ProfileError(ValueError):
    """A profile or vocabulary file is missing, unparsable, or inconsistent."""


@dataclass(frozen=True)
class IndustryTag:
    """One entry of the closed industry vocabulary."""

    slug: str
    label: str
    description: str


@dataclass(frozen=True)
class ProfileTag:
    """A tag on a company: its share of the business and where that came from."""

    tag: IndustryTag
    share: float
    source: str


@dataclass(frozen=True)
class CompanyProfile:
    """Description, source filing and tags (share descending, then slug)."""

    ticker: str
    description: str
    fiscal_year: int
    accession: str
    tags: tuple[ProfileTag, ...]


def _read(path: Path) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise ProfileError(f"{path}: cannot read file: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ProfileError(f"{path}: malformed YAML: {exc}") from exc


def _text(raw: Any, where: str, field: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise ProfileError(f"{where}: {field} is missing or not a non-empty string")
    return raw.strip()


def _industry_tag(raw: Any, index: int) -> IndustryTag:
    where = f"industry tag #{index}"
    if not isinstance(raw, dict):
        raise ProfileError(f"{where}: not a mapping")
    slug = raw.get("slug")
    if not isinstance(slug, str) or not _SLUG.match(slug):
        raise ProfileError(f"{where}: slug {slug!r} is not kebab-case")
    where = f"industry tag {slug!r}"
    return IndustryTag(
        slug=slug,
        label=_text(raw.get("label"), where, "label"),
        description=_text(raw.get("description"), where, "description"),
    )


def load_industry_tags(path: Path) -> dict[str, IndustryTag]:
    """Load the vocabulary, keyed by slug.

    Raises:
        ProfileError: Missing or malformed file, a non-kebab or duplicate slug,
            or an empty label or description.
    """
    data = _read(path)
    if not isinstance(data, list) or not data:
        raise ProfileError(f"{path}: top level is not a non-empty list of tags")
    tags: dict[str, IndustryTag] = {}
    for index, raw in enumerate(data):
        tag = _industry_tag(raw, index)
        if tag.slug in tags:
            raise ProfileError(f"{path}: duplicate slug {tag.slug!r}")
        tags[tag.slug] = tag
    return tags


def _share(raw: Any, where: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise ProfileError(f"{where}: share {raw!r} is not a number")
    if not _MIN_SHARE - _SUM_TOLERANCE <= raw <= _MAX_SHARE:
        raise ProfileError(f"{where}: share {raw} outside [{_MIN_SHARE}, {_MAX_SHARE}]")
    return float(raw)


def _profile_tag(raw: Any, ticker: str, vocabulary: Mapping[str, IndustryTag]) -> ProfileTag:
    if not isinstance(raw, dict):
        raise ProfileError(f"{ticker}: tag entry {raw!r} is not a mapping")
    slug = raw.get("tag")
    if not isinstance(slug, str) or slug not in vocabulary:
        raise ProfileError(f"{ticker}: unknown tag {slug!r}")
    where = f"{ticker}.{slug}"
    source = raw.get("source")
    if source not in SOURCES:
        raise ProfileError(f"{where}: source {source!r} not one of {', '.join(SOURCES)}")
    return ProfileTag(vocabulary[slug], _share(raw.get("share"), where), source)


def _profile(ticker: str, raw: Any, vocabulary: Mapping[str, IndustryTag]) -> CompanyProfile:
    if not isinstance(raw, dict):
        raise ProfileError(f"{ticker}: entry is not a mapping")
    description = _text(raw.get("description"), ticker, "description")
    year = raw.get("fiscal_year")
    if isinstance(year, bool) or not isinstance(year, int):
        raise ProfileError(f"{ticker}: fiscal_year {year!r} is missing or not an integer")
    accession = raw.get("accession")
    if not isinstance(accession, str) or not _ACCESSION.match(accession):
        raise ProfileError(f"{ticker}: accession {accession!r} is not NNNNNNNNNN-YY-NNNNNN")
    raw_tags = raw.get("tags")
    if not isinstance(raw_tags, list) or not raw_tags:
        raise ProfileError(f"{ticker}: tags is missing or not a non-empty list")
    tags = [_profile_tag(entry, ticker, vocabulary) for entry in raw_tags]
    slugs = [t.tag.slug for t in tags]
    for slug in sorted(set(slugs)):
        if slugs.count(slug) > 1:
            raise ProfileError(f"{ticker}: duplicate tag {slug!r}")
    if sum(t.share for t in tags) > 1 + _SUM_TOLERANCE:
        raise ProfileError(f"{ticker}: tag shares sum to more than 1")
    ordered = tuple(sorted(tags, key=lambda t: (-t.share, t.tag.slug)))
    return CompanyProfile(ticker, description, year, accession, ordered)


def load_company_profiles(
    path: Path, vocabulary: Mapping[str, IndustryTag]
) -> dict[str, CompanyProfile]:
    """Load the profiles, keyed by ticker, validated against ``vocabulary``.

    Raises:
        ProfileError: Missing or malformed file, or any invalid entry.
    """
    data = _read(path)
    if not isinstance(data, dict):
        raise ProfileError(f"{path}: top level is not a mapping of ticker to profile")
    profiles: dict[str, CompanyProfile] = {}
    for ticker, raw in data.items():
        if not isinstance(ticker, str) or not ticker.strip():
            raise ProfileError(f"{path}: ticker key {ticker!r} is not a non-empty string")
        profiles[ticker] = _profile(ticker, raw, vocabulary)
    return profiles


def load_profiles(
    profiles_path: Path = COMPANY_PROFILES_PATH, tags_path: Path = INDUSTRY_TAGS_PATH
) -> dict[str, CompanyProfile]:
    """Load the vocabulary, then the profiles that reference it."""
    return load_company_profiles(profiles_path, load_industry_tags(tags_path))
