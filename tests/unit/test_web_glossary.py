"""The web viewer names every DCF input, flag and source in words, with a description."""

from __future__ import annotations

import re

from bot.valuator.assumptions import AssumptionSource
from bot.valuator.sensitivity import PATH_AXES, SensitivityAxis
from bot.web import glossary
from bot.web.glossary import Term, axis_term, flag_term, input_term, source_term
from bot.web.views import ASSUMPTION_KEYS

_SNAKE = re.compile(r"[a-z]+_[a-z_]+")


def _is_worded(term: Term) -> None:
    assert term.label and not _SNAKE.search(term.label), term
    assert term.description.endswith("."), term
    assert len(term.description) > 20, term


def test_every_assumption_row_has_a_worded_term() -> None:
    for key in ASSUMPTION_KEYS:
        _is_worded(input_term(key))


def test_every_sensitivity_axis_has_a_worded_term() -> None:
    for axis in SensitivityAxis:
        _is_worded(axis_term(axis))


def test_axis_term_marks_path_axes_as_year_one() -> None:
    for axis in SensitivityAxis:
        label = axis_term(axis).label
        assert label.endswith("(yr 1)") is (axis in PATH_AXES), label


def test_axis_and_input_share_the_description() -> None:
    assert axis_term(SensitivityAxis.SALES_TO_CAPITAL) == input_term("sales_to_capital")
    assert input_term("sales_to_capital").label == "Sales-to-capital"


def test_every_narrative_flag_has_a_worded_term() -> None:
    for name in (
        "story_margin",
        "growth_reinvestment",
        "beta_business_risk",
        "terminal_value_share",
        "country_exposure",
        "hypergrowth_story",
        "hypergrowth_revenue_scale",
        "hypergrowth_terminal_roic",
    ):
        _is_worded(flag_term(name))


def test_every_source_has_a_worded_term() -> None:
    for source in AssumptionSource:
        assert source.value in glossary.SOURCES, source
        _is_worded(source_term(source.value))


def test_sources_are_keyed_by_assumption_source() -> None:
    assert set(glossary.SOURCES) == {s.value for s in AssumptionSource}


def test_manual_source_is_worded_as_an_override() -> None:
    assert source_term(AssumptionSource.MANUAL) == Term(
        "manual override", "Written by hand in the company's assumptions file."
    )


def test_cross_region_source_names_another_region() -> None:
    description = source_term(AssumptionSource.SECTOR_DEFAULT_DAMODARAN_CROSS_REGION).description
    assert "different region" in description
    assert "company's own" in description


def test_story_source_covers_derived_values() -> None:
    description = source_term(AssumptionSource.STORY).description
    assert description.startswith("Set by or derived from the story section"), description


def test_unresolved_source_says_no_value() -> None:
    assert source_term(AssumptionSource.UNRESOLVED).description.startswith("No value was produced")


def test_unknown_names_fall_back_to_words_without_a_description() -> None:
    assert flag_term("some_new_check") == Term("some new check", "")
    assert source_term("some_new_source") == Term("some new source", "")
    assert input_term("some_new_input") == Term("some new input", "")


def test_glossary_has_no_leftover_identifier() -> None:
    for table in (glossary.INPUTS, glossary.FLAGS, glossary.SOURCES):
        for term in table.values():
            assert not _SNAKE.search(term.label + " " + term.description), term
