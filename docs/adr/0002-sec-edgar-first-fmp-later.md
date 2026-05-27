# ADR 0002 — SEC EDGAR for US fundamentals; FMP for international (deferred to M2)

**Status:** Accepted (2026-05-25)

## Context

We need fundamentals for a global universe. The spec settles on a hybrid: free, authoritative source for US + paid provider for international.

## Decision

- **M1:** Implement SEC EDGAR adapter only (US coverage, official XBRL data, free).
- **M2:** Add Financial Modeling Prep adapter for non-US fundamentals (target ~50k companies) and global daily EOD prices.
- IBKR remains the source of truth for portfolio + execution-adjacent data (M5).

## Consequences

- M1 is shippable as a US-only research tool — useful for early iteration on Capa B/C even without global coverage.
- The `Adapter` interface in `src/bot/ingest/base.py` (currently a shared `IngestResult` dataclass; will grow as M2 adds adapters) is designed so M2 plugs in without touching the screener or valuator.
- We accept the column-mapping work that comes with FMP (their schema ≠ XBRL); that's part of M2.
