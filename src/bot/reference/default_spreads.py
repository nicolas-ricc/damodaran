"""The curated coverage -> rating -> default-probability tables (#213, spec §7.3).

``config/default_spreads.yaml`` is hand-curated from two sources: Damodaran's
synthetic-rating table (interest coverage ratio to rating) and Table 5 of
"Valuing Distressed and Declining Companies" (rating to ten-year cumulative
default probability). The loader is a pure ``path -> table`` function that
degrades to an empty table when the file is missing or malformed (spec §13.2)
and fails loudly on out-of-range or inconsistent values.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from itertools import pairwise
from pathlib import Path
from types import MappingProxyType
from typing import Any

import structlog
import yaml

log = structlog.get_logger(__name__)

DEFAULT_SPREADS_PATH = Path("config/default_spreads.yaml")

_TOP_LEVEL = ("horizon_years", "coverage_to_rating", "rating_to_default_probability")
_BRACKET_FIELDS = ("lower", "upper", "rating", "source", "as_of")
_PROBABILITY_FIELDS = ("probability", "source", "as_of")


@dataclass(frozen=True)
class CoverageBracket:
    """Interest-coverage interval ``[lower, upper)`` mapped to a rating.

    ``None`` marks an unbounded side.
    """

    lower: float | None
    upper: float | None
    rating: str
    source: str
    as_of: date


@dataclass(frozen=True)
class DefaultProbability:
    """Cumulative default probability for a rating, as a decimal."""

    probability: float
    source: str
    as_of: date


@dataclass(frozen=True)
class DefaultSpreadTable:
    """Brackets sorted by coverage, tiling the real line, plus rating probabilities."""

    horizon_years: int | None
    brackets: tuple[CoverageBracket, ...]
    probabilities: Mapping[str, DefaultProbability]

    @property
    def is_empty(self) -> bool:
        """``True`` when there are no brackets (absent or malformed file)."""
        return not self.brackets

    def rating_for(self, coverage: float) -> str | None:
        """Rating of the bracket containing ``coverage``; ``None`` for NaN or an empty table."""
        if math.isnan(coverage):
            return None
        for bracket in self.brackets:
            if bracket.upper is None or coverage < bracket.upper:
                return bracket.rating
        return None

    def probability_for(self, rating: str) -> float | None:
        """Default probability for ``rating``; ``None`` when the rating is unknown."""
        row = self.probabilities.get(rating)
        return row.probability if row is not None else None


EMPTY_DEFAULT_SPREADS = DefaultSpreadTable(None, (), MappingProxyType({}))


class _MalformedError(Exception):
    pass


class _UniqueKeyLoader(yaml.SafeLoader):
    """``SafeLoader`` that rejects a repeated key instead of keeping the last one."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in seen:
                raise _MalformedError(f"duplicate key {key!r}")
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def _number(raw: Any, where: str, field: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise _MalformedError(f"{where}.{field}: not a number")
    return float(raw)


def _text(raw: Any, where: str, field: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise _MalformedError(f"{where}.{field}: missing or not a string")
    return raw.strip()


def _date(raw: Any, where: str) -> date:
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    if isinstance(raw, str):
        try:
            return date.fromisoformat(raw.strip())
        except ValueError:
            pass
    raise _MalformedError(f"{where}.as_of: not a date")


def _bound(raw: Any, where: str, field: str) -> float | None:
    return None if raw is None else _number(raw, where, field)


def _row(raw: Any, where: str, fields: tuple[str, ...]) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise _MalformedError(f"{where}: row is not a mapping")
    for field in fields:
        if field not in raw:
            raise _MalformedError(f"{where}.{field}: missing")
    return raw


def _bracket(raw: Any, index: int) -> CoverageBracket:
    where = f"coverage_to_rating[{index}]"
    row = _row(raw, where, _BRACKET_FIELDS)
    return CoverageBracket(
        lower=_bound(row["lower"], where, "lower"),
        upper=_bound(row["upper"], where, "upper"),
        rating=_text(row["rating"], where, "rating"),
        source=_text(row["source"], where, "source"),
        as_of=_date(row["as_of"], where),
    )


def _probability(raw: Any, rating: Any) -> DefaultProbability:
    where = f"rating_to_default_probability[{rating!r}]"
    row = _row(raw, where, _PROBABILITY_FIELDS)
    return DefaultProbability(
        probability=_number(row["probability"], where, "probability"),
        source=_text(row["source"], where, "source"),
        as_of=_date(row["as_of"], where),
    )


def _check_brackets(path: Path, brackets: tuple[CoverageBracket, ...]) -> None:
    for bracket in brackets:
        if (
            bracket.lower is not None
            and bracket.upper is not None
            and not (bracket.lower < bracket.upper)
        ):
            raise ValueError(
                f"{path}: bracket {bracket.rating} has lower={bracket.lower} "
                f"not below upper={bracket.upper}"
            )
    if brackets[0].lower is not None:
        raise ValueError(f"{path}: first bracket {brackets[0].rating} must have lower: null")
    if brackets[-1].upper is not None:
        raise ValueError(f"{path}: last bracket {brackets[-1].rating} must have upper: null")
    for prev, nxt in pairwise(brackets):
        if nxt.lower is None or prev.upper is None:
            raise ValueError(
                f"{path}: brackets {prev.rating} and {nxt.rating} must have bounded inner edges"
            )
        if prev.upper != nxt.lower:
            raise ValueError(
                f"{path}: brackets {prev.rating} (upper={prev.upper}) and {nxt.rating} "
                f"(lower={nxt.lower}) leave a gap or overlap"
            )


def _parse(path: Path, data: Any) -> DefaultSpreadTable:
    if not isinstance(data, dict):
        raise _MalformedError("top level is not a mapping")
    if set(data) != set(_TOP_LEVEL):
        raise _MalformedError(f"top-level keys must be exactly {', '.join(_TOP_LEVEL)}")
    horizon = data["horizon_years"]
    _number(horizon, "horizon_years", "value")
    raw_brackets = data["coverage_to_rating"]
    if not isinstance(raw_brackets, list) or not raw_brackets:
        raise _MalformedError("coverage_to_rating: not a non-empty list")
    raw_probabilities = data["rating_to_default_probability"]
    if not isinstance(raw_probabilities, dict):
        raise _MalformedError("rating_to_default_probability: not a mapping")
    brackets = [_bracket(raw, i) for i, raw in enumerate(raw_brackets)]
    probabilities: dict[str, DefaultProbability] = {}
    for rating, raw in raw_probabilities.items():
        if not isinstance(rating, str) or not rating.strip():
            raise _MalformedError(f"rating key {rating!r} is not a non-empty string")
        probabilities[rating.strip()] = _probability(raw, rating)

    if not (isinstance(horizon, int) and horizon > 0):
        raise ValueError(f"{path}: horizon_years={horizon!r} is not a positive integer")
    for rating, row in probabilities.items():
        if not 0.0 <= row.probability <= 1.0:
            raise ValueError(
                f"{path}: {rating} probability={row.probability} outside [0, 1]; "
                "values are decimals (0.81, not 81)"
            )
    ordered = tuple(
        sorted(
            brackets, key=lambda b: (b.lower is not None, b.lower if b.lower is not None else 0.0)
        )
    )
    _check_brackets(path, ordered)
    for bracket in ordered:
        if bracket.rating not in probabilities:
            raise ValueError(f"{path}: bracket rating {bracket.rating} has no default probability")
    return DefaultSpreadTable(horizon, ordered, MappingProxyType(probabilities))


def load_default_spreads(path: Path | None = None) -> DefaultSpreadTable:
    """Load the default-spread tables.

    Args:
        path: YAML location; ``None`` reads :data:`DEFAULT_SPREADS_PATH`.

    Returns:
        The table, or :data:`EMPTY_DEFAULT_SPREADS` (with one warning) when the
        file is absent or malformed.

    Raises:
        ValueError: A probability outside [0, 1], a ``horizon_years`` that is not
            a positive integer, brackets that do not tile the real line, or a
            bracket rating without a probability.
    """
    target = path if path is not None else DEFAULT_SPREADS_PATH
    if not target.exists():
        log.warning("default_spreads.absent", path=str(target))
        return EMPTY_DEFAULT_SPREADS
    try:
        table = _parse(target, yaml.load(target.read_text(), Loader=_UniqueKeyLoader))
    except (yaml.YAMLError, _MalformedError, OSError, UnicodeDecodeError) as exc:
        log.warning("default_spreads.malformed", path=str(target), reason=str(exc))
        return EMPTY_DEFAULT_SPREADS
    log.info(
        "default_spreads.loaded",
        path=str(target),
        brackets=len(table.brackets),
        ratings=len(table.probabilities),
    )
    return table
