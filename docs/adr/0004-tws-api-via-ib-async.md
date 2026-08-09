# ADR 0004 — IBKR portfolio sync over the TWS socket API via `ib_async`

## Status

Accepted (2026-08-09). Supersedes [ADR 0003](0003-client-portal-api-over-tws.md).

## Context

M5 needs a daily, unattended, read-only sync of positions, cash balances and
trades from Interactive Brokers (spec §8.1/§8.2). ADR 0003 chose the Client Portal
API (REST). Implementing it surfaced two blockers:

1. The gateway is a Docker container that must be running and reachable.
2. Authentication is a browser OAuth flow whose session expires and must be
   re-established interactively — incompatible with the cron schedule in §9.3.

## Decision

Use the **TWS socket API** through the `ib_async` library (`ib-async>=2.1.0`),
against a locally running TWS or IB Gateway.

- Host/port/client id are configuration, not constants: `BOT_IBKR_HOST`
  (default `127.0.0.1`), `BOT_IBKR_PORT` (default `7496` = live TWS; `7497` paper,
  `4001`/`4002` IB Gateway live/paper), `BOT_IBKR_CLIENT_ID` (default `1`).
- The client is **read-only by construction**: `src/bot/ingest/ibkr.py` exposes
  only `accounts`, `positions`, `cash_balances` and `trades`. There are no order
  placement methods. Operationally, TWS's "Read-Only API" toggle must be enabled.

## Consequences

Positive:
- No Docker, no browser step; the daily cron works unattended once TWS is up.
- `ib_async` is asyncio-native and matches the rest of the codebase's typing.

Negative:
- Requires a TWS/IB Gateway process running on the same host. This is acceptable
  for a single-user local tool (spec §2) but rules out a server deployment where
  no desktop session exists.
- **Trade history is session-limited.** The socket returns only the current
  session's fills, so `trades` cannot be backfilled historically. Documented in
  `src/bot/storage/schema.sql` above the `trades` table.
- **Corporate actions are out of reach.** Dividends and splits need the IBKR Flex
  Web Service, not the socket. The `corporate_actions` table is created but stays
  empty, so the `DIVIDEND` and `SPLIT` events in spec §8.3 cannot fire yet.

## Alternatives rejected

- **Client Portal API** — the original ADR 0003 choice; rejected for the
  interactive-auth reason above.
- **IBKR Flex Web Service alone** — good for historical statements and corporate
  actions, but it is a batch report API with no live positions, so it cannot serve
  the daily snapshot on its own. It remains the candidate for closing the
  corporate-actions gap later.
