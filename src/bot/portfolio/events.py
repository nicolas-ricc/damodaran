"""Diff consecutive portfolio snapshots into a typed event stream (spec §8.3).

The portfolio monitor compares the two most recent daily snapshots and emits a
list of :class:`Event` describing what changed. Two sources feed the stream:

* **IBKR-observed** — facts read straight off the broker snapshots: a position
  opened or closed, a size change beyond a threshold (default 10%), a dividend
  or split (from ``corporate_actions``), or a position's listing currency
  changing.
* **Derived from capas A/B/C** (the valuable part) — a new filing for a held
  ticker (which the CLI turns into an auto-analyze, #29), the intrinsic value
  crossing the current price in either direction, a new red narrative flag, a
  drop below a quality gate, a sector WACC recalibration, and single-position
  concentration above a threshold (default 15%).

Explicitly **not** events (anti-noise, spec §8.3): raw price moves and news.

Design: every event type has its own *pure* detector taking plain inputs, so the
threshold arithmetic (>10% size, >15% concentration, IV-crosses-price, a newly
red flag) is isolated and unit-testable at its boundaries. The valuation-derived
detectors diff two :class:`~bot.portfolio.marks.HoldingMark` values, one per
snapshot, read back from ``holding_marks``: the baseline is what was persisted
on the previous run, never a recomputation, so an event fires once on the diff
where the state changes. :func:`compute_events` is the reader-orchestrator: it
gathers snapshot/filing/mark inputs off the connection, fans them through the
detectors, and returns the events. It never writes — persisting marks (via
``mark_holdings``) before calling it, and persisting events after, is the
caller's job.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING

from bot.portfolio.marks import HoldingMark, load_marks

if TYPE_CHECKING:
    import duckdb


#: Default fractional position-size change that counts as an event (spec §8.3).
DEFAULT_SIZE_CHANGE_THRESHOLD = 0.10
#: Default single-position concentration that counts as an event (spec §8.3).
DEFAULT_CONCENTRATION_THRESHOLD = 0.15
#: Default sector WACC move (in absolute fraction, 100bps) that recalibrates.
DEFAULT_WACC_RECALIBRATION_BPS = 0.01


class EventType(StrEnum):
    """The §8.3 event taxonomy. Value is the stored ``event_type`` string."""

    # IBKR-observed
    POSITION_OPENED = "position_opened"
    POSITION_CLOSED = "position_closed"
    POSITION_SIZE_CHANGED = "position_size_changed"
    DIVIDEND = "dividend"
    SPLIT = "split"
    CURRENCY_CHANGED = "currency_changed"
    # Derived from capas A/B/C
    NEW_FILING = "new_filing"
    INTRINSIC_VALUE_CROSSED_PRICE = "intrinsic_value_crossed_price"
    NEW_RED_FLAG = "new_red_flag"
    BELOW_QUALITY_GATE = "below_quality_gate"
    SECTOR_RECALIBRATED = "sector_recalibrated"
    CONCENTRATION = "concentration"


@dataclass(frozen=True)
class Event:
    """A single detected portfolio event, ready to persist to ``events_log``.

    Attributes:
        event_type: Which §8.3 category fired.
        ticker: The affected position (upper-cased).
        curr_snapshot_date: The snapshot the event was detected on.
        prev_snapshot_date: The prior baseline snapshot, or ``None`` for the very
            first snapshot (nothing to diff against).
        details: Event-specific payload (the % change, the crossed values, the
            flag name, the filing accession, etc.). JSON-serialisable.
    """

    event_type: EventType
    ticker: str
    curr_snapshot_date: date
    prev_snapshot_date: date | None = None
    details: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Position:
    """A single held position as read off a portfolio snapshot."""

    ticker: str
    qty: float
    market_value: float | None
    currency: str | None


@dataclass(frozen=True)
class Filing:
    """A filing-log entry for a held ticker (subset of ``filings_log``).

    ``fetched_on`` is the day we first ingested the row. It, not ``filing_date``,
    decides whether the filing is new to the user: filings are often ingested
    days after they are filed, or backfilled long after.
    """

    ticker: str
    filing_type: str
    filing_date: date
    accession_number: str | None
    fetched_on: date


# --------------------------------------------------------------------------- #
# Pure detectors — one per event type, each independently unit-testable.       #
# --------------------------------------------------------------------------- #


def detect_position_changes(
    prev: list[Position],
    curr: list[Position],
    *,
    snapshot_date: date,
    prev_date: date | None,
    size_change_threshold: float = DEFAULT_SIZE_CHANGE_THRESHOLD,
) -> list[Event]:
    """Opened / closed positions and size changes beyond a threshold (spec §8.3).

    A position present in ``curr`` but not ``prev`` is opened; present in ``prev``
    but not ``curr`` (or zeroed out) is closed. For positions in both, a relative
    quantity change with absolute value strictly greater than
    ``size_change_threshold`` fires a ``POSITION_SIZE_CHANGED`` event. A change
    exactly at the threshold does *not* fire (boundary is exclusive).
    """
    prev_by_ticker = {p.ticker: p for p in prev if p.qty != 0.0}
    curr_by_ticker = {p.ticker: p for p in curr if p.qty != 0.0}
    events: list[Event] = []

    for ticker, position in curr_by_ticker.items():
        if ticker not in prev_by_ticker:
            events.append(
                Event(
                    event_type=EventType.POSITION_OPENED,
                    ticker=ticker,
                    curr_snapshot_date=snapshot_date,
                    prev_snapshot_date=prev_date,
                    details={"qty": position.qty},
                )
            )

    for ticker, position in prev_by_ticker.items():
        if ticker not in curr_by_ticker:
            events.append(
                Event(
                    event_type=EventType.POSITION_CLOSED,
                    ticker=ticker,
                    curr_snapshot_date=snapshot_date,
                    prev_snapshot_date=prev_date,
                    details={"prev_qty": position.qty},
                )
            )
            continue
        before = prev_by_ticker[ticker].qty
        after = curr_by_ticker[ticker].qty
        if before == 0.0:
            continue
        change = (after - before) / abs(before)
        if abs(change) > size_change_threshold:
            events.append(
                Event(
                    event_type=EventType.POSITION_SIZE_CHANGED,
                    ticker=ticker,
                    curr_snapshot_date=snapshot_date,
                    prev_snapshot_date=prev_date,
                    details={"prev_qty": before, "qty": after, "change": change},
                )
            )

    return events


def detect_currency_changes(
    prev: list[Position],
    curr: list[Position],
    *,
    snapshot_date: date,
    prev_date: date | None,
) -> list[Event]:
    """A held position's listing currency changed between snapshots (spec §8.3)."""
    prev_ccy = {p.ticker: p.currency for p in prev}
    events: list[Event] = []
    for position in curr:
        before = prev_ccy.get(position.ticker)
        if before is not None and position.currency is not None and before != position.currency:
            events.append(
                Event(
                    event_type=EventType.CURRENCY_CHANGED,
                    ticker=position.ticker,
                    curr_snapshot_date=snapshot_date,
                    prev_snapshot_date=prev_date,
                    details={"from": before, "to": position.currency},
                )
            )
    return events


def detect_corporate_action_events(
    actions: list[tuple[str, str, dict[str, object]]],
    *,
    snapshot_date: date,
    prev_date: date | None,
) -> list[Event]:
    """Dividends and splits effective in the diff window (spec §8.3).

    ``actions`` is a list of ``(ticker, action_type, details)`` tuples already
    filtered to the window. ``action_type`` is matched case-insensitively against
    ``dividend`` / ``split``; anything else is ignored (mergers etc. are not yet
    a §8.3 event type).
    """
    events: list[Event] = []
    for ticker, action_type, details in actions:
        normalised = action_type.strip().lower()
        if normalised == "dividend":
            event_type = EventType.DIVIDEND
        elif normalised == "split":
            event_type = EventType.SPLIT
        else:
            continue
        events.append(
            Event(
                event_type=event_type,
                ticker=ticker.upper(),
                curr_snapshot_date=snapshot_date,
                prev_snapshot_date=prev_date,
                details=details,
            )
        )
    return events


def detect_new_filings(
    filings: list[Filing],
    *,
    held_tickers: set[str],
    reported: set[tuple[str, str, str]],
    window_start: date | None,
    window_end: date,
    snapshot_date: date,
    prev_date: date | None,
) -> list[Event]:
    """New filings for held tickers, by ingestion date, each reported once (spec §8.3).

    A filing qualifies when it is filed on or before ``window_end``, is not in
    ``reported``, and either was filed after ``window_start`` or was ingested on
    or after it. The ingestion bound is inclusive so a fetch later on the previous
    run's day is not lost; ``reported`` (``(ticker, filing_type, filing_date ISO)``
    triples already in ``events_log``) absorbs the resulting double-count and
    re-runs of the same window. A ``window_start`` of ``None`` (first snapshot)
    admits every unreported filing up to ``window_end``. The CLI (#29) turns
    this into an auto-analyze; we only emit the signal.
    """
    events: list[Event] = []
    for filing in filings:
        if filing.ticker.upper() not in held_tickers:
            continue
        if filing.filing_date > window_end:
            continue
        if (filing.ticker.upper(), filing.filing_type, filing.filing_date.isoformat()) in reported:
            continue
        if (
            window_start is not None
            and filing.filing_date <= window_start
            and filing.fetched_on < window_start
        ):
            continue
        events.append(
            Event(
                event_type=EventType.NEW_FILING,
                ticker=filing.ticker.upper(),
                curr_snapshot_date=snapshot_date,
                prev_snapshot_date=prev_date,
                details={
                    "filing_type": filing.filing_type,
                    "filing_date": filing.filing_date.isoformat(),
                    "accession_number": filing.accession_number,
                },
            )
        )
    return events


def detect_intrinsic_value_cross(
    prev: HoldingMark | None,
    curr: HoldingMark,
    *,
    snapshot_date: date,
    prev_date: date | None,
) -> Event | None:
    """Intrinsic value crossed the price in either direction (spec §8.3).

    A cross fires when the sign of ``intrinsic_value - price`` flips between the
    two marks (under -> over or over -> under). Equal-to is not a cross. Needs
    both marks' prices and intrinsic values; returns ``None`` when any is
    unknown or there is no prior mark to compare against.
    """
    if prev is None:
        return None
    if (
        prev.intrinsic_value is None
        or prev.price is None
        or curr.intrinsic_value is None
        or curr.price is None
    ):
        return None
    prev_gap = prev.intrinsic_value - prev.price
    curr_gap = curr.intrinsic_value - curr.price
    crossed_up = prev_gap < 0.0 <= curr_gap and curr_gap != 0.0
    crossed_down = prev_gap > 0.0 >= curr_gap and curr_gap != 0.0
    if not (crossed_up or crossed_down):
        return None
    return Event(
        event_type=EventType.INTRINSIC_VALUE_CROSSED_PRICE,
        ticker=curr.ticker.upper(),
        curr_snapshot_date=snapshot_date,
        prev_snapshot_date=prev_date,
        details={
            "direction": "above_price" if crossed_up else "below_price",
            "prev_intrinsic_value": prev.intrinsic_value,
            "prev_price": prev.price,
            "intrinsic_value": curr.intrinsic_value,
            "price": curr.price,
        },
    )


def detect_new_red_flags(
    prev: HoldingMark | None,
    curr: HoldingMark,
    *,
    snapshot_date: date,
    prev_date: date | None,
) -> list[Event]:
    """Narrative flags that newly turned red on a held position (spec §8.3).

    A flag fires only if it is red now *and* was not red in the prior mark (so a
    persistently-red flag is not re-reported every run). With no prior mark, or
    one whose flags are unknown (``None``), every currently-red flag is new. A
    current mark with unknown flags yields nothing: it is not an all-clear, but
    there is nothing to report either.
    """
    if curr.red_flags is None:
        return []
    prev_red = set(prev.red_flags) if prev is not None and prev.red_flags else set()
    return [
        Event(
            event_type=EventType.NEW_RED_FLAG,
            ticker=curr.ticker.upper(),
            curr_snapshot_date=snapshot_date,
            prev_snapshot_date=prev_date,
            details={"flag": name, "reason": reason},
        )
        for name, reason in curr.red_flags.items()
        if name not in prev_red
    ]


def detect_concentration(
    positions: list[Position],
    *,
    snapshot_date: date,
    prev_date: date | None,
    threshold: float = DEFAULT_CONCENTRATION_THRESHOLD,
) -> list[Event]:
    """Single positions exceeding a fraction of total market value (spec §8.3).

    Weight is ``market_value / sum(market_value)`` over positions with a known,
    positive market value. A weight strictly greater than ``threshold`` fires;
    exactly at the threshold does not (boundary exclusive).
    """
    valued = [p for p in positions if p.market_value is not None and p.market_value > 0.0]
    total = sum(p.market_value or 0.0 for p in valued)
    if total <= 0.0:
        return []
    events: list[Event] = []
    for position in valued:
        weight = (position.market_value or 0.0) / total
        if weight > threshold:
            events.append(
                Event(
                    event_type=EventType.CONCENTRATION,
                    ticker=position.ticker,
                    curr_snapshot_date=snapshot_date,
                    prev_snapshot_date=prev_date,
                    details={"weight": weight, "market_value": position.market_value},
                )
            )
    return events


def detect_sector_recalibration(
    prev_wacc: float | None,
    curr_wacc: float | None,
    ticker: str,
    *,
    snapshot_date: date,
    prev_date: date | None,
    threshold: float = DEFAULT_WACC_RECALIBRATION_BPS,
) -> Event | None:
    """Sector WACC moved beyond a threshold between datasets (spec §8.3).

    A move with absolute value strictly greater than ``threshold`` (default
    100bps) fires. Returns ``None`` when either WACC is unknown or the move is
    within the band.
    """
    if prev_wacc is None or curr_wacc is None:
        return None
    delta = curr_wacc - prev_wacc
    if abs(delta) <= threshold:
        return None
    return Event(
        event_type=EventType.SECTOR_RECALIBRATED,
        ticker=ticker.upper(),
        curr_snapshot_date=snapshot_date,
        prev_snapshot_date=prev_date,
        details={"prev_wacc": prev_wacc, "wacc": curr_wacc, "delta": delta},
    )


def detect_below_quality_gate(
    prev_failed: Sequence[str] | None,
    curr_failed: Sequence[str] | None,
    ticker: str,
    *,
    snapshot_date: date,
    prev_date: date | None,
) -> list[Event]:
    """A held position newly tripped one or more screener quality gates (§8.3).

    Fires one event per gate in ``curr_failed`` that was not in ``prev_failed``
    (e.g. ``max_net_debt_to_ebitda``). ``None`` on either side means the gates
    could not be evaluated: with no baseline a standing failure is not "new", and
    with no current evaluation there is nothing to report.
    """
    if prev_failed is None or curr_failed is None:
        return []
    already_failing = set(prev_failed)
    return [
        Event(
            event_type=EventType.BELOW_QUALITY_GATE,
            ticker=ticker.upper(),
            curr_snapshot_date=snapshot_date,
            prev_snapshot_date=prev_date,
            details={"gate": gate},
        )
        for gate in curr_failed
        if gate not in already_failing
    ]


# --------------------------------------------------------------------------- #
# DB reader-orchestrator                                                        #
# --------------------------------------------------------------------------- #


def _load_positions(conn: duckdb.DuckDBPyConnection, snapshot_date: date) -> list[Position]:
    """Aggregate a snapshot's rows into one :class:`Position` per ticker."""
    rows = conn.execute(
        "SELECT ticker, SUM(qty) AS qty, "
        "SUM(market_value) AS market_value, "
        "ANY_VALUE(currency) AS currency "
        "FROM portfolio_snapshots WHERE snapshot_date = ? "
        "GROUP BY ticker ORDER BY ticker",
        [snapshot_date],
    ).fetchall()
    return [
        Position(
            ticker=str(r[0]).upper(),
            qty=float(r[1]) if r[1] is not None else 0.0,
            market_value=float(r[2]) if r[2] is not None else None,
            currency=str(r[3]) if r[3] is not None else None,
        )
        for r in rows
    ]


def _load_filings(
    conn: duckdb.DuckDBPyConnection,
    held_tickers: set[str],
    window_end: date,
) -> list[Filing]:
    """Held filings up to ``window_end``; the detector applies the lower bound."""
    if not held_tickers:
        return []
    placeholders = ", ".join("?" for _ in held_tickers)
    rows = conn.execute(
        f"SELECT ticker, filing_type, filing_date, accession_number, "
        f"COALESCE(CAST(fetched_at AS DATE), filing_date) "
        f"FROM filings_log WHERE UPPER(ticker) IN ({placeholders}) "
        f"AND filing_date <= ?",
        [*sorted(held_tickers), window_end],
    ).fetchall()
    return [
        Filing(
            ticker=str(r[0]),
            filing_type=str(r[1]),
            filing_date=r[2],
            accession_number=str(r[3]) if r[3] is not None else None,
            fetched_on=r[4],
        )
        for r in rows
    ]


def _load_reported_filings(
    conn: duckdb.DuckDBPyConnection,
    held_tickers: set[str],
) -> set[tuple[str, str, str]]:
    """``(ticker, filing_type, filing_date ISO)`` of filings already reported."""
    if not held_tickers:
        return set()
    placeholders = ", ".join("?" for _ in held_tickers)
    rows = conn.execute(
        f"SELECT UPPER(ticker), json_extract_string(details, '$.filing_type'), "
        f"json_extract_string(details, '$.filing_date') "
        f"FROM events_log WHERE event_type = 'new_filing' "
        f"AND UPPER(ticker) IN ({placeholders})",
        sorted(held_tickers),
    ).fetchall()
    return {(str(r[0]), str(r[1]), str(r[2])) for r in rows}


def _load_corporate_actions(
    conn: duckdb.DuckDBPyConnection,
    held_tickers: set[str],
    window_start: date | None,
    window_end: date,
) -> list[tuple[str, str, dict[str, object]]]:
    if not held_tickers:
        return []
    placeholders = ", ".join("?" for _ in held_tickers)
    params: list[object] = [*sorted(held_tickers), window_end]
    sql = (
        f"SELECT ticker, action_type, details FROM corporate_actions "
        f"WHERE UPPER(ticker) IN ({placeholders}) AND effective_date <= ?"
    )
    if window_start is not None:
        sql += " AND effective_date > ?"
        params.append(window_start)
    rows = conn.execute(sql, params).fetchall()
    out: list[tuple[str, str, dict[str, object]]] = []
    for r in rows:
        details: dict[str, object] = {}
        if r[2] is not None:
            parsed = json.loads(r[2]) if isinstance(r[2], str) else r[2]
            if isinstance(parsed, dict):
                details = parsed
        out.append((str(r[0]), str(r[1]), details))
    return out


def compute_events(
    conn: duckdb.DuckDBPyConnection,
    prev_snapshot_date: date | None,
    curr_snapshot_date: date,
    *,
    size_change_threshold: float = DEFAULT_SIZE_CHANGE_THRESHOLD,
    concentration_threshold: float = DEFAULT_CONCENTRATION_THRESHOLD,
) -> list[Event]:
    """Diff two portfolio snapshots into the §8.3 event stream.

    Reads positions, filings, corporate actions and the persisted holding marks
    off ``conn`` and fans them through the pure detectors. Valuation-derived
    events (IV cross, new red flag, quality gate, sector recalibration) diff the
    ``holding_marks`` of the two snapshots, so the caller must have persisted the
    current snapshot's marks (``mark_holdings``) first; a held ticker with no
    current mark still produces its broker events. ``prev_snapshot_date`` of
    ``None`` treats ``curr`` as the first snapshot: every current position is
    "opened" and there is no baseline mark, so only red flags (all new) fire.

    This function is a pure reader: it never writes to ``events_log`` — the
    caller persists the returned events (and may run auto-analyze on
    ``NEW_FILING``, which is the CLI's job per #29).
    """
    curr_positions = _load_positions(conn, curr_snapshot_date)
    prev_positions = (
        _load_positions(conn, prev_snapshot_date) if prev_snapshot_date is not None else []
    )
    held_tickers = {p.ticker for p in curr_positions if p.qty != 0.0}

    events: list[Event] = []

    # --- IBKR-observed -----------------------------------------------------
    events.extend(
        detect_position_changes(
            prev_positions,
            curr_positions,
            snapshot_date=curr_snapshot_date,
            prev_date=prev_snapshot_date,
            size_change_threshold=size_change_threshold,
        )
    )
    if prev_snapshot_date is not None:
        events.extend(
            detect_currency_changes(
                prev_positions,
                curr_positions,
                snapshot_date=curr_snapshot_date,
                prev_date=prev_snapshot_date,
            )
        )
    events.extend(
        detect_corporate_action_events(
            _load_corporate_actions(conn, held_tickers, prev_snapshot_date, curr_snapshot_date),
            snapshot_date=curr_snapshot_date,
            prev_date=prev_snapshot_date,
        )
    )

    # --- Concentration (snapshot-only) -------------------------------------
    events.extend(
        detect_concentration(
            curr_positions,
            snapshot_date=curr_snapshot_date,
            prev_date=prev_snapshot_date,
            threshold=concentration_threshold,
        )
    )

    # --- New filings for held tickers --------------------------------------
    events.extend(
        detect_new_filings(
            _load_filings(conn, held_tickers, curr_snapshot_date),
            held_tickers=held_tickers,
            reported=_load_reported_filings(conn, held_tickers),
            window_start=prev_snapshot_date,
            window_end=curr_snapshot_date,
            snapshot_date=curr_snapshot_date,
            prev_date=prev_snapshot_date,
        )
    )

    # --- Valuation-derived (diff of persisted holding marks) ---------------
    prev_marks = load_marks(conn, prev_snapshot_date) if prev_snapshot_date else {}
    curr_marks = load_marks(conn, curr_snapshot_date)
    for ticker in sorted(held_tickers):
        curr_mark = curr_marks.get(ticker)
        if curr_mark is None:
            continue
        prev_mark = prev_marks.get(ticker)
        cross = detect_intrinsic_value_cross(
            prev_mark,
            curr_mark,
            snapshot_date=curr_snapshot_date,
            prev_date=prev_snapshot_date,
        )
        if cross is not None:
            events.append(cross)
        events.extend(
            detect_new_red_flags(
                prev_mark,
                curr_mark,
                snapshot_date=curr_snapshot_date,
                prev_date=prev_snapshot_date,
            )
        )
        events.extend(
            detect_below_quality_gate(
                prev_mark.failed_gates if prev_mark is not None else None,
                curr_mark.failed_gates,
                ticker,
                snapshot_date=curr_snapshot_date,
                prev_date=prev_snapshot_date,
            )
        )
        recalibration = detect_sector_recalibration(
            prev_mark.sector_wacc if prev_mark is not None else None,
            curr_mark.sector_wacc,
            ticker,
            snapshot_date=curr_snapshot_date,
            prev_date=prev_snapshot_date,
        )
        if recalibration is not None:
            events.append(recalibration)

    return events


def persist_events(conn: duckdb.DuckDBPyConnection, events: list[Event]) -> int:
    """Append ``events`` to ``events_log``. Returns the number of rows written."""
    if not events:
        return 0
    conn.executemany(
        "INSERT INTO events_log "
        "(event_type, ticker, prev_snapshot_date, curr_snapshot_date, details) "
        "VALUES (?, ?, ?, ?, ?)",
        [
            [
                str(e.event_type),
                e.ticker,
                e.prev_snapshot_date,
                e.curr_snapshot_date,
                json.dumps(e.details),
            ]
            for e in events
        ],
    )
    return len(events)
