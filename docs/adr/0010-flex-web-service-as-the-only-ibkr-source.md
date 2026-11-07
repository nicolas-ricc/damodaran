# ADR 0010 — IBKR Flex Web Service as the only IBKR source

## Status

Implemented (2026-11-07, issue #256). Supersedes [ADR 0004](0004-tws-api-via-ib-async.md).

The code is in `src/bot/ingest/ibkr_flex.py` (`FlexPortfolioClient`) and
`src/bot/portfolio/command.py` (`run_portfolio`).

## Context

ADR 0004 read positions, cash and trades over the TWS socket (`ib_async`), which needs a
TWS or IB Gateway process running and logged in on the same host. From 2026-11-02 to
2026-11-06 nobody was logged in, so `bot portfolio` failed every day and the week has no
snapshots, no trades and no events. The Flex Web Service was already in the codebase for
corporate actions (#56) and needs only a token and a query id.

## Decision

The Flex Web Service is the only IBKR source. The TWS socket client, `ib_async` and the
`BOT_IBKR_HOST` / `BOT_IBKR_PORT` / `BOT_IBKR_CLIENT_ID` settings are removed.

- One Activity Flex Query (XML, period Last 7 Calendar Days) carries Open Positions, Cash
  Report, Trades, Corporate Actions and Cash Transactions. `FlexPortfolioClient`
  downloads it once per run and serves positions, cash, trades and corporate actions
  from that one statement.
- A statement missing Open Positions, Cash Report or Trades is a misconfigured query and
  raises `FlexError`: reading it as "no positions" would snapshot an empty book and fire a
  position-closed event for every holding.
- `bot portfolio` keys the snapshot and `reports/<as_of>/` on the statement date: the
  latest `reportDate` of the Open Positions, falling back to the latest `toDate`. A statement
  more than 5 days older than the run day logs a warning, not an error.
- Trade `dateTime` is in the account's reporting time zone, `BOT_IBKR_FLEX_TZ` (default
  `America/New_York`); it is converted to UTC before `trades.executed_at` (naive UTC).
- Missing `BOT_IBKR_FLEX_TOKEN` or `BOT_IBKR_FLEX_QUERY_ID` exits 2; a Flex failure exits 1.
  A failing download stops the run before anything is written.

## Consequences

Positive:
- No desktop process: `bot portfolio` runs unattended from cron on any host.
- Trade history is no longer limited to a TWS session. Widening the query period once in
  IBKR and running `bot portfolio` backfills history; `exec_id` dedupe absorbs the overlap.
- Corporate actions share the statement, so they no longer have a separate, optional import.

Negative:
- The snapshot is the previous business day's statement, not live: it carries the statement
  date, and the report header `generated_on` stays the run day. Snapshots stored before the
  cutover are keyed on the run day and later ones on the statement date; there is no
  migration, and `--history` has one point per stored date.
- The Flex token expires at most yearly and must be renewed by hand.
- A gap between two runs longer than the query period (7 days) loses the fills in between,
  with no runtime detection. Widen the period once to recover them.
- `BOT_IBKR_FLEX_TZ` must match the account's reporting time zone, or fills shift.
- `events_log` is append-only, so rerunning with a statement whose date was already synced
  repeats its events (open issue #83); a holiday rerun hits it more often.
- An existing corporate-actions-only query must gain the three new sections.

## Alternatives rejected

- **Keep TWS and add Flex** — two sources and a desktop dependency for no gain once Flex
  serves everything.
- **IB Gateway auto-login** — still a process to keep alive; out of scope.
- **Client Portal API** — rejected in ADR 0004 for its interactive authentication.
