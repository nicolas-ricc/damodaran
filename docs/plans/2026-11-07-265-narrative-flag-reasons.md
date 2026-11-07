# Narrative flags: skip a check that does not apply, word every reason for a reader — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `story_margin` is emitted only for a `high-growth` story, and every `reason` of the eight narrative checks reads as one or two plain sentences for a human.

**Architecture:** `narrative_flags()` keeps its five-function tuple but filters `story_margin_flag` out unless `context.story_type == "high-growth"`, the way `hypergrowth_flags()` already omits its flags. `story_margin_flag` loses its "not high-growth" branch. The reason strings are rewritten in place; no new types. Docs that state the old rule (spec §7.5, lesson, pipeline boards, TLA+ model, status plan) change with the code.

**Tech Stack:** Python 3.12, pytest, mypy --strict, ruff; d2 boards + `docs/pipeline/check.py`; TLA+ (TLC in CI via `check.sh`); `docs/leccion/check.py`.

**Spec:** GitHub issue #265 (`gh issue view 265 --repo nicolas-ricc/damodaran`), plus `docs/superpowers/specs/2026-05-25-investment-bot-design.md` §7.5.

## Global Constraints

- A check that does not apply is not emitted. `UNKNOWN` is not "does not apply": it stays visible (`country_exposure` keeps showing `unknown`).
- Reason rule: one or two plain sentences; an acronym appears only with its expansion the first time **in the same string** (`after-tax operating profit (NOPAT)`, `free cash flow to the firm (FCFF)`, `equity risk premium (ERP)`, `return on invested capital (ROIC)`); no `—`; no `(<= 80%)` / `(> 300)` notation, no `<=`, no `>`; thresholds in words; `bps` written as `basis points`; the numbers the check compared stay in the text.
- `not evaluated:` prefixes stay exactly; the text after them follows the rule.
- Thresholds in reasons are formatted from the module constants, never retyped.
- Already-written sidecars under `reports/*/analysis/*.json` are not touched.
- The web viewer (`src/bot/web/`) is out of scope.
- `uv run ruff check . && uv run mypy --strict src && uv run pytest -q` green; `uv run python docs/leccion/check.py` and `uv run python docs/pipeline/check.py` report 0 errors.

## Review Focus

1. `story_type=None` (no classification reached the context) or `"hypergrowth"`: not `high-growth`, so `story_margin` is absent and four base flags come out. Pinned in Task 1.
2. A `high-growth` context with a missing margin still emits `story_margin` as `unknown` (the check applies, the data is missing). Pinned in Task 1.
3. `country_exposure` green with a *negative* ERP gap (weighted below listing): the sentence must still read correctly ("a gap of -50 basis points"). Pinned in Task 2.
4. Red-capability bookkeeping (`test_every_flag_is_classified_by_red_capability`) used a hypergrowth context, which no longer emits `story_margin`; it must union a high-growth context so the classification still covers every flag. Pinned in Task 1.
5. A reason built from a module constant (80% ceiling, 300 basis points, 2 times the sector ROIC, 750 billion) must change with the constant: every wording test formats the constant, or pins the current value and the constant together. Pinned in Task 2.

## Exact reason copy (Task 2 implements, stage-3 tests pin)

Placeholders are the existing local variables; formats as shown.

| Flag | Colour | Reason |
|---|---|---|
| story_margin | unknown | `not evaluated: the company's latest operating margin or the sector's median margin is missing.` |
| story_margin | yellow | `A high-growth story, but the operating margin of {company:.1%} already exceeds the sector's {sector:.1%}: little room left for the margin to improve.` |
| story_margin | green | `A high-growth story with an operating margin of {company:.1%}, at or below the sector's {sector:.1%}: there is room for the margin to improve.` |
| growth_reinvestment | red | `In at least one year growth needs more reinvestment than after-tax operating profit (NOPAT) provides, so free cash flow to the firm (FCFF) turns negative.` |
| growth_reinvestment | yellow | `In year {worst_year} reinvestment takes {worst_rate:.0%} of after-tax operating profit (NOPAT): growth is funded, but only just.` |
| growth_reinvestment | green | `Every year the reinvestment growth needs fits within after-tax operating profit (NOPAT).` |
| beta_business_risk | unknown | `not evaluated: the sector beta, the operating leverage or the company's debt share is missing.` |
| beta_business_risk | yellow | `The sector beta of {beta:.2f} is below {_DEFENSIVE_BETA:g}, which looks defensive, but operating leverage of {operating_leverage:.2f} is above {_HIGH_OPERATING_LEVERAGE:g} and debt at {financial_leverage:.0%} of capital is above {_HIGH_FINANCIAL_LEVERAGE:.0%}: the beta understates the risk.` |
| beta_business_risk | green | `The sector beta of {beta:.2f} fits operating leverage of {operating_leverage:.2f} and debt at {financial_leverage:.0%} of capital.` |
| terminal_value_share | yellow | `{share:.0%} of enterprise value comes from the terminal value, above the {_TERMINAL_VALUE_SHARE_CEILING:.0%} ceiling: the valuation rests almost entirely on the perpetuity.` |
| terminal_value_share | green | `{share:.0%} of enterprise value comes from the terminal value, within the {_TERMINAL_VALUE_SHARE_CEILING:.0%} ceiling.` |
| country_exposure | unknown | `not evaluated: it needs revenue by geography and a revenue-weighted equity risk premium (ERP), and no data source supplies either.` |
| country_exposure | red | `{foreign:.0%} of revenue is earned abroad and the revenue-weighted equity risk premium (ERP) of {erp_weighted:.1%} is {gap_bps} basis points above the listing country's {erp_listing:.1%}, more than {threshold_bps}: the discount rate under-prices country risk.` |
| country_exposure | green | `{foreign:.0%} of revenue is earned abroad and the revenue-weighted equity risk premium (ERP) is {erp_weighted:.1%} against {erp_listing:.1%} for the listing country, a gap of {gap_bps} basis points.` |
| hypergrowth_story | red | `The classifier sees hypergrowth signals but there is no story file, so the default valuation is not reliable.` |
| hypergrowth_story | yellow | `A story file is present but the classifier sees no hypergrowth signals: the two disagree.` |
| hypergrowth_story | green (both) | `The classifier's hypergrowth signals and the story file agree.` |
| hypergrowth_story | green (neither) | `No hypergrowth signals and no story file: there is nothing to reconcile.` |
| hypergrowth_revenue_scale | yellow | `Year-10 revenue of {revenue / 1e9:,.0f} billion is larger than the revenue of the largest company today, about {largest_b:,.0f} billion.` |
| hypergrowth_revenue_scale | green | `Year-10 revenue of {revenue / 1e9:,.0f} billion is within the revenue of the largest company today, about {largest_b:,.0f} billion.` |
| hypergrowth_terminal_roic | unknown (missing) | `not evaluated: the terminal return on invested capital (ROIC) or the sector's ROIC is missing.` |
| hypergrowth_terminal_roic | unknown (sector ≤ 0) | `not evaluated: a sector return on invested capital (ROIC) of {sector:.1%} is not a usable benchmark.` |
| hypergrowth_terminal_roic | yellow | `The terminal return on invested capital (ROIC) of {terminal:.1%} is above {limit:.1%}, {_ROIC_SECTOR_MULTIPLE:g} times the sector's {sector:.1%}: the story claims an advantage far beyond the sector's.` |
| hypergrowth_terminal_roic | green | `The terminal return on invested capital (ROIC) of {terminal:.1%} is within {limit:.1%}, {_ROIC_SECTOR_MULTIPLE:g} times the sector's {sector:.1%}.` |

`gap_bps = round(gap * 10000)` and `threshold_bps = round(_ERP_GAP_THRESHOLD * 10000)`, both `int`, so a gap of -0.3 basis points prints `0`, never `-0`.

The table has 24 rows, one per `return NarrativeFlag` that remains in `narrative_flags.py` after Task 1 deletes the not-high-growth branch (25 returns today). `growth_reinvestment`, `terminal_value_share` and `hypergrowth_revenue_scale` have no `unknown` branch in the code.

---

### Task 1: `story_margin` only for a high-growth story

**Files:**
- Modify: `src/bot/valuator/narrative_flags.py` (`story_margin_flag`, `narrative_flags`, module and function docstrings)
- Modify: `src/bot/valuator/analysis.py:120` (docstring "The five §7.5 consistency flags")
- Test: `tests/unit/test_valuator_narrative_flags.py`, `tests/unit/test_valuator_analysis.py`

**Interfaces:**
- Produces: `narrative_flags(financials, assumptions, result, context) -> tuple[NarrativeFlag, ...]` — four flags (`growth_reinvestment`, `beta_business_risk`, `terminal_value_share`, `country_exposure`) unless `context.story_type == "high-growth"`, then five with `story_margin` first. `story_margin_flag` keeps its signature; called with a non-high-growth context it no longer has a dedicated branch (it compares margins as for high-growth); only `narrative_flags` gates it.

- [ ] **Step 1: The failing tests are in (stage 3).** `test_story_margin_green_for_other_story_types` is replaced by `test_narrative_flags_omit_story_margin_for_other_story_types` (parametrized over `mature-stable`, `mature-decline`, `cyclical`, `distressed`, `hypergrowth`, `None`: four flags, names in order, no `story_margin`); `test_narrative_flags_runs_five_for_high_growth`; `test_narrative_flags_keep_an_unknown_story_margin_for_high_growth`; `test_narrative_flags_runs_all_five_in_spec_order` becomes the four-name order for a default context; the two `stay_five` hypergrowth tests become `stay_four`; `test_every_flag_is_classified_by_red_capability` unions a `high-growth` context.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_valuator_narrative_flags.py -q` — Expected: the tests above FAIL (five flags returned).
- [ ] **Step 3: Implement.** In `narrative_flags`, skip `story_margin_flag` unless `context.story_type == _HIGH_GROWTH_STORY`; delete the `!= _HIGH_GROWTH_STORY → GREEN` branch of `story_margin_flag`. Update docstrings (module: "four flags always, `story_margin` only for high-growth"; `narrative_flags` Returns; `analysis.py:120`).
- [ ] **Step 4: Run** `uv run pytest tests/unit/test_valuator_narrative_flags.py tests/unit/test_valuator_analysis.py -q` — Expected: Task-1 tests PASS (wording tests of Task 2 may still fail).
- [ ] **Step 5: Commit** `feat(#265): emit story_margin only for a high-growth story`.

### Task 2: every reason reads as a sentence for a human

**Files:**
- Modify: `src/bot/valuator/narrative_flags.py` (the reason strings of all eight checks)
- Test: `tests/unit/test_valuator_narrative_flags.py`, `tests/unit/test_valuator_analysis.py:258-295`

**Interfaces:**
- Consumes: Task 1's `narrative_flags`.
- Produces: the reason copy in the table above, nothing else changes (names, colours, thresholds).

- [ ] **Step 1: The failing tests are in (stage 3).** One whole-sentence test per branch in the table (e.g. `test_growth_reinvestment_green_reason`, `test_country_exposure_green_reason_with_a_negative_gap` asserting `"a gap of -50 basis points."`), the fragment asserts (`"30.0%" in`, `"at/below sector" not in`, `"bps" in`, `"12.0%" in`) replaced by whole sentences, and `test_every_reason_reads_for_a_person`: over a branch-covering set of inputs (the existing `_sweep_results()` × `_sweep_contexts()`, which already reach beta yellow with beta 0.5 / leverage 3.0 / debt 0.9 and terminal ROIC with sector ROIC 0.0; plus country contexts `(None, None, None)`, `(0.70, 0.09, 0.05)`, `(0.70, 0.046, 0.045)`; plus `hypergrowth_story_flag` over the four `(signals, story_file_present)` combinations) it collects every reason of the eight checks, asserts it saw every `(name, colour)` pair of the table, and asserts for each reason: no `—`, no `<=`, no `>`, no `bps`, and for each of `NOPAT`, `FCFF`, `ERP`, `ROIC` present, its expansion appears in the same string before it.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_valuator_narrative_flags.py tests/unit/test_valuator_analysis.py -q` — Expected: wording tests FAIL.
- [ ] **Step 3: Implement** the table copy in each flag function, formatting thresholds from the module constants.
- [ ] **Step 4: Run** the same command — Expected: PASS. Then `uv run pytest -q` — Expected: only the isolation golden tests fail (Task 3).
- [ ] **Step 5: Commit** `feat(#265): word every narrative-flag reason for a reader`.

### Task 3: regenerate the isolation golden fixtures

**Files:**
- Modify: `tests/fixtures/valuator/isolation/{cyclical,distressed,high_growth,mature_decline,mature_stable,override}.{md,json}`
- Modify: `tests/unit/test_valuator_isolation_golden.py` (module docstring: add "Regenerated for #265 …")

All six fixtures carry the narrative-flag rows, so all six move, not only `distressed` (the issue names one as the example).

- [ ] **Step 1: Run** `uv run pytest tests/unit/test_valuator_isolation_golden.py -q` — Expected: markdown/JSON golden tests FAIL on the flag rows.
- [ ] **Step 2: Regenerate** with `uv run python -c "from tests.unit.test_valuator_isolation_golden import regenerate; regenerate()"`.
- [ ] **Step 3: Review the diff** `git diff --stat tests/fixtures` and `git diff tests/fixtures`: only the narrative-flag section/array changes; in the five non-high-growth fixtures the `story_margin` row/object disappears; in `high_growth` it rewords. Any other moved line is a bug: stop and report.
- [ ] **Step 4: Run** `uv run pytest -q` — Expected: PASS.
- [ ] **Step 5: Commit** `test(#265): regenerate the isolation golden fixtures`.

### Task 4: docs state the new rule

**Files:**
- Modify: `docs/superpowers/specs/2026-05-25-investment-bot-design.md` §7.5
- Modify: `docs/leccion/index.html` (the "Alertas de narrativa" paragraph: "Cuatro controles …, cinco para `high-growth`"; the `story_margin` row with the issue's exact text)
- Modify: `docs/pipeline/analyze-flags.d2`, `docs/pipeline/analyze-sensitivity.d2` (same three/four edges into `story_margin_checked`), `docs/pipeline/analyze.d2:201` (`story_margin` node: "only for a high-growth story type; other story types carry no such flag", keeping `high-growth`, `> sector op_margin`, `yellow`, `unknown`, which `tests/unit/test_pipeline_diagram.py:1744` pins), objective/out notes that say "five flags"
- Modify: `docs/pipeline/models/analyze.tla`, `docs/pipeline/models/analyze.view.js`
- Modify: `docs/plano/estado.py:132` (last sentence: story_margin now only runs for high-growth)

**Model decisions.** The model's `storyType` takes `"unset"`, `"other"`, `"hypergrowth"`; no action yields `"high-growth"`, so a `storyType = "high-growth"` guard would make the three story-margin actions dead. Therefore:
- `HypergrowthWithoutAStoryFallsBack` sets `storyType' = "high-growth"` (the code falls back to high-growth).
- `NoManualStoryType` and `TheOverrideSetsTheStoryType` set `storyType' \in {"high-growth", "other"}` (the classifier or the override can give either; `storyFile' \in {...}` at line 145 is the precedent).
- New `StoryMarginSkipped` (comment cites `narrative_flags.py: narrative_flags skips story_margin_flag`): `phase = "scenarios_done"`, `phase' = "story_margin_checked"`, `valued`, `storyType # "high-growth"`, `flags` unchanged. `StoryMarginGreen/Yellow/Unknown` gain `storyType = "high-growth"`.
- `FlagsAfterTheDcfNotInTheVerdict`: `flags \in {F, F \cup {"hypergrowth story"}, F \cup HypergrowthFlagNames, B, B \cup {"hypergrowth story"}, B \cup HypergrowthFlagNames}` with `B == FlagNames \ {"story margin"}` (define a helper `BaseFlagNames`).
- `Next` lists `StoryMarginSkipped` beside the other three; `analyze.view.js` `steps` maps it to `"story margin is skipped [not high-growth]"`, and the other three labels change to match the d2 edges.
- d2 edge labels (analyze-flags and analyze-sensitivity): `story margin is green [company margin at most the sector's]`, yellow and unknown unchanged, new `scenarios_done -> story_margin_checked: "story margin is skipped [not high-growth]"`; analyze-flags `out`: `"Comes out:\nfour flags, five for high-growth, each green, yellow, red or unknown, with its reason; three more for hypergrowth"`; objective note: "four narrative flags, five for a high-growth story, …".

- [ ] **Step 1: Run** `uv run pytest tests/unit/test_pipeline_models.py tests/unit/test_pipeline_diagram.py tests/unit/test_pipeline_subboards.py tests/unit/test_leccion.py -q` after the edits — Expected: PASS (they pin labels drawn, groups ≤ 24 arrows, actions cited).
- [ ] **Step 2: Run** `uv run python docs/leccion/check.py` and `uv run python docs/pipeline/check.py` — Expected: `0 errores` / `0 errors`.
- [ ] **Step 3: Run TLC** if Java is obtainable: `TLA2TOOLS=… STATECHART=… docs/pipeline/models/check.sh /tmp/models-265` — Expected: `0 errors`. Otherwise CI runs it (job `models`).
- [ ] **Step 4: Run** `uv run pytest -q` — Expected: PASS.
- [ ] **Step 5: Commit** `docs(#265): story margin runs only for high-growth`.

## Assumptions

Decided during plan review (stage 2); listed again in the PR.

- **Wording outside the issue's six reference sentences is authored by the plan** under the issue's rule (B.6 "Rewrite the reason strings of all eight checks under one rule"). Rejected: leaving the other eighteen strings untouched (the issue names all eight checks).
- **"Thresholds in words" means a phrase around the number, not spelled-out digits**: the issue's own example is "above the 80% ceiling". Rejected: "eighty percent".
- **Threshold values are formatted from the constants with `:g` / `:.0%`** (`_DEFENSIVE_BETA = 1.0` → `1`, `_HIGH_OPERATING_LEVERAGE = 1.5` → `1.5`, `_HIGH_FINANCIAL_LEVERAGE = 0.40` → `40%`, `_TERMINAL_VALUE_SHARE_CEILING = 0.80` → `80%`, `_ROIC_SECTOR_MULTIPLE = 2.0` → `2`). Rejected: `.0f` / `.1f`, which would misrender a constant later set to 0.8 or 1.25.
- **Basis points are rounded to an `int`**: a gap of 300.4 still prints "300 … more than 300". Accepted: the colour carries the strict comparison; rejected: one decimal on basis points, which reads as false precision.
- **`story_type=None` and `"hypergrowth"` both drop `story_margin`**: the issue says "For any other story type the flag is absent". In the pipeline `story_type` is never `None` (`analysis.py:944`, `assumptions.story_type or auto_story.value`); `None` only arises for direct callers using the dataclass default.
- **`story_margin_flag` keeps no story-type guard of its own**: its only caller is `narrative_flags()` (grep: `src/` has no other caller; tests and docs cite the symbol only). Rejected: keeping a guard that returns something for a check that "is not emitted".
- **Intermediate commits may leave the suite red** (stage-3 failing tests, Task 1 before Task 2, Task 2 before Task 3); the branch is green before push. The pipeline mandates committing failing evals; no repo rule forbids it (CONTEXT.md "Conventions").
- **All six golden fixtures regenerate**, not only `distressed`: every fixture's section 6 lists the flags (`tests/fixtures/valuator/isolation/*.md`, line ~84).
- **TLA+ `storyType` gains `"high-growth"`** as described in Task 4; no invariant reads `storyType` except `HypergrowthOnlyWithAStoryFile` (`storyType = "hypergrowth" => …`), and every guard compares with `"hypergrowth"`, so `"high-growth"` behaves as `"other"` did everywhere except the new story-margin guards.

## Grilling

- Rounds: 1 (griller model: fable). Revisions were refinements (format specs, bps rounding, the sweep inputs, this section), not new steps or seams, so no second round.
- Questions: 16. Sources: ISSUE 7, CODE 13, DOC 2 (several questions cite more than one); NO SOURCE 5, all technical assumptions (above). Spec ambiguities: 0. Out of scope: 0.
- Issues opened: none.
