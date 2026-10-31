# Portfolio model (TLA+, TLC-checked) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A checked TLA+ model of `bot portfolio`: one holding through one run, from the notifier check and the Interactive Brokers (IBKR) sync through its mark, the twelve events, the two reports and the alert, with eleven rules as INVARIANTs.

**Architecture:** Three files beside the site, refresh and screen models in `docs/pipeline/models/`: `portfolio.tla` (one holding, one run; `phase` is the reader's state; one named action per thing that happens), `portfolio.cfg` (`SPECIFICATION Spec` + one `INVARIANT` per rule), `portfolio.view.js` (labels; groups = the five portfolio sub-boards). The convention tests in `tests/unit/test_pipeline_models.py` already run over every `*.tla`; three portfolio tests are added. TLC runs in CI only (job `models` of `pipeline-diagram`).

**Tech Stack:** TLA+ (TLC 1.7.4), the statechart skill at `STATECHART_COMMIT`, ES module view, pytest.

**Spec:** GitHub issue #171 (parent story #161, design decisions 6, 7, 9 in its plan comment). Model conventions: `docs/pipeline/models/README.md`; worked examples: `docs/pipeline/models/screen.tla`, `screen.cfg`, `screen.view.js`. Stage board: `docs/pipeline/portfolio.d2`.

## Global Constraints

- Files: `docs/pipeline/models/portfolio.tla`, `portfolio.cfg`, `portfolio.view.js`; first line `---- MODULE portfolio ----`. No `EXTENDS` (README: SANY's XML export fails on `FiniteSets`).
- Groups are exactly `portfolio-sync`, `portfolio-marks`, `portfolio-events`, `portfolio-mark-events`, `portfolio-alerts`.
- `Next == A1 \/ ... \/ Done`; `Done == phase \in EndPhases /\ UNCHANGED vars`; `Spec == Init /\ [][Next]_vars`; deadlock checking stays on.
- Each action has exactly one source phase, written `phase = "<from>"` (no `phase \in`), then `phase' = "<to>"`: the #164 label-match tests that #172 turns on for this stage read them with `phase = "(\w+)".*?phase' = "(\w+)"`.
- Each rule: a `(* Cites: ... *)` line, then the `\*` reader's sentence, then its definition. `\*` is reserved for rule sentences; every other comment is `(* ... *)`. Each action carries a `(* ... *)` citation of the code it mirrors.
- View maps `states`, `steps`, `groups` are plain `const`, one `key: "value",` per line, keys unquoted (the README and the screen model; the issue's `export const` is rejected by the skill's loader). The five exports verbatim as in `screen.view.js`; `title = "portfolio: one holding through bot portfolio"`.
- Labels: reader's words, no underscore, no camelCase, no action name; acronyms expanded at first use; conditions in `[brackets]` at the end of a step label.
- At most 500 distinct states (the skill writes no `chart.mmd` above that). The design below reaches 351, counted with a scratch Python mirror of these tables; the TLC count is authoritative.
- No file under `src/` or `docs/pipeline/*.d2` changes. Pipeline code never changes in this task.
- TLC cannot run in the sandbox (no Java, downloaded binaries refused); CI is the gate.

## Review Focus

- A rule that holds only because a guard forbids its violation. Each rule names the variable another action could set to break it; the reviewer checks the guard is the code's condition, cited, and not added for the rule.
- A reset that breaks a rule: some steps reset variables no later step reads (see "Resets"). A rule may read a variable only in phases before its reset; the reviewer checks each rule against the reset table.
- A closed holding (in the previous snapshot, not today's): it gets no mark, no weight, no dividend, split or filing check, and fires `position_closed` only (`_held_tickers`, `held_tickers` in `compute_events`). The model must reach `position closed` with `held = FALSE` and no mark stored.
- A previous mark with unknown red flags: `detect_new_red_flags` counts it as no red flag, so a red flag fires. The model folds that case into `NewRedFlagFires` with `prevMark = "present"`; rule (f) pins the no-previous-mark case.
- The state budget: one more persistent variable doubles a stretch of the graph. Any variable beyond the table needs a reset or a reason.

## Assumptions (technical, declared)

- **Order of the two event families.** `compute_events` runs the seven snapshot detectors before the five mark detectors. The model checks the five mark events (and concentration) first, then reads the previous snapshot's positions and checks the seven. Each detector reads stored rows only and no detector reads another's result, so the order changes no rule; checking the mark events first lets the model drop the mark's values before the seven, which keeps it under 500 states (in code order it reaches 554). Concentration sits with the mark events because the issue puts it in `portfolio-mark-events`.
- **Where the previous snapshot is read.** `run_portfolio` computes `prev_date` before `mark_holdings`; `compute_events` reads its positions (`_load_positions`) and marks (`load_marks`). The model reads the previous mark at the start of the mark events and the previous snapshot's positions at the start of the seven events. A previous mark exists only when the previous snapshot held the holding, so the first-run and not-held-before steps require `prevMark # "present"`.
- **The channel is split late.** `build_notifier` fixes the channel before the sync. The model only records valid or misconfigured there, and picks none or configured at the send. Nothing in between reads the channel, so this changes no behaviour and halves the states.
- **Left out:** the preset check (`damodaran_value.yaml` missing: exit code 2 before the sync; same shape as the channel check, not in the issue's list); a dividend and a split in the same window (each check fires at most one event); corporate actions as a store (the import's outcome is read by no rule except (k)); several accounts.
- **TWS dropping before the trades** is modelled: `sync_trades` connects again, and a `ConnectionError` there ends the run with exit code 1 after the snapshot is stored. Rule (b) covers both connections.
- **Two actions with the same effects** (`ItIsStoredWithAMarketValue`, `ItIsStoredUnpriced`): the issue's `portfolio-sync` lists "market value", and the stage board draws the unpriced case; no rule reads the difference, so no variable records it, and the two arrows differ by label only. `ItsWeightIsNotAbove15` names "unpriced" because `detect_concentration` drops positions without a positive market value. Rejected alternative: a `priced` variable, which would double the sync and marks stretch for no rule.
- **Rule (h) restates the detector's guard.** `above` is set by the weighing step, before and apart from the detector, so the rule checks that the detector follows the weight with no condition on the previous snapshot or mark (`detect_concentration` reads `curr_positions` only). The model has no previous weight, because the code has none.
- **The closed holding** goes from `trades_synced` straight to `concentration_checked`, labelled "its mark events and concentration are settled": nothing is computed for it there (`_held_tickers`, `held_tickers`, `detect_concentration` on positions with a market value).
- **Resets.** To stay under the budget, these steps reset a variable that no later step reads: leaving `flags_checked` resets `valuation`; leaving `recal_checked` resets `gates`; leaving `concentration_checked` resets `above` and `prevMark` (after the first-run guards have read it); leaving `currency_checked` resets `prev`; leaving `filings_checked` resets `filing`; leaving `alerts_written` resets `anyFired`. The `.tla` says so in one `(* ... *)` comment above `Init`.

---

### Task 1: portfolio model, config, view and its tests

**Files:**
- Create: `docs/pipeline/models/portfolio.tla`, `docs/pipeline/models/portfolio.cfg`, `docs/pipeline/models/portfolio.view.js`
- Modify: `tests/unit/test_pipeline_models.py` (add `_PORTFOLIO_GROUPS`, `_PORTFOLIO_RULES`, `test_portfolio_groups`, `test_portfolio_title`, `test_portfolio_rules_are_all_present`), `docs/pipeline/models/README.md` (the sentence "`site`, `refresh` and `screen` are modelled." gains `portfolio`)

**Interfaces:**
- Consumes: the convention tests (parametrised over `_STEMS`), which pick `portfolio` up automatically.
- Produces: phase names, action names and labels that #172 (portfolio sub-boards) draws; the rule sentences the sub-boards show.

#### Variables

`VARIABLES phase, channel, stored, flexFailed, held, valuation, gates, prevMark, above, prev, filing, event, anyFired, alerts`

| variable | Init | values | meaning |
| --- | --- | --- | --- |
| `phase` | `"started"` | the phases below | the reader's state |
| `channel` | `"unchecked"` | `"unchecked"`, `"misconfigured"`, `"valid"`, `"none"`, `"configured"` | the notifier channel |
| `stored` | `{}` | subsets of `{"portfolio_snapshots", "cash_balances", "trades", "holding_marks", "events_log", "portfolio_md", "alerts_md"}` | what this run has written |
| `flexFailed` | `FALSE` | BOOLEAN | the corporate-actions import raised |
| `held` | `FALSE` | BOOLEAN | today's summed quantity is not 0 |
| `valuation` | `"unread"` | `"unread"`, `"red"`, `"clear"`, `"unknown"` | today's mark: valued with a red flag / valued with none / not valued |
| `gates` | `"unread"` | `"unread"`, `"with_wacc"`, `"without_wacc"`, `"unknown"` | today's mark: failed gates and sector WACC known / gates known, WACC not / both unknown |
| `prevMark` | `"unread"` | `"unread"`, `"present"`, `"absent"` | the previous snapshot's mark of the holding |
| `above` | `FALSE` | BOOLEAN | its weight is above 15% |
| `prev` | `"unread"` | `"unread"`, `"none"`, `"without_it"`, `"with_it"` | no previous snapshot / one without the holding / one with it |
| `filing` | `"unread"` | `"unread"`, `"unreported"`, `"reported"` | a filing in the window, not yet / already in `events_log` |
| `event` | `"none"` | `"none"` and the twelve `EventType` values | the event the last step fired; every action sets it |
| `anyFired` | `FALSE` | BOOLEAN | an event of the holding fired this run |
| `alerts` | `"unwritten"` | `"unwritten"`, `"text"`, `"blank"` | `alerts.md` |

`EndPhases == {"channel_misconfigured", "tws_unreachable", "tws_lost", "not_sent", "sent", "send_failed"}`.

#### Phases, groups and state labels

| group | phase: label |
| --- | --- |
| portfolio-sync | `started`: "bot portfolio starts"; `channel_misconfigured`: "the run ends with exit code 2 before any sync"; `channel_checked`: "the notifier channel is valid"; `tws_unreachable`: "the run ends with exit code 1 before the snapshot"; `tws_reached`: "Trader Workstation (TWS) answers"; `snapshot_stored`: "today's snapshot and cash are stored"; `actions_synced`: "the corporate actions are fetched, skipped or failed"; `tws_lost`: "the run ends with exit code 1 after the snapshot"; `trades_synced`: "the new fills are stored" |
| portfolio-marks | `holding`: "it is a holding today"; `valuation_done`: "its intrinsic value, price and red flags are known, or unknown"; `gates_done`: "its failed gates and sector weighted average cost of capital (WACC) are known, or unknown"; `marked`: "today's mark is stored" |
| portfolio-mark-events | `marks_read`: "the previous mark is read, or there is none"; `cross_checked`: "intrinsic value and price are compared"; `flags_checked`: "its red flags are compared"; `gates_checked`: "its failed gates are compared"; `recal_checked`: "its sector WACC is compared"; `weighed`: "its weight in the portfolio is known"; `concentration_checked`: "its mark events and concentration are settled" |
| portfolio-events | `window`: "the previous snapshot is read, or there is none"; `positions_diffed`: "its position is compared"; `currency_checked`: "its currency is compared"; `dividend_checked`: "its dividends are checked"; `split_checked`: "its splits are checked"; `filing_found`: "a filing of it is in the window"; `filings_checked`: "its filings are checked" |
| portfolio-alerts | `logged`: "its events are in the events log"; `portfolio_written`: "portfolio.md is written"; `alerts_written`: "alerts.md is written"; `not_sent`: "the run ends with exit code 0, nothing sent"; `sent`: "the run ends with exit code 0, alerts sent"; `send_failed`: "the run ends with exit code 1, the send failed" |

#### Actions

Each action: `phase = "<from>"`, its guard, `phase' = "<to>"`, the effects named, `event' = "none"` unless it fires (then `event' = "<type>"` and `anyFired' = TRUE`), the resets of "Assumptions", and `UNCHANGED` for the rest. A `(* ... *)` citation above it. Paths are under `src/bot/`.

| action | from → to | guard / effect | cite | step label |
| --- | --- | --- | --- | --- |
| `TheChannelIsMisconfigured` | started → channel_misconfigured | `channel' = "misconfigured"` | `cli.py` `portfolio`: `build_notifier` raises `NotifierConfigError` → `typer.Exit(code=2)`, before `_open_db` and `run_portfolio` | "the notifier check fails [a missing setting, or a password in cleartext]" |
| `TheChannelIsValid` | started → channel_checked | `channel' = "valid"` | `notifier/__init__.py` `build_notifier` returns a notifier or `None` | "the notifier check passes [no channel, or every setting present]" |
| `TwsIsUnreachable` | channel_checked → tws_unreachable | — | `portfolio/sync.py` `sync_portfolio`: `client.connect()` raises before `_replace_account_day`; `cli.py` catches `ConnectionError`, `TimeoutError` → exit 1 | "Interactive Brokers (IBKR) Trader Workstation (TWS) cannot be reached [connection error or timeout]" |
| `TwsAnswers` | channel_checked → tws_reached | — | `sync_portfolio`, `client.connect()`, `client.accounts()` | "TWS answers" |
| `ItIsStoredWithAMarketValue` | tws_reached → snapshot_stored | `held' = TRUE`; `stored' = stored \cup {"portfolio_snapshots", "cash_balances"}` | `sync_portfolio`: `value_positions`, `_replace_account_day`, `_insert_positions`, `_insert_cash` | "its position is stored with a market value [a close, converted when its currency differs]" |
| `ItIsStoredUnpriced` | tws_reached → snapshot_stored | same effects | `value_positions`: no close, close ≤ 0, or a missing rate → `market_value` `None` | "its position is stored unpriced [no close, a close of 0 or less, or a missing rate]" |
| `TheSnapshotIsStoredWithoutIt` | tws_reached → snapshot_stored | `held' = FALSE`; stored as above | `sync_portfolio` writes only the positions the accounts return | "the snapshot is stored without it [no account holds it any more]" |
| `FlexIsNotConfigured` | snapshot_stored → actions_synced | — | `ingest/ibkr_flex.py` `import_corporate_actions` returns `None` without token or query id | "no corporate action is fetched [Flex token or query id not set]" |
| `FlexImportsTheActions` | snapshot_stored → actions_synced | — | `import_corporate_actions`: `fetch_statement`, `upsert_corporate_actions` | "new corporate actions are stored from the IBKR Flex Web Service" |
| `FlexFails` | snapshot_stored → actions_synced | `flexFailed' = TRUE` | `portfolio/command.py` `run_portfolio`: `except Exception` → `log.warning("corporate_actions_import_failed")` | "the corporate actions step fails and a warning is logged" |
| `TwsDropsBeforeTheTrades` | actions_synced → tws_lost | — | `portfolio/trades.py` `sync_trades` calls `client.connect()` again; `cli.py` → exit 1 | "TWS cannot be reached for the trades [connection error or timeout]" |
| `TheNewFillsAreStored` | actions_synced → trades_synced | `stored' = stored \cup {"trades"}` | `sync_trades`, `_watermark`, `_insert_dedup` | "the fills at or after the newest stored one are added" |
| `ItIsAHolding` | trades_synced → holding | guard `held` | `portfolio/marks.py` `_held_tickers`: `HAVING SUM(qty) <> 0` | "it is held today [its summed quantity is not 0]" |
| `ItIsNoLongerAHolding` | trades_synced → concentration_checked | guard `~held` | `_held_tickers`; `compute_events` `held_tickers`; `detect_concentration` weighs positions with a market value > 0 | "it is neither marked nor weighed [no longer held]" |
| `TheValuatorValuesItWithARedFlag` | holding → valuation_done | `valuation' = "red"` | `mark_holdings`: `analyze_fn` → `intrinsic_value`, `current_price`, flags with `FlagColor.RED` | "the valuator values it [a narrative flag is red]" |
| `TheValuatorValuesItWithNoRedFlag` | holding → valuation_done | `valuation' = "clear"` | same | "the valuator values it [no narrative flag is red]" |
| `TheValuatorCannotValueIt` | holding → valuation_done | `valuation' = "unknown"` | `mark_holdings`: `except (LookupError, ValueError)` leaves all three `None` | "the valuator cannot value it, so all three stay unknown" |
| `TheGatesAreJudged` | valuation_done → gates_done | `gates' = "with_wacc"` | `screener/engine.py` `load_holding_inputs`; `mark_holdings` `failed_gates`, `benchmarks.wacc` | "the gates are judged and the sector WACC is read [in companies, with a sector benchmark that has a WACC]" |
| `TheGatesAreJudgedWithoutWacc` | valuation_done → gates_done | `gates' = "without_wacc"` | `mark_holdings`: `sector_wacc = benchmarks.wacc if benchmarks else None` | "the gates are judged without a sector WACC [no sector benchmark, or no WACC in it]" |
| `TheGatesCannotBeJudged` | valuation_done → gates_done | guard `valuation = "unknown"`; `gates' = "unknown"` | `mark_holdings`: `if ticker in inputs` is false; `valuator/analysis.py` raises `LookupError` for a ticker not in `companies`, so it was not valued either | "the gates and the sector WACC stay unknown [not in companies]" |
| `TheMarkIsStored` | gates_done → marked | `stored' = stored \cup {"holding_marks"}` | `persist_marks` | "today's mark is stored, replacing any earlier mark of the day" |
| `ThePreviousMarkIsRead` | marked → marks_read | `prevMark' = "present"` | `compute_events`: `load_marks(conn, prev_snapshot_date)` | "the previous mark is read [it was marked then]" |
| `ThereIsNoPreviousMark` | marked → marks_read | `prevMark' = "absent"` | `compute_events`: `prev_marks` is `{}`, or lacks the ticker | "there is no previous mark [first run, or not marked then]" |
| `IntrinsicValueCrossFires` | marks_read → cross_checked | guard `prevMark = "present" /\ valuation # "unknown"`; fires `intrinsic_value_crossed_price` | `portfolio/events.py` `detect_intrinsic_value_cross` | "intrinsic value crossed price fires [the gap changed sign]" |
| `NoCross` | marks_read → cross_checked | — | same, returns `None` | "no cross [same sign, a zero gap, no previous mark, or a value unknown]" |
| `NewRedFlagFires` | cross_checked → flags_checked | guard `valuation = "red"`; fires `new_red_flag` | `detect_new_red_flags` | "new red flag fires [red now, not red in the previous mark]" |
| `NoNewRedFlag` | cross_checked → flags_checked | guard `valuation # "red" \/ prevMark = "present"` | same, returns `[]` | "no new red flag [none red now, already red before, or flags unknown]" |
| `BelowQualityGateFires` | flags_checked → gates_checked | guard `prevMark = "present" /\ gates # "unknown"`; fires `below_quality_gate`; resets `valuation` | `detect_below_quality_gate` | "below quality gate fires [a gate fails now that passed before]" |
| `NoNewFailedGate` | flags_checked → gates_checked | resets `valuation` | same, returns `[]` | "no new failed gate [none new, no previous mark, or gates unknown]" |
| `SectorRecalibratedFires` | gates_checked → recal_checked | guard `prevMark = "present" /\ gates = "with_wacc"`; fires `sector_recalibrated` | `detect_sector_recalibration`, `DEFAULT_WACC_RECALIBRATION_BPS` | "sector recalibrated fires [the sector WACC moved more than 100 basis points]" |
| `NoRecalibration` | gates_checked → recal_checked | — | same, returns `None` | "no recalibration [100 basis points or less, no previous mark, or a WACC unknown]" |
| `ItsWeightIsAbove15` | recal_checked → weighed | `above' = TRUE`; resets `gates` | `detect_concentration`: weight = market value ÷ total of positive market values; `DEFAULT_CONCENTRATION_THRESHOLD` | "its weight is computed [above 15% of the portfolio]" |
| `ItsWeightIsNotAbove15` | recal_checked → weighed | `above' = FALSE`; resets `gates` | same | "its weight is computed [15% or less, or unpriced]" |
| `ConcentrationFires` | weighed → concentration_checked | guard `above`; fires `concentration` | `detect_concentration`, `weight > threshold` | "concentration fires [above 15%]" |
| `NotConcentrated` | weighed → concentration_checked | guard `~above` | same | "no concentration [15% or less]" |
| `ThisIsTheFirstRun` | concentration_checked → window | guard `held /\ prevMark # "present"`; `prev' = "none"`; resets `above`, `prevMark` | `run_portfolio` `_previous_snapshot_date` → `None`; `compute_events` `prev_positions = []` | "there is no earlier snapshot [first run]" |
| `ThePreviousSnapshotHeldIt` | concentration_checked → window | `prev' = "with_it"`; resets `above`, `prevMark` | `compute_events` `_load_positions(conn, prev_snapshot_date)` | "the previous snapshot is read [it held it]" |
| `ThePreviousSnapshotLacksIt` | concentration_checked → window | guard `held /\ prevMark # "present"`; `prev' = "without_it"`; resets `above`, `prevMark` | same | "the previous snapshot is read [it did not hold it]" |
| `PositionOpenedFires` | window → positions_diffed | guard `held /\ prev # "with_it"`; fires `position_opened` | `detect_position_changes` | "position opened fires [held now, not in the previous snapshot]" |
| `PositionClosedFires` | window → positions_diffed | guard `~held`; fires `position_closed` | same | "position closed fires [held before, not now]" |
| `PositionSizeChangedFires` | window → positions_diffed | guard `held /\ prev = "with_it"`; fires `position_size_changed` | same, `DEFAULT_SIZE_CHANGE_THRESHOLD` | "position size changed fires [the quantity moved more than 10%]" |
| `PositionSizeHolds` | window → positions_diffed | guard `held /\ prev = "with_it"` | same | "no position event [the quantity moved 10% or less]" |
| `CurrencyChangedFires` | positions_diffed → currency_checked | guard `held /\ prev = "with_it"`; fires `currency_changed` | `compute_events` `if prev_snapshot_date is not None`; `detect_currency_changes` | "currency changed fires [both known and different]" |
| `CurrencyIsTheSame` | positions_diffed → currency_checked | — | same | "no currency event [same, unknown, or nothing to compare]" |
| `DividendFires` | currency_checked → dividend_checked | guard `held`; fires `dividend`; resets `prev` | `_load_corporate_actions` (held tickers, the window), `detect_corporate_action_events` | "dividend fires [a dividend in the window]" |
| `NoDividend` | currency_checked → dividend_checked | resets `prev` | same | "no dividend [none in the window, or no longer held]" |
| `SplitFires` | dividend_checked → split_checked | guard `held`; fires `split` | same | "split fires [a split in the window]" |
| `NoSplit` | dividend_checked → split_checked | — | same | "no split [none in the window, or no longer held]" |
| `ItsFilingIsNotInTheLog` | split_checked → filing_found | guard `held`; `filing' = "unreported"` | `_load_filings`, `_load_reported_filings` | "a filing of it is in the window [not yet in the events log]" |
| `ItsFilingIsInTheLog` | split_checked → filing_found | guard `held`; `filing' = "reported"` | same | "a filing of it is in the window [already in the events log]" |
| `NoFilingInTheWindow` | split_checked → filings_checked | — | `detect_new_filings` window bounds; `held_tickers` | "no filing in the window [none, or no longer held]" |
| `NewFilingFires` | filing_found → filings_checked | guard `filing = "unreported"`; fires `new_filing` | `detect_new_filings` | "new filing fires" |
| `NewFilingIsSkipped` | filing_found → filings_checked | guard `filing = "reported"` | `detect_new_filings`: `in reported: continue` | "the filing is skipped [already reported]" |
| `TheEventsAreAppended` | filings_checked → logged | `stored' = IF anyFired THEN stored \cup {"events_log"} ELSE stored`; resets `filing` | `persist_events` (writes nothing for no events) | "every event fired is appended to the events log" |
| `PortfolioMdIsWritten` | logged → portfolio_written | `stored' = stored \cup {"portfolio_md"}` | `run_portfolio`: `build_report`, `render_portfolio`, `portfolio_path.write_text` | "portfolio.md is written with positions, profit and loss (P&L) and concentration" |
| `AlertsMdListsTheEvents` | portfolio_written → alerts_written | `alerts' = "text"`; `stored' = stored \cup {"alerts_md"}` | `portfolio/report.py` `render_alerts`; `alerts_path.write_text` | "alerts.md lists today's events [a holding had an event]" |
| `AlertsMdIsBlank` | portfolio_written → alerts_written | guard `~anyFired`; `alerts' = "blank"`; stored as above | `render_alerts` returns `""` without events | "alerts.md is written empty [no holding had an event]" |
| `NoChannelIsSet` | alerts_written → not_sent | `channel' = "none"`; resets `anyFired` | `build_notifier` returns `None`; `notify_alerts` returns `False` | "nothing is sent [no channel]" |
| `TheBlankFileIsNotSent` | alerts_written → not_sent | guard `alerts = "blank"`; `channel' = "configured"`; resets `anyFired` | `notify_alerts`: `if not text.strip()` | "nothing is sent [a channel, but alerts.md is blank]" |
| `TheAlertsAreSent` | alerts_written → sent | guard `alerts = "text"`; `channel' = "configured"`; resets `anyFired` | `notify_alerts`: `notifier.send(text)` | "the alerts are sent by email or Telegram" |
| `TheSendFails` | alerts_written → send_failed | guard `alerts = "text"`; `channel' = "configured"`; resets `anyFired` | `cli.py`: `NotificationError` → exit 1 | "the send fails [email or Telegram error]" |
| `Done` | end phases | `UNCHANGED vars` | | "the run ends" |

#### The rules (eleven INVARIANTs, in this order in `.tla` and `.cfg`)

| issue | name | formula | reader's sentence |
| --- | --- | --- | --- |
| (a) | `MisconfiguredChannelStoresNothing` | `channel = "misconfigured" => (phase = "channel_misconfigured" /\ stored = {})` | A misconfigured notifier channel ends the run before any sync, so nothing is stored. |
| (b) | `UnreachableTwsWritesNoMarkOrEvent` | `(phase = "tws_unreachable" => stored = {}) /\ (phase \in {"tws_unreachable", "tws_lost"} => ("holding_marks" \notin stored /\ "events_log" \notin stored /\ ~anyFired))` | When Trader Workstation (TWS) cannot be reached, the run ends: before the snapshot on the first call, and never with a mark or an event written. |
| (c) | `MarkedAfterTheSnapshot` | `"holding_marks" \in stored => ("portfolio_snapshots" \in stored /\ held)` | A holding is marked only after the day's snapshot is stored, and only while it is held. |
| (d) | `UnknownValueFiresNoMarkEvent` | `(valuation = "unknown" => event \notin {"intrinsic_value_crossed_price", "new_red_flag"}) /\ (gates = "unknown" => event \notin {"below_quality_gate", "sector_recalibrated"}) /\ (gates = "without_wacc" => event # "sector_recalibrated")` | An unknown current value never fires a mark event: no intrinsic value cross, new red flag, failed gate or recalibration. |
| (e) | `FirstRunOpensEveryPosition` | `prev = "none" => (event \notin {"position_closed", "currency_changed", "position_size_changed"} /\ (phase = "positions_diffed" => event = "position_opened"))` | On the first run every position fires position opened, and none fires position closed, size changed or currency changed. |
| (f) | `NoPreviousMarkOnlyRedFlags` | `prevMark = "absent" => (event \notin {"intrinsic_value_crossed_price", "below_quality_gate", "sector_recalibrated"} /\ ((phase = "flags_checked" /\ valuation = "red") => event = "new_red_flag"))` | With no previous mark, intrinsic value cross, below quality gate and sector recalibration never fire, while a red flag now does fire. |
| (g) | `ReportedFilingNeverFiresAgain` | `event = "new_filing" => filing = "unreported"` | A filing already in the events log never fires new filing again. |
| (h) | `ConcentrationOnEveryRun` | `phase = "concentration_checked" => (above = (event = "concentration"))` | A holding above 15% of the portfolio fires concentration on every run while it stays above, whatever the previous snapshot held. |
| (i) | `EventsLoggedBeforeAlerts` | `("alerts_md" \in stored /\ anyFired) => "events_log" \in stored` | Every event fired is appended to the events log before alerts.md is written. |
| (j) | `AlertsWrittenSentOnlyWithText` | `(phase \in {"not_sent", "sent", "send_failed"} => "alerts_md" \in stored) /\ (phase \in {"sent", "send_failed"} => (channel = "configured" /\ alerts = "text"))` | alerts.md is always written, and it is sent only when a channel is configured and the file is not blank. |
| (k) | `CorporateActionsFailureNeverStops` | `(flexFailed /\ phase \in EndPhases) => (phase = "tws_lost" \/ {"portfolio_md", "alerts_md"} \subseteq stored)` | A corporate actions failure never stops the run: both reports are still written unless TWS drops afterwards. |

Each rule's `(* Cites: ... *)` names the code from the action table (for (h): `detect_concentration` reads only `curr_positions`; for (k): `run_portfolio`'s `except Exception` around `corporate_actions_fn`).

`portfolio.cfg`: `SPECIFICATION Spec`, then the eleven `INVARIANT <name>` lines.

`portfolio.view.js`: as `screen.view.js`; `colors = { "portfolio-sync": "blue", "portfolio-marks": "purple", "portfolio-mark-events": "orange", "portfolio-events": "teal", "portfolio-alerts": "yellow" }`.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_pipeline_models.py`, after the refresh tests:

```python
_PORTFOLIO_GROUPS = {
    "portfolio-sync",
    "portfolio-marks",
    "portfolio-events",
    "portfolio-mark-events",
    "portfolio-alerts",
}
# Issue #171 rules (a)-(k): checked, or marked broken.
_PORTFOLIO_RULES = {
    "MisconfiguredChannelStoresNothing",
    "UnreachableTwsWritesNoMarkOrEvent",
    "MarkedAfterTheSnapshot",
    "UnknownValueFiresNoMarkEvent",
    "FirstRunOpensEveryPosition",
    "NoPreviousMarkOnlyRedFlags",
    "ReportedFilingNeverFiresAgain",
    "ConcentrationOnEveryRun",
    "EventsLoggedBeforeAlerts",
    "AlertsWrittenSentOnlyWithText",
    "CorporateActionsFailureNeverStops",
}


def test_portfolio_groups() -> None:
    assert "portfolio" in _STEMS
    assert set(_map("portfolio", "groups").values()) == _PORTFOLIO_GROUPS


def test_portfolio_title() -> None:
    assert 'export const title = "portfolio: one holding through bot portfolio";' in _text(
        "portfolio", ".view.js"
    )


def test_portfolio_rules_are_all_present() -> None:
    defs = {name: comments for name, comments, _ in _definitions("portfolio")}
    checked = set(_invariants("portfolio"))
    for rule in _PORTFOLIO_RULES:
        assert rule in defs, f"portfolio.tla does not define {rule}"
        assert rule in checked or _is_broken(defs[rule]), (
            f"{rule} is neither checked nor marked broken"
        )
    assert not checked & {n for n, c in defs.items() if _is_broken(c)}
    assert len(checked) >= 9
```

- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_pipeline_models.py -k portfolio` → FAIL (`portfolio` not in `_STEMS`; `portfolio.view.js` missing).
- [ ] **Step 3: Write** `portfolio.tla`, `portfolio.cfg`, `portfolio.view.js` from the tables above; update the README sentence.
- [ ] **Step 4: Run** `uv run pytest -q tests/unit/test_pipeline_models.py` → PASS (every convention test, now also parametrised over `portfolio`).
- [ ] **Step 5: Run** `uv run pytest -q`, `uv run ruff check . && uv run mypy src`, `python3 docs/pipeline/check.py` → all pass.
- [ ] **Step 6: Commit** `docs(#171): portfolio model`.

### Task 2: TLC in CI (controller, not a subagent)

- [ ] Stopping rule: at most five push/watch rounds; still red after the fifth: comment the stage and the report on #171 and stop with an error.
- [ ] Push; `id=$(gh run list --branch agent/171-portfolio-model --workflow pipeline-diagram --limit 1 --json databaseId --jq '.[0].databaseId')`; `gh run watch "$id" --exit-status || true`; `gh run download "$id" -n pipeline-models -D /tmp/models-<round>`; read `portfolio/report.md`, `portfolio/chart.mmd`, `portfolio/tlc.out`.
- [ ] Green means: `## Rules that hold` lists the eleven rules plus `NoDeadlock` (fewer only when the missing ones are marked broken under the protocol, never fewer than nine); no `breaks`, `Rules not checked` or `TLC stopped`; `chart.mmd` present (under 500 states). A parse error is fixed in the model. A broken rule follows the protocol: replay the path as a pytest against the real code in `tests/unit/test_portfolio_model_replay.py`; model wrong → fix the model, never the rule (the replay test is not committed); code wrong → `bug` issue titled after the rule, `\* broken: #n`, out of the `.cfg`, README table row, replay test committed. Each fix round commits `fix(#171): portfolio model, <what>`.
- [ ] Over 500 states (no `chart.mmd`, no break): the designated cut is `TheGatesAreJudgedWithoutWacc` (fold it into `TheGatesAreJudged` and drop the `"without_wacc"` value and its conjunct in rule (d)); the scratch mirror counts 76 fewer states without it (275). A red round on a parse error and a red round on a broken rule share the same five-round budget.
- [ ] Stopped after the fifth round: the branch keeps its pushed `fix(#171)` commits; an uncommitted replay test is deleted (`git clean` of `tests/unit/test_portfolio_model_replay.py`); the #171 comment names the round, the failing section of the report and the rules still in the `.cfg`.
- [ ] Full suite, lint, `python3 docs/pipeline/check.py` → pass.

## Grilling

- Rounds: 1. The revision moved one reset, added one guard and changed one label. No task was added or removed and no seam changed, so a second round was not needed.
- Questions: 18. Sources:
  - ISSUE, 3: 3 (the parent's plan, decision 6: "groups are the sub-board stems"; the order of independent detectors is not fixed); 10 ("listing at least nine rules"); 17 (decisions 6, 7 and 9 copied into Global Constraints and Task 2).
  - CODE, 9: 2 (`check.sh` loops `for tla in "$DIR"/*.tla`; `check.py` never reads `models/`); 7 (`run_portfolio` calls `sync_trades` outside any `try`; `cli.py` `portfolio` turns `ConnectionError`/`TimeoutError` into exit 1); 8 (`valuator/analysis.py:145-149` raises `LookupError` for a ticker not in `companies`); 9 (`_STEMS` globs `*.tla`; `_definitions`, `_invariants`, `_is_broken`, `_map`, `_text` exist with these shapes); 12 (`test_every_cfg_invariant_has_a_sentence` skips `\* broken:` lines; `_is_broken` reads them); 13 (`_transitions` searches each action's own body from `_definitions` and skips `Done`); 14 (`render_alerts(events)` lists every holding's events, so text without this holding's event is a real case); 16 (`_COLORS` and `test_groups_are_stage_subboards` check `colors`); 1 (the mirror reset `prevMark` before the guard).
  - DOC, 1: 17 (`docs/pipeline/models/README.md`: the modelled-stages sentence and the "Known broken rules" table).
  - NO SOURCE, 5: 4, 5, 6, 11 and 15. All are technical assumptions.
- Assumptions added (see `## Assumptions` and Task 2):
  - 4: the designated cut over 500 states.
  - 5: the closed-holding label.
  - 6: rule (h) restates the detector's guard.
  - 11: parse errors and breaks share the five rounds, and no local parse check exists.
  - 15: two arrows with the same effects.
  - 18: the state left behind after five red rounds.
- Plan corrected:
  - Q1: the `prevMark` reset moves to after the first-run guards, which were vacuous before.
  - Q8: `TheGatesCannotBeJudged` requires `valuation = "unknown"`.
  - Q5: the `concentration_checked` label.
  - State count: 387 → 351.
- Issues opened: none.
