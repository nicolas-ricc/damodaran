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
| `TheValueIsBlended` | equity_found → valued | `valued' = TRUE` | the intrinsic value per share blends going concern and distress [per share, or on the enterprise value before the bridge when the story sets a failure proceeds share] |
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

## Review Focus

1. A label in `view.js` that differs by one character from the edge first line on its board → `test_step_labels_are_drawn` / `test_subboard_edges_join_the_model_states` fail. Copy labels from the table above.
2. A state whose class flips (decision ⇔ step) because the count of conditioned steps leaving it changed: `resolved`, `tg_set`, `country_checked`, `scenarios_done`, `hg_story_checked`, `discounted` become decisions; `scale_checked`, `hypergrowth_checked`, `override_read` are steps. `test_subboard_state_classes` pins it on every board where the node is drawn, neighbours included.
3. An uncited digit on a new board line (750B, 2 ×, 15 years, 10) → `test_subboard_digits_are_cited` / `check.py`.
4. A `.tla` variable missing from an `UNCHANGED` list → TLC fails in CI only; no local test sees it. Check every action lists all 18 variables exactly once (assigned or unchanged).
5. A neighbour node on a board that does not link its own sub-board, or a board over 24 edges after adding the new steps (assumptions is at 24).

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

- analyze-assumptions: `tg_set` becomes a decision; edges `TaxAndBankruptcyAreSet` and `TheStoryShapesThePaths` to the `ready` neighbour. The story edge's lines cite `bot.valuator.hypergrowth.apply_story`, `bot.valuator.hypergrowth.solve_stage_growth` and `@const bot.valuator.hypergrowth.HORIZON`: growth year 1 = `year1_growth`, years 2 to 5 one rate solved so year-10 revenue meets the target, fade to terminal growth; margin ramp from `year1_margin` to `target_margin − regulatory_drag`; WACC `wacc_start` to year 5 then linear to `wacc_terminal` (else sector WACC); tax `effective_tax_rate` to year 5 then linear to the marginal rate; every value sourced `story`. Sources note gains `- story: the story file of a hypergrowth company`. `TheStoryCannotBeApplied` is not drawn here. Exactly ≤ 24 edges.
- analyze-dcf: `resolved` becomes a decision; neighbour `region_set` (link analyze-inputs) replaces `classified`; neighbour `grid_done` (link analyze-sensitivity) for `TheScenarioRangeFails`; the `tg_set` neighbour becomes a decision. Formula lines: `WACC_t` path, `discount factor_t = ∏ 1 ÷ (1 + WACC_k), k = 1 … t`, `present value_t = FCFF_t × discount factor_t`; terminal `reinvestment = NOPAT_N+1 × g_terminal ÷ ROIC`, discounted by the last cumulative factor at the last year's WACC; bridge line `with a story: − fixed commitments + extra cash`; failure line `EV after failure = (1 − p) × EV + p × proceeds share × EV, then the bridge`.

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
- `sensitivity`: tornado line about the skipped axis; new step `sensitivity.scenarios` (scenario range, base first).
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
