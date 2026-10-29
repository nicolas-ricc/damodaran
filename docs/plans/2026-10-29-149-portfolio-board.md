# Portfolio board (#149) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Draw `docs/pipeline/portfolio.d2`, the board that shows how `bot portfolio` syncs the Interactive Brokers account, marks every holding with the valuator and the screener gates, diffs two snapshots into the twelve typed events, writes `portfolio.md` and `alerts.md`, and optionally sends the alerts. CI renders it to `portfolio.svg`; `pipeline.d2` links it.

**Architecture:** One new d2 board pulling the shared classes with `...@classes`. Top level: the cron, the three external services, the files, a `duckdb` container with the nine tables, the outputs, the command, then five containers in run order (`sync`, `marks`, `events`, `reports`, `notify`), then the edges. Every name from the code is cited by a directive in a d2 line comment. Tests in `tests/unit/test_pipeline_diagram.py` pin required citations, node keys and classes, phrases, threshold directions (evaluated against the detectors at equality), the run-step order (against `run_portfolio`'s source) and the gap notes (each tied to the code fact it reports). Rendering happens only in the `pipeline-diagram` workflow (no d2 locally).

**Tech Stack:** d2 v0.9.0 + TALA (CI only), Python 3 / pytest, `docs/pipeline/check.py` (stdlib).

**Spec:** GitHub issue #149 (child of story #144), its "Inherited decisions" section, and `docs/pipeline/README.md` (directive syntax).

## Global Constraints

- Board file: `docs/pipeline/portfolio.d2`; first line `...@classes`; then `direction: down`; imports no other board; `class:` is a node's first attribute.
- Only the nine classes of `classes.d2`. No new shapes, no styles.
- A note is a child of the node it annotates, label `|md ... |`. A `gap` note is a single-line `|md Gap: ... |`; its directives trail the closing `| {class: gap}` on the same line.
- English; domain words exactly as in `CONTEXT.md` (quality gates, trap detection, sector benchmark, listing currency, ...). Event types are written exactly as their `EventType` values (`position_opened`, `intrinsic_value_crossed_price`, ...).
- Formulas in plain math with Unicode operators (`×`, `÷`, `−`, `≠`, `≤`, `≥`), never function names.
- Every acronym is a key of `_ACRONYMS` or `_ACRONYMS_EXEMPT` and its expansion appears earlier in the board or on the same line. Do not write `NULL`, `IB`, `FS`, `RS`, `SMTP`, `HTTP`, `XML`, `API`, `IV` (spell out: "empty", "Interactive Brokers Gateway", "forward and reverse splits", "web requests", "intrinsic value").
- Directives live in `#` comments trailing the line whose visible text they check, never inside `|md ... |`. A `@const` value must be visible on that same source line (so a multi-line label stays one source line with `\n`). Arguments fully qualified. No `@` starting a word anywhere else. Write "issue 110", not a `#` number.
- Absolute values (`|x|`) only inside double-quoted labels, never inside `|md ... |`.
- Label lines about 70 characters at most, broken with `\n` inside double quotes; never put an acronym right after `\n`.
- Every edge carries a label. Edges are declared at top level, after all nodes, with dotted paths.
- Do not touch `src/`. Never hand-write or edit an SVG or `rendered.sha256`.
- Quality bar: `uv run ruff check . && uv run mypy src && uv run pytest -q` green, and the `pipeline-diagram` workflow green on the head commit.
- Commits: board work `docs(#144): ...` (story convention); pipeline stages `test(#149)`, `fix(#149)`, `chore(#149)`.

## Review Focus

1. **A boundary drawn on the wrong side** (`> 10%` and `> 15%` exclusive; `> 100 bps` exclusive; equality is not a cross). Pinned by `test_portfolio_directions_match_code`: each detector evaluated exactly at its threshold.
2. **A thirteenth event type added in the code without the board.** `@enum bot.portfolio.events.EventType` + `test_portfolio_every_event_type_is_a_decision`.
3. **A run step reordered in `run_portfolio`** (e.g. marks after events: the derived events would diff stale marks). `test_portfolio_run_steps_match_code` reads the call order from the source.
4. **A gap that stopped being true** (Flex verified, ADR 0005 implemented, mergers become events, filings start triggering analyze). Each gap has a `*_is_current` test, like `test_analyze_ipo_date_gap_is_current`.
5. **A d2 syntax error only CI sees.** Copy syntax only from `analyze.d2` / `screen.d2`, which render; the controller reads `--log-failed`.

---

## Acronyms (test machinery change, written in stage 3)

`_ACRONYM_RE` matches slash tokens (`P/E`) as whole tokens but not `P&L` (two one-letter words). Change: the whole-token set becomes every `_ACRONYMS` key containing `/` or `&` (rename `_SLASHED` → `_SYMBOLIC`), and `_token_re` uses the lookarounds `(?<![\w/&])` / `(?![\w/&])` for those keys. Add `"P&L": "profit and loss"` and `"UTC": "Coordinated Universal Time"`. No existing board writes `P&L` or `UTC`, so nothing else changes.

## Node map (all tasks use these exact keys)

Source order (the acronym test reads top to bottom): `daily`, externals, files, `duckdb`, outputs, `cli`, the five containers, then edges.

**Top level**
- `daily` (cron) `# @file scripts/daily.sh @file scripts/install_cron.sh`: `"scripts/daily.sh, weekdays 09:00 (installed by scripts/install_cron.sh)\nprice rounds, then the foreign exchange (FX) refresh,\nthen bot portfolio only when both succeeded"`.
- Externals (class `external`):
  - `tws` `# @symbol bot.ingest.ibkr.IbkrClient`: `"Interactive Brokers (IBKR) Trader Workstation (TWS)\nor the Interactive Brokers Gateway, read-only socket through ib_async\nBOT_IBKR_HOST, BOT_IBKR_PORT, BOT_IBKR_CLIENT_ID (architecture decision record (ADR) 0004)"`.
  - `flex` `# @symbol bot.ingest.ibkr_flex.import_corporate_actions`: `"IBKR Flex Web Service: an Activity Flex Query,\ntwo web requests (send the request, then poll for the statement)"`.
  - `channels`: `"email or Telegram"`.
- Files (class `file`): `preset` `"config/presets/damodaran_value.yaml: its quality gates and trap detection gate every holding"` `# @file config/presets/damodaran_value.yaml`; `override_yaml` `"config/assumptions/TICKER.yaml, manual overrides when valuing a holding"` `# @file config/assumptions @symbol bot.valuator.assumptions.conventional_override_path`; `portfolio_template` `"src/bot/reporting/templates/portfolio.md.j2"` and `alerts_template` `"src/bot/reporting/templates/alerts.md.j2"`, each with its `@file`.
- `duckdb` container `"DuckDB (bot.duckdb)"`, one `store` child per table, each `# @table <name>`: `portfolio_snapshots`, `cash_balances`, `trades`, `corporate_actions`, `holding_marks`, `events_log`, `filings_log`, `prices_daily`, `currencies`. (Marks also read `companies`, `financials_annual`, `damodaran_industry` through the screener inputs; they are named in the `marks.gates` label, not drawn as stores — the issue fixes the nine.)
- Outputs (class `output`): `portfolio_md` `"reports/YYYY-MM-DD/portfolio.md"`, `alerts_md` `"reports/YYYY-MM-DD/alerts.md"`, `message` `"alert message"`.
- `cli` (step) `# @symbol bot.cli.portfolio`: `"bot portfolio [--history] [--concentration]\nsync the account, mark every holding, diff two snapshots into events,\nwrite two reports, send the alerts"`. Note `cli.exits` (md list): notifier misconfigured: exit code 2, before anything else; preset `damodaran_value.yaml` missing: exit code 2; TWS unreachable (connection error or timeout): exit code 1; alerts not sent: exit code 1. Note `cli.gates` (md): the gates are the preset's quality gates plus its trap detection rules.

**`sync`** `"1–3. sync the account"` (`# @symbol bot.portfolio.command.run_portfolio`)
- `snapshot` (step) `# @symbol bot.portfolio.sync.sync_portfolio`: `"1. snapshot: every managed account's open positions and cash by currency\nidempotent per (snapshot_date, account): delete that day's rows of the account,\nthen insert into portfolio_snapshots and cash_balances;\nother accounts' rows of the day untouched"`.
- `value` (step) `# @symbol bot.portfolio.sync.value_positions`: `"market value = quantity × latest close\nlatest close = newest prices_daily close on or before the snapshot date\nin the position's currency; listing currency differs:\nclose × rate_to_usd(listing currency) ÷ rate_to_usd(position currency),\nnearest prior rates from currencies\nno close, close ≤ 0, or a missing or non-positive rate: market value empty (unpriced)"`. Gap `value.adr_0005`: `Gap: ADR 0005 (store money as reported, convert at the point of calculation) is not implemented; the universe is US-only and every holding trades in USD, so no real data exercises the cross-currency branch today.` trailing `# @file docs/adr/0005-currency-handling-and-valuation-currency.md`.
- `corporate_actions` (step) `# @symbol bot.ingest.ibkr_flex.import_corporate_actions`: `"2. corporate actions, best effort\nonly when BOT_IBKR_FLEX_TOKEN and BOT_IBKR_FLEX_QUERY_ID are set\ndividend cash transactions → dividend, action_id ct:<id>\nforward and reverse splits → split; any other type kept lower-cased,\naction_id ca:<id>\ninserted de-duplicated on action_id\nany failure: a warning, the run goes on"`. Gap `corporate_actions.unverified`: `Gap: the Flex importer was written from IBKR's documentation against a synthetic fixture and is not yet verified against a real pull (issue 110).` trailing `# @symbol bot.ingest.ibkr_flex`.
- `trades` (step) `# @symbol bot.portfolio.trades.sync_trades`: `"3. trades, per account\nwatermark = newest executed_at stored for the account\nonly fills newer than the watermark are fetched\ninserted de-duplicated on exec_id\ntimestamps stored as naive Coordinated Universal Time (UTC)"`.

**`marks`** `"4a. mark every holding"` (`# @symbol bot.portfolio.marks.mark_holdings`)
- `held` (step): `"holdings = tickers whose summed quantity ≠ 0 on the snapshot date"`.
- `valuation` (step) `# @symbol bot.valuator.analysis.analyze`: `"valuation: the analyze stage with config/assumptions/TICKER.yaml when present\n→ intrinsic value per share, latest close, red narrative flags\ncannot value: all three unknown"`.
- `gates` (step) `# @symbol bot.screener.engine.load_holding_inputs`: `"gates: screener inputs built as the screen builds them\n(companies, financials_annual, prices_daily, damodaran_industry)\nfailed gates = the gates that fail; a skipped rule does not count\nsector weighted average cost of capital (WACC) from the sector benchmark\nticker not in companies: failed gates and sector WACC unknown"`.
- `persist` (step): `"holding_marks: one row per holding; the snapshot date's rows deleted, then inserted\nunknown values stored empty"`. Note `persist.unknowns` (md): An unknown current value never fires an event. An unknown previous red-flag set counts as empty, so standing red flags re-fire after a day without a valuation. Unknown previous gates or sector WACC fire nothing.

**`events`** `"4b. diff two snapshots into events"` (`# @symbol bot.portfolio.events.compute_events @enum bot.portfolio.events.EventType`)
- `window` (step): `"previous snapshot = newest snapshot_date before today; none on the first run\npositions summed per ticker across accounts\nderived events diff the two persisted marks, never a recomputation"`.
- Twelve `decision`s, key = the `EventType` value, label's first line = the value:
  - `position_opened` `# @symbol bot.portfolio.events.detect_position_changes`: `"position_opened\nquantity ≠ 0 now, absent or 0 in the previous snapshot\nfirst run: every position"`.
  - `position_closed`: `"position_closed\nquantity ≠ 0 in the previous snapshot, absent or 0 now\n(an account that returns no positions closes all of its holdings)"`.
  - `position_size_changed` `# @const bot.portfolio.events.DEFAULT_SIZE_CHANGE_THRESHOLD`: `"position_size_changed: held in both and |Δquantity ÷ |previous quantity|| > 10%\nexactly 10%: no event"`.
  - `currency_changed` `# @symbol bot.portfolio.events.detect_currency_changes`: `"currency_changed\nthe position's listing currency differs from the previous snapshot's, both known\nnot on the first run"`.
  - `dividend` `# @symbol bot.portfolio.events.detect_corporate_action_events`: `"dividend\na corporate_actions row of type dividend for a holding,\neffective after the previous snapshot, on or before this one"`.
  - `split`: `"split\nthe same rule for type split"`. Gap `split.other_actions`: `Gap: spec §8.3 lists dividend, split and corporate action; mergers, spin-offs and every other corporate action type are stored in corporate_actions but fire no event.`
  - `new_filing` `# @symbol bot.portfolio.events.detect_new_filings`: `"new_filing\na filings_log row of a holding, filed on or before this snapshot,\nfiled after the previous snapshot or ingested on or after its date,\nnot reported before: (ticker, filing type, filing date) absent from events_log\nfirst run: every unreported filing"`. Gap `new_filing.no_auto_analyze`: `Gap: spec §8.3 says a new filing auto-runs bot analyze and leaves an updated report. Verified against run_portfolio and the portfolio command: nothing reacts to new_filing; every holding is re-valued on every run by mark_holdings, and no analysis report is written.`
  - `intrinsic_value_crossed_price` `# @symbol bot.portfolio.events.detect_intrinsic_value_cross`: `"intrinsic_value_crossed_price\n(intrinsic value − price) < 0 before and > 0 now, or > 0 before and < 0 now\nequality is not a cross\nno previous mark, or any of the four values unknown: nothing"`.
  - `new_red_flag` `# @symbol bot.portfolio.events.detect_new_red_flags`: `"new_red_flag: one per narrative flag red now and not red in the previous mark\nno previous mark or unknown previous flags: counts as none red\nunknown flags now: nothing"`.
  - `below_quality_gate` `# @symbol bot.portfolio.events.detect_below_quality_gate`: `"below_quality_gate: one per gate failing now and not failing before\nfailed gates unknown on either side, or no previous mark: nothing"`.
  - `sector_recalibrated` `# @symbol bot.portfolio.events.detect_sector_recalibration @const bot.portfolio.events.DEFAULT_WACC_RECALIBRATION_BPS`: `"sector_recalibrated: |sector WACC now − sector WACC before| > 100 bps\nexactly 100 bps: no event; either unknown: nothing"`.
  - `concentration` `# @symbol bot.portfolio.events.detect_concentration @const bot.portfolio.events.DEFAULT_CONCENTRATION_THRESHOLD`: `"concentration: market value ÷ total market value > 15%, exactly 15%: no event\ntotal over positions with a market value > 0\nnot a diff: fires on every run while above"`.
- `not_events` (note, md): Not events, by design (spec §8.3): price moves and news.
- `persist` (step) `# @symbol bot.portfolio.events.persist_events`: `"append every event to events_log:\nevent_type, ticker, previous and current snapshot dates, details"`. Note `persist.reruns` (md): A second run on the same day diffs against the same previous snapshot, so it appends the same events again and sends them again; only new_filing is checked against events_log.

**`reports`** `"5. reports, written to reports/YYYY-MM-DD/"`
- `portfolio` (step) `# @symbol bot.portfolio.report.build_report @symbol bot.portfolio.report.render_portfolio @const bot.portfolio.events.DEFAULT_CONCENTRATION_THRESHOLD`: `"portfolio.md, the full state: positions, profit and loss (P&L), concentration, suggested reviews\nP&L = market value − quantity × average cost; unpriced: P&L unknown\nconcentration weight = market value ÷ total of positions with a market value > 0; flagged above 15%\nsuggested review: each flagged position, consider trimming\n--history: P&L per snapshot; --concentration: the breakdown table"`. (The 15% sits on the same source line as the `@const`.)
- `alerts` (step) `# @symbol bot.portfolio.report.render_alerts`: `"alerts.md, today's events only: type, ticker, details\nalways written; an empty file when there are no events"`.

**`notify`** `"6. notify (after the run)"`
- `channel` (decision) `# @symbol bot.notifier.build_notifier`: `"which channel? BOT_NOTIFIER\nnone: nothing is sent\nemail: needs BOT_SMTP_HOST, BOT_SMTP_FROM, BOT_SMTP_TO\ntelegram: needs BOT_TELEGRAM_BOT_TOKEN, BOT_TELEGRAM_CHAT_ID\na missing setting, or a password in cleartext: exit code 2, before the sync"`.
- `send` (decision) `# @symbol bot.notifier.notify_alerts`: `"send alerts.md?\nno channel, or a blank file: not sent\nelse its text is sent; a send failure: exit code 1"`.

**Edges (all labelled), at least:**
- `daily -> cli` ("bot portfolio, after prices and FX succeeded; TWS not running: exit code 1, logged to .cache/daily.log"); `cli -> sync.snapshot` ("1. run_portfolio"); `preset -> marks.gates` ("quality gates and trap detection"); `override_yaml -> marks.valuation` ("override of the holding").
- Sync: `tws -> sync.snapshot` ("accounts, positions, cash"); `duckdb.prices_daily -> sync.value` ("latest close and its currency"); `duckdb.currencies -> sync.value` ("rates to USD"); `sync.snapshot -> sync.value` ("positions"); `sync.value -> duckdb.portfolio_snapshots` ("positions with market value"); `sync.snapshot -> duckdb.cash_balances` ("cash by currency"); `flex -> sync.corporate_actions` ("statement"); `sync.corporate_actions -> duckdb.corporate_actions` ("new actions"); `tws -> sync.trades` ("fills newer than the watermark"); `duckdb.trades -> sync.trades` ("watermark"); `sync.trades -> duckdb.trades` ("new fills"); `sync.snapshot -> sync.corporate_actions` ("2."), `sync.corporate_actions -> sync.trades` ("3."), `sync.trades -> marks` ("4.").
- Marks: `duckdb.portfolio_snapshots -> marks.held` ("snapshot rows"); `marks.held -> marks.valuation` / `marks.held -> marks.gates` ("each holding"); `marks.valuation -> marks.persist` ("intrinsic value, price, red flags"); `marks.gates -> marks.persist` ("failed gates, sector WACC"); `marks.persist -> duckdb.holding_marks` ("marks of the day").
- Events: `marks -> events.window` ("marks persisted"); `duckdb.portfolio_snapshots -> events.position_opened` / `events.position_closed` / `events.position_size_changed` / `events.currency_changed` / `events.concentration` ("both snapshots" / "this snapshot"); `duckdb.corporate_actions -> events.dividend` / `events.split` ("actions in the window"); `duckdb.filings_log -> events.new_filing` ("filings of holdings"); `duckdb.events_log -> events.new_filing` ("filings already reported"); `duckdb.holding_marks -> events.intrinsic_value_crossed_price` / `events.new_red_flag` / `events.below_quality_gate` / `events.sector_recalibrated` ("previous and current marks"); each of the twelve decisions `-> events.persist` ("fires"); `events.persist -> duckdb.events_log` ("new events").
- Reports and notify: `events -> reports.alerts` ("today's events"); `duckdb.portfolio_snapshots -> reports.portfolio` ("positions and history"); `duckdb.cash_balances -> reports.portfolio` ("cash"); `portfolio_template -> reports.portfolio` ("layout"); `alerts_template -> reports.alerts` ("layout"); `reports.portfolio -> portfolio_md` ("markdown file"); `reports.alerts -> alerts_md` ("markdown file"); `alerts_md -> notify.send` ("its text"); `cli -> notify.channel` ("first, before the sync"); `notify.channel -> notify.send` ("channel"); `notify.send -> channels` ("non-blank alerts"); `channels -> message` ("delivered").

**`pipeline.d2` changes:** add `link: "./portfolio.svg"` as the `portfolio` node's second attribute (after `class: step`); the edge `portfolio -> duckdb.corporate_actions` reads `"splits, mergers, spin-offs"`, which omits the dividends the Flex importer stores: change it to `"dividends, splits and other corporate actions"`.

---

### Task 1: Command, externals, files, stores, outputs, sync and marks

**Files:**
- Create: `docs/pipeline/portfolio.d2`
- Test: `tests/unit/test_pipeline_diagram.py` (written and committed in stage 3; listed here for ownership).

**Interfaces:**
- Consumes (tests, from stage 3): `_portfolio() -> str`, `_portfolio_block(key: str) -> str`, `_PORTFOLIO_NODES: list[tuple[str, str]]`, `_PORTFOLIO_TEXT: dict[str, list[str]]`, `_PORTFOLIO_GAPS: dict[str, list[str]]`, plus the existing `_check()`, `_block()`, `_node_class()`, `_edge_line()`.
- Produces: the top-level nodes, `duckdb`, outputs, `cli`, `sync.*`, `marks.*` keys of the node map.

- [ ] **Step 1:** Run `uv run pytest -q tests/unit/test_pipeline_diagram.py` — Expected: the stage-3 portfolio tests FAIL (no `portfolio.d2`); everything else PASS.
- [ ] **Step 2:** Write `portfolio.d2`: `...@classes`, `direction: down`, top level, `duckdb`, outputs, `cli`, `sync`, `marks`, and the edges among them.
- [ ] **Step 3:** Run the file — Expected: PASS for `test_acronyms_are_expanded`, `test_every_directive_is_valid`, `test_every_edge_is_labelled`, `test_gap_notes_start_with_gap`, and every parametrized case keyed under the top level, `sync.*`, `marks.*`, the ADR 0005 and Flex gap tests; the rest still FAIL.
- [ ] **Step 4: Commit** `docs(#144): portfolio board — command, sync and marks`.

### Task 2: Events

**Files:** Modify `docs/pipeline/portfolio.d2`.

- [ ] **Step 1:** Run `uv run pytest -q tests/unit/test_pipeline_diagram.py -k "portfolio and (event or direction or gap)"` — Expected: FAIL.
- [ ] **Step 2:** Add the `events` container (window, twelve decisions, two gaps, `not_events` note, persist) and its edges.
- [ ] **Step 3:** Run the file — Expected: the Task 1 PASS set plus every case keyed under `events.*`, `test_portfolio_every_event_type_is_a_decision`, `test_portfolio_directions_match_code`, the merger and filing gap tests.
- [ ] **Step 4: Commit** `docs(#144): portfolio board — the twelve events`.

### Task 3: Reports, notify and the overview link

**Files:** Modify `docs/pipeline/portfolio.d2`, `docs/pipeline/pipeline.d2` (link + corporate-actions edge wording).

- [ ] **Step 1:** Run `-k "portfolio and (report or notify or link or required or edges or steps)"` — Expected: FAIL.
- [ ] **Step 2:** Add `reports`, `notify`, the remaining edges, the link and the edge wording.
- [ ] **Step 3:** Run the file — every test PASS except `test_check_py_exits_zero` and `test_each_board_has_a_rendered_svg` (no `portfolio.svg` yet, so the link target is also missing).
- [ ] **Step 4: Commit** `docs(#144): portfolio board — reports and notify, linked from the overview`.
- [ ] **Step 5:** Mutation drill on the committed board: edit `> 15%` on `events.concentration` to `> 20%`, run `-k every_directive` — Expected: FAIL naming `DEFAULT_CONCENTRATION_THRESHOLD`; restore with `git checkout docs/pipeline/portfolio.d2`.

### Task 4: Render through CI and commit the render (controller, needs push)

- [ ] Push; find the `pipeline-diagram` run whose `headSha` equals `git rev-parse HEAD`; `gh run watch <id> --exit-status`.
- [ ] Build failure: `gh run view <id> --log-failed`, fix the `.d2` line d2 names, push again.
- [ ] Build green: `gh run download <id> -n pipeline-render -D /tmp/render`; copy `*.svg` and `rendered.sha256` into `docs/pipeline/`; look at `/tmp/render/portfolio.png`; fix unreadable layout in the source (then re-render); commit `docs(#144): render portfolio and the other boards`; push; the run on that commit must be fully green.
- [ ] `python3 docs/pipeline/check.py` exits 0; `uv run ruff check . && uv run mypy src && uv run pytest -q` green.

## Tests written in stage 3 (all in `tests/unit/test_pipeline_diagram.py`)

- Acronym machinery change (see "Acronyms") and the two new `_ACRONYMS` entries.
- `_REQUIRED_*["portfolio"]`: symbols (the 25 of the issue), tables (the nine), files (`scripts/daily.sh`, `config/presets/damodaran_value.yaml`), consts (the three `DEFAULT_*`), enums (`EventType`).
- `test_portfolio_nodes(key, cls)` over `_PORTFOLIO_NODES` (every key of the node map with its class, gaps and notes included).
- `test_portfolio_text(key)` over `_PORTFOLIO_TEXT`: `sync.snapshot`: `(snapshot_date, account)`, `delete`, `then insert`; `sync.value`: `market value = quantity × latest close`, `on or before the snapshot date`, `close × rate_to_usd(listing currency) ÷ rate_to_usd(position currency)`, `close ≤ 0`, `unpriced`; `sync.corporate_actions`: `BOT_IBKR_FLEX_TOKEN`, `BOT_IBKR_FLEX_QUERY_ID`, `ct:<id>`, `ca:<id>`, `de-duplicated on action_id`, `warning`; `sync.trades`: `newest executed_at`, `de-duplicated on exec_id`, `naive Coordinated Universal Time (UTC)`; `marks.held`: `≠ 0`; `marks.valuation`: `config/assumptions/TICKER.yaml`, `red narrative flags`, `unknown`; `marks.gates`: `skipped rule does not count`, `sector WACC`; `marks.persist.unknowns`: `never fires`, `counts as empty`; the twelve events' rules (`> 10%`, `exactly 10%: no event`, `> 15%`, `exactly 15%: no event`, `> 100 bps`, `equality is not a cross`, `not red in the previous mark`, `failing now and not failing before`, `after the previous snapshot, on or before this one`, `absent from events_log`, `not on the first run`, `fires on every run while above`); `events.not_events`: `price moves`, `news`; `reports.portfolio`: `P&L = market value − quantity × average cost`, `suggested review`, `--history`, `--concentration`; `reports.alerts`: `always written`, `empty`; `notify.channel`: `BOT_NOTIFIER`, `exit code 2`; `notify.send`: `blank`, `exit code 1`; `cli.exits`: `exit code 2`, `exit code 1`; `daily`: `only when both succeeded`, `09:00`; `events.position_closed`: `returns no positions`; `events.window`: `per ticker across accounts`; `events.persist.reruns`: `same events again`.
- `test_portfolio_every_event_type_is_a_decision`: for each `EventType` member, `events.<value>` is a `decision` and its block's first line contains the value; and no other `decision` sits in `events`.
- `test_portfolio_directions_match_code` (parametrized `(node, phrase, op, fires)`): each detector exactly at its threshold, thresholds passed explicitly as exact binary fractions when the default is not exact: size change (quantity 2 → 3 with `size_change_threshold=0.5`), `>`; concentration (market values 1 and 3, weight 0.25 with `threshold=0.25`), `>`; sector recalibration (0.5 → 0.75 with `threshold=0.25`), `>`; intrinsic value cross (gap −1 before, 0 now: no event), phrase `equality is not a cross`. Asserts the phrase is in the node's block and `fires() == (op in "≤≥")`; the equality case expects no event. A companion assertion checks each detector's default threshold *is* the module constant (`inspect.signature(...).parameters[...].default`), so the explicit thresholds test the same comparison.
- `test_portfolio_run_steps_match_code`: in `inspect.getsource(run_portfolio)` the calls `sync_portfolio(`, `corporate_actions_fn(conn)`, `sync_trades(`, `mark_holdings(`, `compute_events(`, `persist_events(`, `build_report(` appear in that order; on the board, the first lines of `sync.snapshot`, `sync.corporate_actions`, `sync.trades` start `1.`, `2.`, `3.`, and the container labels of `marks`, `events`, `reports` start `4a.`, `4b.`, `5.`.
- `_PORTFOLIO_GAPS` / `test_portfolio_gap_notes`: `sync.value.adr_0005`: `ADR 0005`, `not implemented`; `sync.corporate_actions.unverified`: `not yet verified against a real pull`, `issue 110`; `events.split.other_actions`: `mergers`, `fire no event`; `events.new_filing.no_auto_analyze`: `Verified`, `run_portfolio`, `mark_holdings`, `no analysis report`.
- `test_portfolio_adr_0005_gap_is_current`: ADR 0005's `## Status` section (whitespace collapsed) contains `Not implemented` exactly when the gap exists.
- `test_portfolio_flex_gap_is_current`: `bot.ingest.ibkr_flex.__doc__` with whitespace collapsed (the phrase wraps a line today) contains `not yet verified against a real pull` exactly when the gap exists.
- `test_portfolio_other_actions_gap_is_current`: positive control first — `detect_corporate_action_events([("T", "dividend", {})], snapshot_date=d, prev_date=None)` returns one `dividend` event — then `[("T", "merger", {})]` returns `[]` exactly when the gap exists.
- `test_portfolio_cli_order_matches_code`: in `inspect.getsource(bot.cli.portfolio)`, `build_notifier(` precedes `preset_path.exists()`, which precedes `run_portfolio(`, which precedes `notify_alerts(`; the source holds `typer.Exit(code=2)` and `typer.Exit(code=1)`. (Pins `cli.exits` order and the "6. notify after the run" placement.)
- `test_portfolio_filing_auto_analyze_gap_is_current`: neither `inspect.getsource(bot.cli.portfolio)` nor `inspect.getsource(run_portfolio)` mentions `NEW_FILING` or `new_filing` exactly when the gap exists.
- `test_portfolio_flow_edges`: `daily -> cli`, `tws -> sync.snapshot`, `flex -> sync.corporate_actions`, `sync.value -> duckdb.portfolio_snapshots`, `marks.persist -> duckdb.holding_marks`, `duckdb.holding_marks -> events.intrinsic_value_crossed_price`, `events.persist -> duckdb.events_log`, `reports.portfolio -> portfolio_md`, `reports.alerts -> alerts_md`, `notify.send -> channels` exist.
- `test_portfolio_daily_runs_after_prices_and_fx`: in `scripts/daily.sh` the line `((worst == 0)) || exit "$worst"` precedes `uv run bot portfolio`.
- `test_pipeline_links_the_portfolio_board`: `_block(_overview(), "portfolio")` has a line `link: "./portfolio.svg"`.

## Acceptance criteria → tasks

- AC1 (SVG rendered with d2 v0.9.0 + TALA, workflow green, link, hash): Task 3 link + `test_pipeline_links_the_portfolio_board`; Task 4.
- AC2 (twelve event types as decisions with rule, threshold and boundaries): Task 2; `test_portfolio_every_event_type_is_a_decision`, `test_portfolio_directions_match_code`, `_PORTFOLIO_TEXT`.
- AC3 (five run steps, idempotency and de-duplication, market-value formula, marks' unknown-handling): Tasks 1 and 3; `test_portfolio_run_steps_match_code`, `_PORTFOLIO_TEXT`.
- AC4 (gap notes, filing finding verified): Tasks 1 and 2; `test_portfolio_gap_notes` and the four `*_is_current` tests.
- AC5 (citations, `_REQUIRED_*["portfolio"]`, check.py 0, acronyms P&L and UTC, quality bar): `test_required_citations_present`, `test_every_directive_is_valid`, `test_check_py_exits_zero`, `test_acronyms_are_expanded`; Task 4 last step.

## Manual verification (goes in the PR)

- Open `portfolio.svg` and, for each of the twelve event types, point at the rule that fires it.

## Assumptions

- **`P&L` is made visible to the acronym test** the way `P/E` was in #148, instead of a dead dict entry.
- **`config/assumptions/<TICKER>.yaml` is cited as `@file config/assumptions`** plus `@symbol conventional_override_path`, as on the analyze board.
- **The tables the screener inputs read for the gates** (`companies`, `financials_annual`, `damodaran_industry`) are named in a label, not drawn: the issue fixes the nine `store` nodes.
- **The `pipeline.d2` corporate-actions edge wording is corrected** (it omits dividends); one label, inside this issue's board's subject.
- **The stage-3 `test(#149): evals` commit is red on purpose**, and intermediate commits are red until the render lands; only the head commit must be green.
- **"Five run steps" are `run_portfolio`'s numbered steps 1–5** (its docstring and comments, `command.py`); the board numbers them `1.`, `2.`, `3.`, `4a.` (marks), `4b.` (events), `5.` because step 4 does both. Notify (`6.`) is in `bot.cli.portfolio`, after `run_portfolio` returns.
- **Same-day re-runs and empty broker responses are drawn as notes**, not gaps: no spec line says otherwise, so they are facts of the code, not discrepancies.
- **Every SVG in the artifact is copied**, including unchanged boards: the artifact renders every board and `rendered.sha256` covers all sources.

## Grilling

- Rounds: 1 (the revision adds one test, a positive control, three notes and four label phrases; no task, seam or file changed, so no second round).
- Questions: 18. Sources: CODE 17, ISSUE 0, DOC 1, NO SOURCE 0 (two answers also recorded as technical assumptions for clarity).
  - Q1 CODE `src/bot/portfolio/events.py:131,382,417`: thresholds are parameters `size_change_threshold`, `threshold`, `threshold`, defaulting to the module constants; no `src/` change needed.
  - Q2 CODE `events.py:48-53` values 0.10, 0.15, 0.01; `docs/pipeline/check.py:148-164` `renderings()` gives `10%`, `15%`, `100 bps`.
  - Q3 Pipeline stage 3 (`test(#149): evals`) precedes Task 1; `_portfolio()` returns `""` via `_boards().get`, `_portfolio_block` asserts per test; parametrize lists are static, so collection never crashes (same pattern as `_analyze()`, `tests/unit/test_pipeline_diagram.py:1060-1067`).
  - Q4 CODE `check.py` resolves modules through `codemap.escanear()` (`indice()`, lines 174-180); `refresh.d2` already cites modules (`bot.ingest.stooq`). The 25 required symbols are the issue's list; extras (`bot.valuator.analysis.analyze`, `conventional_override_path`, the module `bot.ingest.ibkr_flex`) are allowed (`test_required_citations_present` checks required − cited).
  - Q5 CODE `events.py:217-248`: the detector is pure, window filtering is in `_load_corporate_actions` (`events.py:516-545`); a dividend tuple fires with `prev_date=None` → **added** positive control.
  - Q6 CODE `src/bot/portfolio/report.py` `render_alerts` returns `""` when `events` is empty; `src/bot/notifier/__init__.py` `notify_alerts` skips a blank file.
  - Q7 CODE `src/bot/cli.py:576-622`: `build_notifier` → Exit 2, preset missing → Exit 2, `ConnectionError`/`TimeoutError` → Exit 1, `NotificationError` → Exit 1 → **added** `test_portfolio_cli_order_matches_code`.
  - Q8 CODE `command.py` `_previous_snapshot_date` (`< before`), `compute_events` recomputes, `persist_events` appends; only `detect_new_filings` reads `events_log` → **added** note `events.persist.reruns`.
  - Q9 CODE `sync.py` `sync_portfolio` has no guard; `detect_position_changes` treats an absent ticker as closed → **added** to `events.position_closed`.
  - Q10 CODE `test_pipeline_diagram.py:307-350`: FX, IBKR, TWS, ADR, WACC in `_ACRONYMS`; USD, YAML, TICKER, YYYY, MM, DD exempt; `BOT_IBKR_HOST` is one `\w` run, so `\b[A-Z][A-Z0-9]+\b` never matches inside it.
  - Q11 CODE `src/bot/storage/schema.sql:40-49`: `rate_to_usd` is the `currencies` column, not a function; kept.
  - Q12 CODE `report.py:30-31,247` imports and defaults to `DEFAULT_CONCENTRATION_THRESHOLD`; `report.py` `_concentration` and `events.py` `detect_concentration` both keep `market_value > 0` → wording aligned.
  - Q13 CODE `scripts/install_cron.sh:28` (`0 9  * * 1-5`) → cited; `scripts/daily.sh` comment calls a TWS-down run expected but nothing special-cases it → edge now says "exit code 1, logged to .cache/daily.log".
  - Q14 CODE `command.py` docstring steps 1–5; notify in `cli.py:618-624` → assumption recorded.
  - Q15 DOC `docs/adr/0005-...md:5` "Not implemented."; CODE `src/bot/ingest/ibkr_flex.py:10-11` the phrase wraps → tests collapse whitespace.
  - Q16 CODE `command.py` step 2: `corporate_actions_fn(conn)` inside a `try`; a substring search is unaffected; a changed call form fails the test loudly, as intended.
  - Q17 CODE `events.py` `_load_positions` groups by ticker; `marks.py` `_held_tickers` likewise → **added** to `events.window`.
  - Q18 CODE no test pins the old overview label (grep `spin-offs` in `tests/`: none); the inherited decision "the diagram shows what the code does" covers the correction; recorded under Assumptions.
- Assumptions added: five run steps numbering (Q14); re-runs and empty responses as notes (Q8, Q9).
- Issues opened: none.
- Result: ok.
