"""DuckDB connection and schema management."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import duckdb

DbPath = Path | str


def connect(db_path: DbPath) -> duckdb.DuckDBPyConnection:
    """Open (and create if missing) a DuckDB database at the given path.

    Pass ":memory:" for an in-memory DB (useful in tests).
    """
    if isinstance(db_path, Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return duckdb.connect(str(db_path))
    return duckdb.connect(db_path)


def apply_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Apply the DDL in `schema.sql`. Idempotent (uses CREATE TABLE IF NOT EXISTS)."""
    sql = resources.files("bot.storage").joinpath("schema.sql").read_text()
    conn.execute(sql)
