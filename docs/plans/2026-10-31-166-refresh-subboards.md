# Refresh sub-boards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Five d2 sub-boards (`refresh-damodaran`, `refresh-fundamentals`, `refresh-facts`, `refresh-prices`, `refresh-fx`) draw the checked refresh statechart one level below `refresh.d2`, so a reader who clicks a step on `refresh.svg` follows one ticker (or, for Damodaran, one run) through it: objective, how, criteria, what comes out.

**Architecture:** Each sub-board is a flat d2 board with no containers. Its nodes are the model states of one `groups` value of `docs/pipeline/models/refresh.view.js`. The neighbouring states the flow enters from or leaves to are drawn too, plus three fixed nodes (`objective`, `back`, `out`) and the sources and stores at the edge of the flow. Its edges are the model steps, labelled with the view's `steps` text, with the how on further lines. The generic tests from #164 (`tests/unit/test_pipeline_subboards.py`, the label match in `tests/unit/test_pipeline_models.py`, the board audits in `tests/unit/test_pipeline_diagram.py`) already enforce the conventions. This issue registers `refresh` and adds refresh-specific citations and phrases. d2 renders in CI only.

**Tech Stack:** d2 v0.9.0 + TALA (CI only), pytest, `docs/pipeline/check.py`.

**Spec:** issue #166 (its body, including "Sub-board conventions"). Parent story #161, plan comment decisions 2 to 8. Worked example: `docs/pipeline/site-*.d2` and `docs/plans/2026-10-31-164-site-subboards.md` (its declared decisions 1 to 7 apply here unchanged).

## Global Constraints

- New files: `docs/pipeline/refresh-damodaran.d2`, `refresh-fundamentals.d2`, `refresh-facts.d2`, `refresh-prices.d2`, `refresh-fx.d2`. Their `.svg` files and `rendered.sha256` come only from the CI artifact `pipeline-render`; never edit an SVG or the hash by hand.
- Every sub-board starts with `...@classes`, a blank line, `direction: down`. `class:` is a node's first attribute. Expand every acronym at its first use on each board (SEC, EDGAR, FX, EBIT, EBITDA, D/E, SIC, FMP, ADR). The expansion must be on the line of the first use or before it, in file order (nodes come before edges). No all-caps token outside `_ACRONYMS` / `_ACRONYMS_EXEMPT`.
- Every number other than 0, 1 and 100 on a node or edge label is cited by `@const`/`@param` on that line; otherwise write it as a word ("eight files", "three or more").
- At most 24 edges per sub-board; aim for 20.
- A node that is a model state has that state's `states` label as the exact first line of its label. An edge that is a model step has that step's `steps` label as the exact first line, and it joins the two states that the `.tla` action joins.
- A state is `decision` when two or more of its model steps carry a `[condition]`, otherwise `step`. This includes neighbours. Every edge leaving a decision has a `[...]` somewhere in its label. A model label without one gets the condition on its second line.
- Every step and decision node has a directive (`@symbol`, `@const`, `@table`, `@file`, ...) on its line or the line before.
- Neighbour `step` nodes carry `# No incoming edge: the flow enters from refresh-<sub>` or `# No outgoing edge: the flow goes on in refresh-<sub>`; a terminal state carries `# No outgoing edge: the run ends here`.
- No `#`, `{`, `}`, `|` or `"` inside a quoted label. Write `×`, `÷`, `−`, `≤` as on `refresh.d2`.
- `refresh.d2` gains five `link:` lines and nothing else. `pipeline.d2` does not change. No file under `src/` changes. The TLA+ logic (`refresh.tla`, `refresh.cfg`) does not change.
- Formulas, thresholds, names and paths are copied from the code, and each is cited. `refresh.d2` already carries most of them with their citations: reuse its wording and directives.

## Model facts the boards must match (from `refresh.view.js` and `refresh.tla`)

Order of the groups, which is also the order of `out` links: damodaran → fundamentals → facts → prices → fx → `./refresh.svg`.

Classes (computed with the test's rule): decision = `started`, `downloaded`, `derived`, `ticker_checked`, `fetching`, `facts_parsed`, `fact_read`, `fact_in_period`, `fact_derived`, `row_labelled`, `price_listing`, `price_listed`, `price_queued`, `bars_fetched`, `fx_listing`. All other states are `step`.

Two actions that share a label and a pair of states are drawn as one edge: `TheCheckFindsNoNewerStoredFiling`/`TheRunHasForce`, `TheCheckIsRateLimited`/`AnEarlierTickerHitTheLimit`, `TheInstantJoinsAYearRow`/`TheInstantJoinsAQuarterRow`, `ThePriceFetchIsRateLimited`/`AnEarlierPriceFetchHitTheLimit`. Two actions with different labels between the same two states are two edges (d2 allows repeated `a -> b`). `Done` ("the run ends") is drawn once, as `fx_done -> out` on refresh-fx.

## Declared decisions

1. **Neighbours drawn per board.**
   - damodaran: `mapping_loading`, which links to fundamentals.
   - fundamentals: `damodaran_written` and `damodaran_failed` (link damodaran), `fact_read`, `fact_in_row` and `fact_dropped` (link facts), and `price_listing` (link prices).
   - facts: `fetching` and `facts_parsed`, which link to fundamentals.
   - prices: `ticker_counted` (link fundamentals) and `fx_listing` (link fx).
   - fx: `price_counted`, which links to prices.

   A step that crosses groups is drawn on both of its boards.
2. **Cron nodes** appear only where they enter. `weekly.sh` (`bot refresh --all`) goes into `started` on refresh-damodaran. `daily.sh` goes into `price_listing` on refresh-prices (`bot refresh --prices`, repeated) and into `fx_listing` on refresh-fx (`bot refresh --fx`). `price_fill.sh` goes into `price_listing` on refresh-prices (`--only-missing`). This is tested.
3. **Run status.** refresh-prices and refresh-fx each get one extra `step` node `status`: "status of the run" with `failure rate = failed ÷ attempted`, at most 5% success, at most 25% partial, above that error, not success gives exit code 2, and deferred items are left out of the attempted count. It cites `@symbol bot.ingest.universe._resolve_status @const bot.ingest.universe.SUCCESS_MAX_FAILURE_RATE @const bot.ingest.universe.PARTIAL_MAX_FAILURE_RATE`. On refresh-fundamentals the same thresholds go on the `ticker_counted` node's how line, which saves edges (budget 23).
4. **The facts label "1 to 4".** `TheQuarterTakesItsFilingLabel` reads `... a quarter number outside 1 to 4]`. No constant holds 4 (`_fiscal_quarter_key` uses the literal), so the digit cannot be cited on a sub-board edge. Its view label becomes `... a quarter number outside one to four]`. Issue task 7 allows this: it is a view label, not TLA+ logic. CI re-runs the models job.
5. **Stage-board links:**
   - `damodaran` container → `./refresh-damodaran.svg`
   - `fundamentals` container → `./refresh-fundamentals.svg`
   - `fundamentals.periods` node, the first step of the per-fact path → `./refresh-facts.svg`
   - `prices` container → `./refresh-prices.svg`
   - `fx` container → `./refresh-fx.svg`

   A child link inside a linked container renders in d2 v0.9.0: `site.d2` does this with `build.rows`, and `test_svg_keeps_every_link` passes on `site.svg`.
6. **README.** `docs/pipeline/README.md` is at 88 lines, with a cap of 90. The sentence naming the site sub-boards is rewritten in place to name the five refresh sub-boards too. The line count stays at 89 or under.
7. **`site` workflow.** It runs only on a push to master (#164 assumption A2), so it cannot be green on a PR into the feature branch. Its commands are run locally on the head, and the PR says so as a manual verification.

## Review Focus

1. **A step drawn between the wrong states**, e.g. the share rescale drawn out of `fact_derived` instead of `row_labelled`. Expected: every edge joins the states its action joins. Test: `test_subboard_edges_join_the_model_states` (once `refresh` is in `_SUBBOARDED`, Task 1).
2. **A threshold shown without its citation**, or cited with the wrong value (350/380, 80/100, 380, 91.3, 1,000,000/1,000, 2, 3, 7 days, 5%/25%). Expected: every digit is cited on its line and every `@const` value is shown. Tests: `test_subboard_digits_are_cited`, `test_every_directive_is_valid`, and the `_REQUIRED_CONSTS` entries added in Task 1.
3. **A cron node on a board it does not enter**, e.g. `weekly.sh` on refresh-prices. Expected: crons only where they enter. Test: `test_refresh_subboard_crons` (Task 1).
4. **A decision's edge with no condition**, e.g. `the eight files download` out of `started`. Expected: a `[...]` on every edge out of a decision. Test: `test_decision_edges_carry_a_condition`.
5. **The SVG drops a link** (stage board → sub-board, or `out` → next). Expected: every `link:` becomes an `<a href>`. Tests: `test_stage_svg_links_its_subboards`, `test_subboard_svg_hrefs`, `test_svg_keeps_every_link`, run on the SVGs committed from CI (Task 7).

---

### Task 1: evals (registration, required citations, refresh phrases)

Done in the evals stage, before any board exists. The new tests fail.

**Files:**
- Modify: `tests/unit/test_pipeline_models.py` (`_SUBBOARDED`)
- Modify: `tests/unit/test_pipeline_diagram.py` (`_REQUIRED_SYMBOLS`, `_REQUIRED_TABLES`, `_REQUIRED_FILES`, `_REQUIRED_CONSTS`)
- Modify: `tests/unit/test_pipeline_subboards.py` (refresh tests)

- [ ] **Step 1:** `_SUBBOARDED = ("site", "refresh")`.
- [ ] **Step 2:** Add these required citations, keyed by stem:
  - symbols:
    - `refresh-damodaran`: `bot.ingest.damodaran.import_damodaran`, `bot.ingest.damodaran.merge_industry_datasets`, `bot.ingest.damodaran.derive_industry_columns`
    - `refresh-fundamentals`: `bot.ingest.universe.import_company`, `bot.ingest.universe._should_skip`, `bot.ingest.industry_mapping.load_industry_mapping`, `bot.ingest.universe._run_bulk_refresh`
    - `refresh-facts`: `bot.ingest.sec_edgar._collect_period_rows`, `bot.ingest.sec_edgar._rescale_shares_diluted`, `bot.ingest.sec_edgar._fiscal_quarter_key`, `bot.ingest.sec_edgar._derive_financial_fields`
    - `refresh-prices`: `bot.ingest.universe.refresh_prices`, `bot.ingest.universe._stale_first`, `bot.ingest.universe._last_weekday_before`
    - `refresh-fx`: `bot.ingest.universe.refresh_fx`
  - tables:
    - `refresh-damodaran`: `damodaran_industry`, `damodaran_country`, `refresh_log`
    - `refresh-fundamentals`: `companies`, `filings_log`, `refresh_log`
    - `refresh-facts`: `financials_annual`, `financials_quarterly`
    - `refresh-prices`: `prices_daily`, `refresh_log`
    - `refresh-fx`: `companies`, `currencies`, `refresh_log`
  - files:
    - `refresh-damodaran`: `scripts/weekly.sh`
    - `refresh-fundamentals`: `src/bot/ingest/industry_mapping.csv`, `src/bot/ingest/universe_default.csv`
    - `refresh-prices`: `scripts/daily.sh`, `scripts/price_fill.sh`
    - `refresh-fx`: `scripts/daily.sh`
  - consts:
    - `refresh-facts`: `bot.ingest.sec_edgar.ANNUAL_SPAN_DAYS`, `QUARTERLY_SPAN_DAYS`, `_QUARTER_DAYS`, `_SHARE_SCALE_FACTORS`, `_MIN_SHARE_COMPARATORS`, `_SHARE_SCALE_TOLERANCE` (full dotted paths)
    - `refresh-prices`: `bot.ingest.universe.SUCCESS_MAX_FAILURE_RATE`, `bot.ingest.universe.PARTIAL_MAX_FAILURE_RATE`, `bot.ingest.edgar_base._FRESH_DAYS`
    - `refresh-fx`: `bot.ingest.universe.SUCCESS_MAX_FAILURE_RATE`, `bot.ingest.universe.PARTIAL_MAX_FAILURE_RATE`
- [ ] **Step 3:** In `test_pipeline_subboards.py`, add:
  - `test_refresh_has_five_subboards`: the refresh stems equal the five names above.
  - `test_refresh_subboard_crons`: for each refresh sub-board, the set of `@file` arguments cited on `cron`-class nodes equals:
    - `refresh-damodaran`: `{"scripts/weekly.sh"}`
    - `refresh-fundamentals`: `set()`
    - `refresh-facts`: `set()`
    - `refresh-prices`: `{"scripts/daily.sh", "scripts/price_fill.sh"}`
    - `refresh-fx`: `{"scripts/daily.sh"}`
  - `test_refresh_subboard_text` (parametrized on stem): each phrase is in the board's normalized visible text. The phrases:
    - `refresh-damodaran`: `"eight files"` (in the objective), `"the earlier file wins a shared column"`, `"D/E = w ÷ (1 − w)"`, `"beta_unlevered = beta_levered ÷ (1 + (1 − tax) × D/E)"`
    - `refresh-facts`: `"350 to 380 days"`, `"80 to 100 days"`, `"the first concept in the list"`, `"calendar year of its end"`, `"91.3"`, `"1,000,000"`, `"financials_annual"`, `"financials_quarterly"`
    - `refresh-prices`: `"5%"`, `"25%"`, `"deferred, not failed"`, `"stalest first"`
    - `refresh-fx`: `"5%"`, `"25%"`, `"deferred"`
  - The objective of `refresh-damodaran` contains `"eight files"`: assert it on the `objective` label, not the whole board.
- [ ] **Step 4:** Run `uv run pytest -q tests/unit/test_pipeline_subboards.py tests/unit/test_pipeline_models.py tests/unit/test_pipeline_diagram.py`. Expected: the new tests and the refresh label-match tests fail because the boards are missing. Everything else passes.
- [ ] **Step 5:** Commit `test(#166): evals`.

### Task 2: refresh-damodaran

**Files:** Create `docs/pipeline/refresh-damodaran.d2`.

**Consumes:** Task 1's tests; the model facts above.

- [ ] **Step 1:** Write the board.
  - `objective`: "Objective: refresh the Damodaran industry and country benchmarks for one (region, year); the unit is the run of eight files, not a company."
  - Sources:
    - `weekly` (cron, `@file scripts/weekly.sh`): `weekly.sh` runs `bot refresh --all`.
    - `damodaran_data` (external): `pages.stern.nyu.edu/~adamodar/pc/datasets/`.
  - States, each with its first line plus how lines:
    - `started`: wacc.xls, ctryprem.xls, then the six others into --download-dir. A failure of one of the first two stops the downloads.
    - `downloaded`
    - `industry_read`: each sheet picked by keywords; columns by exact header.
    - `merged`: outer join on industry name, earlier file wins, a later file fills only empty columns. Rows without an industry name are dropped.
    - `country_read`: sheet 'ERPs by country'.
    - `derived`: `D/E = w ÷ (1 − w)`, `w = D/(D+E)`, empty unless 0 ≤ w < 1; `beta_unlevered = beta_levered ÷ (1 + (1 − tax) × D/E)`, where a missing tax counts as 0; the country tax rate comes from sheet 'Country Tax Rates', kept within [0, 1]. Expand "debt to equity" before the first `D/E`.
    - `damodaran_written`: replace the (region, year) rows of damodaran_industry and the year rows of damodaran_country; one refresh_log row, status success or partial.
    - `damodaran_failed`: one refresh_log row, status error, with the message.
  - Neighbour `mapping_loading` (step, `link: "./refresh-fundamentals.svg"`, `# No outgoing edge: the flow goes on in refresh-fundamentals`).
  - Stores: `damodaran_industry`, `damodaran_country`, `refresh_log` (class `store`, `@table`).
  - `out`: "Comes out:" one damodaran_industry row per industry for (region, year), with D/E and beta_unlevered, and one damodaran_country row per country for the year. `link: "./refresh-fundamentals.svg"`. Fed from `damodaran_written`.
  - Edges: the 15 model steps of the group (13 inside and 2 into `mapping_loading`); `weekly -> started`; `damodaran_data -> started`; `damodaran_written ->` each store; `damodaran_failed -> refresh_log`; `damodaran_written -> out`. That makes about 22 edges.
  - Second-line conditions:
    - `started -> downloaded` "the eight files download": `[every download succeeds]`
    - `downloaded -> industry_read` "the industry files are read": `[every file can be read]`
  - Cite with `@symbol bot.ingest.damodaran.import_damodaran`, `.merge_industry_datasets`, `.derive_industry_columns`, `.parse_country_tax_rates`, `._import_files_into_run`, `.upsert_industry_rows`, `.upsert_country_rows` as on `refresh.d2`.
- [ ] **Step 2:** Run the three test files with `-k "damodaran or refresh"`. Expected: every test passes for this stem except those that need the SVG (`test_subboard_svg_hrefs`, `test_svg_keeps_every_link`, `test_each_board_has_a_rendered_svg`, `test_svgs_show_their_step_labels`, `test_check_py_exits_zero`). Label-match tests still fail for the other groups until their boards exist.
- [ ] **Step 3:** Commit `docs(#166): refresh-damodaran sub-board`.

### Task 3: refresh-fundamentals

**Files:** Create `docs/pipeline/refresh-fundamentals.d2`.

- [ ] **Step 1:** Write the board.
  - `objective`: "Objective: for each ticker of the universe, decide whether its filings are new, fetch its SEC EDGAR company facts and write the company with its Damodaran industry." Expand SEC and EDGAR on this line.
  - Sources:
    - `industry_mapping_csv` (file) → `mapping_loading`
    - `universe_csv` (file) → `ticker_checked`, "tickers, one at a time; --limit takes the first N"
    - `edgar` (external) → `ticker_checked`, "submissions: newest 10-K, 10-Q or 20-F filing date"
    - `filings_log` (store) → `ticker_checked`, "newest stored filing date of this provider"
    - `edgar` → `fetching`, "company facts, submissions"
  - States:
    - `mapping_loading`: provider label → companies.industry_damodaran; the SEC EDGAR label is the SIC (Standard Industrial Classification) description; matching folds case, collapses spaces, treats dash variants alike.
    - `mapping_refused`: terminal; the command stops before any ticker.
    - `ticker_checked`: skipped when the provider's newest filing date is not after the newest filings_log date; --force bypasses; a probe error fetches anyway.
    - `fetching`
    - `facts_parsed`
    - `ticker_counted`: outcome imported, skipped, failed or deferred; failure rate = failed ÷ attempted, deferred left out; at most 5% success, at most 25% partial, else error. Cite `@symbol bot.ingest.universe._run_bulk_refresh @const ...SUCCESS_MAX_FAILURE_RATE @const ...PARTIAL_MAX_FAILURE_RATE`.
  - Neighbours as in decision 1.
  - Stores: `companies` (written by `facts_parsed -> companies`, condition "[written in either case, in one transaction with the financials and filings_log rows]") and `refresh_log` (`ticker_counted -> refresh_log`: one row per ticker, source = provider name; one summary row, source = provider name + _universe).
  - `out`: "Comes out:" per ticker one outcome, and for each fetched ticker its company facts, read fact by fact in refresh-facts. `link: "./refresh-facts.svg"`. Fed from `ticker_counted`.
  - Edges: 15 model or cross steps (see the model facts; the two merged pairs give one edge each), plus 5 source edges, 2 store edges and 1 out edge = 23.
  - `fetching -> fact_read` "the facts of the ticker are read one by one" gets `[the company facts arrive]` on its second line.
- [ ] **Step 2:** Run the tests as in Task 2. Expected: same as Task 2, for this stem.
- [ ] **Step 3:** Commit `docs(#166): refresh-fundamentals sub-board`.

### Task 4: refresh-facts (and the view label of decision 4)

**Files:** Create `docs/pipeline/refresh-facts.d2`. Modify `docs/pipeline/models/refresh.view.js` (only the `TheQuarterTakesItsFilingLabel` label: `1 to 4` → `one to four`).

- [ ] **Step 1:** Change the view label.
- [ ] **Step 2:** Write the board.
  - `objective`: "Objective: follow one fact of one ticker's company facts into the annual or quarterly row it belongs to, or out of the import."
  - Neighbours:
    - `fetching` (decision, link fundamentals): the entry state.
    - `facts_parsed` (decision, link fundamentals).
  - States, with their how lines:
    - `fact_read`: duration facts by their own start and end; the filing's fy and fp never pick the period.
    - `fact_in_period`: concept precedence per column and period end, e.g. revenue: Revenues, then RevenueFromContractWithCustomerExcludingAssessedTax, ...; is_restated when a fact used comes from an amendment.
    - `fact_chosen`
    - `fact_derived`: EBITDA = EBIT + depreciation, free cash flow = operating cash flow − capex, working capital = current assets − current liabilities; a reported aggregate is never overwritten. Expand EBIT on this line.
    - `row_labelled`
    - `fact_in_row`
    - `fact_dropped`
  - Edge how lines, each with its `@const` on the line:
    - year span `350 to 380 days`: `ANNUAL_SPAN_DAYS`
    - quarter span `80 to 100 days`: `QUARTERLY_SPAN_DAYS`
    - quarter numbered: `4 − round(days to the year end ÷ 91.3)`, `_QUARTER_DAYS`, plus `within 380 days`, `ANNUAL_SPAN_DAYS`. Write the 4 as "fourth quarter minus whole 91.3-day steps", because 4 has no constant.
    - rescale: `ratio = median of the other positive annual counts ÷ count; factors 1,000,000 then 1,000; kept when factor ÷ 2 ≤ ratio ≤ factor × 2; needs ≥ 3 other counts`, with `_SHARE_SCALE_FACTORS`, `_SHARE_SCALE_TOLERANCE` and `_MIN_SHARE_COMPARATORS`
    - `fiscal year = calendar year of its end` on the year label
    - collision: `the later period end is kept`
  - Stores: `financials_annual` and `financials_quarterly`, fed from `fact_in_row`. They are written by refresh-fundamentals in its one transaction, and the edge label says so.
  - `out`: "Comes out:" annual rows, one per fiscal_year, to financials_annual, and quarterly rows, one per (fiscal_year, fiscal_quarter), to financials_quarterly, with share counts corrected. `link: "./refresh-prices.svg"`. Fed from `fact_in_row`.
  - Edges, about 22:
    - entry 1
    - fact_read 4 (the merged instant edge counts once)
    - fact_in_period 2
    - fact_chosen 1
    - fact_derived 5
    - row_labelled 4
    - exits 2
    - stores 2
    - out 1
  - `fetching -> fact_read` gets `[the company facts arrive]`.
- [ ] **Step 3:** Run the tests as in Task 2. Expected: same, for this stem, and `tests/unit/test_pipeline_models.py` passes for the view change.
- [ ] **Step 4:** Commit `docs(#166): refresh-facts sub-board`.

### Task 5: refresh-prices

**Files:** Create `docs/pipeline/refresh-prices.d2`.

- [ ] **Step 1:** Write the board.
  - `objective`: "Objective: bring each ticker's end-of-day price bars up to date, stalest first, and give the newest bar its market cap."
  - Sources:
    - crons `daily` and `price_fill` → `price_listing`. daily: "bot refresh --prices, repeated while tickers are deferred (BOT_PRICE_ROUNDS, default 10 rounds, BOT_PRICE_RETRY_PAUSE, default 3600 s apart)". Digits 10 and 3600 have no Python constant, so write them in words or drop them; they are on `refresh.d2`'s cron edge only.
    - external `tiingo` ("Tiingo, default source; Stooq the alternative") → `bars_fetched`
    - `edgar` (SEC EDGAR shares outstanding) → `bars_fetched`
    - store `prices_daily` → `price_listed` ("newest bar per ticker")
  - States:
    - `price_listing`
    - `price_listed`: current means its newest bar is on or after the last weekday before today; cite `_last_weekday_before`.
    - `price_queued`: never priced first, then oldest newest bar, ties in input order; cite `_stale_first`.
    - `bars_fetched`: market cap = close × shares outstanding, newest bar only, `_FRESH_DAYS` 7.
    - `price_counted`
  - Neighbours as in decision 1.
  - Extra `status` node (decision 3): `price_counted -> status`, `status -> refresh_log`, `status -> out`.
  - `price_counted -> prices_daily`: "bars with close, volume, market cap".
  - `out`: "Comes out:" new prices_daily bars per ticker, the newest with market cap when fresh, and one run status. `link: "./refresh-fx.svg"`.
  - The deferral edge carries the how: "the rest skip the request; deferred tickers are left out of the failure rate; daily.sh runs another round".
  - Edges, about 21:
    - entry 1
    - crons 2
    - model 11 (the merged deferral counts once)
    - `price_counted -> fx_listing` 1
    - sources 3
    - `prices_daily` write 1
    - status 2
    - out 1 (from `status`)
  - `price_queued -> bars_fetched` "only the bars after the newest stored one are fetched" gets `[the request succeeds]`.
- [ ] **Step 2:** Run the tests as in Task 2.
- [ ] **Step 3:** Commit `docs(#166): refresh-prices sub-board`.

### Task 6: refresh-fx

**Files:** Create `docs/pipeline/refresh-fx.d2`.

- [ ] **Step 1:** Write the board.
  - `objective`: "Objective: store a daily rate to US dollars for every listing currency other than USD, so later reads can convert amounts."
  - Sources:
    - cron `daily` → `fx_listing`: "bot refresh --fx, after the price rounds, even when they failed"
    - store `companies` → `fx_listing`: "distinct listing currencies other than USD"
    - external `fmp` (Financial Modeling Prep, BOT_DATA_PROVIDER=fmp only) → `fx_requested`
  - States:
    - `fx_listing`
    - `fx_requested`: under the SEC EDGAR providers, edgar-tiingo (the default) and edgar-stooq, no rates come back; only Financial Modeling Prep supplies them. Cite `@symbol bot.ingest.edgar_base.EdgarPricedProvider.fx_rates`.
    - `fx_done`
  - Neighbour `price_counted` (step, link prices, No incoming edge).
  - `fx_requested -> currencies`: "rate_to_usd per currency and date; a later read uses the nearest prior date". Cite `@symbol bot.utils.fx.import_fx_rates`.
  - Extra `status` node (decision 3): `fx_requested -> status` ("each currency counted: imported, failed or deferred; a rate limit defers this and every later currency"), `status -> refresh_log`, `status -> fx_done`.
  - `fx_done -> out`: "the run ends".
  - `out`: "Comes out:" currencies rows (rate_to_usd per currency and date), one run status, and the exit code of the command (the worst source). `link: "./refresh.svg"`.
  - Edges, about 12.
- [ ] **Step 2:** Run the full three test files. Expected: every test passes except the SVG and hash ones (Task 7).
- [ ] **Step 3:** Commit `docs(#166): refresh-fx sub-board`.

### Task 7: stage-board links, README, render

**Files:**
- Modify: `docs/pipeline/refresh.d2` (five `link:` lines, decision 5)
- Modify: `docs/pipeline/README.md` (one sentence, decision 6)
- Add from CI: `docs/pipeline/refresh*.svg`, `rendered.sha256`

- [ ] **Step 1:** Add the links. `git diff docs/pipeline/refresh.d2` shows only five added `link:` lines. Inside a node block, `link:` goes after `class:`.
- [ ] **Step 2:** Update the README sentence. `wc -l docs/pipeline/README.md` ≤ 90.
- [ ] **Step 3:** Push. Watch `pipeline-diagram` with `gh run watch`. Fix any d2 error from `--log-failed` and repeat.
- [ ] **Step 4:** Download `pipeline-render`, copy every `*.svg` and `rendered.sha256` into `docs/pipeline/`, and commit `docs(#166): render refresh sub-boards`. Push.
- [ ] **Step 5:** Run `uv run pytest -q`, `uv run ruff check . && uv run mypy src`, and `python3 docs/pipeline/check.py` (`0 errors`). Watch the run on the final head until both jobs (`render`, `models`) are green.
