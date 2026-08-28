"""DuckDB connection and schema management."""

from __future__ import annotations

import re
from importlib import resources
from pathlib import Path

import duckdb

DbPath = Path | str

_CREATE_TABLE = re.compile(
    r"^\s*CREATE\s+TABLE(?:\s+IF\s+NOT\s+EXISTS)?\s+", re.IGNORECASE | re.MULTILINE
)


def _count_create_tables(sql: str) -> int:
    """Count CREATE TABLE statements, ignoring SQL line comments."""
    uncommented = "\n".join(line.split("--", 1)[0] for line in sql.splitlines())
    return len(_CREATE_TABLE.findall(uncommented))


def connect(db_path: DbPath) -> duckdb.DuckDBPyConnection:
    """Open (and create if missing) a DuckDB database at the given path.

    Pass ":memory:" for an in-memory DB (useful in tests).
    """
    if isinstance(db_path, Path):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return duckdb.connect(str(db_path))
    return duckdb.connect(db_path)


def apply_schema(conn: duckdb.DuckDBPyConnection) -> None:
    """Apply the DDL in schema.sql. Idempotent."""
    sql = resources.files("bot.storage").joinpath("schema.sql").read_text()
    conn.execute(sql)


def schema_table_count() -> int:
    """Number of tables ``schema.sql`` defines (used by ``bot doctor``)."""
    sql = resources.files("bot.storage").joinpath("schema.sql").read_text()
    return _count_create_tables(sql)
