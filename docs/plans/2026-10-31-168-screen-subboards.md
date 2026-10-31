# Screen sub-boards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Six d2 sub-boards (`screen-snapshot`, `screen-coverage`, `screen-quality`, `screen-value`, `screen-traps`, `screen-ranking`) draw the checked screen statechart one level below `screen.d2`, so a reader who clicks a layer on `screen.svg` follows one company through it: objective, how, criteria, what comes out.

**Architecture:** Each sub-board is a flat d2 board. Its nodes are the model states of one `groups` value of `docs/pipeline/models/screen.view.js`, the neighbouring states the flow enters from or leaves to, one decision node per screener rule on the three rule boards, three fixed nodes (`objective`, `back`, `out`) and the stores and files at the edge of the flow. Its edges are the model steps, labelled with the view's `steps` text, with the how on further lines. The generic tests from #164 and #166 already enforce the conventions; this issue registers `screen`, adds screen-specific citations and phrases, and a rule-placement test. d2 renders in CI only.

**Tech Stack:** d2 v0.9.0 + TALA (CI only), pytest, `docs/pipeline/check.py`.

**Spec:** issue #168 (its body, including "Sub-board conventions"). Parent story #161, plan comment decisions 2 to 8. Worked examples: `docs/pipeline/refresh-*.d2` and `docs/plans/2026-10-31-166-refresh-subboards.md` (its Global Constraints and assumptions A1 to A5 apply here unchanged).

## Global Constraints

- New files: `docs/pipeline/screen-snapshot.d2`, `screen-coverage.d2`, `screen-quality.d2`, `screen-value.d2`, `screen-traps.d2`, `screen-ranking.d2`. Their `.svg` files and `rendered.sha256` come only from the CI artifact `pipeline-render`; never edit an SVG or the hash by hand.
- Every sub-board starts with `...@classes`, a blank line, `direction: down`. `class:` is a node's first attribute. Expand every acronym at its first use on each board, on that line or before it in file order (nodes come before edges): WACC, DCF, MoS, ROIC, ROE, EPS, P/E, P/BV, EV, EBIT, EBITDA, CAGR, FX, ADR, GDP as they appear. No all-caps token outside `_ACRONYMS` / `_ACRONYMS_EXEMPT`.
- Every number other than 0, 1 and 100 on a node or edge label is cited by `@const`/`@param` on that line; otherwise it is a word ("seven quality gates", "the last five years" is not allowed when 5 is a param: cite it).
- At most 24 edges per sub-board; aim for 20.
- A node that is a model state has that state's `states` label as the exact first line. An edge that is a model step has that step's `steps` label as the exact first line, and it joins the two states the `.tla` action joins (an action with `phase \in {a, b}` is one edge per source state).
- A state is `decision` when two or more of its model steps carry a `[condition]`, else `step`; this holds for neighbours too. Every edge leaving a decision has a `[...]` in its label; a model label without one gets the condition on its second line.
- Every step and decision node has a directive on its line or the line before. A neighbour `step` node with no incoming (outgoing) edge carries `# No incoming edge: the flow enters from screen-<sub>` (`# No outgoing edge: ...`).
- No `#`, `{`, `}`, `|` or `"` inside a quoted label. Write `×`, `÷`, `−`, `≤`, `≥` as on `screen.d2`.
- `screen.d2` gains six `link:` lines and nothing else. `pipeline.d2` does not change. No file under `src/` changes. `screen.tla` and `screen.cfg` do not change.
- Formulas, thresholds, names and paths are copied from the code and cited. `screen.d2` carries all of them with their directives: reuse its wording and directives.

## Model facts the boards must match (from `screen.view.js` and `screen.tla`)

Group order, which is also the order of the `out` links: snapshot → coverage → quality → value → traps → ranking → `./screen.svg`.

Decision states (the test's rule, `test_subboard_state_classes`, which classifies only nodes whose first line is a model state label): `listed`, `loaded`, `currency_read`, `region_set`, `ratios`, `cap_in_usd`, `benchmark_looked`, `benchmarked`, `quality_passed`, `quality_failed`, `traps_passed`, `first_ranked`. Every other state is a `step`.

Steps per group (source → target):

- snapshot (12 inside): `listed→loaded` ×2, `loaded→currency_read` ×2, `currency_read→region_set` ×3, `region_set→tax_set` ×2, `tax_set→ratios`, `ratios→cap_in_usd` ×2. Out of the group: `cap_in_usd→benchmark_looked` ×3 (into coverage).
- coverage (5 inside): `benchmark_looked→rejected_coverage` ×2, `benchmark_looked→benchmarked`, `benchmarked→rejected_coverage`, `benchmarked→measured`. Out: `measured→quality_passed`, `measured→quality_failed` (into quality); `rejected_coverage→rejected_saved` (into ranking).
- quality → value: `AValueIndicatorPasses`, `AValueIndicatorPassesAnotherFails`, `NoValueIndicatorPasses`, `EveryValueIndicatorIsSkipped`, each from `quality_passed` and from `quality_failed` (8 edges).
- value → traps: `EveryTrapDetectorPasses`, `ATrapDetectorFails`, each from `value_passed`, `value_failed`, `value_skipped` (6 edges).
- traps (2 inside): `traps_passed→rejected_rules`, `traps_failed→rejected_rules`. Out: `traps_passed→survivor`, `rejected_rules→rejected_saved` (into ranking).
- ranking (12 inside): `survivor→metrics→percentiles→first_ranked`, `first_ranked→kept` ×2, `first_ranked→cut`, `kept→valued`, `kept→unvalued`, `valued→rescored`, `unvalued→rescored`, `rescored→saved→reported`. `Done` ("the run ends") is drawn once, as `reported -> out`.

## Declared decisions

1. **Cross-layer steps where the cap forbids both boards.** The issue requires a [pass]/[fail](/[skipped]) branch per rule into the layer's verdict state: 14 edges on quality, 12 on value, 11 on traps. Drawing the 8 quality→value steps on both boards puts screen-quality at 25 edges, and value→traps on both puts screen-value at 27. So these two families of steps are drawn once, on the board of the layer they enter (value, traps), and the leaving board sends each verdict state to `out` with "on to the <next layer> [always: every layer runs]". Every other cross-group step is drawn on both boards, as on refresh. `docs/pipeline/README.md`'s line "A step that crosses groups is drawn on both boards" gains this exception in place (the README stays at 90 lines).
2. **Rules are decision nodes with no incoming edge.** One node per rule, key = rule name, label "`<rule name>`\n<threshold as plain math>\n<what a missing figure does>", class `decision`, with `@rule <name>` and every `@param <name>.<p>` on its line. Branches: `[pass]` into the passing verdict state, `[fail]` into the failing one, `[skipped]` where the rule can skip. Value: `[skipped]` → `value_skipped`. Traps: `roic_above_sector_wacc` `[skipped]` → `traps_failed` ("a skip is eliminatory, ADR 0006 (Implemented)"). Quality rules never skip. Rules of a layer: the preset section (`quality_gates` → screen-quality, `value_indicators` → screen-value, `trap_detection` → screen-traps).
3. **Ratio formulas** go in a note child `formulas` of the `ratios` state (as `screen.d2` does under `snapshot.ratios`), a multi-line `|md` block, so the edge labels stay short.
4. **Neighbours per board.**
   - snapshot: `benchmark_looked` (decision, link coverage).
   - coverage: `cap_in_usd` (decision, link snapshot), `quality_passed`, `quality_failed` (decision, link quality), `rejected_saved` (step, link ranking, no outgoing edge).
   - quality: `measured` (step, link coverage, no incoming edge).
   - value: `quality_passed`, `quality_failed` (decision, link quality).
   - traps: `value_passed`, `value_failed`, `value_skipped` (step, link value, no incoming edge), `survivor` (step, link ranking), `rejected_saved` (step, link ranking, no outgoing edge).
   - ranking: `traps_passed` (decision, link traps), `rejected_coverage` (step, link coverage, no incoming edge), `rejected_rules` (step, link traps, no incoming edge).
5. **Hand-off to analyze.** screen-ranking has an extra `step` node `analyze` ("the analyze stage values the ticker by DCF, see the analyze board", `link: "./analyze.svg"`, `@symbol bot.screener.engine._batch_dcf_margins`), with `kept -> analyze` and `assumptions -> analyze` (file `config/assumptions/TICKER.yaml`, `@symbol bot.valuator.assumptions.conventional_override_path`). The model steps `kept→valued`/`kept→unvalued` stay drawn directly.
6. **Stage-board links** on the containers of `screen.d2`: `snapshot` → `./screen-snapshot.svg`, `coverage_gate` → `./screen-coverage.svg`, `quality_gates` → `./screen-quality.svg`, `value_indicators` → `./screen-value.svg`, `trap_detection` → `./screen-traps.svg`, `ranking` → `./screen-ranking.svg`.
7. **`site` workflow** runs only on a push to master; its commands are run locally on the head and the PR lists it as manual verification (as #164, #166).

## Assumptions (from the plan grilling; decided, with the rejected alternative)

- A1. **Cap over the both-boards convention** (decision 1). The issue fixes both the cap ("At most 24 edges per sub-board") and the rule branches ("[pass], [fail] and, where the rule can skip, [skipped] branches into the layer's verdict state"); its remedy for an oversize board ("split the sub-board and the group together") cannot help, because the rule branches belong to one layer. The both-boards line is a README convention, not a test: `test_subboard_edges_join_the_model_states` checks the union of the stage's boards. Rejected: dropping rule branches (breaks the issue), raising the cap (the issue fixes it).
- A2. **Rule nodes are decisions with no incoming edge**, as on `screen.d2` (`quality_gates.*` etc.). `test_subboard_state_classes` classifies only model states; `test_every_step_has_purpose_and_edges` checks only `step` nodes. Rejected: an edge from the entry state into each rule (+7 edges on quality, over the cap).
- A3. **`Done` drawn once**, `reported -> out: "the run ends"`. `test_step_labels_are_drawn` needs the label on one edge; `_transitions` skips `Done`. `cut` is terminal with a `No outgoing edge` comment. Rejected: three `Done` edges, which add nothing for the reader.
- A4. **Only `ranking` links `screen-ranking`**; `persist_and_report` gets no link. `test_stage_board_links_its_subboards` requires every sub-board to be linked, not every container to link. Rejected: two links to one target, against the issue's "change nothing else".
- A5. **Red intermediate commits.** The evals commit fails by design (stage 3), and the issue says the render check "fails once, on the push before the SVGs are committed; that is expected". Only the final head must be green. A stalled render leaves `rendered.sha256` stale against the `.d2` sources on this branch only.
- A6. **Rendering on a branch push.** `pipeline-diagram.yml` runs `on: [push, workflow_dispatch]`, so it renders this branch; `site.yml` runs only on master (decision 7).
- A7. **README in place.** `test_readme_has_build_and_check_commands` caps it at 90 lines; it has 90 today. The count sentence is rewritten and the exception is appended to the existing "A step that crosses groups" bullet, without new lines.
- A8. **ADR mention in a multi-line note.** `test_subboard_digits_are_cited` reads single-line labels and would read `0006` as an uncited 6; no `@const` can cite an ADR number. The ADR goes in a multi-line `|md` note child, as on `screen.d2`, with its `@file`. Rejected: dropping the ADR (the issue asks for it on screen-coverage).

## Review Focus

1. **A rule drawn on the wrong layer or twice** (e.g. `roic_above_sector_wacc` on screen-quality). Expected: each registered rule is a decision node on exactly the sub-board of its preset section. Test: `test_screen_rules_sit_on_their_layer_subboard` (Task 1).
2. **A threshold shown with the wrong value or uncited** (100M, 5 years, 4, 2, 4 of 5, 0.5, 0.7, 8%, −5%, −200 basis points, 0.1, 5%, 0.40/0.30/0.20/0.10, MoS 0.5, 21%). Tests: `test_subboard_digits_are_cited`, `test_every_directive_is_valid`, `_REQUIRED_PARAMS` per sub-board (Task 1).
3. **Coverage reasons out of precedence order** on screen-coverage. Test: `test_screen_coverage_reasons_in_order` (Task 1): `industry_unmapped`, `benchmark_missing`, `currency_uncovered` appear in that order in the visible text.
4. **A [skipped] branch into the wrong state** (a skipped trap detector drawn as passing). Test: `test_screen_skip_branches` (Task 1): on screen-value every edge with `[skipped]` ends in `value_skipped`; on screen-traps every `[skipped]` edge ends in `traps_failed`.
5. **The SVG drops a link** (stage → sub-board, `out` → next, ranking → analyze). Tests: `test_stage_svg_links_its_subboards`, `test_subboard_svg_hrefs`, `test_svg_keeps_every_link` on the SVGs from CI (Task 8).

---

### Task 1: evals (registration, required citations, screen tests)

Done in the evals stage, before any board exists. The new tests fail.

**Files:** Modify `tests/unit/test_pipeline_models.py` (`_SUBBOARDED`), `tests/unit/test_pipeline_diagram.py` (`_REQUIRED_*`), `tests/unit/test_pipeline_subboards.py` (screen tests).

- [ ] **Step 1:** `_SUBBOARDED = ("site", "refresh", "screen")`.
- [ ] **Step 2:** Required citations keyed by stem:
  - symbols: `screen-snapshot`: `bot.screener.engine.build_company_data`, `bot.screener.engine._resolve_region`, `bot.screener.engine._resolve_tax_rate`, `bot.screener.engine._market_cap_usd`; `screen-coverage`: `bot.screener.engine.CoverageReason`, `bot.screener.benchmarks.load_industry_benchmarks`; `screen-quality`, `screen-value`, `screen-traps`: `bot.screener.engine.evaluate_company`; `screen-value` also `bot.screener.rules._value_score`; `screen-ranking`: `bot.screener.ranking.rank`, `bot.screener.ranking.rescore_with_margins`, `bot.screener.ranking._percentiles`, `bot.screener.persist.persist_candidates`.
  - tables: `screen-snapshot`: `companies`, `financials_annual`, `prices_daily`, `damodaran_country`, `currencies`; `screen-coverage`: `damodaran_industry`; `screen-ranking`: `screener_candidates`.
  - files: `screen-coverage`: `config/currencies.yaml`, `docs/adr/0006-unmeasurable-companies-leave-the-universe.md`.
  - consts: `screen-snapshot`: `bot.screener.engine.DEFAULT_REGION`, `bot.screener.engine.DEFAULT_TAX_RATE`; `screen-quality`: `bot.screener.rules.DEFAULT_EXCLUDED_SECTORS`; `screen-ranking`: `bot.screener.ranking.PLACEHOLDER_MARGIN_OF_SAFETY`.
  - enums: `screen-coverage`: `bot.screener.engine.CoverageReason`.
  - rules and params, derived from the preset with a helper `_preset_layer_params(section) -> dict[str, Any]` (the `<rule>.<param>` keys of one section) and `_preset_rule_layers()`: `_REQUIRED_RULES["screen-quality" | "screen-value" | "screen-traps"]` = the rule names of `quality_gates` | `value_indicators` | `trap_detection`; `_REQUIRED_PARAMS` the same per section, and `_REQUIRED_PARAMS["screen-ranking"]` = the four `ranking.*` keys. A constant `_SCREEN_LAYER_BOARDS = {"quality_gates": "screen-quality", "value_indicators": "screen-value", "trap_detection": "screen-traps"}` drives both.
- [ ] **Step 3:** In `test_pipeline_subboards.py`:
  - `test_screen_has_six_subboards`: screen stems equal the six names.
  - `test_screen_rules_sit_on_their_layer_subboard`: for every name in `registered_rules()`, the screen sub-boards on which a `decision` node carries `@rule <name>` on its line (or the line before) equal exactly `{_SCREEN_LAYER_BOARDS[layer of the rule in the preset]}`.
  - `test_screen_skip_branches`: as Review Focus 4.
  - `test_screen_coverage_reasons_in_order`: as Review Focus 3, on screen-coverage.
  - `test_screen_subboard_text` (parametrized): normalized visible text contains
    - `screen-snapshot`: `"ROE = net income ÷ total equity"`, `"EV ÷ EBITDA = (market cap + net debt) ÷ EBITDA"`, `"ROIC = EBIT × (1 − tax) ÷ (total debt + total equity)"`, `"free cash flow yield = free cash flow ÷ market cap"`, `"21%"`
    - `screen-coverage`: `"ADR 0006 (Implemented)"`, `"config/currencies.yaml"`
    - `screen-quality`: `"100M"`, `"≤ 4"`, `"≥ 2"`, `"≤ 0.5"`
    - `screen-value`: `"0.7 × sector median"`, `"8%"`, `"value metric = highest score among passing indicators"`
    - `screen-traps`: `"−5%"`, `"−200 basis points"`, `"< 0.1"`, `"5%"`
    - `screen-ranking`: `"0.40 × value"`, `"0.30 × quality"`, `"0.20 × growth"`, `"0.10 × margin of safety"`, `"ties share a percentile"`, `"--top"`, `"0.5"`
- [ ] **Step 4:** Run `uv run pytest -q tests/unit/test_pipeline_subboards.py tests/unit/test_pipeline_models.py tests/unit/test_pipeline_diagram.py`. Expected: the new tests and the screen label-match tests fail (boards missing); everything else passes.
- [ ] **Step 5:** Commit `test(#168): evals`.

### Task 2: screen-snapshot

**Files:** Create `docs/pipeline/screen-snapshot.d2`.

- [ ] **Step 1:** Write the board.
  - `objective`: "Objective: turn one company's stored rows into the figures the screen judges it on: region, tax rate, ratios and market cap in US dollars."
  - States (first line = `states` label), with how lines from `screen.d2`'s `snapshot.*` nodes: `listed` (every company of companies), `loaded` (non-restated financials_annual rows oldest first; newest close and newest market cap from prices_daily), `currency_read` (valuation currency = currency of the newest non-restated annual row), `region_set` (`@const bot.screener.engine.DEFAULT_REGION`), `tax_set`, `ratios` (with the `formulas` note of decision 3: net debt, ROE, EPS, P/E, BV per share, P/BV, EV ÷ EBITDA, ROIC, free cash flow yield, operating margin, histories), `cap_in_usd`.
  - Neighbour `benchmark_looked`.
  - Stores (class `store`, `@table`): `companies → listed`, `financials_annual → loaded`, `prices_daily → loaded`, `damodaran_country → region_set`, `damodaran_country → tax_set`, `currencies → cap_in_usd`.
  - `out`: "Comes out:" one company snapshot: ratios and histories, market cap in USD or empty, region, tax rate, valuation currency, Damodaran industry or none. `link: "./screen-coverage.svg"`. Fed from `benchmark_looked` with `[always]`.
  - Edges: 15 model + 6 store + 1 out = 22. Edge how lines: the region rules (China, India, Japan; the country grouping mapped to a dataset region; else US), the tax rule (country rate within [0, 1), else 21%, cite `DEFAULT_TAX_RATE`), the USD conversion (market cap × rate_to_usd on or before its date).
- [ ] **Step 2:** Run the three test files with `-k screen`. Expected: this stem passes everything except the SVG-dependent tests (`test_subboard_svg_hrefs`, `test_svg_keeps_every_link`, `test_each_board_has_a_rendered_svg`, `test_svgs_show_their_step_labels`, `test_check_py_exits_zero`) and the label-match tests of the other groups.
- [ ] **Step 3:** Commit `docs(#168): screen-snapshot sub-board`.

### Task 3: screen-coverage

**Files:** Create `docs/pipeline/screen-coverage.d2`.

- [ ] **Step 1:** Write the board.
  - `objective`: "Objective: decide whether the company can be measured at all, and if not, remove it from the universe with exactly one reason."
  - States: `benchmark_looked` (newest-year damodaran_industry row for (industry, region), industry = industry_damodaran else the provider industry, `@symbol bot.screener.benchmarks.load_industry_benchmarks`), `benchmarked`, `rejected_coverage` (the three reasons in precedence order, `@enum bot.screener.engine.CoverageReason @symbol bot.screener.engine.CoverageReason`), `measured` ("every rule of the three layers runs").
  - The ADR goes in a multi-line `|md` note child `adr` of `rejected_coverage` (assumption A8), cited `@file docs/adr/0006-unmeasurable-companies-leave-the-universe.md` on its declaration line: first line `Architecture decision record (ADR):`, second line `ADR 0006 (Implemented): a company that cannot be measured leaves the universe before any rule runs.`
  - Neighbours per decision 4. Stores/files: `damodaran_industry → benchmark_looked`, `currencies_yaml` (file, `@file config/currencies.yaml`) `→ benchmarked`.
  - `out`: "Comes out:" a measured company with its sector benchmark (medians and WACC), or one rejected row with one reason. `link: "./screen-quality.svg"`. Fed from `measured`.
  - Edges: 3 in + 5 inside + 2 to quality + 1 to `rejected_saved` + 2 sources + 1 out = 14.
- [ ] **Step 2:** Tests as Task 2. **Step 3:** Commit `docs(#168): screen-coverage sub-board`.

### Task 4: screen-quality

**Files:** Create `docs/pipeline/screen-quality.d2`.

- [ ] **Step 1:** Write the board.
  - `objective`: "Objective: drop the company if any of the seven quality gates fails; every gate runs, so every failure is recorded."
  - States `quality_passed`, `quality_failed`; neighbour `measured`.
  - Seven rule nodes (decision 2), thresholds as on `screen.d2`'s `quality_gates.*`: market cap in USD ≥ 100M (missing fails); annual rows ≥ 5; excluded sectors (financial services label, bank, insurance; `@const bot.screener.rules.DEFAULT_EXCLUDED_SECTORS @symbol bot.reference.sectors.is_financial_services`); net debt ÷ EBITDA ≤ 4 (net debt ≤ 0 passes; EBITDA ≤ 0 with positive net debt fails); EBIT ÷ interest expense ≥ 2 (interest ≤ 0 passes); operating cash flow > 0 in ≥ 4 of the last 5 years; goodwill ÷ total assets ≤ 0.5.
  - `out`: "Comes out:" the company with its failed quality gates (none or several), on to the value indicators whatever the result. `link: "./screen-value.svg"`.
  - Edges: 2 model in + 14 rule branches + `quality_passed -> out`, `quality_failed -> out` (decision 1) = 18.
- [ ] **Step 2:** Tests as Task 2. **Step 3:** Commit `docs(#168): screen-quality sub-board`.

### Task 5: screen-value

**Files:** Create `docs/pipeline/screen-value.d2`.

- [ ] **Step 1:** Write the board.
  - `objective`: "Objective: keep the company only if it is cheap on at least one value indicator against its sector, and score how cheap."
  - States `value_passed` (score lines: score = (threshold − value) ÷ threshold clipped to [0, 1], threshold = 0.7 × sector median; free cash flow yield score = min(1, yield ÷ minimum); value metric = highest score among passing indicators; `@symbol bot.screener.rules._value_score`), `value_failed`, `value_skipped`; neighbours `quality_passed`, `quality_failed`.
  - Four rule nodes: P/E < 0.7 × sector median P/E; EV/EBITDA < 0.7 × sector median EV/EBITDA; P/BV < 0.7 × sector median P/BV and ROE > sector median ROE; free cash flow yield > 8%. Each with `[pass]`, `[fail]`, `[skipped]` (when the median or the company figure is missing or ≤ 0).
  - `out`: "Comes out:" the company with its value metric and its failed indicators, on to the trap detectors whatever the result. `link: "./screen-traps.svg"`.
  - Edges: 8 in (decision 1, each with a second-line condition when its label has none) + 12 rule branches + 3 to `out` = 23.
- [ ] **Step 2:** Tests as Task 2. **Step 3:** Commit `docs(#168): screen-value sub-board`.

### Task 6: screen-traps

**Files:** Create `docs/pipeline/screen-traps.d2`.

- [ ] **Step 1:** Write the board.
  - `objective`: "Objective: drop a company that looks cheap for a reason, then decide whether it survives all three layers."
  - States `traps_passed`, `traps_failed`, `rejected_rules` ("failed rules of every layer recorded"); neighbours per decision 4.
  - Five rule nodes: average revenue growth over the last 3 years > −5% (average growth = mean of (current − previous) ÷ previous; fewer revenues or undefined growth fails); operating margin change (last − first) over the last 3 years ≥ −200 basis points (write "basis points", never "bps": the digit test reads `bps` as a unit and −200 bps as −0.02, while the preset value is −200.0; no "× 10,000" factor on the label); ROIC > sector WACC (`[skipped]` → `traps_failed`, "a skipped detector counts as failed", `@symbol bot.screener.engine.evaluate_company`; no ADR number on this board); Sloan ratio (net income − operating cash flow) ÷ total assets < 0.1; average diluted share growth ≤ 5% a year.
  - `out`: "Comes out:" a survivor with its value, quality and growth inputs, or a rejected company with its failed rules. `link: "./screen-ranking.svg"`. Fed from `survivor`.
  - Edges: 6 in + 2 inside + 11 rule branches + `traps_passed -> survivor` + `rejected_rules -> rejected_saved` + `survivor -> out` = 22.
- [ ] **Step 2:** Tests as Task 2. **Step 3:** Commit `docs(#168): screen-traps sub-board`.

### Task 7: screen-ranking

**Files:** Create `docs/pipeline/screen-ranking.d2`.

- [ ] **Step 1:** Write the board.
  - `objective`: "Objective: rank the survivors, keep the best N, value them by DCF and re-rank with their real margin of safety."
  - States: the twelve ranking states; neighbours per decision 4; the `analyze` node and `assumptions` file of decision 5.
  - How lines, from `screen.d2`'s `ranking.*` and `persist_and_report.*`: metrics (value, quality = (ROIC − sector WACC) + ROE, growth = revenue CAGR); percentile = 0-based rank among distinct values ÷ (distinct values − 1), ties share a percentile, one survivor or all equal: 1; score = 100 × (0.40 × value + 0.30 × quality + 0.20 × growth + 0.10 × margin of safety) with the four `@param ranking.*`; first pass MoS 0.5 (`@const bot.screener.ranking.PLACEHOLDER_MARGIN_OF_SAFETY`), best first, ties by ticker; `--top N` keeps the best N; second pass margin of safety = intrinsic value ÷ price; rescore keeps first-pass percentiles; persisted columns; report columns.
  - Stores/outputs: `screener_candidates` (`saved →`, `rejected_saved →`), `report` (output, `reports/YYYY-MM-DD/screen/<preset>.md and .csv`, `reported →`).
  - `out`: "Comes out:" the shortlist rows of the run in screener_candidates and the shortlist report; rejected rows with their reasons. `link: "./screen.svg"`. Fed by `reported -> out: "the run ends"`.
  - Edges: 12 inside + 3 in + Done + 3 analyze (`kept -> analyze`, `assumptions -> analyze`, `analyze -> valued` "margin of safety = intrinsic value ÷ price, or an error") + 2 store + 1 report = 22. `cut` carries `# No outgoing edge: the run ends here`; `rejected_saved` has its edge into `screener_candidates`.
- [ ] **Step 2:** Tests as Task 2. **Step 3:** Commit `docs(#168): screen-ranking sub-board`.

### Task 8: stage links, README, render

**Files:** Modify `docs/pipeline/screen.d2` (six `link:` lines, decision 6), `docs/pipeline/README.md` (sub-board count and names, the decision 1 exception; still ≤ 90 lines). Then the CI render loop of the issue: push, `gh run watch`, download `pipeline-render`, copy every SVG and `rendered.sha256`, commit, push; a d2 error or an edge layout that drops a link is fixed in the `.d2`.

- [ ] **Step 1:** Add the links and README edits; run the three test files: everything passes except the SVG-dependent tests.
- [ ] **Step 2:** Commit `docs(#168): link the screen sub-boards`; push; render loop until `pipeline-diagram` is green on the head with the committed SVGs.
- [ ] **Step 3:** Full suite, `uv run ruff check . && uv run mypy src`, `python3 docs/pipeline/check.py` (`0 errors`), and the `site` workflow's commands locally.

## Grilling

- Rounds: 1 (the revisions changed counts, phrases and one edge, not the task list or the seam).
- Questions: 18. Sources: CODE 14 (`tests/unit/test_pipeline_models.py`, `test_pipeline_subboards.py`, `test_pipeline_diagram.py`, `screen.tla`, `screen.view.js`, `pipeline-diagram.yml`, `check.py`), ISSUE 3, NO SOURCE 1 (Q2, cap vs both-boards: technical assumption A1).
- Fixes: traps edge count (21 → 22); "−200 bps" → "−200 basis points" (the digit test reads bps as a unit); the ADR phrase moved to a note (A8); `analyze -> valued` added so the `analyze` step has an outgoing edge.
- Assumptions: A1–A8. Issues opened: none.
