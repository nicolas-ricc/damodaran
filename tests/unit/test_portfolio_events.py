"""Unit tests for the §8.3 portfolio event detectors (M5, #28).

Each pure detector is exercised at its threshold boundaries; the orchestrator
``compute_events`` is covered in the integration test. These never touch a live
broker or the network.
"""

from __future__ import annotations

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
from bot.portfolio.marks import HoldingMark

PREV = date(2026, 5, 1)
CURR = date(2026, 5, 2)


def _pos(ticker: str, qty: float, mv: float | None = None, ccy: str | None = "USD") -> Position:
    return Position(ticker=ticker, qty=qty, market_value=mv, currency=ccy)


def _mark(
    ticker: str = "AAPL",
    iv: float | None = 100.0,
    price: float | None = 100.0,
    red: dict[str, str] | None = None,
) -> HoldingMark:
    return HoldingMark(ticker=ticker, intrinsic_value=iv, price=price, red_flags=red)


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


def _filings(filings: list[Filing], reported: set[tuple[str, str, str]] | None = None) -> list[Event]:
    return detect_new_filings(
        filings,
        held_tickers={"AAPL"},
        reported=reported or set(),
        window_start=PREV,
        window_end=CURR,
        snapshot_date=CURR,
        prev_date=PREV,
    )


def test_new_filing_in_window_for_held_ticker() -> None:
    filings = [
        Filing("AAPL", "10-Q", date(2026, 5, 2), "0001", fetched_on=CURR),
        Filing("AAPL", "10-K", date(2026, 4, 1), "0000", fetched_on=date(2026, 4, 2)),
        Filing("TSLA", "10-Q", date(2026, 5, 2), "0002", fetched_on=CURR),  # not held
    ]
    events = _filings(filings)
    assert len(events) == 1
    assert events[0].event_type is EventType.NEW_FILING
    assert events[0].ticker == "AAPL"
    assert events[0].details["accession_number"] == "0001"


def test_filing_on_window_start_excluded_on_end_included() -> None:
    filings = [
        Filing("AAPL", "8-K", PREV, "a", fetched_on=date(2026, 4, 30)),  # old news
        Filing("AAPL", "8-K", CURR, "b", fetched_on=CURR),
    ]
    assert {e.details["accession_number"] for e in _filings(filings)} == {"b"}


def test_old_filing_ingested_in_window_fires() -> None:
    # A 10-K filed weeks ago but only imported today is news today.
    events = _filings([Filing("AAPL", "10-K", date(2026, 4, 10), "k", fetched_on=CURR)])
    assert [e.details["accession_number"] for e in events] == ["k"]


def test_filing_fetched_on_window_start_fires() -> None:
    # Fetched on the previous snapshot's day, possibly after that run: not lost.
    events = _filings([Filing("AAPL", "10-K", date(2026, 4, 10), "k", fetched_on=PREV)])
    assert [e.details["accession_number"] for e in events] == ["k"]


def test_already_reported_filing_does_not_fire_again() -> None:
    filing = Filing("AAPL", "10-K", date(2026, 4, 10), "k", fetched_on=CURR)
    assert _filings([filing], reported={("AAPL", "10-K", "2026-04-10")}) == []


def test_filing_after_window_end_excluded() -> None:
    late = Filing("AAPL", "8-K", date(2026, 5, 3), "z", fetched_on=CURR)
    assert _filings([late]) == []


def test_first_snapshot_admits_every_unreported_filing() -> None:
    filings = [
        Filing("AAPL", "10-K", date(2025, 1, 1), "old", fetched_on=date(2025, 1, 2)),
        Filing("AAPL", "10-Q", date(2025, 4, 1), "seen", fetched_on=date(2025, 4, 2)),
    ]
    events = detect_new_filings(
        filings,
        held_tickers={"AAPL"},
        reported={("AAPL", "10-Q", "2025-04-01")},
        window_start=None,
        window_end=CURR,
        snapshot_date=CURR,
        prev_date=None,
    )
    assert [e.details["accession_number"] for e in events] == ["old"]


# --------------------------------------------------------------------------- #
# Intrinsic-value cross                                                        #
# --------------------------------------------------------------------------- #


def test_iv_crosses_above_price() -> None:
    prev = _mark(iv=90.0, price=100.0)  # IV below price
    curr = _mark(iv=110.0, price=100.0)  # IV above price
    event = detect_intrinsic_value_cross(prev, curr, snapshot_date=CURR, prev_date=PREV)
    assert event is not None
    assert event.event_type is EventType.INTRINSIC_VALUE_CROSSED_PRICE
    assert event.details["direction"] == "above_price"


def test_iv_crosses_below_price() -> None:
    prev = _mark(iv=110.0, price=100.0)
    curr = _mark(iv=90.0, price=100.0)
    event = detect_intrinsic_value_cross(prev, curr, snapshot_date=CURR, prev_date=PREV)
    assert event is not None
    assert event.details["direction"] == "below_price"


def test_iv_no_cross_when_same_side() -> None:
    prev = _mark(iv=120.0, price=100.0)
    curr = _mark(iv=130.0, price=100.0)  # still above
    assert detect_intrinsic_value_cross(prev, curr, snapshot_date=CURR, prev_date=PREV) is None


def test_iv_cross_needs_prior_mark() -> None:
    curr = _mark(iv=130.0, price=100.0)
    assert detect_intrinsic_value_cross(None, curr, snapshot_date=CURR, prev_date=PREV) is None


def test_iv_cross_needs_prices() -> None:
    prev = _mark(iv=90.0, price=None)
    curr = _mark(iv=110.0, price=100.0)
    assert detect_intrinsic_value_cross(prev, curr, snapshot_date=CURR, prev_date=PREV) is None


def test_iv_cross_needs_intrinsic_values() -> None:
    prev = _mark(iv=90.0, price=100.0)
    curr = _mark(iv=None, price=100.0)  # valuator failed today
    assert detect_intrinsic_value_cross(prev, curr, snapshot_date=CURR, prev_date=PREV) is None


# --------------------------------------------------------------------------- #
# New red narrative flag                                                       #
# --------------------------------------------------------------------------- #


def test_newly_red_flag_fires_persistent_red_does_not() -> None:
    prev = _mark(red={"story_margin": "high"})
    curr = _mark(red={"story_margin": "high", "beta_risk": "levered"})
    events = detect_new_red_flags(prev, curr, snapshot_date=CURR, prev_date=PREV)
    assert [e.details["flag"] for e in events] == ["beta_risk"]
    assert events[0].details["reason"] == "levered"


def test_all_red_new_when_no_prior_mark() -> None:
    curr = _mark(red={"story_margin": "high"})
    events = detect_new_red_flags(None, curr, snapshot_date=CURR, prev_date=None)
    assert [e.details["flag"] for e in events] == ["story_margin"]


def test_all_red_new_when_prior_mark_unvalued() -> None:
    curr = _mark(red={"story_margin": "high"})
    events = detect_new_red_flags(_mark(red=None), curr, snapshot_date=CURR, prev_date=PREV)
    assert [e.details["flag"] for e in events] == ["story_margin"]


def test_no_red_flag_event_when_current_unvalued() -> None:
    prev = _mark(red={})
    assert detect_new_red_flags(prev, _mark(red=None), snapshot_date=CURR, prev_date=PREV) == []


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


def test_below_quality_gate_only_newly_failed_gates() -> None:
    events = detect_below_quality_gate(
        ["min_interest_coverage"],
        ["max_net_debt_to_ebitda", "min_interest_coverage", "min_market_cap"],
        "AAPL",
        snapshot_date=CURR,
        prev_date=PREV,
    )
    assert [e.details["gate"] for e in events] == ["max_net_debt_to_ebitda", "min_market_cap"]
    assert all(e.event_type is EventType.BELOW_QUALITY_GATE for e in events)


def test_below_quality_gate_needs_baseline() -> None:
    assert (
        detect_below_quality_gate(
            None, ["max_net_debt_to_ebitda"], "AAPL", snapshot_date=CURR, prev_date=PREV
        )
        == []
    )


def test_below_quality_gate_needs_current_verdict() -> None:
    assert (
        detect_below_quality_gate([], None, "AAPL", snapshot_date=CURR, prev_date=PREV) == []
    )


def test_event_is_frozen() -> None:
    from dataclasses import FrozenInstanceError

    e = Event(EventType.DIVIDEND, "AAPL", CURR)
    with pytest.raises(FrozenInstanceError):
        e.ticker = "MSFT"  # type: ignore[misc]
