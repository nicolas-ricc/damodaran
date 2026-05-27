"""DuckDB connection and schema management."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

import duckdb

DbPath = Path | str


def connect(db_path: DbPath) -> duckdb.DuckDBPyConnection:
    if isinstance(db_path, Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return duckdb.connect(str(db_path))
    return duckdb.connect(db_path)


def apply_schema(conn: duckdb.DuckDBPyConnection) -> None:
    sql = resources.files("bot.storage").joinpath("schema.sql").read_text()
    conn.execute(sql)
