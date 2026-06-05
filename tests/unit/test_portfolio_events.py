"""Unit tests for the §8.3 portfolio event detectors (M5, #28).

Each pure detector is exercised at its threshold boundaries; the orchestrator
``compute_events`` is covered in the integration test. These never touch a live
broker or the network.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

import pytest

from bot.portfolio.events import (
    Event,
    EventType,
    Filing,
    Position,
    detect_below_quality_gate,
    detect_concentration,
    detect_corporate_action_events,
    detect_currency_changes,
    detect_intrinsic_value_cross,
    detect_new_filings,
    detect_new_red_flags,
    detect_position_changes,
    detect_sector_recalibration,
)
from bot.valuator.narrative_flags import FlagColor, NarrativeFlag

PREV = date(2026, 5, 1)
CURR = date(2026, 5, 2)


def _pos(ticker: str, qty: float, mv: float | None = None, ccy: str | None = "USD") -> Position:
    return Position(ticker=ticker, qty=qty, market_value=mv, currency=ccy)


# --------------------------------------------------------------------------- #
# Stub Analysis (only the fields the valuation detectors read).                #
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class _DCF:
    intrinsic_value: float


@dataclass(frozen=True)
class _Analysis:
    ticker: str
    dcf_result: _DCF
    current_price: float | None
    narrative_flags: tuple[NarrativeFlag, ...] = field(default_factory=tuple)


def _an(ticker: str, iv: float, price: float | None, flags: tuple[NarrativeFlag, ...] = ()) -> _Analysis:
    return _Analysis(ticker=ticker, dcf_result=_DCF(iv), current_price=price, narrative_flags=flags)


# --------------------------------------------------------------------------- #
# Position open / close / size change                                          #
# --------------------------------------------------------------------------- #


def test_position_opened_and_closed() -> None:
    events = detect_position_changes(
        [_pos("AAPL", 10.0)],
        [_pos("MSFT", 5.0)],
        snapshot_date=CURR,
        prev_date=PREV,
    )
    by_type = {(e.event_type, e.ticker) for e in events}
    assert (EventType.POSITION_OPENED, "MSFT") in by_type
    assert (EventType.POSITION_CLOSED, "AAPL") in by_type
    assert len(events) == 2


def test_size_change_above_threshold_fires() -> None:
    events = detect_position_changes(
        [_pos("AAPL", 100.0)],
        [_pos("AAPL", 111.0)],  # +11% > 10%
        snapshot_date=CURR,
        prev_date=PREV,
    )
    assert [e.event_type for e in events] == [EventType.POSITION_SIZE_CHANGED]
    assert events[0].details["change"] == pytest.approx(0.11)


def test_size_change_at_threshold_does_not_fire() -> None:
    events = detect_position_changes(
        [_pos("AAPL", 100.0)],
        [_pos("AAPL", 110.0)],  # exactly +10%, boundary exclusive
        snapshot_date=CURR,
        prev_date=PREV,
    )
    assert events == []


def test_size_decrease_above_threshold_fires() -> None:
    events = detect_position_changes(
        [_pos("AAPL", 100.0)],
        [_pos("AAPL", 80.0)],  # -20%
        snapshot_date=CURR,
        prev_date=PREV,
    )
    assert [e.event_type for e in events] == [EventType.POSITION_SIZE_CHANGED]


def test_zero_qty_treated_as_closed() -> None:
    events = detect_position_changes(
        [_pos("AAPL", 100.0)],
        [_pos("AAPL", 0.0)],
        snapshot_date=CURR,
        prev_date=PREV,
    )
    assert [e.event_type for e in events] == [EventType.POSITION_CLOSED]


# --------------------------------------------------------------------------- #
# Currency change                                                              #
# --------------------------------------------------------------------------- #


def test_currency_change_fires() -> None:
    events = detect_currency_changes(
        [_pos("BP", 10.0, ccy="GBP")],
        [_pos("BP", 10.0, ccy="USD")],
        snapshot_date=CURR,
        prev_date=PREV,
    )
    assert [e.event_type for e in events] == [EventType.CURRENCY_CHANGED]
    assert events[0].details == {"from": "GBP", "to": "USD"}


def test_currency_unchanged_no_event() -> None:
    events = detect_currency_changes(
        [_pos("BP", 10.0, ccy="USD")],
        [_pos("BP", 10.0, ccy="USD")],
        snapshot_date=CURR,
        prev_date=PREV,
    )
    assert events == []


# --------------------------------------------------------------------------- #
# Corporate actions                                                            #
# --------------------------------------------------------------------------- #


def test_dividend_and_split_detected_other_ignored() -> None:
    events = detect_corporate_action_events(
        [
            ("aapl", "Dividend", {"amount": 0.24}),
            ("msft", "split", {"ratio": "2:1"}),
            ("xyz", "merger", {}),
        ],
        snapshot_date=CURR,
        prev_date=PREV,
    )
    types = {(e.event_type, e.ticker) for e in events}
    assert types == {(EventType.DIVIDEND, "AAPL"), (EventType.SPLIT, "MSFT")}


# --------------------------------------------------------------------------- #
# New filings                                                                  #
# --------------------------------------------------------------------------- #


def test_new_filing_in_window_for_held_ticker() -> None:
    filings = [
        Filing("AAPL", "10-Q", date(2026, 5, 2), "0001"),
        Filing("AAPL", "10-K", date(2026, 4, 1), "0000"),  # before window
        Filing("TSLA", "10-Q", date(2026, 5, 2), "0002"),  # not held
    ]
    events = detect_new_filings(
        filings,
        held_tickers={"AAPL"},
        window_start=PREV,
        window_end=CURR,
        snapshot_date=CURR,
        prev_date=PREV,
    )
    assert len(events) == 1
    assert events[0].event_type is EventType.NEW_FILING
    assert events[0].ticker == "AAPL"
    assert events[0].details["accession_number"] == "0001"


def test_filing_on_window_start_excluded_on_end_included() -> None:
    filings = [
        Filing("AAPL", "8-K", PREV, "a"),  # == window_start -> excluded
        Filing("AAPL", "8-K", CURR, "b"),  # == window_end -> included
    ]
    events = detect_new_filings(
        filings,
        held_tickers={"AAPL"},
        window_start=PREV,
        window_end=CURR,
        snapshot_date=CURR,
        prev_date=PREV,
    )
    assert {e.details["accession_number"] for e in events} == {"b"}


# --------------------------------------------------------------------------- #
# Intrinsic-value cross                                                        #
# --------------------------------------------------------------------------- #


def test_iv_crosses_above_price() -> None:
    prev = _an("AAPL", iv=90.0, price=100.0)  # IV below price
    curr = _an("AAPL", iv=110.0, price=100.0)  # IV above price
    event = detect_intrinsic_value_cross(prev, curr, snapshot_date=CURR, prev_date=PREV)
    assert event is not None
    assert event.event_type is EventType.INTRINSIC_VALUE_CROSSED_PRICE
    assert event.details["direction"] == "above_price"


def test_iv_crosses_below_price() -> None:
    prev = _an("AAPL", iv=110.0, price=100.0)
    curr = _an("AAPL", iv=90.0, price=100.0)
    event = detect_intrinsic_value_cross(prev, curr, snapshot_date=CURR, prev_date=PREV)
    assert event is not None
    assert event.details["direction"] == "below_price"


def test_iv_no_cross_when_same_side() -> None:
    prev = _an("AAPL", iv=120.0, price=100.0)
    curr = _an("AAPL", iv=130.0, price=100.0)  # still above
    assert detect_intrinsic_value_cross(prev, curr, snapshot_date=CURR, prev_date=PREV) is None


def test_iv_cross_needs_prior_analysis() -> None:
    curr = _an("AAPL", iv=130.0, price=100.0)
    assert detect_intrinsic_value_cross(None, curr, snapshot_date=CURR, prev_date=PREV) is None


def test_iv_cross_needs_prices() -> None:
    prev = _an("AAPL", iv=90.0, price=None)
    curr = _an("AAPL", iv=110.0, price=100.0)
    assert detect_intrinsic_value_cross(prev, curr, snapshot_date=CURR, prev_date=PREV) is None


# --------------------------------------------------------------------------- #
# New red narrative flag                                                       #
# --------------------------------------------------------------------------- #


def _flag(name: str, color: FlagColor) -> NarrativeFlag:
    return NarrativeFlag(name=name, color=color, reason=f"{name} {color}")


def test_newly_red_flag_fires_persistent_red_does_not() -> None:
    prev = _an(
        "AAPL",
        iv=100.0,
        price=100.0,
        flags=(_flag("story_margin", FlagColor.RED), _flag("beta_risk", FlagColor.GREEN)),
    )
    curr = _an(
        "AAPL",
        iv=100.0,
        price=100.0,
        flags=(_flag("story_margin", FlagColor.RED), _flag("beta_risk", FlagColor.RED)),
    )
    events = detect_new_red_flags(prev, curr, snapshot_date=CURR, prev_date=PREV)
    assert [e.details["flag"] for e in events] == ["beta_risk"]


def test_all_red_new_when_no_prior_analysis() -> None:
    curr = _an("AAPL", iv=100.0, price=100.0, flags=(_flag("story_margin", FlagColor.RED),))
    events = detect_new_red_flags(None, curr, snapshot_date=CURR, prev_date=None)
    assert [e.details["flag"] for e in events] == ["story_margin"]


# --------------------------------------------------------------------------- #
# Concentration                                                                #
# --------------------------------------------------------------------------- #


def test_concentration_above_threshold() -> None:
    events = detect_concentration(
        [_pos("AAPL", 1, mv=20.0), _pos("MSFT", 1, mv=80.0)],  # 20% / 80%
        snapshot_date=CURR,
        prev_date=PREV,
    )
    assert {e.ticker for e in events} == {"AAPL", "MSFT"}


def test_concentration_at_threshold_excludes() -> None:
    events = detect_concentration(
        [_pos("AAPL", 1, mv=15.0), _pos("MSFT", 1, mv=85.0)],  # AAPL exactly 15%
        snapshot_date=CURR,
        prev_date=PREV,
    )
    assert {e.ticker for e in events} == {"MSFT"}


def test_concentration_ignores_missing_market_value() -> None:
    events = detect_concentration(
        [_pos("AAPL", 1, mv=None), _pos("MSFT", 1, mv=100.0)],
        snapshot_date=CURR,
        prev_date=PREV,
    )
    assert {e.ticker for e in events} == {"MSFT"}


# --------------------------------------------------------------------------- #
# Sector recalibration                                                         #
# --------------------------------------------------------------------------- #


def test_sector_recalibration_above_100bps() -> None:
    event = detect_sector_recalibration(
        0.08, 0.095, "AAPL", snapshot_date=CURR, prev_date=PREV
    )  # +150bps
    assert event is not None
    assert event.event_type is EventType.SECTOR_RECALIBRATED


def test_sector_recalibration_at_100bps_excluded() -> None:
    assert (
        detect_sector_recalibration(0.08, 0.09, "AAPL", snapshot_date=CURR, prev_date=PREV)
        is None
    )


# --------------------------------------------------------------------------- #
# Below quality gate                                                           #
# --------------------------------------------------------------------------- #


def test_below_quality_gate_one_event_per_gate() -> None:
    events = detect_below_quality_gate(
        ["max_net_debt_to_ebitda", "min_interest_coverage"],
        "AAPL",
        snapshot_date=CURR,
        prev_date=PREV,
    )
    assert [e.details["gate"] for e in events] == [
        "max_net_debt_to_ebitda",
        "min_interest_coverage",
    ]
    assert all(e.event_type is EventType.BELOW_QUALITY_GATE for e in events)


def test_event_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    e = Event(EventType.DIVIDEND, "AAPL", CURR)
    with pytest.raises(FrozenInstanceError):
        e.ticker = "MSFT"  # type: ignore[misc]
