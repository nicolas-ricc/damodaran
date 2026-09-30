"""A query-counting DuckDB connection proxy shared by the #53 N+1 tests."""

from __future__ import annotations

import duckdb


class CountingConn:
    """A connection proxy that counts ``execute`` calls (a query spy).

    Delegates every attribute to the wrapped DuckDB connection so it is a
    drop-in for the loaders and the valuator, while tallying every query issued.
    """

    def __init__(self, conn: duckdb.DuckDBPyConnection) -> None:
        self._conn = conn
        self.executes = 0

    def execute(self, *args: object, **kwargs: object) -> object:
        self.executes += 1
        return self._conn.execute(*args, **kwargs)

    def __getattr__(self, name: str) -> object:
        return getattr(self._conn, name)
