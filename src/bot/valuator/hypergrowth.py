"""Story file schema of the hypergrowth story type (spec §7.1/§7.6, #194, story #192).

``config/assumptions/<TICKER>.yaml`` may carry a ``story`` section (the
hypergrowth inputs) and a ``scenarios`` section (named subsets of story keys
merged over the base story). :func:`parse_story`, :func:`parse_scenarios` and
:func:`story_from_override` turn them into frozen :class:`StoryInputs`.

The module is pure: no I/O, no global state. Every refusal is a ``ValueError``,
so ``bot analyze`` fails that ticker alone; a parse refusal's message starts
with the file path (``where``) and names the key. Money amounts are in the raw reporting
currency of ``financials_annual``, not millions.

The ten-year paths of a story (growth, operating margin, WACC, tax rate) are
built by :func:`growth_path`, :func:`margin_path`, :func:`wacc_path` and
:func:`tax_path`; :func:`solve_stage_growth` finds the constant growth rate of years
2-5 that reaches ``target_revenue_y10``.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Mapping
from dataclasses import MISSING, dataclass, fields, replace
from typing import TYPE_CHECKING, Any, TypeGuard

if TYPE_CHECKING:
    from bot.valuator.assumptions import Assumptions

#: Story-type label of a story file. ``StoryType.HYPERGROWTH`` arrives in #195.
STORY_TYPE = "hypergrowth"


def is_finite_number(value: object) -> TypeGuard[int | float | str]:
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


#: Years of the explicit forecast: every path has this many values.
HORIZON: int = 10

#: Last year of the constant-growth stage (years 2-5); growth fades to the
#: terminal rate over the remaining ``HORIZON - _STAGE_END`` years.
_STAGE_END: int = 5

#: Bracket of the stage growth bisection: just above total loss up to 1,000%.
_SOLVE_BOUNDS: tuple[float, float] = (-0.99, 10.0)

#: Bisection steps; 200 halvings exhaust float precision on the bracket.
_SOLVE_ITERATIONS: int = 200

#: Per-key rule: ``(is_int, in_range, rule text)``.
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
_REQUIRED = tuple(f.name for f in fields(StoryInputs) if f.default is MISSING)


def _check_value(key: str, value: object, *, where: str, prefix: str) -> float | int:
    is_int, in_range, rule = _RULES[key]
    label = f"{prefix}{key}"
    if is_int:
        if not isinstance(value, int) or isinstance(value, bool) or not in_range(value):
            raise ValueError(f"{where}: {label} must be {rule}, got {value!r}")
        return value
    if not is_finite_number(value) or not in_range(float(value)):
        raise ValueError(f"{where}: {label} must be a number {rule}, got {value!r}")
    return float(value)


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
            raise ValueError(f"{where}: scenarios: each name must be a string, got {name!r}")
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


def _stage_growth_rates(
    year1_growth: float, stage: float, terminal_growth: float
) -> tuple[float, ...]:
    """Growth of years 1..HORIZON: year 1, flat stage, then a linear fade to terminal."""
    fade = HORIZON - _STAGE_END
    return (
        (year1_growth,)
        + (stage,) * (_STAGE_END - 1)
        + tuple(stage - k * (stage - terminal_growth) / fade for k in range(1, fade + 1))
    )


def _revenue_y10(
    base_revenue: float, story: StoryInputs, stage: float, terminal_growth: float
) -> float:
    revenue = base_revenue
    for rate in _stage_growth_rates(story.year1_growth, stage, terminal_growth):
        revenue *= 1 + rate
    return revenue


def solve_stage_growth(base_revenue: float, story: StoryInputs, terminal_growth: float) -> float:
    """Stage growth rate (years 2-5) that compounds ``base_revenue`` to the story's year-10 revenue.

    Revenue is increasing in the rate, so this bisects on ``_SOLVE_BOUNDS``.
    Raises ``ValueError`` when ``terminal_growth <= -1`` or the target is
    unreachable (including a non-positive ``base_revenue``).
    """
    if terminal_growth <= -1:
        raise ValueError(f"terminal_growth must be greater than -1, got {terminal_growth!r}")
    target = story.target_revenue_y10
    low, high = _SOLVE_BOUNDS
    if base_revenue <= 0 or not (
        _revenue_y10(base_revenue, story, low, terminal_growth)
        <= target
        <= _revenue_y10(base_revenue, story, high, terminal_growth)
    ):
        raise ValueError(
            f"target_revenue_y10 {target} unreachable from base revenue {base_revenue}: "
            f"stage growth must lie between {low} and {high}"
        )
    for _ in range(_SOLVE_ITERATIONS):
        mid = (low + high) / 2
        if _revenue_y10(base_revenue, story, mid, terminal_growth) < target:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def growth_path(
    base_revenue: float, story: StoryInputs, terminal_growth: float
) -> tuple[float, ...]:
    """Revenue growth of years 1..10: year 1, solved stage rate, fade to ``terminal_growth``."""
    stage = solve_stage_growth(base_revenue, story, terminal_growth)
    return _stage_growth_rates(story.year1_growth, stage, terminal_growth)


def margin_path(story: StoryInputs) -> tuple[float, ...]:
    """Operating margin of years 1..10: linear from year 1 to the drag-adjusted target."""
    target = story.target_margin - story.regulatory_drag
    first, converge = story.year1_margin, story.margin_converge_year
    later = (
        first + (target - first) * t / converge if t <= converge else target
        for t in range(2, HORIZON + 1)
    )
    return (first, *later)


def _fade_path(start: float, end: float) -> tuple[float, ...]:
    """Flat at ``start`` through the stage, linear fade to ``end`` (exact) in year 10."""
    fade = HORIZON - _STAGE_END
    if start == end:
        return (start,) * HORIZON
    return (
        (start,) * _STAGE_END
        + tuple(start + (end - start) * k / fade for k in range(1, fade))
        + (end,)
    )


def wacc_path(story: StoryInputs, wacc_terminal: float) -> tuple[float, ...]:
    """WACC of years 1..10: ``wacc_start`` through year 5, fading to ``wacc_terminal``."""
    return _fade_path(story.wacc_start, wacc_terminal)


def tax_path(story: StoryInputs, marginal_tax_rate: float) -> tuple[float, ...]:
    """Tax rate of years 1..10: ``effective_tax_rate`` through year 5, fading to marginal."""
    return _fade_path(story.effective_tax_rate, marginal_tax_rate)


def apply_story(
    bundle: Assumptions,
    story: StoryInputs,
    *,
    base_revenue: float,
    sector_wacc: float | None,
) -> Assumptions:
    """Overlay ``story`` on a resolved generic ``bundle``, every set field sourced ``STORY``.

    ``terminal_growth``, ``tax_rate`` and ``pretax_cost_of_debt`` stay the
    bundle's own objects. The terminal WACC is the story's, else ``sector_wacc``.
    Raises ``ValueError`` when the terminal WACC, ``terminal_growth`` or
    ``tax_rate`` is unresolved.
    """
    # Imported here: assumptions.py imports this module at load time.
    from bot.valuator.assumptions import AssumptionSource, Sourced

    wacc_terminal = story.wacc_terminal if story.wacc_terminal is not None else sector_wacc
    if wacc_terminal is None:
        raise ValueError(
            "apply_story: wacc_terminal unresolved: no sector WACC; set story.wacc_terminal"
        )
    terminal_growth = bundle.terminal_growth.value
    if terminal_growth is None:
        raise ValueError("apply_story: terminal_growth unresolved")
    marginal_tax_rate = bundle.tax_rate.value
    if marginal_tax_rate is None:
        raise ValueError("apply_story: tax_rate unresolved")

    def sourced[T](value: T) -> Sourced[T]:
        return Sourced(value, AssumptionSource.STORY)

    return replace(
        bundle,
        revenue_growth=sourced(growth_path(base_revenue, story, terminal_growth)),
        operating_margin=sourced(margin_path(story)),
        sales_to_capital=sourced(story.sales_to_capital),
        cost_of_equity=sourced(story.wacc_start),
        equity_weight=sourced(1.0),
        debt_weight=sourced(0.0),
        probability_of_bankruptcy=sourced(story.failure_probability),
        wacc_path=sourced(wacc_path(story, wacc_terminal)),
        tax_rate_path=sourced(tax_path(story, marginal_tax_rate)),
        terminal_roic=None if story.terminal_roic is None else sourced(story.terminal_roic),
        distress_proceeds_pct=sourced(story.failure_proceeds_pct_of_value),
        fixed_commitments=sourced(story.fixed_commitments_pv),
        extra_cash=sourced(story.extra_cash),
        governance_discount=sourced(story.governance_discount),
        story=story,
    )
