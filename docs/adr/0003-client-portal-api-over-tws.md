# ADR 0003 — Use IBKR Client Portal API (REST) over TWS API (deferred to M5)

**Status:** Accepted (2026-05-25)

## Context

For M5 we need to sync portfolio positions from Interactive Brokers UK. IBKR offers two main APIs:

- **TWS API** (Python `ib_insync`, etc.): TCP socket, requires TWS or IB Gateway running headless. Robust but operationally heavy.
- **Client Portal API**: HTTP/JSON REST. Local `cp-gateway` Docker. OAuth + session that requires re-login every ~24h.

We only need **read** access (no order execution in M5).

## Decision

Use Client Portal API.

## Consequences

- Daily re-auth via browser (~10 seconds, tolerable).
- Simpler ops (one Docker container vs full TWS install).
- If the daily re-auth becomes intolerable or we want execution later, migrate to TWS API. Sync logic is behind an adapter so this is a contained change.
