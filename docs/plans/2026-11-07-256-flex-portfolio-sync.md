# Portfolio sync from the IBKR Flex Web Service — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `bot portfolio` takes positions, cash, trades and corporate actions from one IBKR Flex statement over HTTPS, so it runs unattended with no TWS / IB Gateway; the TWS socket client and `ib_async` are removed.

**Architecture:** `src/bot/ingest/ibkr_flex.py` gains a pure parser `parse_statement(xml, tz) -> FlexStatement` and a `FlexPortfolioClient` that downloads once per instance (reusing `FlexClient.fetch_statement`), parses lazily and serves the existing `PortfolioSource` / `TradeSource` protocols plus `as_of()` and `corporate_actions()`. `run_portfolio` keys the snapshot and the report directory on `client.as_of()` and upserts the corporate actions from the same statement. `src/bot/ingest/ibkr.py` keeps only the three transport-neutral dataclasses.

**Tech Stack:** Python 3.12, httpx, `xml.etree.ElementTree`, `zoneinfo`, DuckDB, pydantic-settings, Typer, pytest; d2 v0.9.0 and TLC for the pipeline boards and model.

**Spec:** issue #256 ("Design (approved in conversation 2026-11-07)", sections 1–6, and "Acceptance").

## Acceptance criteria (verbatim from the issue)

- AC1: `uv run bot portfolio` with only `BOT_IBKR_FLEX_TOKEN` and `BOT_IBKR_FLEX_QUERY_ID` set writes `reports/<statement-date>/portfolio.md` and `alerts.md`, a `portfolio_snapshots` row per account, `cash_balances`, new `trades` and `corporate_actions`, and the events diff, with no TWS / IB Gateway running. (Task 3)
- AC2: `grep -r ib_async src uv.lock` returns nothing. (Task 4)
- AC3: `uv run pytest -q`, `uv run ruff check .`, `uv run mypy src` pass. (each task runs its own tests; the full suite is green from Task 7, see A4)

## Global Constraints

- Flex becomes the **only** IBKR source. No socket client, no `ib_async`, no `ibapi`, and the string `ib_async` appears nowhere under `src/` (docstrings included) nor in `uv.lock`.
- Settings: `ibkr_flex_token`, `ibkr_flex_query_id` (existing), new `ibkr_flex_tz: str = "America/New_York"` (`BOT_IBKR_FLEX_TZ`); `ibkr_host`, `ibkr_port`, `ibkr_client_id` removed.
- Mapping (issue §2), exact:
  - `OpenPosition` rows whose `levelOfDetail` is `SUMMARY` (or absent) → `PortfolioPosition(account=accountId, con_id=conid, symbol, sec_type=assetCategory, currency, exchange=listingExchange, quantity=position, avg_cost=costBasisPrice)`.
  - `CashReportCurrency` rows with `levelOfDetail == "Currency"`, skipping `currency == "BASE_SUMMARY"` → `CashBalance(account=accountId, currency, amount=endingCash)`.
  - `Trade` rows with `levelOfDetail == "EXECUTION"` → `TradeExecution(account=accountId, exec_id=ibExecID, con_id=conid, symbol, sec_type=assetCategory, currency, side=buySell, quantity, price=tradePrice, executed_at=dateTime, perm_id=ibOrderID)`.
- `dateTime` is in the reporting time zone `BOT_IBKR_FLEX_TZ`; `TradeExecution.executed_at` is timezone-aware UTC; `trades.executed_at` stays naive UTC (unchanged `_to_naive_utc`).
- `as_of()` = max `reportDate` over `OpenPosition` rows; fallback max `toDate` over `FlexStatement` elements.
- Download/poll loop reused unchanged (`RETRYABLE_CODES = {"1019", "1009"}`, `MAX_POLLS`, `POLL_DELAY_SECONDS`).
- `run_portfolio`: snapshot date = `client.as_of()`; stale when `as_of` is more than **5** days before the run day → `log.warning`, not an error. The `corporate_actions_fn` hook and its try/except are removed.
- CLI: missing token or query id → exit **2** with a clear message. Flex failure (`FlexError`) → exit 1.
- Out of scope (issue): using `markPrice` for market value; a backfill command; IB Gateway auto-login.

## Decisions taken here

1. **Accounts** = the `accountId` attribute of each `FlexStatement` element (one per account in a multi-account statement), in document order, de-duplicated.
2. **Required sections.** Every `FlexStatement` must contain an `OpenPositions`, a `CashReport` and a `Trades` element (they may be empty). An absent one raises `FlexError("Flex statement for <acct> has no <Section> section: add it to the Flex Query (README)")`. An absent section means a misconfigured query; reading it as "no positions" would snapshot an empty book and fire a position-closed event for every holding. `CorporateActions` / `CashTransactions` stay optional, as today.
3. **Date formats.** `reportDate` / `toDate`: `yyyyMMdd` (existing `_flex_date`). `dateTime`: `yyyyMMdd;HHmmss` (IBKR's default; the README tells the operator to keep the default date/time format). An unparseable trade `dateTime` raises `FlexError` naming the expected format, rather than silently dropping a fill.
4. **Numbers.** Empty or non-numeric `ibOrderID`, or a trade's `conid` → `0` (as the socket mapper did with `permId or 0`). An `OpenPosition` with an empty or non-numeric `conid` → `FlexError`: `con_id` is part of the `portfolio_snapshots` primary key (`src/bot/storage/schema.sql:191`), so two such rows would collide. Empty or non-numeric `position`, `costBasisPrice`, `endingCash`, `quantity`, `tradePrice` → `FlexError` naming the field and the row.
5. **Report header date.** `generated_on` stays the run day; the snapshot, directory, marks, events and report data use `as_of`.
6. **`run_portfolio(today=...)`** keeps the keyword, now meaning "the run day" (staleness check and `generated_on` only); default `date.today()`.
7. **`import_corporate_actions`** is deleted (its only caller was the removed hook), with `tests/unit/test_ibkr_flex_import.py`. `fetch_flex_statement`, `parse_flex_statement`, `parse_flex_row`, `upsert_corporate_actions` stay (used by `flex-capture` and the client).
8. **Bootstrap** prints a Flex checklist instead of the TWS one; it does not prompt for the Flex keys (they stay optional for everything but `bot portfolio`).
9. **Pipeline boards and the portfolio TLA+ model** (Task 7) are updated, although the issue's docs list does not name them, because `check.py` and `tests/unit/test_pipeline_diagram.py` cite `bot.ingest.ibkr.IbkrClient`, `import_corporate_actions` and `corporate_actions_fn(conn)`, which this issue deletes (CONTEXT.md: the boards must match the code).
10. **Absent attributes.** `_attr` returns `""` for an absent attribute (`src/bot/ingest/ibkr_flex.py` `_attr`), so an absent field is handled exactly like an empty one: a required field (Decision 3/4) raises `FlexError` naming it.
11. **`bot flex-capture` follows the query.** The issue says one query, validated by `bot flex-capture`, which records a *redacted* fixture. The redaction today fakes only `amount`, `proceeds`, `value`, `quantity`; the new sections carry the operator's holdings and cash, so `position`, `costBasisPrice`, `markPrice`, `endingCash`, `tradePrice` join the faked columns, and the capture runs `parse_statement` so a query missing a new section fails the capture (exit 1) instead of recording an unusable fixture (Task 6).
12. **TWS rule in the model.** `UnreachableTwsWritesNoMarkOrEvent` becomes `UnavailableStatementWritesNoMarkOrEvent`; `CorporateActionsFailureNeverStops` is dropped (the actions now come from the statement whose failure stops the run before anything is written).

## Review Focus

1. A Flex Query missing the Open Positions / Cash Report / Trades section → `FlexError`, never an empty snapshot (Task 1 test `test_missing_section_raises`).
2. Short positions and several accounts in one statement → negative quantity kept, rows attributed per account (Task 1 tests `test_positions_long_short_per_account`).
3. A flat book (no `OpenPosition` rows) → `as_of` falls back to `toDate`; no `toDate` either → `FlexError` (Task 1 tests `test_as_of_fallback_to_date`, `test_as_of_missing_raises`).
4. A fill at exactly the stored watermark → kept and absorbed by `exec_id` dedupe (Task 2 test `test_trades_since_is_inclusive`), and a DST-boundary `dateTime` converts with the right offset (Task 1 test `test_trade_time_zone_conversion`).
5. Re-running `bot portfolio` on a later day with the same statement → same `as_of`, same snapshot overwritten, no duplicate trades or corporate actions (Task 3 test `test_rerun_same_statement_is_idempotent`).

## Assumptions

Technical choices made during plan grilling (rejected alternative in brackets):

- A1. Lot rows (`levelOfDetail="LOT"`) in Open Positions are skipped; only `SUMMARY` (or no `levelOfDetail`) rows become positions. [Trusting the operator to pick "Summary": a "Summary and Lot" query would double-count every position.]
- A2. A present-but-empty `<OpenPositions />` is a flat book and is snapshotted as such, exactly as the socket client stored whatever `positions()` returned (`src/bot/portfolio/sync.py` `sync_portfolio`). [A guard comparing with the previous snapshot: new product behaviour the issue does not ask for.]
- A3. A gap longer than the 7-day query period between two runs loses the fills in between; it is written down in ADR 0010 and the README next to the backfill procedure, with no runtime detection. [A warning when the watermark precedes `fromDate`: it would fire every day for an account that simply has not traded.]
- A4. Intermediate commits may leave `tests/unit/test_pipeline_*.py` red between Task 3 and Task 7 (the boards cite symbols Task 3/4 delete); the branch is squash-merged and the full suite is green from Task 7 on. [Editing boards in every task: the render needs d2 once, not four times.]
- A5. `trade dateTime` format `yyyyMMdd;HHmmss` (IBKR's default) is assumed until `bot flex-capture` records a real statement; the issue already says the real capture replaces the synthetic fixture.
- A7. `TradeExecution.quantity` takes Flex's signed `quantity` as is (the issue's mapping); nothing under `src/` reads `trades.qty` (only `max(executed_at)` in `src/bot/portfolio/trades.py` `_watermark`). [Normalising to unsigned like the socket fills.]
- A8. Snapshots stored before the cutover are keyed on the run day, later ones on the statement date; no migration. ADR 0010 says so. The `--history` series simply has one point per stored date.
- A9. A rerun with a statement whose `as_of` was already synced replaces that date's snapshot (`_replace_account_day`), but `events_log` is append-only (`src/bot/portfolio/events.py` `persist_events`), so events repeat: that is the open issue #83, not this one. A holiday rerun now hits it more often; ADR 0010 mentions #83.
- A6. The protocol conformance is enforced by `uv run mypy src` on the call `run_portfolio(conn, FlexPortfolioClient.from_settings(settings), ...)` in `src/bot/cli.py`; the test only checks behaviour.

---

### Task 1: Flex statement parser

**Files:**
- Modify: `src/bot/ingest/ibkr_flex.py`
- Modify: `tests/fixtures/ibkr_flex/statement_sample.xml` (add synthetic `OpenPositions`, `CashReport`, `Trades` sections to both `FlexStatement`s; update the header comment's expected import)
- Test: `tests/unit/test_ibkr_flex_statement.py` (new)

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class FlexStatement: positions: list[PortfolioPosition]; cash: list[CashBalance]; trades: list[TradeExecution]; corporate_actions: list[CorporateActionRecord]; accounts: list[str]; as_of: date`
  - `def parse_statement(xml: str, *, tz: ZoneInfo) -> FlexStatement` — pure; raises `FlexError` per Decisions 2–4. `corporate_actions` = `parse_flex_statement(xml)`.
  - `FlexError` must be defined above `parse_statement` (move the class up).

- [ ] **Step 1: Write the failing tests** (synthetic XML strings built in the test, plus one over the fixture):
  - `test_positions_long_short_per_account`: two `FlexStatement`s (`U1`, `U2`), `U1` holds `AAPL position="100" costBasisPrice="150.5"` and `TSLA position="-20"`; `U2` holds `KO position="50"` → three positions, TSLA quantity `-20.0`, accounts `["U1", "U2"]`, every field mapped as in Global Constraints.
  - `test_cash_skips_base_summary`: rows `BASE_SUMMARY` (Currency), `USD` (Currency, `endingCash="1234.5"`), `EUR` (`levelOfDetail="Summary"`) → `[CashBalance("U1", "USD", 1234.5)]`.
  - `test_trades_only_executions`: `Trade` rows `EXECUTION`, `ORDER`, `CLOSED_LOT`, plus an `Order` element → one `TradeExecution` with `exec_id=ibExecID`, `perm_id=int(ibOrderID)`, `side="BUY"`.
  - `test_trade_time_zone_conversion`: `dateTime="20261105;093000"` with `tz=ZoneInfo("America/New_York")` → `datetime(2026, 11, 5, 14, 30, tzinfo=UTC)`; `"20261030;093000"` → `13:30 UTC` (EDT).
  - `test_bad_trade_datetime_raises`: `dateTime="2026-11-05 09:30:00"` → `FlexError` mentioning `yyyyMMdd;HHmmss`.
  - `test_missing_section_raises` (parametrized over `OpenPositions`, `CashReport`, `Trades`) → `FlexError` naming the section; an empty `<OpenPositions />` parses to no positions.
  - `test_as_of_is_max_report_date` (two accounts with `reportDate` 20261105 and 20261106, a third flat account → `date(2026, 11, 6)`), `test_as_of_fallback_to_date` (no positions, `toDate="20261106"` → `date(2026, 11, 6)`), `test_as_of_missing_raises`.
  - `test_empty_order_id_is_zero`; `test_bad_number_raises` (`position=""`); `test_position_without_conid_raises`.
  - `test_lot_rows_skipped`: one `SUMMARY` row and two `LOT` rows for `AAPL` → one position.
  - `test_absent_trade_datetime_raises`: a `Trade` row with no `dateTime` attribute → `FlexError` naming `dateTime`.
  - `test_fixture_parses`: `statement_sample.xml` → the corporate actions are the five existing records, plus the positions/cash/trades the fixture header lists.
- [ ] **Step 2:** `uv run pytest tests/unit/test_ibkr_flex_statement.py -q` → FAIL (`ImportError: parse_statement`).
- [ ] **Step 3:** Implement `FlexStatement` and `parse_statement` in `ibkr_flex.py`. Iterate `root.iter("FlexStatement")`; per statement read `OpenPositions/OpenPosition`, `CashReport/CashReportCurrency`, `Trades/Trade`. Reuse `_attr` and `_flex_date`.
- [ ] **Step 4:** The new tests plus `tests/unit/test_ibkr_flex_parser.py tests/unit/test_ibkr_flex_row.py tests/unit/test_flex_docs.py tests/integration/test_ibkr_flex_events.py` → PASS.
- [ ] **Step 5:** Commit `feat(#256): parse positions, cash and trades from a Flex statement`.

### Task 2: `FlexPortfolioClient` and the `BOT_IBKR_FLEX_TZ` setting

**Files:**
- Modify: `src/bot/ingest/ibkr_flex.py`, `src/bot/config.py`
- Test: `tests/unit/test_ibkr_flex_portfolio_client.py` (new), `tests/unit/test_config.py`

**Interfaces:**
- Consumes: `parse_statement`, `FlexStatement`, `FlexClient` (Task 1 / existing).
- Produces:
  - `class FlexPortfolioClient` with `__init__(self, token: str, query_id: str, *, tz: ZoneInfo, transport: httpx.BaseTransport | None = None)`, `@classmethod from_settings(cls, settings: Settings, *, transport: httpx.BaseTransport | None = None) -> FlexPortfolioClient`, and methods `connect() -> None`, `disconnect() -> None` (no-ops), `accounts() -> list[str]`, `positions(account_id: str) -> list[PortfolioPosition]`, `cash_balances(account_id: str) -> list[CashBalance]`, `trades(account_id: str, since: datetime | None = None) -> list[TradeExecution]`, `as_of() -> date`, `corporate_actions() -> list[CorporateActionRecord]`.
  - `Settings.ibkr_flex_tz: str = "America/New_York"` with a `field_validator` rejecting an unknown zone (`ValueError`).

- [ ] **Step 1: Write the failing tests** with an `httpx.MockTransport` that answers SendRequest with Success and GetStatement with the fixture (pattern of `tests/unit/test_ibkr_flex_client.py`):
  - `test_downloads_once`: call `as_of()`, `accounts()`, `positions(...)`, `cash_balances(...)`, `trades(...)`, `corporate_actions()` → the transport saw exactly two requests.
  - `test_nothing_downloaded_until_used`: constructing the client makes no request.
  - `test_positions_and_cash_filter_by_account`.
  - `test_trades_since_filters_client_side` and `test_trades_since_is_inclusive` (a fill at exactly `since` is returned); naive `since` → `ValueError`.
  - `test_flex_error_propagates`: GetStatement answers a non-retryable error → `FlexError` from `as_of()`.
  - `test_network_error_is_flex_error`: a `MockTransport` raising `httpx.ConnectError` → `FlexError` from `as_of()` (existing `_get` wraps `httpx.HTTPError`).
  - `test_config.py`: `ibkr_flex_tz` default `"America/New_York"`; `Settings(ibkr_flex_tz="Mars/Base")` → `ValidationError`.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement. `from_settings` uses `settings.ibkr_flex_token.strip()`, `settings.ibkr_flex_query_id.strip()`, `ZoneInfo(settings.ibkr_flex_tz)`. The statement is cached on first use (`functools.cached_property` or an `Optional` field).
- [ ] **Step 4:** Run → PASS.
- [ ] **Step 5:** Commit `feat(#256): FlexPortfolioClient serves the portfolio and trade sources`.

### Task 3: `run_portfolio` and `bot portfolio` on the Flex statement

**Files:**
- Modify: `src/bot/portfolio/command.py`, `src/bot/cli.py`
- Modify tests: `tests/integration/test_portfolio_command.py` (fake gains `as_of()` / `corporate_actions()`; new full-flow test over the fixture), `tests/unit/test_cli_portfolio.py` (fake replaces `FlexPortfolioClient`; exit-2 and exit-1 tests)

**Interfaces:**
- Consumes: `FlexPortfolioClient` (Task 2), `upsert_corporate_actions`, `CorporateActionRecord`, `FlexError`.
- Produces: `PortfolioClient(PortfolioSource, TradeSource, Protocol)` gains `def as_of(self) -> date: ...` and `def corporate_actions(self) -> list[CorporateActionRecord]: ...`. `run_portfolio(conn, client, *, reports_dir, today=None, history=False, concentration=False, analyze_fn=None, quality_gates=(), assumptions_dir=None, currencies=None, default_spreads=None)` — `corporate_actions_fn` removed. Module constant `STALE_AFTER_DAYS = 5`.

- [ ] **Step 1: Write the failing tests:**
  - Integration `test_full_flow_over_flex_fixture`: `FlexPortfolioClient` over a mock transport serving `statement_sample.xml`, prices seeded for the fixture tickers; `run_portfolio(..., today=as_of + 1 day)` → `reports/<as_of>/portfolio.md` and `alerts.md` exist, one `portfolio_snapshots` row set per fixture account at `as_of`, `cash_balances` rows, `trades` rows equal to the fixture executions, `corporate_actions` has the five fixture records, `result.snapshot_date == as_of`.
  - `test_snapshot_keyed_on_as_of`: fake `as_of()` = 2026-06-01, `today` = 2026-06-03 → `reports/2026-06-01/`, `portfolio_snapshots.snapshot_date == 2026-06-01`.
  - `test_stale_statement_warns`: `as_of` 6 days before `today` → a `portfolio_statement_stale` warning (structlog `capture_logs`), run completes; 5 days → no warning.
  - `test_rerun_same_statement_is_idempotent`: two runs with the same fake on different `today` → one snapshot date, no duplicate trades / actions (events_log duplication is #83, not asserted).
  - In `test_full_flow_over_flex_fixture`, also assert one `SELL` trade keeps its negative quantity, and that `events_log` holds the first-run `position_opened` rows for the snapshot date (the events diff of AC1).
  - CLI `test_portfolio_requires_flex_credentials` (parametrized: token missing, query id missing) → exit 2, stderr names `BOT_IBKR_FLEX_TOKEN` / `BOT_IBKR_FLEX_QUERY_ID`.
  - CLI `test_portfolio_flex_failure_exits_1`: the fake's `as_of()` raises `FlexError("1020 Invalid request")` → exit 1, stderr contains `IBKR Flex statement unavailable` and the message.
- [ ] **Step 2:** Run → FAIL.
- [ ] **Step 3:** Implement. `run_portfolio`: `snapshot_date = client.as_of()` first; staleness warning `log.warning("portfolio_statement_stale", as_of=..., today=..., days=...)` when `(run_day - snapshot_date).days > STALE_AFTER_DAYS`; then `sync_portfolio(..., snapshot_date=snapshot_date)`, `upsert_corporate_actions(conn, client.corporate_actions())`, `sync_trades`, marks/events/reports keyed on `snapshot_date`; `generated_on=run_day`. Update the module docstring steps. CLI: build the client with `FlexPortfolioClient.from_settings(settings)` after checking both credentials (exit 2: `"bot portfolio needs BOT_IBKR_FLEX_TOKEN and BOT_IBKR_FLEX_QUERY_ID (README → Portfolio sync)"`), catch `FlexError` → exit 1 `"IBKR Flex statement unavailable: <msg>"`. Update the command docstring.
- [ ] **Step 4:** Run the two test files and `tests/unit/test_pipeline_diagram.py -k portfolio_cli` → PASS (the run-steps test is updated in Task 7).
- [ ] **Step 5:** Commit `feat(#256): bot portfolio keys the snapshot on the Flex statement date`.

### Task 4: Remove the socket client and `ib_async`

**Files:**
- Modify: `src/bot/ingest/ibkr.py` (only `PortfolioPosition`, `CashBalance`, `TradeExecution` + a docstring saying they are transport-neutral, filled by `bot.ingest.ibkr_flex`), `src/bot/ingest/ibkr_flex.py` (delete `import_corporate_actions`; module docstring), `src/bot/portfolio/sync.py`, `src/bot/portfolio/trades.py` (docstrings: no TWS / `ib_async`), `src/bot/config.py` (drop host/port/client_id; flex token/query descriptions say "required by `bot portfolio`"), `pyproject.toml`, `uv.lock` (`uv lock`), `scripts/bootstrap.sh` (Flex checklist), `scripts/daily.sh` (comment), `.env.example`
- Delete: `tests/unit/test_ibkr_client.py`, `tests/unit/test_ibkr_flex_import.py`
- Modify tests: `tests/unit/test_ibkr_dependencies.py`, `tests/integration/test_scripts.py` (bootstrap needles), any test still referencing removed settings

- [ ] **Step 1:** Rewrite `test_ibkr_dependencies.py`: `test_no_ibkr_socket_library_declared` (neither `ib-async` nor `ibapi` in `[project].dependencies`), `test_no_ibkr_socket_library_locked` (neither in `uv.lock`), `test_ib_async_not_mentioned_in_src` (no file under `src/` contains `ib_async`). Update bootstrap needles to `"Flex Web Service"`, `"BOT_IBKR_FLEX_TOKEN"`, `"BOT_IBKR_FLEX_QUERY_ID"`, `"bot flex-capture"`, `"bot portfolio"` (keep the screening needles). Run → FAIL.
- [ ] **Step 2:** Make the edits; `uv remove ib-async` (updates both files).
- [ ] **Step 3:** `grep -r ib_async src uv.lock` → no output; `uv run pytest -q`, `uv run ruff check .`, `uv run mypy src` → pass except the pipeline-board tests owned by Task 7.
- [ ] **Step 4:** Commit `refactor(#256): drop the TWS socket client and ib_async`.

### Task 5: ADR 0010 and the written docs

**Files:**
- Create: `docs/adr/0010-flex-web-service-as-the-only-ibkr-source.md` (Status: Implemented; supersedes 0004; context = the 2026-11-02..06 week without snapshots; decision; consequences: previous-business-day snapshot, `BOT_IBKR_FLEX_TZ`, token yearly expiry, history no longer session-limited, a gap longer than the query period loses fills unless the period is widened once)
- Modify: `docs/adr/0004-tws-api-via-ib-async.md` (Status: Superseded by ADR 0010), spec §8.1 in `docs/superpowers/specs/2026-05-25-investment-bot-design.md`, `src/bot/storage/schema.sql` comments on `trades` and `corporate_actions` (no DDL change), `README.md` (replace the TWS section with "Portfolio sync via Flex Web Service": step-by-step query setup with the five sections and their fields from issue §1, period Last 7 Calendar Days, XML, default date format, token, `.env`, `bot flex-capture`, the backfill procedure, that an existing corporate-actions query must gain the three new sections, and that a gap longer than the query period loses fills (Assumption A3); remove `BOT_IBKR_HOST/PORT/CLIENT_ID` and the TWS smoke test), `CONTEXT.md` (External services: Flex replaces the TWS bullet; ADR 0010), `docs/plano/estado.py` / `docs/plano/views.py` (IBKR rows say Flex, not TWS), then `python3 docs/plano/build.py` and `python3 docs/plano/build_estado.py`
- Test: `tests/unit/test_flex_docs.py` (extend)

- [ ] **Step 1:** Add tests: README mentions each of the five section names and `Last 7 Calendar Days` and `BOT_IBKR_FLEX_TZ`; README and `.env.example` contain no `BOT_IBKR_HOST`; ADR 0004 status contains `Superseded by ADR 0010`; ADR 0010 exists with `## Status` `Implemented`. Run → FAIL.
- [ ] **Step 2:** Write the docs.
- [ ] **Step 3:** Tests pass; `python3 docs/plano/build.py` exits 0.
- [ ] **Step 4:** Commit `docs(#256): ADR 0010, README, spec and context describe the Flex-only portfolio sync`.

### Task 6: `bot flex-capture` validates and redacts the new sections

**Files:**
- Modify: `src/bot/ingest/ibkr_flex_capture.py` (`_NUMERIC_ATTRS` gains `position`, `costBasisPrice`, `markPrice`, `endingCash`, `tradePrice`; `capture` runs `parse_statement(xml, tz=ZoneInfo(settings.ibkr_flex_tz))` before writing anything and lets `FlexError` propagate; `FlexSummary` gains `positions: int`, `cash_rows: int`, `trades: int`)
- Test: `tests/unit/test_ibkr_flex_capture.py`

**Interfaces:**
- Consumes: `parse_statement` (Task 1), `Settings.ibkr_flex_tz` (Task 2).

- [ ] **Step 1:** Tests: `test_redaction_fakes_position_money` (the five new attributes keep sign and shape, not value); `test_summary_counts_new_sections`; `test_capture_rejects_query_without_open_positions` (`FlexError`, no file written). Run → FAIL.
- [ ] **Step 2:** Implement.
- [ ] **Step 3:** `uv run pytest tests/unit/test_ibkr_flex_capture.py tests/unit/test_flex_docs.py -q` → PASS.
- [ ] **Step 4:** Commit `feat(#256): flex-capture validates and redacts positions, cash and trades`.

### Task 7: Pipeline boards and the portfolio model

**Files:**
- Modify: `docs/pipeline/pipeline.d2`, `docs/pipeline/portfolio.d2`, `docs/pipeline/portfolio-sync.d2`, `docs/pipeline/models/portfolio.tla`, `docs/pipeline/models/portfolio.cfg`, `docs/pipeline/models/portfolio.view.js`, `docs/pipeline/models/README.md` (if it names the rules), `tests/unit/test_pipeline_diagram.py`, `tests/unit/test_pipeline_models.py`; the rendered SVGs and `docs/pipeline/rendered.sha256`

- [ ] **Step 1:** Update the tests: expected symbols `bot.ingest.ibkr_flex.FlexPortfolioClient` and `bot.ingest.ibkr_flex.upsert_corporate_actions` replace `IbkrClient` / `import_corporate_actions`; run-steps order `["client.as_of()", "sync_portfolio(", "upsert_corporate_actions(", "sync_trades(", ...]`; `_PORTFOLIO_RULES` per Decision 12. Run → FAIL.
- [ ] **Step 2:** Edit boards: the external node becomes the IBKR Flex Web Service (one statement: positions, cash, trades, corporate actions; `BOT_IBKR_FLEX_TOKEN`, `BOT_IBKR_FLEX_QUERY_ID`, `BOT_IBKR_FLEX_TZ`); exits: missing credentials → 2, statement unavailable → 1; step 2 "corporate actions from the same statement". Edit the model: `tws_*` phases become `statement_unavailable`, the corporate-actions steps read from the statement, no `flexFailed`.
- [ ] **Step 3:** `python3 docs/pipeline/check.py` after rendering with d2 v0.9.0 (`docs/pipeline/build.sh`; d2 installed with the official script into `~/.local` if not on `PATH`, else the `pipeline-render` CI artifact); TLC via `docs/pipeline/models/check.sh` when Java is available, else the `models` CI job.
- [ ] **Step 4:** Full suite, ruff, mypy → pass.
- [ ] **Step 5:** Commit `docs(#256): pipeline boards and portfolio model read the Flex statement`.

## Grilling

Two rounds (griller model: fable), 33 questions (17 + 16).

Sources of the answers:
- ISSUE: 12. The mapping, the attribute values (`Currency`, `BASE_SUMMARY`, `EXECUTION`, `ibExecID`, `ibOrderID`, `costBasisPrice`), one shared query id (`Both go into the existing BOT_IBKR_FLEX_TOKEN / BOT_IBKR_FLEX_QUERY_ID`), `as_of` = max `reportDate`, the backfill procedure, signed quantity (`quantity`).
- CODE: 17. `_previous_snapshot_date` takes the snapshot strictly before (`src/bot/portfolio/command.py:68-79`); `_watermark` re-attaches UTC (`src/bot/portfolio/trades.py:96-114`); `trades.exec_id` primary key plus `ON CONFLICT (exec_id) DO NOTHING` (`schema.sql:220`, `trades.py:129`); `corporate_actions.action_id` primary key (`schema.sql:243`); `FlexClient._get` wraps every `httpx.HTTPError` into `FlexError` (`ibkr_flex.py:275`); worst case 10 polls × 3 s plus 30 s timeouts per request (`ibkr_flex.py:47-48,231`), and `scripts/daily.sh` sets no timeout; `portfolio_snapshots` key includes `con_id` (`schema.sql:191`); CLI seam `monkeypatch.setattr(bot.cli, "IbkrClient", ...)` (`tests/unit/test_cli_portfolio.py:96`); `capture` receives `Settings` and writes after parsing (`ibkr_flex_capture.py:253-281`) and exits 2 on missing credentials; `parse_flex_statement` iterates the whole root; `sync_portfolio(snapshot_date=...)` exists (`sync.py`); marks price on or before the snapshot date (#225, CONTEXT.md "Margin of safety"); `capture_logs` already used (`tests/integration/test_portfolio_command.py:405`); `persist_events` is append-only (open issue #83).
- DOC: 1. CONTEXT.md (boards must match the code; ADRs say when they are implemented).
- NO SOURCE: 9 → all technical assumptions A1–A9 above. No spec ambiguity, nothing out of scope.

Issues opened: none.
