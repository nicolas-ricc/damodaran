# Analyze boards and model: the hypergrowth gate, the story branch, the DCF extensions and the new flags — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring `docs/pipeline/models/analyze.*` and the eight analyze boards up to the hypergrowth code of #193–#198, drawn and checked, with no change to `src/`.

**Architecture:** The TLA+ model is changed first and fixes every new state and step label (below, verbatim). Each sub-board then draws its group of the model: one node per state, one edge per step whose first line is the step label. The stage board `analyze.d2` gets the matching sections. SVGs and `rendered.sha256` come from the `pipeline-render` artifact of the `pipeline-diagram` workflow; TLC runs in its `models` job.

**Tech Stack:** TLA+ (TLC 1.7.4 in CI), d2 v0.9.0 (CI), Python 3 checks (`docs/pipeline/check.py`, pytest).

**Spec:** issue #199 (sub-issue of #192); ADR 0009 (`docs/adr/0009-hypergrowth-story-driven-gated-on-story-file.md`); conventions in `docs/pipeline/README.md` and `docs/pipeline/models/README.md`.

## Global Constraints

- No change under `src/`. Model work never changes the pipeline code.
- Labels in the reader's words, conditions in brackets at the end, acronyms expanded at first use, no identifiers (no `_`, no camelCase, no action names) in model labels.
- At most 24 edges per board (`test_edge_cap`); at most 20 model steps touching one group (`test_analyze_groups_fit_a_subboard`).
- Every digit on a board label cited with `@const`/`@param` on that line, except 0, 1, 100, ordinals and digits inside words (`year-10` needs no citation; `10` alone does).
- Every step and decision node carries a directive on the line above. ADR mentions read `ADR 0009 (Implemented)`.
- Keep every phrase already pinned by `_ANALYZE_TEXT` (both test files) verbatim: add lines, do not rewrite pinned ones (e.g. keep `equity = EV − net debt + adjustments` and add the commitments on its own line).
- Never edit an SVG or `rendered.sha256` by hand; never weaken a rule.

## Decisions taken here

1. **#180 is fixed in the code, so the model's crash is wrong.** `load_override` now turns invalid YAML and non-numbers into `ValueError` (`tests/unit/test_analyze_model_replay.py` passes). The step `TheOverrideFileIsNotYaml` and the state `crashed` are removed, folded into `TheOverrideFileIsInvalid`, and `OnlyTheCommandStopsTheBatch` goes back into `analyze.cfg` without its `\* broken: #180` marker; its row leaves the "Known broken rules" table (the table header stays). This follows `models/README.md` "When a rule breaks": the code is what the suite says.
2. **The override is read after the region**, as in `analysis.analyze` (`load_valuation_input`, which sets the region, then `load_override`, then the signals). New state `override_read` between `region_set` and `signals`.
3. **Story file presence is chosen when the file is read** (`storyFile' \in {"present", "absent"}`). `load_override` already guarantees `story` ⇔ `story_type: hypergrowth`, so a manual story type other than hypergrowth only happens with `storyFile = "absent"`.
4. **The DCF variants are conditions, not steps.** The DCF group is at 20 steps; new steps would break the cap. Each variant goes into the bracket of the step it changes, with the formula on the board.
5. **The scenario range sits in the sensitivity group, before the flags.** In `analyze` it runs after the flags, but neither reads the other, so the order is not observable. Placing it before the flags keeps `FlagsAfterTheDcfNotInTheVerdict` (`flags # {} => valued`) true when a scenario fails: that failure sets `valued' = FALSE` (the `ValueError` discards the whole analysis: no value goes out).
6. **`FlagsAfterTheDcfNotInTheVerdict` is restated, not weakened**: with a verdict the flags are exactly the five, the five plus the story flag, or the five plus the three hypergrowth flags.
7. **Cross-group steps drawn on one board only** (README exception, cap): `ItIsHypergrowth` and `ItIsNotHypergrowth` only on analyze-story (analyze-inputs sends `signals` to `out`); `TheStoryCannotBeApplied` only on analyze-dcf.

## The model, verbatim (Task 1 writes it; Tasks 2–5 draw it)

New variables, each in `vars` and in every `UNCHANGED` list it is not assigned in:
`storyFile` (`"unread"` → `"present"`/`"absent"`), `signal` (`FALSE`; `TRUE` when the classifier says hypergrowth), `storyType` (`"unset"` → `"hypergrowth"`/`"other"`).

New states (`states` label, group):

| key | label | group |
| --- | --- | --- |
| `override_read` | the override file is read and checked | analyze-inputs |
| `not_hypergrowth` | the company is not hypergrowth | analyze-story |
| `scenarios_done` | the scenario range is settled | analyze-sensitivity |
| `hg_story_checked` | the hypergrowth story flag is set | analyze-flags |
| `scale_checked` | the revenue scale flag is set | analyze-flags |
| `hypergrowth_checked` | the hypergrowth flags are settled | analyze-flags |
| `discounted` | the governance discount is applied | analyze-verdict |

Removed: state `crashed` (also from `EndPhases`), step `TheOverrideFileIsNotYaml`.

New or changed steps (from → to, guard/assignments, `steps` label):

| step | from → to | guard / sets | label |
| --- | --- | --- | --- |
| `TheOverrideFileIsRead` | region_set → override_read | `storyFile' \in {"present", "absent"}` | the override file is read and checked [a valid file, or none] |
| `TheOverrideFileIsInvalid` | region_set → cannot_value | exit `"1"` | the ticker cannot be valued, exit code 1 [the override file is not valid YAML, not a mapping, has an unknown key or a value that is not a finite number, or its story file is inconsistent] |
| `TheSignalsAreDerived` | override_read → signals | | net debt, interest coverage, age, founded age and the cyclical sector are derived |
| `ItIsHypergrowth` | signals → classified | `storyTypes' = {"classifier"}`, `signal' = TRUE` | the classifier says hypergrowth [revenue growth at least 50% last year, compound annual growth rate (CAGR) at least 40%, operating margin below the sector's, founded at most 15 years ago or unknown] |
| `ItIsNotHypergrowth` | signals → not_hypergrowth | | not hypergrowth [otherwise] |
| `ItIsDistressed` | not_hypergrowth → classified | (label unchanged) | |
| `ItIsNotDistressed` | not_hypergrowth → not_distressed | (label unchanged) | |
| `NoManualStoryType` | classified → story_set | `storyFile = "absent"`, `~signal`; `storyType' = "other"` | the classifier's story type stands [no story type in the override file, and not hypergrowth] |
| `TheOverrideSetsTheStoryType` | classified → story_set | `storyFile = "absent"`; `storyType' = "other"` | the override file's story type replaces it [a story type other than hypergrowth in the file; an unknown label drives no branch] |
| `HypergrowthWithoutAStoryFallsBack` | classified → story_set | `signal`, `storyFile = "absent"`; `overrideStory' = "absent"`, `storyType' = "other"` | the story type falls back to high-growth [the classifier says hypergrowth, the file sets no story type and has no story section] |
| `TheStoryFileIsPresent` | classified → story_set | `storyFile = "present"`; `overrideStory' = "given"`, `storyTypes' = {"override"}`, `storyType' = "hypergrowth"` | the story type is hypergrowth [a story section and story type hypergrowth in the override file] |
| `TaxAndBankruptcyAreSet` | tg_set → ready | `storyType # "hypergrowth"` | tax rate and bankruptcy odds are set [not hypergrowth; tax manual, sector, country, or 25%; bankruptcy manual or 0] |
| `TheStoryShapesThePaths` | tg_set → ready | `storyType = "hypergrowth"` | the story shapes the ten-year paths [hypergrowth story type] |
| `TheStoryCannotBeApplied` | tg_set → cannot_value | `storyType = "hypergrowth"`, exit `"1"` | the ticker cannot be valued, exit code 1 [hypergrowth, and no latest revenue, a year-10 revenue no growth rate reaches, or no terminal weighted average cost of capital (WACC), terminal growth or tax rate] |
| `TheWaccIsComputed` | resolved → wacc_computed | | the weighted average cost of capital (WACC) is computed [one rate from the weights, or the story's yearly path] |
| `TerminalGrowthIsBelowTheWacc` | wacc_computed → projected | | the years are projected [terminal growth below the last year's weighted average cost of capital (WACC); a cumulative discount with a WACC path] |
| `TheTerminalValueIsComputed` | projected → terminal_valued | | the terminal value is computed [with a terminal return on invested capital (ROIC) the reinvestment is g ÷ ROIC of the profit, else by sales-to-capital] |
| `TheEquityIsFound` | ev_found → equity_found | | equity and the going-concern value per share are found [fixed commitments subtracted and extra cash added when the story sets them] |
| `TheValueIsBlended` | equity_found → valued | `valued' = TRUE` | the intrinsic value per share blends going concern and distress [per share, or on the enterprise value before the bridge with a hypergrowth story] |
| `TheScenariosAreValued` | grid_done → scenarios_done | `storyType = "hypergrowth"` | the scenario range is valued, base first [scenarios in the story file] |
| `NoScenarios` | grid_done → scenarios_done | | no scenario range [no scenarios in the story file] |
| `TheScenarioRangeFails` | grid_done → cannot_value | `storyType = "hypergrowth"`; `valued' = FALSE`, exit `"1"` | the ticker cannot be valued, exit code 1 [a scenario cannot be built, or its terminal growth reaches its weighted average cost of capital (WACC)] |
| `StoryMargin{Green,Yellow,Unknown}` | **scenarios_done** → story_margin_checked | (labels unchanged) | |
| `TheHypergrowthStoryFlagIsSet` | country_checked → hg_story_checked | `signal \/ storyType = "hypergrowth"`; `flags \cup {"hypergrowth story"}` | the hypergrowth story flag is set [hypergrowth signals, or the hypergrowth story type] |
| `NoHypergrowthFlag` | country_checked → hypergrowth_checked | `~signal /\ storyType # "hypergrowth"` | no hypergrowth flag [no hypergrowth signals, and another story type] |
| `TheRevenueScaleFlagIsSet` | hg_story_checked → scale_checked | `storyType = "hypergrowth"`; `flags \cup {"revenue scale"}` | the revenue scale flag is set [hypergrowth story type] |
| `OnlyTheStoryFlag` | hg_story_checked → hypergrowth_checked | `storyType # "hypergrowth"` | the scale and return flags are skipped [signals without the hypergrowth story type] |
| `TheTerminalRoicFlagIsSet` | scale_checked → hypergrowth_checked | `flags \cup {"terminal ROIC"}` | the terminal return on invested capital (ROIC) flag is set |
| `TheGovernanceDiscountIsApplied` | hypergrowth_checked → discounted | | the value after the governance discount is set [the story's discount, else none] |
| `TheMarginIs…`, `TheTickerHasNoPrice` | **discounted** → verdict_given | (labels unchanged) | |

Every other step keeps its from, to and label. Each new action carries a `(* src/...: ... *)` citation of the code it mirrors (see #199 "The code to mirror").

Rules:

- New, in `.tla` and `.cfg`, cited and with its sentence:
  ```
  (* Cites: assumptions.py _resolve_story_type turns a hypergrowth label without a story section into high-growth; load_override refuses story_type hypergrowth without story. *)
  \* The story type is hypergrowth only when the story file is present.
  HypergrowthOnlyWithAStoryFile ==
    storyType = "hypergrowth" => storyFile = "present"
  ```
- `FlagsAfterTheDcfNotInTheVerdict`: same sentence; `flags = FlagNames` becomes `flags \in {FlagNames, FlagNames \cup {"hypergrowth story"}, FlagNames \cup HypergrowthFlagNames}` with `HypergrowthFlagNames == {"hypergrowth story", "revenue scale", "terminal ROIC"}`.
- `OnlyTheCommandStopsTheBatch`: unchanged body, `\* broken: #180` removed, listed in `.cfg`.

Group budgets after the change (model steps touching each group): inputs 18, story 16, assumptions 20, dcf 20, sensitivity 8, flags 18, verdict 7.

## Stage-3 evals (written before Task 1, committed failing as `test(#199): evals`)

`tests/unit/test_pipeline_models.py`:
- `_ANALYZE_RULES` gains `"HypergrowthOnlyWithAStoryFile"`; `_ANALYZE_END` loses `"crashed"`.
- `test_analyze_rule_antecedents_are_set` gains `storyType' = "hypergrowth"`, `signal' = TRUE`, `storyFile' \in {"present", "absent"}`.
- New `test_analyze_cfg_checks_the_gate_and_the_batch_rule`: `{"HypergrowthOnlyWithAStoryFile", "OnlyTheCommandStopsTheBatch"} <= set(_invariants("analyze"))`.

`tests/unit/test_pipeline_subboards.py`, `_ANALYZE_TEXT` gains:
- analyze-inputs: `"founded_year"`, `"read and checked"`
- analyze-story: `"story file"`, `"founded_year"`, `"falls back to high-growth"`
- analyze-assumptions: `"story: the story file of a hypergrowth company"`, `"ten-year"`, `"solved"`
- analyze-dcf: `"cumulative"`, `"g ÷ ROIC"`, `"fixed commitments"`, `"extra cash"`, `"before the bridge"`
- analyze-sensitivity: `"pretax_cost_of_debt is skipped"`, `"scenario range"`, `"base first"`
- analyze-flags: `"hypergrowth_story"`, `"750B"`, `"2 × the sector ROIC"`
- analyze-verdict: `"governance discount"`, `"value after governance"`, `"scenario range"`

`tests/unit/test_pipeline_diagram.py`:
- `_STORY_ORDER = ("hypergrowth", "distressed", "cyclical", "high_growth", "mature_decline", "mature_stable")`.
- `_ANALYZE_NODES` gains `story_type.gate` (decision), `assumptions.story` (step), `sensitivity.scenario_range` (step), `narrative_flags.hypergrowth` (decision), `verdict.governance` (step).
- `_ANALYZE_TEXT` gains: `override` + `"before the signals"`; `inputs.derived` + `"founded_year"`; `story_type.hypergrowth`: `"≥ 50%"`, `"≥ 40%"`, `"founded ≤ 15 years ago or unknown"`; `story_type.gate`: `"story file"`, `"high-growth"`, `"red"`; `assumptions.story`: `"apply_story"`, `"ten-year"`; `dcf.years` + `"cumulative"`; `dcf.terminal` + `"g ÷ ROIC"`; `dcf.equity` + `"fixed commitments"`, `"extra cash"`; `dcf.blend` + `"before the bridge"`; `sensitivity.tornado` + `"pretax_cost_of_debt is skipped"`; `sensitivity.scenario_range`: `"base first"`, `"scenario"`; `narrative_flags.hypergrowth`: `"750B"`, `"2 × the sector ROIC"`, `"hypergrowth_story"`; `verdict.governance`: `"governance discount"`, `"value after governance"`.
- `_REQUIRED_CONSTS`: analyze-story + `_HYPERGROWTH_LAST_YEAR_GROWTH`, `_HYPERGROWTH_CAGR`, `_HYPERGROWTH_MAX_AGE_YEARS`; analyze-flags + `_LARGEST_COMPANY_REVENUE`, `_ROIC_SECTOR_MULTIPLE`; analyze-assumptions + `bot.valuator.hypergrowth.HORIZON`.
- `_REQUIRED_SYMBOLS`: analyze-inputs + `bot.valuator.assumptions.load_override`; analyze-assumptions + `bot.valuator.hypergrowth.apply_story`, `bot.valuator.hypergrowth.solve_stage_growth`; analyze-sensitivity + `bot.valuator.sensitivity.scenario_range`, `bot.valuator.sensitivity.active_axes`; analyze-flags + `bot.valuator.narrative_flags.hypergrowth_flags`.

Tasks 1–5 make these pass; each task's Step 1 runs the subset it owns.

## Assumptions

- **Scenario range before the flags in the model** (Decision 5). No doc grants a different order explicitly; `analyze` raises on a failed scenario before `Analysis` is returned and `cli._analyze_one` (`except ValueError`, `src/bot/cli.py:486`) writes nothing, so the computed flags never leave the process. Rejected: keeping the code order, which forces either dropping the scenario failure from the model or weakening `FlagsAfterTheDcfNotInTheVerdict`.
- **A failed TLC run is fixed forward** with a new commit on the model, never by reverting the board commits; Java is not installed here, so the local invocation of `models/README.md` "Running" is unavailable and CI is the checker. Rejected: reverting, which loses the boards for a model-only error.
- **`HypergrowthOnlyWithAStoryFile` is a guard on the actions**: today only `TheStoryFileIsPresent` sets `storyType = "hypergrowth"`, under `storyFile = "present"`; the rule is the issue's verbatim deliverable and catches a later action that sets it without the guard. Rejected: a stronger two-way rule, which the issue does not ask for.
- **The fallback is owned by `_resolve_story_type`** (`src/bot/valuator/assumptions.py:954-972`, the classifier path; pinned by `tests/unit/test_valuator_assumptions.py::test_hypergrowth_without_story_falls_back_to_high_growth`); the manual path is refused earlier by `load_override` (`_check_story_file`). The rule's citation names both.

## Review Focus

1. A label in `view.js` that differs by one character from the edge first line on its board → `test_step_labels_are_drawn` / `test_subboard_edges_join_the_model_states` fail. Copy labels from the table above.
2. A state whose class flips (decision ⇔ step) because the count of conditioned steps leaving it changed (README "Sub-boards": a decision when two or more steps leaving it carry a [condition]): `region_set`, `resolved`, `tg_set`, `country_checked`, `scenarios_done`, `hg_story_checked`, `discounted` become decisions; `scale_checked`, `hypergrowth_checked`, `override_read` are steps. `test_subboard_state_classes` pins it on every board where the node is drawn, neighbours included.
3. An uncited digit on a new board line (750B, 2 ×, 15 years, 10) → `test_subboard_digits_are_cited` / `check.py`.
4. A `.tla` variable missing from an `UNCHANGED` list → TLC fails in CI only; no local test sees it. Check every action lists all 18 variables exactly once (assigned or unchanged).
5. A neighbour node on a board that does not link its own sub-board, or a board over 24 edges after adding the new steps (assumptions goes from 22 to 23).

---

### Task 1: The analyze model

**Files:**
- Modify: `docs/pipeline/models/analyze.tla`, `analyze.cfg`, `analyze.view.js`
- Modify: `docs/pipeline/models/README.md` (remove the analyze row of "Known broken rules")
- Modify: `tests/unit/test_analyze_model_replay.py` (module docstring: the rule is checked again since #180; behaviour unchanged)
- Test: `tests/unit/test_pipeline_models.py` (the stage-3 evals)

**Interfaces:**
- Produces: the state and step labels of the table above, used verbatim by Tasks 2–5.

- [ ] **Step 1:** Run `uv run pytest -q tests/unit/test_pipeline_models.py -k "analyze and not drawn and not join and not classes and not neighbour"`; the stage-3 evals (`HypergrowthOnlyWithAStoryFile` in `_ANALYZE_RULES`, `_ANALYZE_END` without `crashed`, the new antecedents) fail.
- [ ] **Step 2:** Edit the three model files as in "The model, verbatim".
- [ ] **Step 3:** Same command passes. `node -e "import('./docs/pipeline/models/analyze.view.js')"` loads without a syntax error.
- [ ] **Step 4:** Commit `docs(#199): analyze model: the hypergrowth gate, the story branch, the DCF variants, the new flags`.

(The cross-board tests — labels drawn, edges joined, classes, neighbours — go green at the end of Task 4.)

### Task 2: analyze-inputs and analyze-story boards

**Files:** Modify `docs/pipeline/analyze-inputs.d2`, `docs/pipeline/analyze-story.d2`.

**Interfaces:** Consumes Task 1's labels.

- analyze-inputs: add `override_read` (step) between `region_set` and `signals`; `region_set` becomes a decision (two conditioned steps leave it: read, invalid); `cannot_value` neighbour (`link: "./analyze-dcf.svg"`). Remove the `classified` and `not_distressed` neighbours and the two classifier edges; `signals -> out`. Second lines: founded age = this year − `founded_year` of the override file; the file is validated whole before the signals. Objective mentions the override is read and checked before the signals. ≤ 24 edges.
- analyze-story: new decision `not_hypergrowth`; edges `signals -> classified` (hypergrowth, citing `_HYPERGROWTH_LAST_YEAR_GROWTH`, `_HYPERGROWTH_CAGR`, `_HYPERGROWTH_MAX_AGE_YEARS`), `signals -> not_hypergrowth`, `not_hypergrowth -> classified` (distressed), `not_hypergrowth -> not_distressed`; the four gate edges `classified -> story_set`; a note on `founded_year` (founded age from the override file, not `ipo_date`, which still feeds high-growth). Remove `crashed` and the two invalid-file edges. `story_set -> out`.

- [ ] **Step 1:** `uv run pytest -q tests/unit/test_pipeline_subboards.py -k "analyze-inputs or analyze-story"` fails on the new `_ANALYZE_TEXT` phrases.
- [ ] **Step 2:** Edit both boards.
- [ ] **Step 3:** That command passes; `python3 docs/pipeline/check.py` reports 0 errors except the render hash.
- [ ] **Step 4:** Commit `docs(#199): analyze-inputs and analyze-story boards`.

### Task 3: analyze-assumptions and analyze-dcf boards

**Files:** Modify `docs/pipeline/analyze-assumptions.d2`, `docs/pipeline/analyze-dcf.d2`.

- analyze-assumptions: `tg_set` becomes a decision; edges `TaxAndBankruptcyAreSet` and `TheStoryShapesThePaths` to the `ready` neighbour. The story edge's lines cite `bot.valuator.hypergrowth.apply_story`, `bot.valuator.hypergrowth.solve_stage_growth` and `@const bot.valuator.hypergrowth.HORIZON`: growth year 1 = `year1_growth`, years 2 to 5 one rate solved so year-10 revenue meets the target, fade to terminal growth; margin ramp from `year1_margin` to `target_margin − regulatory_drag`; WACC `wacc_start` to year 5 then linear to `wacc_terminal` (else sector WACC); tax `effective_tax_rate` to year 5 then linear to the marginal rate; every value sourced `story`. Sources note gains `- story: the story file of a hypergrowth company`. `TheStoryCannotBeApplied` is not drawn here. 23 edges (22 today + the story edge).
- analyze-dcf: `resolved` becomes a decision; neighbour `region_set` (link analyze-inputs) replaces `classified`; neighbour `grid_done` (link analyze-sensitivity) for `TheScenarioRangeFails`; the `tg_set` neighbour becomes a decision. Formula lines: `WACC_t` path, `discount factor_t = ∏ 1 ÷ (1 + WACC_k), k = 1 … t`, `present value_t = FCFF_t × discount factor_t`; terminal `reinvestment = NOPAT_N+1 × g ÷ ROIC, g = g_terminal`, discounted by the last cumulative factor at the last year's WACC; bridge line `with a story: − fixed commitments + extra cash`; failure line `EV after failure = (1 − p) × EV + p × proceeds share × EV, then the bridge`.

- [ ] **Step 1:** `uv run pytest -q tests/unit/test_pipeline_subboards.py -k "analyze-assumptions or analyze-dcf"` fails on the new phrases.
- [ ] **Step 2:** Edit both boards.
- [ ] **Step 3:** That command passes; `check.py` 0 errors except the hash.
- [ ] **Step 4:** Commit `docs(#199): analyze-assumptions and analyze-dcf boards`.

### Task 4: analyze-sensitivity, analyze-flags and analyze-verdict boards

**Files:** Modify `docs/pipeline/analyze-sensitivity.d2`, `analyze-flags.d2`, `analyze-verdict.d2`.

- sensitivity: tornado line `pretax_cost_of_debt is skipped with a WACC path; cost_of_equity scales the whole path` (cite `bot.valuator.sensitivity.active_axes`); new state `scenarios_done` (decision); the three scenario edges, the scenario edge citing `bot.valuator.sensitivity.scenario_range` and `bot.valuator.hypergrowth.scenario_cases` (base first, then file order, one plain DCF each); `cannot_value` neighbour (link analyze-dcf); story-margin edges now leave `scenarios_done`; out mentions the scenario range.
- flags: `country_checked` becomes a decision; new states `hg_story_checked` (decision), `scale_checked`, `hypergrowth_checked` (steps); the five new flag edges plus the governance edge to the `discounted` neighbour (link analyze-verdict). Lines: story flag red signals and no story file / yellow story file and no signals / green; revenue scale yellow when year-10 revenue > 750B (`@const bot.valuator.narrative_flags._LARGEST_COMPANY_REVENUE`); terminal ROIC yellow when > 2 × the sector ROIC (`@const bot.valuator.narrative_flags._ROIC_SECTOR_MULTIPLE`), unknown when a ROIC is missing or the sector's is ≤ 0. The four verdict edges leave this board. Objective: five flags, three more for hypergrowth.
- verdict: new decision `discounted`; the governance edge from the `hypergrowth_checked` neighbour, lines `value after governance = intrinsic value per share × (1 − governance discount)`, `tornado, grid and scenarios keep the raw value`; the four verdict edges leave `discounted`; `verdict_given` second line `MoS = value after governance ÷ latest close`; reports edge names the new sections (story inputs sourced story, scenario range in the sensitivity section, both values in the summary).

- [ ] **Step 1:** `uv run pytest -q tests/unit/test_pipeline_subboards.py -k "analyze-sensitivity or analyze-flags or analyze-verdict"` fails on the new phrases.
- [ ] **Step 2:** Edit the three boards.
- [ ] **Step 3:** `uv run pytest -q tests/unit/test_pipeline_subboards.py tests/unit/test_pipeline_models.py` passes in full; `check.py` 0 errors except the hash.
- [ ] **Step 4:** Commit `docs(#199): analyze-sensitivity, analyze-flags and analyze-verdict boards`.

### Task 5: the analyze stage board

**Files:** Modify `docs/pipeline/analyze.d2`.

- `override`: read after the company is loaded and before the signals; any invalid file (not YAML, not a mapping, unknown key, non-number, inconsistent story file): cannot value, exit code 1.
- `inputs.derived`: add `founded age = this year − founded_year (override file), for the hypergrowth rule only`; keep `age = whole years since ipo_date`. `inputs.derived.age` (gap) states the current truth: the high-growth rule still reads `ipo_date` (Financial Modeling Prep only; unknown under EDGAR), the hypergrowth rule reads `founded_year`, ADR 0009 (Implemented).
- `story_type`: new decision `story_type.hypergrowth` first (the hypergrowth rule with its three constants), `story_type.distressed` keeps only distressed; edges `inputs.derived -> story_type.hypergrowth: "signals"`, `hypergrowth -> distressed: "no"`, `hypergrowth -> manual: "yes"`; new decision `story_type.gate` after `manual`: hypergrowth only with a story file; classifier hypergrowth with no story type and no story section → high-growth and a red `hypergrowth_story` flag; it feeds `assumptions` and `narrative_flags`.
- `assumptions`: title adds `ten for a hypergrowth story`; new step `assumptions.story` (`apply_story`, `solve_stage_growth`, `HORIZON` cited; every value sourced story; ADR 0009 (Implemented)); sources note gains `story`.
- `dcf`: add the four variants as extra lines on `years`, `terminal`, `equity`, `blend` (same wording as analyze-dcf), keeping the pinned lines.
- `sensitivity`: tornado line about the skipped axis; new step `sensitivity.scenario_range` (scenario range, base first).
- `narrative_flags`: title `five checks, three more for hypergrowth`; new decision `narrative_flags.hypergrowth` with the three flags and both constants.
- `verdict`: new step `verdict.governance` before `verdict.mos`; `mos` adds the line about the value after governance.
- `reports.markdown`: the new report content (story inputs, scenario range, both values).

- [ ] **Step 1:** `uv run pytest -q tests/unit/test_pipeline_diagram.py -k analyze` fails on the stage-3 evals (`_STORY_ORDER` with hypergrowth, the new nodes and phrases).
- [ ] **Step 2:** Edit `analyze.d2`.
- [ ] **Step 3:** `uv run pytest -q tests/unit/test_pipeline_diagram.py` passes; `check.py` 0 errors except the hash.
- [ ] **Step 4:** Commit `docs(#199): analyze stage board`.

### Task 6: render and check in CI

- [ ] **Step 1:** `git push -u origin HEAD`.
- [ ] **Step 2:** `gh run list --branch agent/199-analyze-boards-model --workflow pipeline-diagram --limit 1`, then `gh run watch <id> --exit-status` (foreground). `render` may fail only at "committed render is current"; `models` must be green.
- [ ] **Step 3:** `gh run download <id> -n pipeline-render -D docs/pipeline`; remove any downloaded PNG; `git add docs/pipeline/*.svg docs/pipeline/rendered.sha256`.
- [ ] **Step 4:** `gh run download <id> -n pipeline-models -D /tmp/models-199`; `/tmp/models-199/analyze/report.md` lists `HypergrowthOnlyWithAStoryFile` and `OnlyTheCommandStopsTheBatch` under `## Rules that hold`.
- [ ] **Step 5:** `python3 docs/pipeline/check.py` 0 errors; full suite green; commit `docs(#199): render the analyze boards`; push; the new run is green in both jobs.

Any later change to a `.d2` (review fixes, deslop) repeats Task 6 before the pull request.

## Grilling

One round, 17 questions (griller model: fable). The revisions above (a section listing the stage-3 evals, the `region_set` class flip, the assumptions board at 23 edges rather than 24, `## Assumptions`) clarify the plan without changing its tasks, so there was no second round.

1. Where are the failing expectations written? Nowhere yet: the plan was missing them. → the plan now has a "Stage-3 evals" section listing them verbatim.
2. Edges on the assumptions board? CODE: `docs/pipeline/analyze-assumptions.d2` has 17 model edges, 4 file edges and `out`, 22 in all; with the story edge it has 23. → the plan is corrected.
3. Why move the scenario range before the flags? CODE: `src/bot/valuator/analysis.py` (`analyze` raises before returning `Analysis`), `src/bot/cli.py:486` (`except ValueError` returns 1 before any write). No doc grants a different order → technical assumption (see `## Assumptions`).
4. Is invalid YAML a `ValueError`? CODE: `tests/unit/test_valuator_assumptions.py:344` (`pytest.raises(ValueError, match="not valid YAML")`); `src/bot/cli.py:483-487` (`except LookupError` / `except ValueError` inside the per-ticker call); `tests/unit/test_analyze_model_replay.py` (the batch goes on).
5. Who owns the fallback, and is the rule vacuous? CODE: `assumptions.py:954-972` `_resolve_story_type`; test `test_valuator_assumptions.py:1028`. ISSUE: "add the rule `HypergrowthOnlyWithAStoryFile` (the story type is `hypergrowth` only when the story file is present)". It guards the actions → technical assumption.
6. Which README paragraph grants the exception? DOC: `docs/pipeline/README.md` "Exception: when the cap leaves no room (the screen rule layers), the step is drawn only on the board of the state it enters". CODE: `test_step_labels_are_drawn` takes the union of the stage's boards.
7. How can the digits be cited? CODE: `analyze-story.d2` writes the whole edge on one source line, with a trailing `# @const`; `test_subboard_digits_are_cited` reads the directives of that source line.
8. Which states flip class? DOC: README "A state is a `decision` when two or more steps leaving it carry a [condition]". `region_set` becomes a decision (added to the plan); `signals` is already a decision.
9. How are the steps of a group counted? CODE: `test_pipeline_models.py:826-832` counts a step when its source or its target is in the group. Today: inputs 16, story 14, assumptions 17, dcf 17, sensitivity 5, flags 16, verdict 6.
10. Manual story type alongside the signals? CODE: `assumptions.py` `_resolve_story_type` (the manual type wins); `analysis.py` `hypergrowth_signals=auto_story is StoryType.HYPERGROWTH` whatever the manual type; `narrative_flags.py:518-541` emits the story flag whenever there are signals. The model's guard matches.
11. Does anything name `crashed`, and which variables exist? CODE: `analyze.tla:727-728`, the body has no `crashed`, and there is no `TypeOK`. The 15 variables are on `analyze.tla:6-8`. `NoManualStoryType` and `TheOverrideSetsTheStoryType` already assign `overrideStory`.
12. What if TLC fails? DOC: `models/README.md` "Running" needs Java, which is not installed here → technical assumption: fix forward.
13. Is "no scenarios" reachable? DOC: ADR 0009 "an optional `scenarios` mapping"; CODE: `analysis.py` `if assumptions.scenarios:`. Yes.
14. Who returns no flag at all? CODE: `narrative_flags.py:532-533` `hypergrowth_flags` returns `()` without signals and without the hypergrowth type.
15. The citation format? DOC: `models/README.md` "each rule above its sentence, carries a `(* ... *)` citation"; CODE: `test_rules_cite_the_code` and `test_analyze_rules_are_cited` require `(* Cites:`, and the existing rules use `assumptions.py` without `src/`.
16. What does the artifact hold? CODE: `.github/workflows/pipeline-diagram.yml`, artifact paths `docs/pipeline/*.svg`, `*.png`, `rendered.sha256`. No `.d2` file is in it.
17. Which criteria ask for Decision 1 and the gap note? ISSUE: "move the invalid-override steps to the phase after the company is loaded … Keep every existing rule"; "if a rule breaks, the model is wrong (fix the model, never weaken the rule; the code is what the pytest suite says it is)"; "Replace the stage board's \"age comes from ipo_date\" gap note with the current truth".

Sources: ISSUE 2, CODE 13, DOC 6 (some answers cite more than one). NO SOURCE: 3, all technical assumptions. Spec ambiguities: none. Issues opened: none. Status: ok.
