"""Broker symbol -> universe ticker resolution (#338, #84).

``resolve_symbols`` is pure; ``load_symbol_map`` and ``held_symbols`` read an
in-memory DuckDB after ``apply_schema``.
"""

from __future__ import annotations

from datetime import date

import duckdb
import pytest

from bot.portfolio.symbols import held_symbols, load_symbol_map, resolve_symbols
from bot.storage.db import apply_schema


@pytest.fixture
def conn() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    apply_schema(c)
    return c


@pytest.mark.parametrize("symbol", ["BRK B", "BRK.B", "BRK-B"])
def test_share_class_separators_resolve_to_the_hyphen_ticker(symbol: str) -> None:
    m = resolve_symbols([symbol], {"BRK-B"}, {})
    assert dict(m.resolved) == {symbol: "BRK-B"}
    assert m.unresolved == ()
    assert m.ignored == ()


@pytest.mark.parametrize("symbol", ["BRK B", "BRK.B", "BRK-B"])
def test_share_class_separators_resolve_to_a_dot_ticker(symbol: str) -> None:
    assert resolve_symbols([symbol], {"BRK.B"}, {}).ticker(symbol) == "BRK.B"


def test_identity_resolution_and_case_insensitive_ticker() -> None:
    m = resolve_symbols(["AAPL"], {"AAPL"}, {})
    assert dict(m.resolved) == {"AAPL": "AAPL"}
    assert m.ticker("aapl") == "AAPL"


def test_as_is_candidate_wins_over_normalised() -> None:
    assert resolve_symbols(["BRK.B"], {"BRK.B", "BRK-B"}, {}).ticker("BRK.B") == "BRK.B"


def test_hyphen_wins_when_both_spellings_are_known() -> None:
    assert resolve_symbols(["BRK B"], {"BRK-B", "BRK.B"}, {}).ticker("BRK B") == "BRK-B"


def test_override_wins() -> None:
    assert resolve_symbols(["FOO"], {"BAR", "FOO-X"}, {"FOO": "BAR"}).ticker("FOO") == "BAR"


def test_override_is_not_corrected() -> None:
    m = resolve_symbols(["BRK B"], {"BRK-B"}, {"BRK B": "XYZ"})
    assert m.unresolved == ("BRK B",)
    assert m.ticker("BRK B") == "BRK B"


def test_null_override_is_ignored_not_unresolved() -> None:
    m = resolve_symbols(["SPY"], set(), {"SPY": None})
    assert m.ignored == ("SPY",)
    assert m.unresolved == ()
    assert m.ticker("spy") == "SPY"


def test_unresolved_falls_through_upper_cased() -> None:
    m = resolve_symbols(["zzz q"], {"AAPL"}, {})
    assert m.unresolved == ("ZZZ Q",)
    assert m.ticker(" zzz q ") == "ZZZ Q"


def test_no_other_spellings() -> None:
    assert resolve_symbols(["BRKB"], {"BRK-B"}, {}).unresolved == ("BRKB",)
    assert resolve_symbols(["BRK B"], {"BRKB"}, {}).unresolved == ("BRK B",)


def test_unresolved_and_ignored_are_sorted_and_deduplicated() -> None:
    m = resolve_symbols(
        ["ZZZ", "aaa", "AAA", "QQQ", "IEF"], set(), {"QQQ": None, "IEF": None}
    )
    assert m.unresolved == ("AAA", "ZZZ")
    assert m.ignored == ("IEF", "QQQ")


def test_blank_symbols_are_skipped() -> None:
    m = resolve_symbols(["", "  "], {"AAPL"}, {})
    assert dict(m.resolved) == {}
    assert m.unresolved == ()
    assert m.ignored == ()


@pytest.mark.parametrize("stored", ["BRK-B", "brk-b"])
def test_load_symbol_map_reads_companies(conn: duckdb.DuckDBPyConnection, stored: str) -> None:
    conn.execute(
        "INSERT INTO companies (ticker, name, source) VALUES (?, 'Berkshire B', 'sec_edgar')",
        [stored],
    )
    assert load_symbol_map(conn, ["BRK B"], {}).ticker("BRK B") == "BRK-B"


def test_held_symbols_distinct_upper_sorted_for_the_day(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    day = date(2026, 6, 1)
    conn.executemany(
        "INSERT INTO portfolio_snapshots (snapshot_date, account, ticker, con_id, qty) "
        "VALUES (?, ?, ?, ?, 1.0)",
        [
            (day, "DU1", "BRK B", 1),
            (day, "DU2", "BRK B", 1),
            (day, "DU1", "aapl", 2),
            (date(2026, 5, 29), "DU1", "MSFT", 3),
        ],
    )
    assert held_symbols(conn, day) == ["AAPL", "BRK B"]
