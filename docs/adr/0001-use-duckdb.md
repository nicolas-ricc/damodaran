# ADR 0001 — Use DuckDB for storage

**Status:** Accepted (2026-05-25)

## Context

The bot stores fundamentals (~50k companies × 10 years), Damodaran datasets, and portfolio snapshots. Queries are analytical (joins, aggregations across years/sectors) and there's a single user (no concurrency requirement).

Options considered:
- **SQLite**: ubiquitous, embedded, single-file. Fine for OLTP but slow on analytical queries (10–50× slower for our shape).
- **Postgres**: production-grade, but requires a running server, auth, and operational overhead unjustified for a single-user offline tool.
- **DuckDB**: columnar OLAP engine, embedded (single file), no server. Reads Parquet/CSV natively. Optimised for exactly the query shape we have.

## Decision

Use DuckDB.

## Consequences

- Backups = `cp bot.duckdb backup/`.
- No concurrent writes (acceptable — single user, CLI invocations are serial).
- DDL uses DuckDB syntax (some divergence from standard SQL, e.g. `QUALIFY` clause).
- If we ever need multi-user concurrent access, migration path is to Postgres; schema is mostly portable.
