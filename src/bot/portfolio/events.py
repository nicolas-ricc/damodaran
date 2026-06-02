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
red flag) is isolated and unit-testable at its boundaries. :func:`compute_events`
is the reader-orchestrator: it gathers snapshot/filing/valuation inputs off the
connection, fans them through the detectors, and returns the events. It never
writes — persistence (and running auto-analyze) is the caller's job.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from bot.utils.logging import get_logger

if TYPE_CHECKING:
    import duckdb

    from bot.valuator.analysis import Analysis
    from bot.valuator.narrative_flags import NarrativeFlag

log = get_logger(__name__)


class _DCFLike(Protocol):
    @property
    def intrinsic_value(self) -> float: ...


class _AnalysisLike(Protocol):
    """The structural slice of :class:`~bot.valuator.analysis.Analysis` the
    valuation detectors read. A Protocol of read-only members so the real
    (frozen) ``Analysis`` and a lightweight test stub both satisfy it under
    ``mypy --strict``.
    """

    @property
    def ticker(self) -> str: ...

    @property
    def current_price(self) -> float | None: ...

    @property
    def dcf_result(self) -> _DCFLike: ...

    @property
    def narrative_flags(self) -> tuple[NarrativeFlag, ...]: ...


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
    """A filing-log entry for a held ticker (subset of ``filings_log``)."""

    ticker: str
    filing_type: str
    filing_date: date
    accession_number: str | None


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
        if (
            before is not None
            and position.currency is not None
            and before != position.currency
        ):
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
    window_start: date | None,
    window_end: date,
    snapshot_date: date,
    prev_date: date | None,
) -> list[Event]:
    """New filings for held tickers in ``(window_start, window_end]`` (spec §8.3).

    Emits one ``NEW_FILING`` event per qualifying filing. The CLI (#29) turns
    this into an auto-analyze; we only emit the signal. A ``window_start`` of
    ``None`` (first snapshot) admits everything up to and including ``window_end``.
    """
    events: list[Event] = []
    for filing in filings:
        if filing.ticker.upper() not in held_tickers:
            continue
        if filing.filing_date > window_end:
            continue
        if window_start is not None and filing.filing_date <= window_start:
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
    prev_analysis: _AnalysisLike | None,
    curr_analysis: _AnalysisLike,
    *,
    snapshot_date: date,
    prev_date: date | None,
) -> Event | None:
    """Intrinsic value crossed the current price in either direction (spec §8.3).

    A cross fires when the sign of ``intrinsic_value - current_price`` flips
    between the two analyses (under -> over or over -> under). Equal-to is not a
    cross. Needs both analyses' prices and intrinsic values; returns ``None``
    when any is missing or there is no prior analysis to compare against.
    """
    if prev_analysis is None:
        return None
    prev_iv = prev_analysis.dcf_result.intrinsic_value
    curr_iv = curr_analysis.dcf_result.intrinsic_value
    prev_price = prev_analysis.current_price
    curr_price = curr_analysis.current_price
    if prev_price is None or curr_price is None:
        return None
    prev_gap = prev_iv - prev_price
    curr_gap = curr_iv - curr_price
    crossed_up = prev_gap < 0.0 <= curr_gap and curr_gap != 0.0
    crossed_down = prev_gap > 0.0 >= curr_gap and curr_gap != 0.0
    if not (crossed_up or crossed_down):
        return None
    return Event(
        event_type=EventType.INTRINSIC_VALUE_CROSSED_PRICE,
        ticker=curr_analysis.ticker.upper(),
        curr_snapshot_date=snapshot_date,
        prev_snapshot_date=prev_date,
        details={
            "direction": "above_price" if crossed_up else "below_price",
            "prev_intrinsic_value": prev_iv,
            "prev_price": prev_price,
            "intrinsic_value": curr_iv,
            "price": curr_price,
        },
    )


def detect_new_red_flags(
    prev_analysis: _AnalysisLike | None,
    curr_analysis: _AnalysisLike,
    *,
    snapshot_date: date,
    prev_date: date | None,
) -> list[Event]:
    """Narrative flags that newly turned red on a held position (spec §8.3).

    A flag fires only if it is red now *and* was not red in the prior analysis
    (so a persistently-red flag is not re-reported every run). With no prior
    analysis, any currently-red flag is new.
    """
    from bot.valuator.narrative_flags import FlagColor

    prev_red = (
        {f.name for f in prev_analysis.narrative_flags if f.color is FlagColor.RED}
        if prev_analysis is not None
        else set()
    )
    events: list[Event] = []
    for flag in curr_analysis.narrative_flags:
        if flag.color is FlagColor.RED and flag.name not in prev_red:
            events.append(
                Event(
                    event_type=EventType.NEW_RED_FLAG,
                    ticker=curr_analysis.ticker.upper(),
                    curr_snapshot_date=snapshot_date,
                    prev_snapshot_date=prev_date,
                    details={"flag": flag.name, "reason": flag.reason},
                )
            )
    return events


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
    failed_gates: list[str],
    ticker: str,
    *,
    snapshot_date: date,
    prev_date: date | None,
) -> list[Event]:
    """A held position newly tripped one or more screener quality gates (§8.3).

    ``failed_gates`` is the list of gate names the position now fails (e.g.
    ``max_net_debt_to_ebitda``). One event per failed gate.
    """
    return [
        Event(
            event_type=EventType.BELOW_QUALITY_GATE,
            ticker=ticker.upper(),
            curr_snapshot_date=snapshot_date,
            prev_snapshot_date=prev_date,
            details={"gate": gate},
        )
        for gate in failed_gates
    ]


# --------------------------------------------------------------------------- #
# DB reader-orchestrator                                                        #
# --------------------------------------------------------------------------- #


class _AnalyzeFn(Protocol):
    def __call__(
        self, ticker: str, conn: duckdb.DuckDBPyConnection
    ) -> Analysis: ...


def _load_positions(
    conn: duckdb.DuckDBPyConnection, snapshot_date: date
) -> list[Position]:
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
    window_start: date | None,
    window_end: date,
) -> list[Filing]:
    if not held_tickers:
        return []
    placeholders = ", ".join("?" for _ in held_tickers)
    params: list[object] = [*sorted(held_tickers), window_end]
    sql = (
        f"SELECT ticker, filing_type, filing_date, accession_number "
        f"FROM filings_log WHERE UPPER(ticker) IN ({placeholders}) "
        f"AND filing_date <= ?"
    )
    if window_start is not None:
        sql += " AND filing_date > ?"
        params.append(window_start)
    rows = conn.execute(sql, params).fetchall()
    return [
        Filing(
            ticker=str(r[0]),
            filing_type=str(r[1]),
            filing_date=r[2],
            accession_number=str(r[3]) if r[3] is not None else None,
        )
        for r in rows
    ]


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
    analyze_fn: _AnalyzeFn | None = None,
    prev_analyses: dict[str, _AnalysisLike] | None = None,
    size_change_threshold: float = DEFAULT_SIZE_CHANGE_THRESHOLD,
    concentration_threshold: float = DEFAULT_CONCENTRATION_THRESHOLD,
) -> list[Event]:
    """Diff two portfolio snapshots into the §8.3 event stream.

    Reads positions, filings and corporate actions off ``conn`` and fans them
    through the pure detectors. Derived (capa A/B/C) events reuse the valuator
    entrypoint (``analyze_fn``, defaulting to :func:`bot.valuator.analysis.analyze`)
    rather than re-deriving valuation logic, and the filings log rather than
    re-fetching. A ticker that cannot be valued (no data / incomplete
    assumptions) is skipped for derived events but still produces its broker
    events. ``prev_snapshot_date`` of ``None`` treats ``curr`` as the first
    snapshot: every current position is "opened" and no diff-based events fire.

    This function is a pure reader: it never writes to ``events_log`` — the
    caller persists the returned events (and may run auto-analyze on
    ``NEW_FILING``, which is the CLI's job per #29).
    """
    if analyze_fn is None:
        from bot.valuator.analysis import analyze as _analyze

        def analyze_fn_default(
            ticker: str, conn: duckdb.DuckDBPyConnection
        ) -> Analysis:
            return _analyze(ticker, conn)

        analyze_fn = analyze_fn_default

    curr_positions = _load_positions(conn, curr_snapshot_date)
    prev_positions = (
        _load_positions(conn, prev_snapshot_date)
        if prev_snapshot_date is not None
        else []
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
            _load_corporate_actions(
                conn, held_tickers, prev_snapshot_date, curr_snapshot_date
            ),
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
            _load_filings(conn, held_tickers, prev_snapshot_date, curr_snapshot_date),
            held_tickers=held_tickers,
            window_start=prev_snapshot_date,
            window_end=curr_snapshot_date,
            snapshot_date=curr_snapshot_date,
            prev_date=prev_snapshot_date,
        )
    )

    # --- Valuation-derived (intrinsic-value cross, new red flag) -----------
    #
    # The valuator reads *current* DB state, so a single connection only yields
    # the current :class:`Analysis`; the prior valuation is recovered from the
    # events already persisted (``prev_analyses`` injected by the caller / CLI,
    # #29). When no prior valuation is available we treat every currently-red
    # flag as new and report an IV-below/above-price standing as a cross only if
    # a prior baseline was supplied. Detectors stay pure and are unit-tested on
    # synthetic before/after pairs; here we wire current analyses through with a
    # ``None`` baseline by default so the orchestrator never fabricates a cross
    # it cannot substantiate.
    for ticker in sorted(held_tickers):
        try:
            curr_analysis = analyze_fn(ticker, conn)
        except (LookupError, ValueError) as exc:
            log.debug("events.analyze_skipped", ticker=ticker, error=str(exc))
            continue
        prev_analysis = prev_analyses.get(ticker) if prev_analyses else None
        cross = detect_intrinsic_value_cross(
            prev_analysis,
            curr_analysis,
            snapshot_date=curr_snapshot_date,
            prev_date=prev_snapshot_date,
        )
        if cross is not None:
            events.append(cross)
        events.extend(
            detect_new_red_flags(
                prev_analysis,
                curr_analysis,
                snapshot_date=curr_snapshot_date,
                prev_date=prev_snapshot_date,
            )
        )

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
