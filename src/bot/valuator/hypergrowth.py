"""Story file schema of the hypergrowth story type (spec §7.1/§7.6, #194, story #192).

``config/assumptions/<TICKER>.yaml`` may carry a ``story`` section (the
hypergrowth inputs) and a ``scenarios`` section (named subsets of story keys
merged over the base story). :func:`parse_story`, :func:`parse_scenarios` and
:func:`story_from_override` turn them into frozen :class:`StoryInputs`.

The module is pure: no I/O, no global state. Every refusal is a ``ValueError``
whose message starts with the file path (``where``) and names the key, so
``bot analyze`` fails that ticker alone. Money amounts are in the raw reporting
currency of ``financials_annual``, not millions.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any

#: Story-type label of a story file. ``StoryType.HYPERGROWTH`` arrives in #195.
STORY_TYPE = "hypergrowth"


def is_finite_number(value: object) -> bool:
    """Whether ``value`` is a finite ``int``/``float`` (never a ``bool``) or numeric ``str``.

    Strings count because PyYAML reads ``1e11`` (no dot) as a string.
    """
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float, str)):
        return False
    try:
        return math.isfinite(float(value))
    except (ValueError, OverflowError):
        return False


@dataclass(frozen=True, kw_only=True)
class StoryInputs:
    """Validated inputs of a hypergrowth story, in the issue's schema order."""

    year1_growth: float
    target_revenue_y10: float
    year1_margin: float
    target_margin: float
    margin_converge_year: int = 5
    regulatory_drag: float = 0.0
    sales_to_capital: float
    wacc_start: float
    wacc_terminal: float | None = None
    effective_tax_rate: float = 0.0
    terminal_roic: float | None = None
    failure_probability: float = 0.0
    failure_proceeds_pct_of_value: float = 0.0
    fixed_commitments_pv: float = 0.0
    extra_cash: float = 0.0
    governance_discount: float = 0.0


#: Per-key rule: ``(is_int, in_range, rule text)``. Keys of :class:`StoryInputs`
#: outside :data:`_REQUIRED` have a default and are optional.
_Rule = tuple[bool, Callable[[float], bool], str]

#: One validator per story key (ranges of issue #194). It drives unknown-key
#: detection, the required-key check and the scenario path.
_RULES: dict[str, _Rule] = {
    "year1_growth": (False, lambda x: x > -1, "greater than -1"),
    "target_revenue_y10": (False, lambda x: x > 0, "greater than 0"),
    "year1_margin": (False, lambda x: x < 1, "less than 1"),
    "target_margin": (False, lambda x: x < 1, "less than 1"),
    "margin_converge_year": (True, lambda x: 1 <= x <= 10, "an integer from 1 to 10"),
    "regulatory_drag": (False, lambda x: 0 <= x <= 1, "between 0 and 1"),
    "sales_to_capital": (False, lambda x: x > 0, "greater than 0"),
    "wacc_start": (False, lambda x: 0 < x < 1, "greater than 0 and less than 1"),
    "wacc_terminal": (False, lambda x: 0 < x < 1, "greater than 0 and less than 1"),
    "effective_tax_rate": (False, lambda x: 0 <= x <= 1, "between 0 and 1"),
    "terminal_roic": (False, lambda x: x > 0, "greater than 0"),
    "failure_probability": (False, lambda x: 0 <= x <= 1, "between 0 and 1"),
    "failure_proceeds_pct_of_value": (False, lambda x: 0 <= x <= 1, "between 0 and 1"),
    "fixed_commitments_pv": (False, lambda x: x >= 0, "at least 0"),
    "extra_cash": (False, lambda x: x >= 0, "at least 0"),
    "governance_discount": (False, lambda x: 0 <= x < 1, "at least 0 and less than 1"),
}

#: Keys without a default in :class:`StoryInputs`: the file must give them.
_REQUIRED = (
    "year1_growth",
    "target_revenue_y10",
    "year1_margin",
    "target_margin",
    "sales_to_capital",
    "wacc_start",
)


def _check_value(key: str, value: object, *, where: str, prefix: str) -> float | int:
    is_int, in_range, rule = _RULES[key]
    label = f"{prefix}{key}"
    if is_int:
        ok = isinstance(value, int) and not isinstance(value, bool) and in_range(value)
        if not ok:
            raise ValueError(f"{where}: {label} must be {rule}, got {value!r}")
        assert isinstance(value, int)
        return value
    if not is_finite_number(value) or not in_range(float(value)):  # type: ignore[arg-type]
        raise ValueError(f"{where}: {label} must be a number {rule}, got {value!r}")
    return float(value)  # type: ignore[arg-type]


def _check_keys(
    raw: Mapping[str, Any], *, where: str, prefix: str, label: str
) -> dict[str, float | int]:
    unknown = [k for k in raw if k not in _RULES]
    if unknown:
        valid = ", ".join(_RULES)
        raise ValueError(
            f"{where}: unknown {label} key(s): {', '.join(str(k) for k in unknown)}. "
            f"Valid keys: {valid}"
        )
    return {k: _check_value(k, v, where=where, prefix=prefix) for k, v in raw.items()}


def parse_story(raw: Mapping[str, Any], *, where: str) -> StoryInputs:
    """Validate the ``story`` mapping into :class:`StoryInputs`."""
    if not isinstance(raw, Mapping):
        raise ValueError(f"{where}: story must be a mapping, got {raw!r}")
    values = _check_keys(raw, where=where, prefix="story.", label="story")
    missing = [k for k in _REQUIRED if k not in values]
    if missing:
        raise ValueError(f"{where}: story is missing required key(s): {', '.join(missing)}")
    return StoryInputs(**values)  # type: ignore[arg-type]


def parse_scenarios(
    raw: Mapping[str, Any], base: StoryInputs, *, where: str
) -> dict[str, StoryInputs]:
    """Validate ``scenarios`` and merge each over ``base``, in file order."""
    if not isinstance(raw, Mapping):
        raise ValueError(f"{where}: scenarios must be a mapping, got {raw!r}")
    if not raw:
        raise ValueError(f"{where}: scenarios must not be empty")
    out: dict[str, StoryInputs] = {}
    for name, body in raw.items():
        if not isinstance(name, str):
            raise ValueError(f"{where}: scenarios names must be strings, got {name!r}")
        if not isinstance(body, Mapping):
            raise ValueError(
                f"{where}: scenarios.{name} must be a mapping of story keys, got {body!r}"
            )
        if not body:
            raise ValueError(f"{where}: scenarios.{name} must not be empty")
        values = _check_keys(
            body, where=where, prefix=f"scenarios.{name}.", label=f"scenarios.{name}"
        )
        out[name] = replace(base, **values)  # type: ignore[arg-type]
    return out


def story_from_override(
    override: Mapping[str, Any], *, where: str
) -> tuple[StoryInputs, dict[str, StoryInputs]] | None:
    """Parse the ``story`` (and optional ``scenarios``) of an override mapping.

    Returns ``None`` when ``story`` is absent; scenarios are ``{}`` when absent.
    """
    if "story" not in override:
        return None
    story = parse_story(override["story"], where=where)
    if "scenarios" not in override:
        return story, {}
    return story, parse_scenarios(override["scenarios"], story, where=where)
