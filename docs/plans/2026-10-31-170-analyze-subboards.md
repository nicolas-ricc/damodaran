# Analyze sub-boards Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Seven d2 sub-boards (`analyze-inputs`, `analyze-story`, `analyze-assumptions`, `analyze-dcf`, `analyze-sensitivity`, `analyze-flags`, `analyze-verdict`) draw the checked analyze statechart one level below `analyze.d2`, so a reader who clicks a section on `analyze.svg` follows one ticker through it: objective, how, criteria, what comes out.

**Architecture:** Each sub-board is a flat d2 board. Its nodes are the model states of one `groups` value of `docs/pipeline/models/analyze.view.js`, the neighbouring states the flow enters from or leaves to, three fixed nodes (`objective`, `back`, `out`), and the stores, files and outputs at the edge of the flow. Its edges are the model steps, labelled with the view's `steps` text, with the how on further lines. The generic tests from #164/#166/#168 already enforce the conventions; this issue registers `analyze`, adds analyze-specific citations and phrases. d2 renders in CI only.

**Tech Stack:** d2 v0.9.0 + TALA (CI only), pytest, `docs/pipeline/check.py`.

**Spec:** issue #170 (its body, including "Sub-board conventions"). Parent story #161, plan comment decisions 2 to 8. Worked examples: `docs/pipeline/screen-*.d2` and `docs/plans/2026-10-31-168-screen-subboards.md` (its Global Constraints and assumptions A1 to A8 apply here unchanged).

## Global Constraints

- New files: `docs/pipeline/analyze-inputs.d2`, `analyze-story.d2`, `analyze-assumptions.d2`, `analyze-dcf.d2`, `analyze-sensitivity.d2`, `analyze-flags.d2`, `analyze-verdict.d2`. Their `.svg` files and `rendered.sha256` come only from the CI artifact `pipeline-render`; never edit an SVG or the hash by hand.
- Every sub-board starts with `...@classes`, a blank line, `direction: down`. `class:` is a node's first attribute. Node keys are lower-case. Expand every acronym at its first use on each board, on that line or before it in file order (nodes before edges): DCF, WACC, MoS, EBIT, NOPAT, FCFF, EV, GDP, D/E, CAGR, ERP, P/E, EPS as they appear. No all-caps token outside `_ACRONYMS` / `_ACRONYMS_EXEMPT` (YAML, JSON, HTML, US, TICKER, YYYY, MM, DD are exempt).
- Every number other than 0, 1 and 100 on a node or edge label (quoted or one-line `|md`) is cited by `@const`/`@param` on that source line; counts are words ("five by five").
- At most 24 edges per sub-board; aim for 20. Every edge is one line `a -> b: "label"`.
- A node that is a model state has that state's `states` label as its exact first line. An edge that is a model step has that step's `steps` label as its exact first line and joins the two states the `.tla` action joins.
- A state is `decision` when two or more of its model steps carry a `[condition]`, else `step`; this holds for neighbours too. Every edge leaving a decision has a `[...]`; a model label without one gets the condition on its second line.
- Every step and decision node has a directive on its line or the line before. A neighbour or terminal `step` node with no incoming (outgoing) edge carries `# No incoming edge: the flow enters from analyze-<sub>` (`# No outgoing edge: ...`) as a trailing comment.
- No `#`, `{`, `}`, `|` or `"` inside a quoted label. Write `×`, `÷`, `−`, `≤`, `≥`, `Σ` as on `analyze.d2`.
- `analyze.d2` gains seven `link:` lines and nothing else. `pipeline.d2` does not change. No file under `src/` changes. `analyze.tla` and `analyze.cfg` do not change.
- Formulas, thresholds, names and paths are copied from the code and cited. `analyze.d2` carries all of them with their directives and is pinned by `_ANALYZE_TEXT` and the direction tests: reuse its wording and directives.

## Model facts the boards must match (from `analyze.view.js` and `analyze.tla`)

Group order, also the order of the `out` links: inputs → story → assumptions → dcf → sensitivity → flags → verdict → `./analyze.svg`. Every action has one source state.

Decision states: `asked`, `chosen`, `loaded`, `signals`, `not_distressed`, `not_cyclical`, `not_high_growth`, `classified`, `story_set`, `currency_read`, `growth_set`, `margin_set`, `scalars_set`, `weights_set`, `ready`, `wacc_computed`, `grid_done`, `story_margin_checked`, `reinvestment_checked`, `beta_checked`, `country_checked`. Every other state is a `step` (notably `override_picked`, `region_set`, `sector_read`, `tg_set`, `shares_ok`, `resolved`, `tornado_done`, `tv_share_checked`, `verdict_given`, and the end states).

Model labels without a [condition] that leave a decision, so need one on line 2: `TheTickersAreGiven` (`asked`), `RegionFromItsCountryGrouping` (`loaded`).

Steps per group (source → target):

- inputs (14 inside): `asked→chosen` ×2, `asked→command_stops` ×3, `chosen→override_picked` ×3, `override_picked→not_found`, `override_picked→loaded`, `loaded→region_set` ×3, `region_set→signals`. Out: `signals→classified` (ItIsDistressed), `signals→not_distressed`.
- story (9 inside, after the two above): `not_distressed→classified`, `not_distressed→not_cyclical`, `not_cyclical→classified`, `not_cyclical→not_high_growth`, `not_high_growth→classified` ×2, `classified→crashed`, `classified→story_set` ×2. Out: `classified→cannot_value` (into dcf), `story_set→sector_read` ×2 (into assumptions).
- assumptions (14 inside): `sector_read→currency_read` ×2, `currency_read→growth_set` ×2, `growth_set→margin_set` ×2, `margin_set→scalars_set` ×2, `scalars_set→weights_set` ×2, `weights_set→tg_set` ×3. Out: `scalars_set→cannot_value`, `tg_set→ready` (into dcf).
- dcf (13 inside): `ready→cannot_value` ×2, `ready→shares_ok`, `shares_ok→cannot_value`, `shares_ok→resolved`, `resolved→cannot_value`, `resolved→wacc_computed`, `wacc_computed→cannot_value`, `wacc_computed→projected`, `projected→terminal_valued→ev_found→equity_found→valued`. Out: `valued→tornado_done`.
- sensitivity (1 inside): `tornado_done→grid_done`. Out: `grid_done→story_margin_checked` ×3.
- flags (9 inside): `story_margin_checked→reinvestment_checked` ×3, `reinvestment_checked→beta_checked` ×3, `beta_checked→tv_share_checked` ×2, `tv_share_checked→country_checked`. Out: `country_checked→verdict_given` ×4.
- verdict (2 inside): `verdict_given→sanity_checked`, `sanity_checked→reported`. `Done` ("the run of this ticker ends") leaves the five end states; it is drawn once, as `reported -> out`.

## Declared decisions

1. **"exit code 2" becomes "exit code two" in the view** (issue task 7, "a label unreadable"). `test_subboard_digits_are_cited` reads every digit on a sub-board label, no constant holds an exit code, and 2 is not exempt (0, 1, 100 are). The refresh sub-boards already write "exit code two". Four labels of `analyze.view.js` change: state `not_found`, steps `TheArgumentsAreRefused`, `TheScreenLeftNoCandidate`, `TheTickerIsUnknown`. "exit code 1" stays (1 is exempt). The TLA+ logic does not change; the `models` job re-checks the view in CI.
2. **Every cross-group step is drawn on both boards** (no screen-style exception is needed: the largest board is 23 edges). Its far end is a neighbour node with `link:` to its sub-board.
3. **`Done` drawn once**, `reported -> out: "the run of this ticker ends"` (screen A3). The other end states (`command_stops`, `not_found`, `crashed`, `cannot_value`) carry `# No outgoing edge: the run of this ticker ends here`.
4. **Neighbours per board.**
   - inputs: `classified` (decision, link story; no outgoing edge drawn), `not_distressed` (decision, link story).
   - story: `signals` (decision, link inputs), `cannot_value` (step, link dcf, no outgoing edge), `sector_read` (step, link assumptions, no outgoing edge).
   - assumptions: `story_set` (decision, link story), `cannot_value` (step, link dcf, no outgoing edge), `ready` (decision, link dcf).
   - dcf: `tg_set` (step, link assumptions, no incoming edge), `classified`, `scalars_set` (decision, link story / assumptions), `tornado_done` (step, link sensitivity, no outgoing edge).
   - sensitivity: `valued` (step, link dcf, no incoming edge), `story_margin_checked` (decision, link flags).
   - flags: `grid_done` (decision, link sensitivity), `verdict_given` (step, link verdict, no outgoing edge).
   - verdict: `country_checked` (decision, link flags).
5. **`out` edges.** Each board's `out` is fed by the last state of the group: inputs `signals -> out` `[always]`, story `story_set -> out` `[always]`, assumptions `tg_set -> out`, dcf `valued -> out`, sensitivity `grid_done -> out` `[always]`, flags `country_checked -> out` `[always]`, verdict `reported -> out` (the `Done` label).
6. **Formulas on edges, not in multi-line notes.** A multi-line `|md` block is invisible to the digit test (screen A8), so every formula with a cited digit sits on an edge label line (`\n`-separated) with its directive on that line. One-line `|md` notes are allowed (checked like labels).
7. **Assumption sources on the resolve edges.** Each `...IsResolved` edge lists the ordered sources it tries as numbered lines `1. manual → manual`, `2. ... → story_pattern`, ... (ordinals are exempt from the digit test), copied from `analyze.d2`'s `assumptions.*` nodes. A note `sources` (multi-line `|md`, as on `analyze.d2`) gives the seven `AssumptionSource` values; `@enum bot.valuator.assumptions.AssumptionSource` sits on the `sector_read` node line.
8. **Stage-board links** on `analyze.d2`: container `inputs` → `./analyze-inputs.svg`, `story_type` → `./analyze-story.svg`, `assumptions` → `./analyze-assumptions.svg`, `dcf` → `./analyze-dcf.svg`, `sensitivity` → `./analyze-sensitivity.svg`, `narrative_flags` → `./analyze-flags.svg`, `verdict` → `./analyze-verdict.svg`. `sanity_check` and `reports` get no link (screen A4: every sub-board linked, not every container linking).
9. **README in place**: the count sentence becomes "twenty-two sub-boards" and the boards sentence names `analyze` with seven; still ≤ 90 lines.
10. **`site` workflow** runs only on a push to master; its commands run locally on the head and the PR lists it as manual verification (as #164, #166, #168).

## Review Focus

1. **A DCF formula drifting from `dcf.py`** (wrong discount exponent on the terminal value, NOPAT without tax). Test: `test_analyze_subboard_text["analyze-dcf"]` pins each formula string (Task 1).
2. **A story-type branch out of the classifier's order** (cyclical tested before distressed). The model label match pins which state each branch leaves; `test_analyze_subboard_text["analyze-story"]` pins "first match wins" and the six thresholds through `_REQUIRED_CONSTS` (Task 1).
3. **A threshold shown with the wrong value or uncited** (1.81, 1.0, 0.50, 15%, 25 years, −1%, 25%, 1,000,000, 100,000,000,000, 0.8, 1.2, the grid multipliers, 90%, 1.5, 40%, 80%, 50%, 300 bps, MoS 1.3 and 1.0). Tests: `test_subboard_digits_are_cited`, `test_every_directive_is_valid`, `_REQUIRED_CONSTS` per sub-board (Task 1).
4. **A flag colour or story type missing from its board.** Test: `_REQUIRED_ENUMS` per sub-board, checked by `test_every_directive_is_valid` against the board's visible text (Task 1).
5. **The SVG drops a link** (stage → sub-board, `out` → next, JSON sidecar → site). Tests: `test_stage_svg_links_its_subboards`, `test_subboard_svg_hrefs`, `test_svg_keeps_every_link` on the SVGs from CI (Task 9).

---

### Task 1: evals (registration, required citations, analyze tests, view labels)

Done in the evals stage, before any board exists. The new tests fail.

**Files:** Modify `tests/unit/test_pipeline_models.py` (`_SUBBOARDED`), `tests/unit/test_pipeline_diagram.py` (`_REQUIRED_*`), `tests/unit/test_pipeline_subboards.py` (analyze tests), `docs/pipeline/models/analyze.view.js` (decision 1).

- [ ] **Step 1:** `_SUBBOARDED = ("site", "refresh", "screen", "analyze")`. Change the four view labels of decision 1.
- [ ] **Step 2:** Required citations keyed by stem:
  - symbols: `analyze-inputs`: `bot.valuator.analysis.load_valuation_input`, `bot.cli.analyze`, `bot.reference.regions.dataset_region`; `analyze-story`: `bot.valuator.story_types.classify`, `bot.valuator.story_types._earnings_cv`, `bot.valuator.story_types._cagr`; `analyze-assumptions`: `bot.valuator.assumptions.resolve_assumptions`, `bot.valuator.assumptions._resolve_revenue_growth`, `bot.valuator.assumptions._resolve_operating_margin`, `bot.valuator.assumptions._resolve_weights`, `bot.valuator.assumptions._resolve_terminal_growth`, `bot.valuator.assumptions._resolve_tax_rate`; `analyze-dcf`: `bot.valuator.dcf.dcf`, `bot.valuator.dcf._wacc`; `analyze-sensitivity`: `bot.valuator.sensitivity.tornado`, `bot.valuator.sensitivity.grid_2d`; `analyze-flags`: `bot.valuator.narrative_flags.narrative_flags`, `bot.valuator.narrative_flags.country_exposure_flag`; `analyze-verdict`: `bot.reporting.analysis_report.margin_verdict`, `bot.valuator.analysis._sanity_check`, `bot.reporting.analysis_json.render_analysis_json`.
  - tables: `analyze-inputs`: `screener_candidates`, `companies`, `financials_annual`, `prices_daily`, `damodaran_industry`, `damodaran_country`; `analyze-assumptions`: `damodaran_industry`, `damodaran_country`.
  - files: `analyze-story`: `config/assumptions`; `analyze-assumptions`: `config/assumptions`, `config/currencies.yaml`; `analyze-verdict`: `src/bot/reporting/templates/analysis.md.j2`.
  - consts: `analyze-story`: the six `bot.valuator.story_types._DISTRESS_ALTMAN_Z`, `_DISTRESS_INTEREST_COVERAGE`, `_CYCLICAL_EARNINGS_CV`, `_HIGH_GROWTH_CAGR`, `_MATURE_AGE_YEARS`, `_DECLINE_CAGR`; `analyze-assumptions`: `bot.valuator.assumptions._HORIZON`, `_MIN_CYCLE_YEARS`, `_DEFAULT_TAX_RATE`; `analyze-dcf`: `bot.valuator.analysis.MIN_PLAUSIBLE_SHARES`, `MAX_PLAUSIBLE_SHARES`, `bot.valuator.assumptions._HORIZON`; `analyze-sensitivity`: `bot.valuator.sensitivity._TORNADO_LOW`, `_TORNADO_HIGH`, `_GRID_MULTIPLIERS`; `analyze-flags`: the seven `bot.valuator.narrative_flags._TERMINAL_VALUE_SHARE_CEILING`, `_FOREIGN_REVENUE_MAJORITY`, `_ERP_GAP_THRESHOLD`, `_DEFENSIVE_BETA`, `_HIGH_OPERATING_LEVERAGE`, `_HIGH_FINANCIAL_LEVERAGE`, `_STRETCHED_REINVESTMENT_RATE`; `analyze-verdict`: `bot.web.views.MOS_UNDERVALUED`, `bot.web.views.MOS_FAIR`, `bot.reporting.analysis_json.SCHEMA_VERSION`.
  - enums: `analyze-story`: `bot.valuator.story_types.StoryType`; `analyze-assumptions`: `bot.valuator.assumptions.AssumptionSource`; `analyze-flags`: `bot.valuator.narrative_flags.FlagColor`; `analyze-sensitivity`: `bot.valuator.sensitivity.SensitivityAxis`.
- [ ] **Step 3:** In `test_pipeline_subboards.py`, a section `# Analyze sub-boards (#170).`:
  - `test_analyze_has_seven_subboards`: analyze stems equal the seven names.
  - `test_analyze_subboard_text` (parametrized over `_ANALYZE_TEXT`), normalized visible text contains:
    - `analyze-inputs`: `"--from-screen"`, `"config/assumptions/TICKER.yaml"`, `"China, India, Japan"`, `"net debt = total debt − cash"`, `"interest coverage = EBIT ÷ interest expense"`
    - `analyze-story`: `"first match wins"`, `"Altman Z < 1.81"`, `"coefficient of variation = standard deviation ÷ |mean| of net income"`, `"CAGR = (last ÷ first)^(1 ÷ (years − 1)) − 1"`
    - `analyze-assumptions`: `"story_pattern"`, `"historical_average"`, `"sector_default_damodaran_cross_region"`, `"min(risk-free rate, nominal GDP growth)"`, `"debt weight = D/E ÷ (1 + D/E)"`, `"config/currencies.yaml"`
    - `analyze-dcf`: `"WACC = equity weight × cost of equity + debt weight × pre-tax cost of debt × (1 − tax)"`, `"revenue_t = revenue_t−1 × (1 + g_t)"`, `"EBIT_t = revenue_t × margin_t"`, `"NOPAT_t = EBIT_t × (1 − tax)"`, `"reinvestment_t = (revenue_t − revenue_t−1) ÷ sales-to-capital"`, `"FCFF_t = NOPAT_t − reinvestment_t"`, `"present value_t = FCFF_t ÷ (1 + WACC)^t"`, `"terminal value = FCFF_N+1 ÷ (WACC − g_terminal)"`, `"present value of terminal value = terminal value ÷ (1 + WACC)^N"`, `"EV = Σ present value_t + present value of terminal value"`, `"equity = EV − net debt + adjustments"`, `"going-concern value per share = equity ÷ diluted shares"`, `"intrinsic value per share = (1 − p) × going-concern value per share + p × distress value per share"`
    - `analyze-sensitivity`: `"swing = |intrinsic value at × 1.2 − intrinsic value at × 0.8|"`, `"two widest"`, `"cell = intrinsic value ÷ price"`
    - `analyze-flags`: `"always unknown"`, `"300 bps"`, `"operating leverage = %ΔEBIT ÷ %ΔRevenue"`
    - `analyze-verdict`: `"potentially undervalued"`, `"around fair value"`, `"potentially overvalued"`, `"n/a"`, `"decides nothing"`, `"reports/YYYY-MM-DD/analysis/TICKER.json"`
  - `test_analyze_verdict_outputs`: on `analyze-verdict`, exactly three `output` nodes besides `out`, each with an incoming edge from the `reported` node; the one whose label contains `.json` links `./site.svg`.
  - `test_analyze_gap_notes`: `analyze-story` has a `gap` node whose label starts `Gap:` and contains `Altman Z`; `analyze-flags` has one containing `always unknown`; no other analyze sub-board has a `gap` node.
- [ ] **Step 4:** Run `uv run pytest -q tests/unit/test_pipeline_subboards.py tests/unit/test_pipeline_models.py tests/unit/test_pipeline_diagram.py`. Expected: the new tests and the analyze label-match tests fail (boards missing); everything else passes.
- [ ] **Step 5:** Commit `test(#170): evals`.

### Task 2: analyze-inputs

**Files:** Create `docs/pipeline/analyze-inputs.d2`.

- [ ] **Step 1:** Write the board.
  - `objective`: "Objective: pick the tickers to value, find each one's override file, and load its figures, its dataset region and the signals the classifier reads."
  - States with how lines from `analyze.d2`'s `cli`, `tickers`, `override`, `inputs.*`: `asked` (`@symbol bot.cli.analyze`), `command_stops`, `chosen`, `override_picked` (`@symbol bot.valuator.assumptions.conventional_override_path`), `not_found`, `loaded` (`@symbol bot.valuator.analysis.load_valuation_input`), `region_set` (`@symbol bot.reference.regions.dataset_region`), `signals` (net debt, interest coverage, age, cyclical sector; `@symbol bot.valuator.analysis.analyze @symbol bot.reference.sectors.is_cyclical`).
  - Neighbours per decision 4. Stores (`@table`): `screener_candidates → asked`, `companies → loaded`, `financials_annual → loaded`, `prices_daily → loaded`, `damodaran_industry → loaded`, `damodaran_country → region_set`.
  - `out`: "Comes out:" one loaded company: its newest annual figures and histories, newest close, sector multiples, dataset region, valuation currency, override file or none, and the signals. `link: "./analyze-story.svg"`.
  - Edges: 14 inside + 2 to story + 6 stores + `signals -> out` = 23.
- [ ] **Step 2:** Run the three test files with `-k analyze`. Expected: this stem passes everything except the SVG-dependent tests (`test_subboard_svg_hrefs`, `test_svg_keeps_every_link`, `test_each_board_has_a_rendered_svg`, `test_svgs_show_their_step_labels`, `test_check_py_exits_zero`) and the label-match tests of the other groups.
- [ ] **Step 3:** Commit `docs(#170): analyze-inputs sub-board`.

### Task 3: analyze-story

**Files:** Create `docs/pipeline/analyze-story.d2`.

- [ ] **Step 1:** Write the board.
  - `objective`: "Objective: name the company's story type with the first rule that matches, then let the override file replace it."
  - States `not_distressed`, `not_cyclical`, `not_high_growth`, `classified` (lists the five story types, `@symbol bot.valuator.story_types.classify @enum bot.valuator.story_types.StoryType`; "first match wins"), `crashed`, `story_set` (`@symbol bot.valuator.assumptions.resolve_assumptions`). Neighbours per decision 4.
  - Classifier edges carry the thresholds on line 2+, from `analyze.d2`'s `story_type.*`: distressed (interest coverage ≤ 1.0, Altman Z < 1.81, both consts); cyclical (coefficient of variation formula, population standard deviation, fewer than 2 years or mean 0: not cyclical, `_CYCLICAL_EARNINGS_CV`); high-growth (CAGR formula, ≥ 15%, age ≤ 25 years, unknown age counts as young); mature-decline (CAGR ≤ −1%).
  - The Altman Z gap note: top-level node `altman`, class `gap`, one-line `|md`: "Gap: Altman Z is read by the classifier but computed nowhere, and analyze never passes it; only interest coverage can make a company distressed." with no digit on it.
  - File `override_yaml` (`@file config/assumptions @symbol bot.valuator.assumptions.conventional_override_path`) `→ classified` ("story_type key, read with every other override").
  - `out`: "Comes out:" the story type the assumptions will follow, and the classifier's own type for the report. `link: "./analyze-assumptions.svg"`.
  - Edges: 2 in + 9 inside + `classified -> cannot_value` + 2 to `sector_read` + file + `story_set -> out` = 16.
- [ ] **Step 2:** Tests as Task 2. **Step 3:** Commit `docs(#170): analyze-story sub-board`.

### Task 4: analyze-assumptions

**Files:** Create `docs/pipeline/analyze-assumptions.d2`.

- [ ] **Step 1:** Write the board.
  - `objective`: "Objective: give every DCF input a value and a source, trying the sources of each assumption in order; a missing one leaves it unresolved."
  - States `sector_read` (cross-region fallback, `@symbol bot.valuator.assumptions._load_sector_with_fallback @enum bot.valuator.assumptions.AssumptionSource`), `currency_read` (`@symbol bot.reference.currencies.load_currency_table`), `growth_set`, `margin_set`, `scalars_set`, `weights_set`, `tg_set`; neighbours per decision 4. The `sources` note (decision 7).
  - Edges carry the ordered sources (decision 7), from `analyze.d2`'s `assumptions.*`: growth (5-year path, `_HORIZON`), margin (cyclical with ≥ 4 years, `_MIN_CYCLE_YEARS`), scalars, weights (D/E formula), terminal growth (`@file config/currencies.yaml`, min(risk-free rate, nominal GDP growth)), tax (25%, `_DEFAULT_TAX_RATE`) and bankruptcy (manual or 0).
  - Stores/files: `damodaran_industry → sector_read`, `currencies_yaml → currency_read`, `override_yaml → sector_read` ("manual values, tried first by every assumption"), `damodaran_country → ready` ("country tax rate").
  - `out`: "Comes out:" every assumption with its value and source label, or unresolved. `link: "./analyze-dcf.svg"`.
  - Edges: 2 in + 14 inside + 2 out (`scalars_set -> cannot_value`, `tg_set -> ready`) + 4 sources + `tg_set -> out` = 23.
- [ ] **Step 2:** Tests as Task 2. **Step 3:** Commit `docs(#170): analyze-assumptions sub-board`.

### Task 5: analyze-dcf

**Files:** Create `docs/pipeline/analyze-dcf.d2`.

- [ ] **Step 1:** Write the board.
  - `objective`: "Objective: turn the resolved assumptions into an intrinsic value per share with a two-stage discounted cash flow (DCF), or stop when the company cannot be valued."
  - States `ready`, `shares_ok`, `resolved`, `cannot_value`, `wacc_computed`, `projected`, `terminal_valued`, `ev_found`, `equity_found`, `valued` (`@symbol bot.valuator.dcf.dcf` and the `_wacc` symbol on `wacc_computed`); neighbours per decision 4.
  - The formulas of Task 1's `analyze-dcf` phrases on the edges (decision 6): `TheWaccIsComputed` carries the WACC formula; `TerminalGrowthIsBelowTheWacc` the year loop (N = length of the growth path, 5 unless a manual list differs, `_HORIZON`; revenue, EBIT, NOPAT, reinvestment, FCFF, present value); `TheTerminalValueIsComputed` the year N + 1 and the terminal value and its present value; `TheEnterpriseValueIsSummed` EV and the terminal value share; `TheEquityIsFound` equity and going-concern value per share; `TheValueIsBlended` the blend. `TheSharesAreImplausible` cites `MIN_PLAUSIBLE_SHARES` and `MAX_PLAUSIBLE_SHARES`.
  - `out`: "Comes out:" the intrinsic value per share, EV, equity, terminal value share, WACC and the year table. `link: "./analyze-sensitivity.svg"`.
  - Edges: `tg_set -> ready` + `classified -> cannot_value` + `scalars_set -> cannot_value` + 13 inside + `valued -> tornado_done` + `valued -> out` = 18.
- [ ] **Step 2:** Tests as Task 2. **Step 3:** Commit `docs(#170): analyze-dcf sub-board`.

### Task 6: analyze-sensitivity

**Files:** Create `docs/pipeline/analyze-sensitivity.d2`.

- [ ] **Step 1:** Write the board.
  - `objective`: "Objective: show how far the intrinsic value moves when one assumption, then two at once, is wrong."
  - States `tornado_done` (`@symbol bot.valuator.sensitivity.tornado @enum bot.valuator.sensitivity.SensitivityAxis`, the seven axes), `grid_done` (`@symbol bot.valuator.sensitivity.grid_2d`); neighbours per decision 4.
  - `TheTornadoIsRun` carries the multipliers (`_TORNADO_LOW`, `_TORNADO_HIGH`), the swing formula and "an end with g_terminal ≥ WACC: no value, ranked last"; `TheGridIsRun` the five multipliers (`_GRID_MULTIPLIERS`) and the cell rule.
  - `out`: "Comes out:" the tornado bars widest first and the five by five grid of margins of safety. `link: "./analyze-flags.svg"`.
  - Edges: 1 in + 1 inside + 3 to flags + `grid_done -> out` = 6.
- [ ] **Step 2:** Tests as Task 2. **Step 3:** Commit `docs(#170): analyze-sensitivity sub-board`.

### Task 7: analyze-flags

**Files:** Create `docs/pipeline/analyze-flags.d2`.

- [ ] **Step 1:** Write the board.
  - `objective`: "Objective: raise five narrative flags for a human reader; they decide nothing and enter no ranking."
  - States `story_margin_checked`, `reinvestment_checked`, `beta_checked`, `tv_share_checked`, `country_checked`, each with its flag function `@symbol` and `@enum bot.valuator.narrative_flags.FlagColor` once (on `story_margin_checked`); the four colours appear on the edges. Neighbours per decision 4.
  - Edge how lines from `analyze.d2`'s `narrative_flags.*` with their consts on the line. `CountryUnknown` line 2: what red would need (foreign revenue share > 50% and the ERP gap > 300 bps, two consts).
  - Gap note `always_unknown` (class `gap`, one-line `|md`): "Gap: analyze never supplies the foreign revenue share or the two equity risk premiums, so country exposure is always unknown."
  - `out`: "Comes out:" five flags, each green, yellow, red or unknown, with its reason. `link: "./analyze-verdict.svg"`.
  - Edges: 3 in + 9 inside + 4 to verdict + `country_checked -> out` = 17.
- [ ] **Step 2:** Tests as Task 2. **Step 3:** Commit `docs(#170): analyze-flags sub-board`.

### Task 8: analyze-verdict

**Files:** Create `docs/pipeline/analyze-verdict.d2`.

- [ ] **Step 1:** Write the board.
  - `objective`: "Objective: read the margin of safety into a verdict, set the implied multiples beside the sector's, and write the three reports."
  - States `verdict_given` (MoS = intrinsic value per share ÷ latest close, `@symbol bot.reporting.analysis_report.margin_verdict`), `sanity_checked` (`@symbol bot.valuator.analysis._sanity_check`, "decides nothing"), `reported`; neighbour `country_checked`.
  - The four verdict edges cite `MOS_UNDERVALUED` and `MOS_FAIR` and name the verdict word on line 2. `TheMultiplesAreCompared` carries the P/E and EV ÷ sales formulas. `TheReportsAreWritten` names the eight markdown sections.
  - Template file `template` (`@file src/bot/reporting/templates/analysis.md.j2`) `→ reported`. Outputs `report_md`, `report_html`, `report_json` (paths as on `analyze.d2`, `report_json` with `link: "./site.svg"` and `@symbol bot.reporting.analysis_json.render_analysis_json @const bot.reporting.analysis_json.SCHEMA_VERSION`, "schema_version 1").
  - `out`: "Comes out:" a verdict and three reports per ticker: markdown, HTML and the JSON sidecar the site reads. `link: "./analyze.svg"`, fed by `reported -> out: "the run of this ticker ends"`.
  - Edges: 4 in + 2 inside + template + 3 outputs + Done = 11.
- [ ] **Step 2:** Tests as Task 2. **Step 3:** Commit `docs(#170): analyze-verdict sub-board`.

### Task 9: stage links, README, render

**Files:** Modify `docs/pipeline/analyze.d2` (seven `link:` lines, decision 8), `docs/pipeline/README.md` (decision 9). Then the CI render loop of the issue: push, `gh run watch`, download `pipeline-render`, copy every SVG and `rendered.sha256`, commit, push; a d2 error or a layout that drops a link is fixed in the `.d2`.

- [ ] **Step 1:** Add the links and README edits; run the three test files: everything passes except the SVG-dependent tests.
- [ ] **Step 2:** Commit `docs(#170): link the analyze sub-boards`; push; render loop until `pipeline-diagram` (both jobs) is green on the head with the committed SVGs.
- [ ] **Step 3:** Full suite, `uv run ruff check . && uv run mypy src`, `python3 docs/pipeline/check.py` (`0 errors`), and the `site` workflow's commands locally.
