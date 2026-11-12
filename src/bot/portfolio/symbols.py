"""Map IBKR broker symbols to universe tickers (#338).

Vocabulary: a *broker symbol* is what IBKR reports (``BRK B``, ``BRK.B``); a
*universe ticker* is the key in ``companies.ticker`` (``BRK-B``). Only the
seams that join portfolio rows to the universe resolve symbols; everything
else keeps the broker symbol as stored.
"""

from __future__ import annotations

import re
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import date
from types import MappingProxyType
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import duckdb

_SEPARATORS = re.compile(r"[ .\-]")


@dataclass(frozen=True)
class SymbolMap:
    """Outcome of resolving broker symbols against the universe.

    Attributes:
        resolved: Upper-cased broker symbol -> universe ticker, identity
            entries included.
        unresolved: Sorted symbols with no universe ticker.
        ignored: Sorted symbols deliberately mapped to ``None`` in overrides.
    """

    resolved: Mapping[str, str]
    unresolved: tuple[str, ...]
    ignored: tuple[str, ...]

    def ticker(self, symbol: str) -> str:
        """Return the universe ticker, or the upper-cased symbol if unresolved."""
        s = symbol.strip().upper()
        return self.resolved.get(s, s)


def resolve_symbols(
    symbols: Iterable[str],
    known: Collection[str],
    overrides: Mapping[str, str | None],
) -> SymbolMap:
    """Resolve broker symbols to universe tickers.

    An override is the only candidate and is used verbatim; a ``None``
    override marks the symbol ignored. Otherwise the candidates are the
    symbol as is, then with separators (space, dot, hyphen) normalised to
    ``-``, then to ``.``; the first one in ``known`` wins.

    Args:
        symbols: Broker symbols; blanks are skipped.
        known: Universe tickers (upper-case).
        overrides: Broker symbol -> ticker, or ``None`` to ignore.

    Returns:
        The resolution result.
    """
    resolved: dict[str, str] = {}
    unresolved: set[str] = set()
    ignored: set[str] = set()
    for symbol in symbols:
        s = symbol.strip().upper()
        if not s:
            continue
        if s in overrides:
            override = overrides[s]
            if override is None:
                ignored.add(s)
                continue
            candidates: Iterable[str] = (override,)
        else:
            candidates = dict.fromkeys((s, _SEPARATORS.sub("-", s), _SEPARATORS.sub(".", s)))
        match = next((c for c in candidates if c in known), None)
        if match is None:
            unresolved.add(s)
        else:
            resolved[s] = match
    return SymbolMap(
        resolved=MappingProxyType(resolved),
        unresolved=tuple(sorted(unresolved)),
        ignored=tuple(sorted(ignored)),
    )


def load_symbol_map(
    conn: duckdb.DuckDBPyConnection,
    symbols: Iterable[str],
    overrides: Mapping[str, str | None],
) -> SymbolMap:
    """Resolve ``symbols`` against the tickers in ``companies``."""
    known = {row[0] for row in conn.execute("SELECT UPPER(ticker) FROM companies").fetchall()}
    return resolve_symbols(symbols, known, overrides)


def held_symbols(conn: duckdb.DuckDBPyConnection, snapshot_date: date) -> list[str]:
    """Return the distinct upper-cased broker symbols held on ``snapshot_date``."""
    rows = conn.execute(
        "SELECT DISTINCT UPPER(ticker) FROM portfolio_snapshots WHERE snapshot_date = ? ORDER BY 1",
        [snapshot_date],
    ).fetchall()
    return [row[0] for row in rows]
