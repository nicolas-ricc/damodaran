"""Render the portfolio monitor's full-state and alert reports via Jinja2 (M5, #29).

The ``bot portfolio`` command (see :mod:`bot.portfolio.command`) performs a
sync + diff and then needs two artefacts written under the dated report
directory:

* ``portfolio.md`` — the **full state**: positions, profit & loss, concentration
  breakdown and suggested reviews, plus an optional P&L time-series (``--history``)
  and an explicit concentration breakdown (``--concentration``).
* ``alerts.md`` — **today's events only**, rendered from the §8.3 event stream;
  always written, even when there are zero events (an empty-but-present file).

This module is the one place that turns plain report data into those two
strings. It mirrors the other reporting modules: the rendering functions are
*pure* (data in, string out) and the Markdown layout lives in bundled Jinja2
templates so the prose is editable without touching code. Reading the data off
the DB lives in :func:`build_report` (a pure reader: a connection in, a dataclass
out); writing the strings to disk is the command's job.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from jinja2 import Environment, PackageLoader, select_autoescape

from bot.portfolio.events import (
    DEFAULT_CONCENTRATION_THRESHOLD,
    Event,
)

if TYPE_CHECKING:
    import duckdb

_DASH = "—"


@dataclass(frozen=True)
class PositionRow:
    """A single held position with cost basis, market value and derived P&L."""

    ticker: str
    qty: float
    avg_cost: float
    market_value: float | None
    currency: str | None

    @property
    def cost_basis(self) -> float:
        return self.qty * self.avg_cost

    @property
    def pnl(self) -> float | None:
        if self.market_value is None:
            return None
        return self.market_value - self.cost_basis

    @property
    def pnl_pct(self) -> float | None:
        basis = self.cost_basis
        if self.market_value is None or basis == 0.0:
            return None
        return (self.market_value - basis) / abs(basis)


@dataclass(frozen=True)
class ConcentrationRow:
    """A position's weight in the portfolio's total market value."""

    ticker: str
    market_value: float
    weight: float
    flagged: bool


@dataclass(frozen=True)
class HistoryRow:
    """Total market value / cost / P&L for one historical snapshot date."""

    snapshot_date: date
    market_value: float
    cost_basis: float

    @property
    def pnl(self) -> float:
        return self.market_value - self.cost_basis


@dataclass(frozen=True)
class PortfolioReport:
    """Everything the ``portfolio.md`` template needs, as plain data."""

    snapshot_date: date
    positions: tuple[PositionRow, ...]
    concentration: tuple[ConcentrationRow, ...]
    history: tuple[HistoryRow, ...]
    cash: tuple[tuple[str, float], ...]
    total_market_value: float
    total_cost_basis: float
    concentration_threshold: float
    include_history: bool
    include_concentration: bool
    unpriced: tuple[str, ...] = ()

    @property
    def total_pnl(self) -> float:
        return self.total_market_value - self.total_cost_basis


def _load_position_rows(
    conn: duckdb.DuckDBPyConnection, snapshot_date: date
) -> list[PositionRow]:
    """Aggregate a snapshot's rows into one :class:`PositionRow` per ticker."""
    rows = conn.execute(
        "SELECT ticker, SUM(qty) AS qty, "
        "SUM(qty * avg_cost) AS cost_basis, "
        "SUM(market_value) AS market_value, "
        "COUNT(*) FILTER (WHERE market_value IS NULL) AS unpriced_legs, "
        "ANY_VALUE(currency) AS currency "
        "FROM portfolio_snapshots WHERE snapshot_date = ? "
        "GROUP BY ticker ORDER BY ticker",
        [snapshot_date],
    ).fetchall()
    out: list[PositionRow] = []
    for ticker, qty, cost_basis, market_value, unpriced_legs, currency in rows:
        q = float(qty) if qty is not None else 0.0
        basis = float(cost_basis) if cost_basis is not None else 0.0
        avg_cost = basis / q if q != 0.0 else 0.0
        # If *any* leg of a ticker is unpriced, the SUM(market_value) would
        # silently understate (DuckDB drops NULLs from the sum), so report the
        # whole position as unpriced rather than a misleading partial value.
        mv = (
            None
            if (unpriced_legs or 0) > 0 or market_value is None
            else float(market_value)
        )
        out.append(
            PositionRow(
                ticker=str(ticker).upper(),
                qty=q,
                avg_cost=avg_cost,
                market_value=mv,
                currency=str(currency) if currency is not None else None,
            )
        )
    return out


def _load_cash(
    conn: duckdb.DuckDBPyConnection, snapshot_date: date
) -> list[tuple[str, float]]:
    rows = conn.execute(
        "SELECT currency, SUM(amount) AS amount FROM cash_balances "
        "WHERE snapshot_date = ? GROUP BY currency ORDER BY currency",
        [snapshot_date],
    ).fetchall()
    return [
        (str(currency), float(amount) if amount is not None else 0.0)
        for currency, amount in rows
    ]


# A snapshot's total market value and cost basis, defined once and shared by the
# headline (:func:`_snapshot_totals`) and the time series (:func:`_load_history`)
# so they agree by construction. Unpriced legs (NULL ``market_value``) fall back
# to cost basis here — the *one* place that rule lives for totals. Note this
# coalesces per *leg*, whereas the positions table flags a whole ticker as
# unpriced if any leg lacks a price; that only diverges for a partially-priced
# ticker, and only in the table's "—" display, never in these reconciled totals.
_MARKET_VALUE_SQL = "SUM(COALESCE(market_value, qty * avg_cost))"
_COST_BASIS_SQL = "SUM(qty * avg_cost)"


def _snapshot_totals(
    conn: duckdb.DuckDBPyConnection, snapshot_date: date
) -> tuple[float, float]:
    """Return ``(total_market_value, total_cost_basis)`` for one snapshot.

    The single source of truth for the headline totals; the latest
    :func:`_load_history` row is the same two expressions, so headline and
    history can never disagree.
    """
    row = conn.execute(
        f"SELECT {_MARKET_VALUE_SQL}, {_COST_BASIS_SQL} "
        "FROM portfolio_snapshots WHERE snapshot_date = ?",
        [snapshot_date],
    ).fetchone()
    if row is None:
        return 0.0, 0.0
    market_value, cost_basis = row
    return (
        float(market_value) if market_value is not None else 0.0,
        float(cost_basis) if cost_basis is not None else 0.0,
    )


def _load_history(conn: duckdb.DuckDBPyConnection) -> list[HistoryRow]:
    """Total market value + cost basis per snapshot date, oldest first."""
    rows = conn.execute(
        "SELECT snapshot_date, "
        f"{_MARKET_VALUE_SQL} AS market_value, "
        f"{_COST_BASIS_SQL} AS cost_basis "
        "FROM portfolio_snapshots GROUP BY snapshot_date ORDER BY snapshot_date"
    ).fetchall()
    return [
        HistoryRow(
            snapshot_date=snapshot_date,
            market_value=float(market_value) if market_value is not None else 0.0,
            cost_basis=float(cost_basis) if cost_basis is not None else 0.0,
        )
        for snapshot_date, market_value, cost_basis in rows
    ]


def _concentration(
    positions: list[PositionRow], *, threshold: float
) -> list[ConcentrationRow]:
    """Weight each position by market value; flag those over ``threshold``."""
    valued = [
        p for p in positions if p.market_value is not None and p.market_value > 0.0
    ]
    total = sum(p.market_value or 0.0 for p in valued)
    if total <= 0.0:
        return []
    breakdown = [
        ConcentrationRow(
            ticker=p.ticker,
            market_value=p.market_value or 0.0,
            weight=(p.market_value or 0.0) / total,
            flagged=(p.market_value or 0.0) / total > threshold,
        )
        for p in valued
    ]
    breakdown.sort(key=lambda r: r.weight, reverse=True)
    return breakdown


def build_report(
    conn: duckdb.DuckDBPyConnection,
    snapshot_date: date,
    *,
    include_history: bool = False,
    include_concentration: bool = False,
    concentration_threshold: float = DEFAULT_CONCENTRATION_THRESHOLD,
) -> PortfolioReport:
    """Assemble the full-state report data off the DB (a pure reader).

    Args:
        conn: Open DuckDB connection with the schema applied.
        snapshot_date: The snapshot to render the full state of.
        include_history: Whether to gather the P&L time series (``--history``).
        include_concentration: Whether the explicit concentration breakdown is
            requested (``--concentration``); the headline concentration section
            is always rendered.
        concentration_threshold: Weight above which a position is flagged.

    Returns:
        A :class:`PortfolioReport` of plain data, ready to render.
    """
    positions = _load_position_rows(conn, snapshot_date)
    concentration = _concentration(positions, threshold=concentration_threshold)
    # Headline totals: real value where priced, cost-basis fallback for unpriced
    # positions so the total isn't understated (per-position P&L stays "—"). Same
    # expression as the history series, so the two never disagree. Concentration
    # weights, by contrast, use only priced positions.
    total_mv, total_cost = _snapshot_totals(conn, snapshot_date)
    unpriced = tuple(p.ticker for p in positions if p.market_value is None)
    history = _load_history(conn) if include_history else []
    cash = _load_cash(conn, snapshot_date)
    return PortfolioReport(
        snapshot_date=snapshot_date,
        positions=tuple(positions),
        concentration=tuple(concentration),
        history=tuple(history),
        cash=tuple(cash),
        total_market_value=total_mv,
        total_cost_basis=total_cost,
        concentration_threshold=concentration_threshold,
        include_history=include_history,
        include_concentration=include_concentration,
        unpriced=unpriced,
    )


# --------------------------------------------------------------------------- #
# Jinja2 rendering                                                              #
# --------------------------------------------------------------------------- #


def _fmt_money(value: Any) -> str:
    if value is None:
        return _DASH
    number = float(value)
    sign = "-" if number < 0 else ""
    magnitude = abs(number)
    if magnitude >= 1e9:
        return f"{sign}{magnitude / 1e9:,.2f}B"
    if magnitude >= 1e6:
        return f"{sign}{magnitude / 1e6:,.2f}M"
    if magnitude >= 1e3:
        return f"{sign}{magnitude / 1e3:,.2f}K"
    return f"{sign}{magnitude:,.2f}"


def _fmt_signed_money(value: Any) -> str:
    if value is None:
        return _DASH
    number = float(value)
    return ("+" if number >= 0 else "") + _fmt_money(number)


def _fmt_pct(value: Any) -> str:
    if value is None:
        return _DASH
    return f"{float(value):.1%}"


def _fmt_signed_pct(value: Any) -> str:
    if value is None:
        return _DASH
    return f"{float(value):+.1%}"


def _fmt_num(value: Any) -> str:
    if value is None:
        return _DASH
    return f"{float(value):,.2f}"


@lru_cache(maxsize=1)
def _environment() -> Environment:
    env = Environment(
        loader=PackageLoader("bot.reporting", "templates"),
        autoescape=select_autoescape(enabled_extensions=(), default=False),
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["money"] = _fmt_money
    env.filters["signed_money"] = _fmt_signed_money
    env.filters["pct"] = _fmt_pct
    env.filters["signed_pct"] = _fmt_signed_pct
    env.filters["num"] = _fmt_num
    return env


def render_portfolio(report: PortfolioReport, *, generated_on: date | None = None) -> str:
    """Render ``report`` as the full-state ``portfolio.md`` (pure)."""
    template = _environment().get_template("portfolio.md.j2")
    stamp = (generated_on or date.today()).isoformat()
    return template.render(r=report, generated_at=stamp)


def render_alerts(
    events: list[Event],
    snapshot_date: date,
    *,
    generated_on: date | None = None,
) -> str:
    """Render *events* as today-only ``alerts.md`` (pure).

    Always returns a non-empty *header*; the body lists the events, or a short
    "no events" line when ``events`` is empty, so the file is present-but-quiet
    rather than zero-length.
    """
    template = _environment().get_template("alerts.md.j2")
    stamp = (generated_on or date.today()).isoformat()
    return template.render(
        events=events, snapshot_date=snapshot_date.isoformat(), generated_at=stamp
    )
