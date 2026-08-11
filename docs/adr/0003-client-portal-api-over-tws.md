# ADR 0003 — Use IBKR Client Portal API (REST) over TWS API (deferred to M5)

**Status:** Superseded by [ADR 0004](0004-tws-api-via-ib-async.md) (2026-08-09).

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

## Why this was superseded

The Client Portal API requires a Dockerised `cp-gateway` plus a browser OAuth
handshake whose session must be re-established interactively. That is incompatible
with a headless, cron-driven daily sync (spec §9.3). The TWS socket API reached
through `ib_async` needs only a running TWS/IB Gateway with the Read-Only API
toggle enabled, and no browser step. See ADR 0004.
