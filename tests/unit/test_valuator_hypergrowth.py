"""Story file schema of the hypergrowth story type (#194, story #192).

``parse_story`` / ``parse_scenarios`` / ``story_from_override`` turn the
``story`` and ``scenarios`` sections of ``config/assumptions/<TICKER>.yaml`` into
frozen :class:`StoryInputs`. Every refusal is a ``ValueError`` that starts with
the file path and names the key, so ``bot analyze`` fails that ticker alone.
"""

from __future__ import annotations

from dataclasses import fields
from pathlib import Path
from typing import Any

import pytest

from bot.valuator.hypergrowth import (
    StoryInputs,
    parse_scenarios,
    parse_story,
    story_from_override,
)

_WHERE = "config/assumptions/ANTH.yaml"
_ROOT = Path(__file__).resolve().parents[2]

#: The issue's full ``story:`` block (raw reporting currency, not millions).
_STORY: dict[str, Any] = {
    "year1_growth": 4.00,
    "target_revenue_y10": 1011491000000,
    "year1_margin": 0.05,
    "target_margin": 0.325,
    "margin_converge_year": 5,
    "regulatory_drag": 0.05,
    "sales_to_capital": 3.0,
    "wacc_start": 0.0974,
    "wacc_terminal": 0.0913,
    "effective_tax_rate": 0.0,
    "terminal_roic": 0.15,
    "failure_probability": 0.10,
    "failure_proceeds_pct_of_value": 0.50,
    "fixed_commitments_pv": 472336000000,
    "extra_cash": 100000000000,
    "governance_discount": 0.20,
}

_REQUIRED = (
    "year1_growth",
    "target_revenue_y10",
    "year1_margin",
    "target_margin",
    "sales_to_capital",
    "wacc_start",
)

_SCENARIOS: dict[str, Any] = {
    "worst": {
        "target_revenue_y10": 200000000000,
        "target_margin": 0.10,
        "sales_to_capital": 1.0,
        "wacc_start": 0.0988,
        "regulatory_drag": 0.10,
    },
    "best": {
        "target_revenue_y10": 1500000000000,
        "target_margin": 0.40,
        "sales_to_capital": 4.0,
        "wacc_start": 0.0779,
        "regulatory_drag": 0.0,
    },
}


def test_parse_story_round_trips_the_issue_schema() -> None:
    story = parse_story(_STORY, where=_WHERE)
    assert story == StoryInputs(**_STORY)
    assert story.target_revenue_y10 == 1_011_491_000_000.0
    assert story.wacc_terminal == pytest.approx(0.0913)
    assert story.margin_converge_year == 5
    assert isinstance(story.margin_converge_year, int)
    assert isinstance(story.target_revenue_y10, float)


def test_parse_story_defaults() -> None:
    story = parse_story({k: _STORY[k] for k in _REQUIRED}, where=_WHERE)
    assert story.margin_converge_year == 5
    assert story.wacc_terminal is None
    assert story.terminal_roic is None
    for name in (
        "regulatory_drag",
        "effective_tax_rate",
        "failure_probability",
        "failure_proceeds_pct_of_value",
        "fixed_commitments_pv",
        "extra_cash",
        "governance_discount",
    ):
        assert getattr(story, name) == 0.0, name


def _without(key: str) -> dict[str, Any]:
    return {k: v for k, v in _STORY.items() if k != key}


@pytest.mark.parametrize(
    ("raw", "key"),
    [
        pytest.param({**_STORY, "foo": 1}, "foo", id="unknown-key"),
        pytest.param(_without("wacc_start"), "wacc_start", id="missing-required"),
        pytest.param({**_STORY, "sales_to_capital": 0}, "sales_to_capital", id="stc-zero"),
        pytest.param(
            {**_STORY, "failure_probability": 1.5}, "failure_probability", id="prob-above-1"
        ),
        pytest.param({**_STORY, "target_margin": 1}, "target_margin", id="margin-one"),
        pytest.param(
            {**_STORY, "governance_discount": 1}, "governance_discount", id="governance-one"
        ),
        pytest.param(
            {**_STORY, "margin_converge_year": 2.5}, "margin_converge_year", id="year-float"
        ),
        pytest.param(
            {**_STORY, "margin_converge_year": 11}, "margin_converge_year", id="year-11"
        ),
        pytest.param({**_STORY, "year1_growth": -1}, "year1_growth", id="growth-minus-1"),
        pytest.param({**_STORY, "extra_cash": True}, "extra_cash", id="boolean"),
        pytest.param({**_STORY, "wacc_start": float("nan")}, "wacc_start", id="nan"),
        pytest.param(
            {**_STORY, "target_revenue_y10": float("inf")}, "target_revenue_y10", id="inf"
        ),
        pytest.param(
            {**_STORY, "target_revenue_y10": "nan"}, "target_revenue_y10", id="nan-string"
        ),
        pytest.param({**_STORY, "wacc_terminal": None}, "wacc_terminal", id="null"),
    ],
)
def test_parse_story_rejects(raw: dict[str, Any], key: str) -> None:
    with pytest.raises(ValueError) as excinfo:
        parse_story(raw, where=_WHERE)
    message = str(excinfo.value)
    assert message.startswith(_WHERE)
    assert key in message


def test_parse_story_rejects_a_non_mapping() -> None:
    with pytest.raises(ValueError) as excinfo:
        parse_story([1], where=_WHERE)  # type: ignore[arg-type]
    assert str(excinfo.value).startswith(_WHERE)


def test_parse_story_accepts_an_exponent_string() -> None:
    # PyYAML reads `1e12` (no dot) as a string; the override rule accepts it.
    story = parse_story({**_STORY, "target_revenue_y10": "1e12"}, where=_WHERE)
    assert story.target_revenue_y10 == 1e12


def test_parse_scenarios_merges_over_base_in_file_order() -> None:
    base = parse_story(_STORY, where=_WHERE)
    scenarios = parse_scenarios(_SCENARIOS, base, where=_WHERE)
    assert list(scenarios) == ["worst", "best"]
    worst = scenarios["worst"]
    assert worst.target_margin == pytest.approx(0.10)
    assert worst.regulatory_drag == pytest.approx(0.10)
    assert worst.target_revenue_y10 == 200_000_000_000.0
    assert worst.year1_growth == base.year1_growth
    assert worst.governance_discount == base.governance_discount
    assert scenarios["best"].sales_to_capital == pytest.approx(4.0)
    assert scenarios["best"].regulatory_drag == 0.0


@pytest.mark.parametrize(
    ("raw", "fragments"),
    [
        pytest.param({"worst": {"foo": 1}}, ("scenarios.worst", "foo"), id="unknown-key"),
        pytest.param({"worst": 3}, ("scenarios", "worst"), id="not-a-mapping"),
        pytest.param({"worst": {}}, ("scenarios", "worst"), id="empty-scenario"),
        pytest.param({}, ("scenarios",), id="empty-scenarios"),
        pytest.param(
            {"worst": {"target_margin": 1.2}},
            ("scenarios.worst.target_margin",),
            id="out-of-range",
        ),
    ],
)
def test_parse_scenarios_rejects(raw: dict[str, Any], fragments: tuple[str, ...]) -> None:
    base = parse_story(_STORY, where=_WHERE)
    with pytest.raises(ValueError) as excinfo:
        parse_scenarios(raw, base, where=_WHERE)
    message = str(excinfo.value)
    assert message.startswith(_WHERE)
    for fragment in fragments:
        assert fragment in message


def test_parse_scenarios_rejects_a_non_string_name() -> None:
    base = parse_story(_STORY, where=_WHERE)
    with pytest.raises(ValueError) as excinfo:
        parse_scenarios({1: {"target_margin": 0.1}}, base, where=_WHERE)
    message = str(excinfo.value)
    assert message.startswith(_WHERE)
    assert "scenarios" in message


def test_story_from_override() -> None:
    assert story_from_override({}, where=_WHERE) is None
    assert story_from_override({"notes": "x"}, where=_WHERE) is None

    alone = story_from_override({"story": _STORY}, where=_WHERE)
    assert alone is not None
    assert alone == (parse_story(_STORY, where=_WHERE), {})

    full = story_from_override({"story": _STORY, "scenarios": _SCENARIOS}, where=_WHERE)
    assert full is not None
    story, scenarios = full
    assert story.target_margin == pytest.approx(0.325)
    assert list(scenarios) == ["worst", "best"]


def test_example_file_documents_every_story_key() -> None:
    example = (_ROOT / "config" / "assumptions" / "_EXAMPLE.yaml.example").read_text()
    readme = (_ROOT / "config" / "assumptions" / "README.md").read_text()
    for name in [f.name for f in fields(StoryInputs)] + ["founded_year", "story:", "scenarios:"]:
        assert name in example, name
    for word in ("`story`", "`scenarios`", "`founded_year`", "not millions"):
        assert word in readme, word


def test_every_story_field_has_a_rule() -> None:
    from bot.valuator import hypergrowth

    assert list(hypergrowth._RULES) == [f.name for f in fields(StoryInputs)]
    assert hypergrowth._REQUIRED == (
        "year1_growth",
        "target_revenue_y10",
        "year1_margin",
        "target_margin",
        "sales_to_capital",
        "wacc_start",
    )


# --- #196: ten-year paths, apply_story -----------------------------------------


def _cal_story(**changes: Any) -> StoryInputs:
    from dataclasses import replace

    from tests.unit.test_hypergrowth_calibration import CAL_STORY

    return replace(CAL_STORY, **changes)


def test_solve_stage_growth_reproduces_the_sheet() -> None:
    from bot.valuator.hypergrowth import solve_stage_growth

    assert solve_stage_growth(20_608.0, _cal_story(), 0.049) == pytest.approx(0.42, abs=1e-6)


def test_growth_path_matches_the_sheet_and_hits_the_target() -> None:
    from bot.valuator.hypergrowth import HORIZON, growth_path
    from tests.unit.test_hypergrowth_calibration import CAL_GROWTH

    path = growth_path(20_608.0, _cal_story(), 0.049)
    assert len(path) == HORIZON == 10
    assert path == pytest.approx(CAL_GROWTH, abs=1e-6)
    revenue = 20_608.0
    for g in path:
        revenue *= 1.0 + g
    assert revenue == pytest.approx(1_011_491, abs=1)


@pytest.mark.parametrize(
    ("base", "target"),
    [(20_608.0, 1e30), (20_608.0, 1e-9), (0.0, 1_011_491), (-1.0, 1_011_491)],
)
def test_solve_stage_growth_raises_when_unreachable(base: float, target: float) -> None:
    from bot.valuator.hypergrowth import solve_stage_growth

    with pytest.raises(ValueError, match="unreachable"):
        solve_stage_growth(base, _cal_story(target_revenue_y10=target), 0.049)


def test_solve_stage_growth_refuses_terminal_growth_at_or_below_minus_one() -> None:
    from bot.valuator.hypergrowth import solve_stage_growth

    with pytest.raises(ValueError, match="terminal_growth"):
        solve_stage_growth(20_608.0, _cal_story(), -1.0)


def test_margin_path_matches_the_sheet() -> None:
    from bot.valuator.hypergrowth import margin_path
    from tests.unit.test_hypergrowth_calibration import CAL_MARGIN

    assert margin_path(_cal_story()) == pytest.approx(CAL_MARGIN, abs=1e-12)


def test_margin_path_converging_in_year_one_is_flat_from_year_two() -> None:
    from bot.valuator.hypergrowth import margin_path

    path = margin_path(_cal_story(margin_converge_year=1))
    assert path[0] == 0.05
    assert path[1:] == (0.325 - 0.05,) * 9


def test_wacc_path_matches_the_sheet() -> None:
    from bot.valuator.hypergrowth import wacc_path
    from tests.unit.test_hypergrowth_calibration import CAL_WACC

    path = wacc_path(_cal_story(), 0.0913)
    assert path == pytest.approx(CAL_WACC, abs=1e-4)
    assert path[-1] == 0.0913


def test_wacc_path_is_flat_when_terminal_equals_start() -> None:
    from bot.valuator.hypergrowth import wacc_path

    assert wacc_path(_cal_story(), 0.0974) == (0.0974,) * 10


@pytest.mark.parametrize(("effective", "marginal"), [(0.0, 0.25), (0.1, 0.3), (0.07, 0.21)])
def test_tax_path_ends_exactly_at_the_marginal_rate(effective: float, marginal: float) -> None:
    from bot.valuator.hypergrowth import tax_path

    path = tax_path(_cal_story(effective_tax_rate=effective), marginal)
    assert len(path) == 10
    assert path[:5] == (effective,) * 5
    assert path[-1] == marginal


def test_tax_path_matches_the_sheet() -> None:
    from bot.valuator.hypergrowth import tax_path
    from tests.unit.test_hypergrowth_calibration import CAL_TAX

    assert tax_path(_cal_story(), 0.25) == pytest.approx(CAL_TAX, abs=1e-12)


def test_apply_story_sets_story_sourced_values() -> None:
    from bot.valuator.assumptions import AssumptionSource
    from bot.valuator.hypergrowth import apply_story, growth_path, margin_path
    from tests.unit.test_hypergrowth_calibration import generic_bundle

    story = _cal_story()
    bundle = generic_bundle()
    out = apply_story(bundle, story, base_revenue=20_608.0, sector_wacc=0.08)
    story_sourced = {
        "revenue_growth": growth_path(20_608.0, story, 0.049),
        "operating_margin": margin_path(story),
        "sales_to_capital": 3.0,
        "cost_of_equity": 0.0974,
        "equity_weight": 1.0,
        "debt_weight": 0.0,
        "probability_of_bankruptcy": 0.10,
        "terminal_roic": 0.15,
        "distress_proceeds_pct": 0.50,
        "fixed_commitments": 472_336.0,
        "extra_cash": 100_000.0,
        "governance_discount": 0.0,
    }
    for name, value in story_sourced.items():
        field = getattr(out, name)
        assert field.source is AssumptionSource.STORY, name
        assert field.value == value, name
    assert out.wacc_path is not None and out.tax_rate_path is not None
    assert out.wacc_path.source is AssumptionSource.STORY
    assert out.wacc_path.value[-1] == 0.0913  # story.wacc_terminal beats the sector
    assert out.tax_rate_path.source is AssumptionSource.STORY
    assert out.story is story
    assert out.terminal_growth is bundle.terminal_growth
    assert out.tax_rate is bundle.tax_rate
    assert out.pretax_cost_of_debt is bundle.pretax_cost_of_debt


def test_apply_story_wacc_terminal_falls_back_to_sector() -> None:
    from bot.valuator.hypergrowth import apply_story
    from tests.unit.test_hypergrowth_calibration import generic_bundle

    out = apply_story(
        generic_bundle(), _cal_story(wacc_terminal=None), base_revenue=20_608.0, sector_wacc=0.09
    )
    assert out.wacc_path is not None
    assert out.wacc_path.value[-1] == 0.09


def test_apply_story_raises_without_wacc_terminal() -> None:
    from bot.valuator.hypergrowth import apply_story
    from tests.unit.test_hypergrowth_calibration import generic_bundle

    with pytest.raises(ValueError, match="wacc_terminal unresolved"):
        apply_story(
            generic_bundle(),
            _cal_story(wacc_terminal=None),
            base_revenue=20_608.0,
            sector_wacc=None,
        )


@pytest.mark.parametrize("missing", ["terminal_growth", "tax_rate"])
def test_apply_story_raises_on_unresolved_generic_input(missing: str) -> None:
    from bot.valuator.hypergrowth import apply_story
    from tests.unit.test_hypergrowth_calibration import generic_bundle

    with pytest.raises(ValueError, match=f"{missing} unresolved"):
        apply_story(
            generic_bundle(**{missing: None}),
            _cal_story(),
            base_revenue=20_608.0,
            sector_wacc=0.09,
        )


def test_apply_story_without_terminal_roic_leaves_it_none() -> None:
    from bot.valuator.hypergrowth import apply_story
    from tests.unit.test_hypergrowth_calibration import generic_bundle

    out = apply_story(
        generic_bundle(), _cal_story(terminal_roic=None), base_revenue=20_608.0, sector_wacc=None
    )
    assert out.terminal_roic is None
    assert out.to_dcf_assumptions().terminal_roic is None
