# Portfolio sub-boards and the final audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Five d2 sub-boards (`portfolio-sync`, `portfolio-marks`, `portfolio-mark-events`, `portfolio-events`, `portfolio-alerts`) draw the checked portfolio statechart one level below `portfolio.d2`, so a reader who clicks a step on `portfolio.svg` follows one holding through it; then the story's final audit locks every stage to its model and sub-boards and brings the READMEs and `CONTEXT.md` to the final state.

**Architecture:** Each sub-board is a flat d2 board. Its nodes are the model states of one `groups` value of `docs/pipeline/models/portfolio.view.js`, the neighbouring states the flow enters from or leaves to, three fixed nodes (`objective`, `back`, `out`), and the stores, files, services and outputs at the edge of the flow. Its edges are the model steps, labelled with the view's `steps` text, with the how on further lines. The generic tests from #164/#166/#168/#170 already enforce the conventions; this issue registers `portfolio`, adds portfolio-specific citations and phrases, and locks `_SUBBOARDED` to the five stages. d2 renders in CI only.

**Tech Stack:** d2 v0.9.0 + TALA (CI only), TLC (CI only), pytest, `docs/pipeline/check.py`.

**Spec:** issue #172 (its body, including "Sub-board conventions" and "Final audit of the story"). Parent story #161, plan comment decisions 2 to 9. Worked examples: `docs/pipeline/analyze-*.d2`, `docs/pipeline/screen-ranking.d2` and `docs/plans/2026-10-31-170-analyze-subboards.md` (its Global Constraints and assumptions A1 to A5 apply here unchanged).

## Global Constraints

- New files: `docs/pipeline/portfolio-sync.d2`, `portfolio-marks.d2`, `portfolio-mark-events.d2`, `portfolio-events.d2`, `portfolio-alerts.d2`. Their `.svg` files and `rendered.sha256` come only from the CI artifact `pipeline-render`; never edit an SVG or the hash by hand.
- Every sub-board starts with `...@classes`, a blank line, `direction: down`. `class:` is a node's first attribute. Node keys are lower-case. Expand every acronym at its first use on each board, on that line or before it in file order (nodes before edges): TWS, IBKR, WACC, P&L, UTC, ADR as they appear. No all-caps token outside `_ACRONYMS` / `_ACRONYMS_EXEMPT` (USD, YYYY, MM, DD, TICKER are exempt); environment variable names (`BOT_IBKR_FLEX_TOKEN`, `BOT_NOTIFIER`) are fine only if `portfolio.d2` already shows them under the same test.
- Every number other than 0, 1 and 100 on a node or edge label is cited by `@const`/`@param` on that source line; counts are words; exit code 2 is written "exit code two" (decision 1).
- At most 24 edges per sub-board; every edge is one line `a -> b: "label"`.
- A node that is a model state has that state's `states` label as its exact first line. An edge that is a model step has that step's `steps` label as its exact first line and joins the two states the `.tla` action joins.
- A state is `decision` when two or more of its model steps carry a `[condition]`, else `step`; this holds for neighbours too. Every edge leaving a decision has a `[...]`; a model label without one gets the condition on its second line.
- Every step and decision node has a directive on its line or the line before. A neighbour or terminal `step` node with no incoming (outgoing) edge carries `# No incoming edge: the flow enters from portfolio-<sub>` (`# No outgoing edge: ...`) as a trailing comment.
- No `#`, `{`, `}` or `"` inside a quoted label. Write `×`, `÷`, `−`, `≤`, `≥`, `Δ` as on `portfolio.d2`.
- `portfolio.d2` gains `link:` lines only (decision 6). `pipeline.d2` does not change. No file under `src/` changes. `portfolio.tla` and `portfolio.cfg` do not change.
- Formulas, thresholds, names and paths are copied from the code and cited. `portfolio.d2` carries all of them with their directives and is pinned by `_PORTFOLIO_TEXT` and the direction tests: reuse its wording and directives.

## Model facts the boards must match (from `portfolio.view.js` and `portfolio.tla`)

Group order (first appearance in `groups`, also the order of the `out` links): sync → marks → mark-events → events → alerts → `./portfolio.svg`. This is the run order: the five mark diffs and concentration run before the snapshot diffs, because the model follows one holding through `compute_events`.

Decision states: `started`, `tws_reached`, `trades_synced`, `holding`, `valuation_done`, `marked`, `marks_read`, `cross_checked`, `flags_checked`, `gates_checked`, `recal_checked`, `weighed`, `concentration_checked`, `window`, `positions_diffed`, `currency_checked`, `dividend_checked`, `split_checked`, `portfolio_written`, `alerts_written`. Every other state is a `step`.

Model labels without a [condition] that leave a decision, so need one on line 2: `TheValuatorCannotValueIt` (`holding`), `TheAlertsAreSent` (`alerts_written`).

Steps per group (source → target):

- sync (12 inside): `started→channel_misconfigured`, `started→channel_checked`, `channel_checked→tws_unreachable`, `channel_checked→tws_reached`, `tws_reached→snapshot_stored` ×3, `snapshot_stored→actions_synced` ×3, `actions_synced→tws_lost`, `actions_synced→trades_synced`. Out: `trades_synced→holding` (marks), `trades_synced→concentration_checked` (mark-events).
- marks (7 inside): `holding→valuation_done` ×3, `valuation_done→gates_done` ×3, `gates_done→marked`. Out: `marked→marks_read` ×2.
- mark-events (12 inside): `marks_read→cross_checked` ×2, `cross_checked→flags_checked` ×2, `flags_checked→gates_checked` ×2, `gates_checked→recal_checked` ×2, `recal_checked→weighed` ×2, `weighed→concentration_checked` ×2. In: `trades_synced→concentration_checked`, `marked→marks_read` ×2. Out: `concentration_checked→window` ×3.
- events (15 inside): `window→positions_diffed` ×4, `positions_diffed→currency_checked` ×2, `currency_checked→dividend_checked` ×2, `dividend_checked→split_checked` ×2, `split_checked→filing_found` ×2, `split_checked→filings_checked`, `filing_found→filings_checked` ×2. Out: `filings_checked→logged`.
- alerts (7 inside): `logged→portfolio_written`, `portfolio_written→alerts_written` ×2, `alerts_written→not_sent` ×2, `alerts_written→sent`, `alerts_written→send_failed`. `Done` ("the run ends") leaves the six end states.

Event → decision node that decides it (issue task 3; decision 3): mark-events: `marks_read` intrinsic_value_crossed_price, `cross_checked` new_red_flag, `flags_checked` below_quality_gate, `gates_checked` sector_recalibrated, `weighed` concentration. events: `window` position_opened, position_closed, position_size_changed; `positions_diffed` currency_changed; `currency_checked` dividend; `dividend_checked` split; `split_checked` new_filing.

## Declared decisions

1. **"exit code 2" becomes "exit code two" in the view** (issue task 7, "a label unreadable"; analyze A1). State `channel_misconfigured` becomes "the run ends with exit code two before any sync". "exit code 0" and "exit code 1" stay (exempt digits). The TLA+ logic does not change; the `models` job re-checks the view in CI.
2. **Every cross-group step is drawn on both boards.** The largest board is 24 edges (events), within the cap. Its far end is a neighbour node with `link:` to its sub-board.
3. **Each event is named on the decision state that decides it** (table above): line 2 of that state's label names the event value(s) as `EventType` spells them, with the detector's `@symbol` (and threshold `@const`) on the node line. The [fires] / [nothing] branches are the model's own step labels (`... fires [...]` and `no ... [...]`), whose first lines the label-match test fixes. Extra event nodes between states are rejected: `test_subboard_edges_join_the_model_states` needs each model step to join the two states directly, and a node per event would double the edges (events board over the cap). `@enum bot.portfolio.events.EventType` is not cited on either sub-board (`_directive_problem` would demand all twelve members on each board); the union is tested instead (`test_portfolio_events_cover_every_event_type`), as the issue allows.
4. **`Done` drawn on the alerts board only**, from the three send outcomes: `not_sent -> out`, `sent -> out`, `send_failed -> out`, each `"the run ends"` with its exit code on line 2. The other end states (`channel_misconfigured`, `tws_unreachable`, `tws_lost`) carry `# No outgoing edge: the run ends here`.
5. **Neighbours per board.**
   - sync: `holding` (decision, link marks, `# No outgoing edge drawn: its branches are on portfolio-marks`), `concentration_checked` (decision, link mark-events, same comment).
   - marks: `trades_synced` (decision, link sync, `# No incoming edge: the flow enters from portfolio-sync`), `marks_read` (decision, link mark-events, no outgoing edge comment).
   - mark-events: `trades_synced` (decision, link sync), `marked` (decision, link marks), `window` (decision, link events, no outgoing edge comment).
   - events: `concentration_checked` (decision, link mark-events), `logged` (step, link alerts, no outgoing edge).
   - alerts: `filings_checked` (step, link events, no incoming edge).
6. **Stage-board links** on `portfolio.d2`: container `sync` → `./portfolio-sync.svg`, `marks` → `./portfolio-marks.svg`, `events` → `./portfolio-events.svg`, the five mark-diff decision nodes `events.intrinsic_value_crossed_price`, `events.new_red_flag`, `events.below_quality_gate`, `events.sector_recalibrated`, `events.concentration` → `./portfolio-mark-events.svg` (the sub-board expands those five nodes, which sit inside `events`; nested links already exist on `refresh.d2`), `reports` and `notify` → `./portfolio-alerts.svg` (the alerts sub-board expands both).
7. **`out` edges.** sync `trades_synced -> out` `[always: ...]`, marks `marked -> out` `[always]`, mark-events `concentration_checked -> out` `[always]`, events `filings_checked -> out`, alerts the three `Done` edges (decision 4).
8. **The analyze hand-off on marks**: a `step` node `analyze` ("the analyze stage values the holding, see the analyze board", `link: "./analyze.svg"`, `@symbol bot.valuator.analysis.analyze`), fed by `override_yaml` (`@file config/assumptions`) and `currencies_yaml` (`@file config/currencies.yaml`, "loaded once per run"), with `analyze -> valuation_done`; `preset` (`@file config/presets/damodaran_value.yaml`) feeds `valuation_done` ("quality gates and trap detection rules, judged next"), as screen-ranking's `analyze` node.
9. **README in place** (90-line cap, 90 today): the opening paragraph is rewritten to "Six d2 boards and twenty-seven sub-boards" and lists the sub-boards per stage in reading order, within the same line count.
10. **`site` workflow** runs only on a push to master; its commands run locally on the head and the PR lists it as manual verification (as #164 to #170).

## Review Focus

1. **A threshold shown with the wrong value or uncited** (10%, 15%, 100 bps). Tests: `test_subboard_digits_are_cited`, `test_every_directive_is_valid`, `_REQUIRED_CONSTS` per sub-board (Task 1).
2. **An event missing from both event boards, or drawn on a step node.** Test: `test_portfolio_events_cover_every_event_type` (Task 1).
3. **The run order drawn wrong** (snapshot diffs before mark diffs, or the notifier check after the sync). Tests: the label-match tests through `_SUBBOARDED` and `_next_link` (Task 1).
4. **A rate conversion or P&L formula drifting from `sync.py` / `report.py`.** Test: `test_portfolio_subboard_text` pins the formula strings copied from `portfolio.d2` (Task 1).
5. **The SVG drops a link** (stage → sub-board, `out` → next, `analyze` → analyze). Tests: `test_stage_svg_links_its_subboards`, `test_subboard_svg_hrefs`, `test_svg_keeps_every_link` on the CI SVGs (Task 7).

---

### Task 1: evals (registration, required citations, portfolio tests, final-audit lock, view label)

Done in the evals stage, before any board exists. The new tests fail.

**Files:** Modify `tests/unit/test_pipeline_models.py`, `tests/unit/test_pipeline_diagram.py`, `tests/unit/test_pipeline_subboards.py`, `docs/pipeline/models/portfolio.view.js` (decision 1).

- [ ] **Step 1:** `_SUBBOARDED = ("refresh", "screen", "analyze", "portfolio", "site")` and a test `test_every_stage_has_a_model_and_subboards`: `_SUBBOARDED == _STAGES` (imported from `test_pipeline_diagram`), and for each stage `models/<stage>.tla` exists and `_stage_boards(stage)` is not empty. Change decision 1's view label.
- [ ] **Step 2:** Required citations keyed by stem:
  - symbols: `portfolio-sync`: `bot.cli.portfolio`, `bot.notifier.build_notifier`, `bot.portfolio.sync.sync_portfolio`, `bot.portfolio.sync.value_positions`, `bot.ingest.ibkr_flex.import_corporate_actions`, `bot.portfolio.trades.sync_trades`; `portfolio-marks`: `bot.portfolio.marks.mark_holdings`, `bot.valuator.analysis.analyze`, `bot.screener.engine.load_holding_inputs`, `bot.portfolio.marks.persist_marks`; `portfolio-mark-events`: `bot.portfolio.events.compute_events`, `bot.portfolio.marks.load_marks`, `bot.portfolio.events.detect_intrinsic_value_cross`, `detect_new_red_flags`, `detect_below_quality_gate`, `detect_sector_recalibration`, `detect_concentration`; `portfolio-events`: `bot.portfolio.events.compute_events`, `detect_position_changes`, `detect_currency_changes`, `detect_corporate_action_events`, `detect_new_filings`; `portfolio-alerts`: `bot.portfolio.events.persist_events`, `bot.portfolio.report.render_portfolio`, `bot.portfolio.report.render_alerts`, `bot.notifier.notify_alerts`.
  - tables: `portfolio-sync`: `portfolio_snapshots`, `cash_balances`, `corporate_actions`, `trades`, `prices_daily`, `currencies`; `portfolio-marks`: `holding_marks`; `portfolio-mark-events`: `holding_marks`, `portfolio_snapshots`; `portfolio-events`: `portfolio_snapshots`, `corporate_actions`, `filings_log`, `events_log`; `portfolio-alerts`: `events_log`, `portfolio_snapshots`, `cash_balances`.
  - files: `portfolio-marks`: `config/presets/damodaran_value.yaml`, `config/assumptions`, `config/currencies.yaml`; `portfolio-alerts`: `src/bot/reporting/templates/portfolio.md.j2`, `src/bot/reporting/templates/alerts.md.j2`.
  - consts: `portfolio-mark-events`: `DEFAULT_WACC_RECALIBRATION_BPS`, `DEFAULT_CONCENTRATION_THRESHOLD`; `portfolio-events`: `DEFAULT_SIZE_CHANGE_THRESHOLD`; `portfolio-alerts`: `DEFAULT_CONCENTRATION_THRESHOLD` (all `bot.portfolio.events.`).
- [ ] **Step 3:** In `test_pipeline_subboards.py`, a section `# Portfolio sub-boards (#172).`:
  - `test_portfolio_has_five_subboards`: portfolio stems equal the five names.
  - `test_portfolio_subboard_text` (parametrized over `_PORTFOLIO_TEXT`), normalized visible text contains:
    - `portfolio-sync`: `"exit code two"`, `"market value = quantity × latest close"`, `"close × rate_to_usd of the listing currency ÷ rate_to_usd of the position's currency"`, `"BOT_IBKR_FLEX_TOKEN"`, `"exec_id"`, `"watermark"`
    - `portfolio-marks`: `"summed quantity"`, `"config/assumptions/TICKER.yaml"`, `"a skipped rule does not count"`, `"config/presets/damodaran_value.yaml"`, `"unknown values stored empty"`
    - `portfolio-mark-events`: `"equality is not a cross"`, `"100 bps"`, `"market value ÷ total market value > 15%"`, `"fires on every run while above"`, `"counts as none red"`
    - `portfolio-events`: `"exactly 10%: no event"`, `"first run: every position"`, `"(ticker, filing type, filing date)"`
    - `portfolio-alerts`: `"P&L = market value − quantity × average cost"`, `"always written"`, `"a same-day re-run sends the same alerts again"`, `"email or Telegram"`, `"reports/YYYY-MM-DD/portfolio.md"`, `"reports/YYYY-MM-DD/alerts.md"`
  - `test_portfolio_events_cover_every_event_type`: the set of `EventType` values found (as whole words) in the labels of `decision` nodes of `portfolio-events` and `portfolio-mark-events` equals every member; and the five mark-diff values are on `portfolio-mark-events`, the seven others on `portfolio-events`.
  - `test_portfolio_marks_hands_off_to_analyze`: `portfolio-marks` has a node linking `./analyze.svg` with an edge into the `valuation_done` state node.
- [ ] **Step 4:** Run `uv run pytest -q tests/unit/test_pipeline_subboards.py tests/unit/test_pipeline_models.py tests/unit/test_pipeline_diagram.py`. Expected: the new tests and the portfolio label-match tests fail (boards missing); everything else passes.
- [ ] **Step 5:** Commit `test(#172): evals`.

### Task 2: portfolio-sync

**Files:** Create `docs/pipeline/portfolio-sync.d2`.

- [ ] **Step 1:** Write the board.
  - `objective`: "Objective: check the alert channel, then copy today's positions, cash, corporate actions and new fills from Interactive Brokers into the database."
  - States, how lines from `portfolio.d2`'s `cli`, `notify.channel`, `sync.*`: `started` (`@symbol bot.cli.portfolio`; line 2: preset `damodaran_value.yaml` missing → exit code two), `channel_misconfigured`, `channel_checked` (`@symbol bot.notifier.build_notifier`), `tws_unreachable`, `tws_reached` (`@symbol bot.portfolio.sync.sync_portfolio`), `snapshot_stored`, `actions_synced` (`@symbol bot.ingest.ibkr_flex.import_corporate_actions`), `tws_lost`, `trades_synced` (`@symbol bot.portfolio.trades.sync_trades`). Neighbours per decision 5.
  - `TheChannelIsMisconfigured` / `TheChannelIsValid` carry the channel settings (BOT_NOTIFIER none / email / telegram and their required settings). `ItIsStoredWithAMarketValue` carries the market value math (`@symbol bot.portfolio.sync.value_positions`). `TheNewFillsAreStored` carries the watermark, `exec_id` dedup and UTC. `FlexImportsTheActions` carries the dividend / split mapping and `action_id` dedup.
  - Stores/services: `tws` (external) → `tws_reached`; `prices_daily`, `currencies` → `snapshot_stored`; `snapshot_stored` → `portfolio_snapshots`, `cash_balances`; `flex` (external) → `actions_synced`; `actions_synced` → `corporate_actions`; `trades_synced` → `trades`.
  - `out`: "Comes out:" today's snapshot rows (positions with market value or unpriced), cash by currency, new corporate actions and new fills. `link: "./portfolio-marks.svg"`.
  - Edges: 12 inside + 2 out + 8 stores + `trades_synced -> out` = 23.
- [ ] **Step 2:** Run the three test files with `-k portfolio`. Expected: this stem passes everything except the SVG-dependent tests and the label-match tests of the other groups.
- [ ] **Step 3:** Commit `docs(#172): portfolio-sync sub-board`.

### Task 3: portfolio-marks

**Files:** Create `docs/pipeline/portfolio-marks.d2`.

- [ ] **Step 1:** Write the board.
  - `objective`: "Objective: give every holding today's mark: its intrinsic value, price, red flags, failed gates and sector WACC, each known or unknown."
  - States `holding` (`@symbol bot.portfolio.marks.mark_holdings`, "holdings = tickers whose summed quantity ≠ 0 on the snapshot date"), `valuation_done`, `gates_done` (`@symbol bot.screener.engine.load_holding_inputs`), `marked` (`@symbol bot.portfolio.marks.persist_marks`, "the snapshot date's rows deleted, then inserted; unknown values stored empty"). Neighbours per decision 5. The analyze hand-off and the preset per decision 8.
  - Gate edges carry: failed gates = the gates that fail, a skipped rule does not count; sector WACC from the sector benchmark.
  - Store: `marked -> holding_marks` `[always]`.
  - `out`: "Comes out:" one `holding_marks` row per holding for the snapshot date. `link: "./portfolio-mark-events.svg"`.
  - Edges: 1 in + 7 inside + 2 out + 3 analyze/override/currencies + preset + store + `marked -> out` = 16.
- [ ] **Step 2:** Tests as Task 2. **Step 3:** Commit `docs(#172): portfolio-marks sub-board`.

### Task 4: portfolio-mark-events

**Files:** Create `docs/pipeline/portfolio-mark-events.d2`.

- [ ] **Step 1:** Write the board.
  - `objective`: "Objective: diff today's mark against the previous one into the mark events, then weigh the holding for concentration."
  - States `marks_read` (`@symbol bot.portfolio.marks.load_marks @symbol bot.portfolio.events.compute_events`), `cross_checked`, `flags_checked`, `gates_checked`, `recal_checked`, `weighed`, `concentration_checked`, each naming its event per decision 3 with its detector `@symbol` and const. Neighbours per decision 5.
  - Edge how lines from `portfolio.d2`'s `events.intrinsic_value_crossed_price`, `new_red_flag`, `below_quality_gate`, `sector_recalibrated`, `concentration` with their consts on the line.
  - Stores: `holding_marks -> marks_read` ("previous and current marks"), `portfolio_snapshots -> recal_checked` ("this snapshot's market values").
  - `out`: "Comes out:" this holding's mark events (zero to five kinds) and its concentration verdict, handed to the snapshot diff. `link: "./portfolio-events.svg"`.
  - Edges: 3 in + 12 inside + 3 out + 2 stores + `concentration_checked -> out` = 21.
- [ ] **Step 2:** Tests as Task 2. **Step 3:** Commit `docs(#172): portfolio-mark-events sub-board`.

### Task 5: portfolio-events

**Files:** Create `docs/pipeline/portfolio-events.d2`.

- [ ] **Step 1:** Write the board.
  - `objective`: "Objective: diff today's snapshot against the previous one into the position, currency, corporate action and filing events."
  - States `window` (previous snapshot = newest snapshot_date before today), `positions_diffed`, `currency_checked`, `dividend_checked`, `split_checked`, `filing_found`, `filings_checked`, each event decision per decision 3 with its detector `@symbol`; `window` carries `@const bot.portfolio.events.DEFAULT_SIZE_CHANGE_THRESHOLD`. Neighbours per decision 5.
  - Edge how lines from `portfolio.d2`'s `events.position_*`, `currency_changed`, `dividend`, `split`, `new_filing`.
  - Stores: `portfolio_snapshots -> window`, `corporate_actions -> currency_checked` ("dividends and splits in the window"), `filings_log -> split_checked`, `events_log -> split_checked` ("filings already reported").
  - `out`: "Comes out:" this holding's snapshot events, and with the mark events, every event fired for it, handed to the events log. `link: "./portfolio-alerts.svg"`.
  - Edges: 3 in + 15 inside + 1 out + 4 stores + `filings_checked -> out` = 24.
- [ ] **Step 2:** Tests as Task 2. **Step 3:** Commit `docs(#172): portfolio-events sub-board`.

### Task 6: portfolio-alerts

**Files:** Create `docs/pipeline/portfolio-alerts.d2`.

- [ ] **Step 1:** Write the board.
  - `objective`: "Objective: log every event, write the two reports, and send today's alerts when there is a channel and something to say."
  - States `logged` (`@symbol bot.portfolio.events.persist_events`), `portfolio_written` (`@symbol bot.portfolio.report.render_portfolio @const bot.portfolio.events.DEFAULT_CONCENTRATION_THRESHOLD`: P&L and concentration formulas), `alerts_written` (`@symbol bot.portfolio.report.render_alerts`), `not_sent`, `sent`, `send_failed` (`@symbol bot.notifier.notify_alerts`); neighbour `filings_checked`.
  - Stores/files/services/outputs: `logged -> events_log`; `portfolio_snapshots`, `cash_balances`, `portfolio_template -> portfolio_written`; `alerts_template -> alerts_written`; `portfolio_written -> portfolio_md` and `alerts_written -> alerts_md` (`[always]`); `sent -> channels` ("email or Telegram", external).
  - `out`: "Comes out:" `reports/YYYY-MM-DD/portfolio.md`, `reports/YYYY-MM-DD/alerts.md`, the alert message when sent, and the exit code. `link: "./portfolio.svg"`, fed by the three `Done` edges (decision 4).
  - Edges: 1 in + 7 inside + 1 events_log + 3 report inputs + 1 template + 2 outputs + 1 channel + 3 Done = 19.
- [ ] **Step 2:** Tests as Task 2. **Step 3:** Commit `docs(#172): portfolio-alerts sub-board`.

### Task 7: stage links, docs, render

**Files:** Modify `docs/pipeline/portfolio.d2` (decision 6), `docs/pipeline/README.md` (decision 9), `docs/pipeline/models/README.md` and `CONTEXT.md` (final-state wording, only where they are not already final). Then the CI render loop of the issue: push, `gh run watch`, download `pipeline-render`, copy every SVG and `rendered.sha256`, commit, push.

- [ ] **Step 1:** Add the links and doc edits; run the three test files: everything passes except the SVG-dependent tests.
- [ ] **Step 2:** Commit `docs(#172): link the portfolio sub-boards`; push; render loop until `pipeline-diagram` (both jobs) is green on the head with the committed SVGs.
- [ ] **Step 3:** Full suite, `uv run ruff check . && uv run mypy src`, `python3 docs/pipeline/check.py` (`0 errors`), and the `site` workflow's commands locally.

### Task 8: final audit of the story

- [ ] **Step 1:** Read the five stage SVGs' hrefs and every sub-board SVG's hrefs; record that each stage links each of its sub-boards and each sub-board links back (issue audit c).
- [ ] **Step 2:** For each of the 27 sub-boards, read the board alone and write its four answers (objective, how, criteria, what comes out) into `.scratch/audit-172.md`. Where an answer is missing, fix that board (a label line, not a restructure) and re-run the render loop.
- [ ] **Step 3:** List every issue opened by the model children under the broken-rule protocol (the `## Known broken rules` table and the children's PRs).
- [ ] **Step 4:** The PR body carries the 27-board audit, the portfolio four answers, the href check and the broken-rule issues.

## Assumptions (decided, with the rejected alternative)

- A1. **"exit code two" in the view** (decision 1), as analyze A1.
- A2. **Decision neighbours with a missing side** carry trailing `No outgoing edge drawn` / `No incoming edge` comments (analyze A2).
- A3. **Events board at the cap (24).** Every model step of the group, its two cross-group steps, four stores and the `out` edge are required; nothing optional remains. Rejected: dropping a store (events_log is read for new_filing and is what makes a reported filing skip).
- A4. **View labels and links are checked by TLC and d2 in CI only** (parent decision 11).
- A5. **Red intermediate commits** (analyze A5): only the final head must be green.
