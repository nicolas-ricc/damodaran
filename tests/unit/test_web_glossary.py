"""The web viewer names every DCF input, flag and source in words, with a description."""

from __future__ import annotations

import re

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
    for source in ("sector_default_damodaran", "historical_average", "rule_based", "override"):
        _is_worded(source_term(source))


def test_unknown_names_fall_back_to_words_without_a_description() -> None:
    assert flag_term("some_new_check") == Term("some new check", "")
    assert source_term("some_new_source") == Term("some new source", "")
    assert input_term("some_new_input") == Term("some new input", "")


def test_glossary_has_no_leftover_identifier() -> None:
    for table in (glossary.INPUTS, glossary.FLAGS, glossary.SOURCES):
        for term in table.values():
            assert not _SNAKE.search(term.label + " " + term.description), term
