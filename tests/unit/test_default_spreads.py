"""The curated coverage → rating → default probability tables (#213, spec §7.3).

``config/default_spreads.yaml`` is hand-curated from Damodaran's synthetic
rating table and Table 5 of "Valuing Distressed and Declining Companies". The
loader degrades to an empty table when the file is missing or malformed and
fails loudly on out-of-range or inconsistent values.
"""

from __future__ import annotations

import math
from datetime import date
from pathlib import Path

import pytest
from structlog.testing import capture_logs

from bot.config import Settings
from bot.reference.default_spreads import (
    EMPTY_DEFAULT_SPREADS,
    CoverageBracket,
    DefaultProbability,
    load_default_spreads,
)

REPO_FILE = Path(__file__).resolve().parents[2] / "config" / "default_spreads.yaml"

_SRC = "source: https://example.org/x, as_of: 2026-01-01"

_VALID = (
    "horizon_years: 10\n"
    "coverage_to_rating:\n"
    f"  - {{lower: null, upper: 1.0, rating: C, {_SRC}}}\n"
    f"  - {{lower: 1.0, upper: 3.0, rating: BB, {_SRC}}}\n"
    f"  - {{lower: 3.0, upper: null, rating: AAA, {_SRC}}}\n"
    "rating_to_default_probability:\n"
    f"  C: {{probability: 0.8, {_SRC}}}\n"
    f"  BB: {{probability: 0.2, {_SRC}}}\n"
    f"  AAA: {{probability: 0.001, {_SRC}}}\n"
)

_C_ROW = f"  - {{lower: null, upper: 1.0, rating: C, {_SRC}}}\n"
_BB_ROW = f"  - {{lower: 1.0, upper: 3.0, rating: BB, {_SRC}}}\n"
_AAA_ROW = f"  - {{lower: 3.0, upper: null, rating: AAA, {_SRC}}}\n"
_BB_PROB = f"  BB: {{probability: 0.2, {_SRC}}}\n"


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "default_spreads.yaml"
    path.write_text(text)
    return path


def _sub(old: str, new: str) -> str:
    assert old in _VALID, old
    return _VALID.replace(old, new, 1)


# --- loader on tmp files ---------------------------------------------------


def test_loads_a_valid_table(tmp_path: Path) -> None:
    table = load_default_spreads(_write(tmp_path, _VALID))
    assert table.horizon_years == 10
    assert table.brackets[0] == CoverageBracket(
        None, 1.0, "C", "https://example.org/x", date(2026, 1, 1)
    )
    assert table.probabilities["BB"] == DefaultProbability(
        0.2, "https://example.org/x", date(2026, 1, 1)
    )
    assert not table.is_empty


def test_rating_for_bounds(tmp_path: Path) -> None:
    table = load_default_spreads(_write(tmp_path, _VALID))
    assert table.rating_for(0.99) == "C"
    assert table.rating_for(1.0) == "BB"
    assert table.rating_for(3.0) == "AAA"
    assert table.rating_for(-50.0) == "C"


def test_rating_for_nan_and_infinities(tmp_path: Path) -> None:
    table = load_default_spreads(_write(tmp_path, _VALID))
    assert table.rating_for(math.nan) is None
    assert table.rating_for(math.inf) == "AAA"
    assert table.rating_for(-math.inf) == "C"


def test_probability_for(tmp_path: Path) -> None:
    table = load_default_spreads(_write(tmp_path, _VALID))
    assert table.probability_for("C") == 0.8
    assert table.probability_for("ZZZ") is None


def test_brackets_out_of_order_are_sorted(tmp_path: Path) -> None:
    text = _VALID.replace(_C_ROW + _BB_ROW + _AAA_ROW, _AAA_ROW + _C_ROW + _BB_ROW)
    assert text != _VALID
    table = load_default_spreads(_write(tmp_path, text))
    assert [b.rating for b in table.brackets] == ["C", "BB", "AAA"]


def test_probabilities_are_read_only(tmp_path: Path) -> None:
    table = load_default_spreads(_write(tmp_path, _VALID))
    with pytest.raises(TypeError):
        table.probabilities["X"] = table.probabilities["C"]  # type: ignore[index]


def test_absent_file_warns_and_is_empty(tmp_path: Path) -> None:
    with capture_logs() as logs:
        table = load_default_spreads(tmp_path / "absent.yaml")
    assert table is EMPTY_DEFAULT_SPREADS
    assert table.is_empty
    assert table.rating_for(0.5) is None
    assert table.probability_for("C") is None
    assert [e["event"] for e in logs].count("default_spreads.absent") == 1


def test_empty_table_constant() -> None:
    assert EMPTY_DEFAULT_SPREADS.horizon_years is None
    assert EMPTY_DEFAULT_SPREADS.brackets == ()
    assert dict(EMPTY_DEFAULT_SPREADS.probabilities) == {}


_MALFORMED = {
    "unparsable": "horizon_years: [unclosed\n",
    "not-a-mapping": "- 1\n- 2\n",
    "unknown-top-level-key": _VALID + "extra: 1\n",
    "missing-top-level-key": _sub("horizon_years: 10\n", ""),
    "duplicate-key": _VALID + "horizon_years: 10\n",
    "brackets-not-a-list": _sub(_C_ROW + _BB_ROW + _AAA_ROW, "  C: 1\n"),
    "probabilities-not-a-mapping": _VALID.split("rating_to_default_probability:\n")[0]
    + "rating_to_default_probability: []\n",
    "padded-rating-collision": _VALID + f'  " BB": {{probability: 0.3, {_SRC}}}\n',
    "unhashable-key": _VALID.replace("horizon_years: 10\n", "? [a]\n: 1\nhorizon_years: 10\n", 1),
    "bracket-not-a-mapping": _sub(_BB_ROW, "  - 7\n"),
    "probability-row-not-a-mapping": _sub(_BB_PROB, "  BB: 0.2\n"),
    "missing-field": _sub(_BB_ROW, "  - {lower: 1.0, upper: 3.0, rating: BB, source: https://example.org/x}\n"),
    "missing-probability-field": _sub(_BB_PROB, "  BB: {probability: 0.2, source: https://example.org/x}\n"),
    "non-number-bound": _sub("lower: 1.0, upper: 3.0", "lower: abc, upper: 3.0"),
    "bool-probability": _sub("probability: 0.2", "probability: true"),
    "horizon-bool": _sub("horizon_years: 10\n", "horizon_years: true\n"),
    "bad-date": _sub(_BB_PROB, "  BB: {probability: 0.2, source: https://example.org/x, as_of: soon}\n"),
    "empty-rating": _sub("rating: BB,", 'rating: "",'),
    "non-string-rating": _sub("rating: BB,", "rating: 5,"),
    "empty-source": _sub(_BB_PROB, '  BB: {probability: 0.2, source: "", as_of: 2026-01-01}\n'),
}


@pytest.mark.parametrize("text", list(_MALFORMED.values()), ids=list(_MALFORMED))
def test_malformed_file_warns_and_is_empty(tmp_path: Path, text: str) -> None:
    with capture_logs() as logs:
        table = load_default_spreads(_write(tmp_path, text))
    assert table.is_empty
    assert "default_spreads.malformed" in [e["event"] for e in logs]


def test_non_number_horizon_reason_names_the_key(tmp_path: Path) -> None:
    with capture_logs() as logs:
        load_default_spreads(_write(tmp_path, _MALFORMED["horizon-bool"]))
    [event] = [e for e in logs if e["event"] == "default_spreads.malformed"]
    assert event["reason"] == "horizon_years: not a number"


def test_unreadable_path_warns_and_is_empty(tmp_path: Path) -> None:
    with capture_logs() as logs:
        table = load_default_spreads(tmp_path)  # a directory, not a file
    assert table.is_empty
    assert "default_spreads.malformed" in [e["event"] for e in logs]


_INVALID = {
    "probability-above-one": _sub("probability: 0.2", "probability: 1.2"),
    "probability-negative": _sub("probability: 0.2", "probability: -0.01"),
    "horizon-zero": _sub("horizon_years: 10\n", "horizon_years: 0\n"),
    "horizon-negative": _sub("horizon_years: 10\n", "horizon_years: -1\n"),
    "horizon-float": _sub("horizon_years: 10\n", "horizon_years: 10.0\n"),
    "lower-not-below-upper": _sub("lower: 1.0, upper: 3.0", "lower: 3.0, upper: 1.0"),
    "gap": _sub("lower: 1.0, upper: 3.0", "lower: 1.5, upper: 3.0"),
    "overlap": _sub("lower: 1.0, upper: 3.0", "lower: 0.5, upper: 3.0"),
    "first-lower-bounded": _sub("lower: null, upper: 1.0", "lower: 0.0, upper: 1.0"),
    "last-upper-bounded": _sub("lower: 3.0, upper: null", "lower: 3.0, upper: 100.0"),
    "two-unbounded-lowers": _sub("lower: 1.0, upper: 3.0", "lower: null, upper: 3.0"),
    "rating-without-probability": _sub(_BB_PROB, ""),
}


@pytest.mark.parametrize("text", list(_INVALID.values()), ids=list(_INVALID))
def test_invalid_value_fails_at_load(tmp_path: Path, text: str) -> None:
    path = _write(tmp_path, text)
    with pytest.raises(ValueError) as excinfo:
        load_default_spreads(path)
    assert str(path) in str(excinfo.value)


def test_probability_bounds_are_closed(tmp_path: Path) -> None:
    text = _sub("probability: 0.2", "probability: 1.0").replace(
        "probability: 0.001", "probability: 0.0"
    )
    table = load_default_spreads(_write(tmp_path, text))
    assert table.probability_for("BB") == 1.0
    assert table.probability_for("AAA") == 0.0


def test_datetime_as_of_is_narrowed_to_date(tmp_path: Path) -> None:
    text = _sub(_BB_PROB, "  BB: {probability: 0.2, source: https://example.org/x, as_of: 2026-01-01T00:00:00}\n")
    as_of = load_default_spreads(_write(tmp_path, text)).probabilities["BB"].as_of
    assert type(as_of) is date


# --- the repo file -----------------------------------------------------------

TABLE_5_TEN_YEAR = {
    "AAA": 0.0007,
    "AA": 0.0051,
    "A+": 0.0057,
    "A": 0.0066,
    "A-": 0.0500,
    "BBB": 0.0754,
    "BB": 0.1963,
    "B+": 0.2825,
    "B": 0.3680,
    "B-": 0.4212,
    "CCC": 0.5902,
    "CC": 0.6660,
    "C+": 0.7516,
    "C": 0.8103,
    "C-": 0.8716,
}


def test_repo_file_shape() -> None:
    with capture_logs() as logs:
        table = load_default_spreads(REPO_FILE)
    [loaded] = [e for e in logs if e["event"] == "default_spreads.loaded"]
    assert (loaded["path"], loaded["brackets"], loaded["ratings"]) == (str(REPO_FILE), 15, 17)
    assert table.horizon_years == 10
    assert len(table.brackets) == 15
    assert table.brackets[0].lower is None
    assert table.brackets[-1].upper is None
    assert [b.rating for b in table.brackets] == [
        "D", "C", "CC", "CCC", "B-", "B", "B+", "BB", "BB+", "BBB", "A-", "A", "A+", "AA", "AAA",
    ]  # fmt: skip


def test_every_repo_row_has_https_source_and_as_of() -> None:
    table = load_default_spreads(REPO_FILE)
    rows: list[CoverageBracket | DefaultProbability] = [*table.brackets, *table.probabilities.values()]
    assert rows
    for row in rows:
        assert row.source.startswith("https://"), row
        assert isinstance(row.as_of, date), row


def test_every_repo_bracket_rating_has_a_probability() -> None:
    table = load_default_spreads(REPO_FILE)
    assert table.brackets
    for bracket in table.brackets:
        assert bracket.rating in table.probabilities, bracket.rating


def test_repo_lookups() -> None:
    table = load_default_spreads(REPO_FILE)
    assert table.rating_for(0.6) == "C"
    assert table.rating_for(0.67) == "CC"
    assert table.rating_for(-3.0) == "D"
    assert table.rating_for(2.5) == "BBB"
    assert table.rating_for(8.5) == "AAA"
    assert table.rating_for(100.0) == "AAA"
    assert table.probability_for("C") == pytest.approx(0.8103)
    assert table.probability_for("BB+") == table.probability_for("BB")
    assert table.probability_for("D") == table.probability_for("C-")
    assert table.probability_for("ZZZ") is None
    assert table.probability_for("C+") == pytest.approx(0.7516)


def test_repo_probabilities_match_table_5() -> None:
    table = load_default_spreads(REPO_FILE)
    for rating, expected in TABLE_5_TEN_YEAR.items():
        assert table.probability_for(rating) == pytest.approx(expected), rating


def test_settings_default_spreads_path_default_and_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "test test@example.com")
    monkeypatch.delenv("BOT_DEFAULT_SPREADS_PATH", raising=False)
    assert Settings(_env_file=None).default_spreads_path == Path("./config/default_spreads.yaml")  # type: ignore[call-arg]
    monkeypatch.setenv("BOT_DEFAULT_SPREADS_PATH", str(tmp_path / "d.yaml"))
    assert Settings(_env_file=None).default_spreads_path == tmp_path / "d.yaml"  # type: ignore[call-arg]
