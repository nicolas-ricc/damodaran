# Which flags can be red: notes on four boards and a guard test — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Say on the analyze-flags and portfolio-mark-events boards, and on their stage boards, which narrative flags can turn red, and so which ones can fire `new_red_flag`. Add a test that fails when that statement stops being true.

**Architecture:** There are two `note` nodes on the analyze side: one inside `narrative_flags` on `analyze.d2` and one at top level on `analyze-flags.d2`. There are two on the portfolio side: one inside `events.new_red_flag` on `portfolio.d2` and one at top level on `portfolio-mark-events.d2`. Notes add no edges. One new test module section in `tests/unit/test_valuator_narrative_flags.py` pins the statement against `src/bot/valuator/narrative_flags.py`. SVGs and `rendered.sha256` come from the `pipeline-render` artifact of the `pipeline-diagram` workflow, because d2 is not on `PATH` here.

**Tech Stack:** d2 v0.9.0 (CI), Python 3 checks (`docs/pipeline/check.py`, pytest).

**Spec:** issue #218 and its Agent Brief comment. The conventions are in `docs/pipeline/README.md`.

## Global Constraints

- No change under `src/`. This plan does not change flag severities or supply country-exposure inputs (both are out of scope in #218).
- Notes use `class: note`, never `gap`, and carry no `@` directive inside the `|md ... |` block. Outside directives, no `@` starts a word in a comment (README "Directives").
- At most 24 edges per board (`test_edge_cap`). Notes add none.
- Keep every phrase that `_ANALYZE_TEXT` / `_PORTFOLIO_TEXT` already pin, in both test files, verbatim.
- Never edit an SVG or `rendered.sha256` by hand. Render with `docs/pipeline/build.sh`, or take the files from the `pipeline-render` artifact.
- Digits: the note text uses none (counts are written in words: "three", "five").

## Decisions taken here

1. **The brief's wording is narrowed to the five §7.5 flags, and `hypergrowth_story` is named.** `analyze` returns `narrative_flags(...) + hypergrowth_flags(...)` (`src/bot/valuator/analysis.py:827`). `mark_holdings` keeps every red flag of `analysis.narrative_flags` (`src/bot/portfolio/marks.py:158`). `hypergrowth_story_flag` returns `FlagColor.RED` for hypergrowth signals without a story file. So "only growth_reinvestment can fire it" is false today for a company with hypergrowth signals. The issue's goal is a board statement that is true and checked against the code, and a literally false note would defeat it. The exact copy is:
   - analyze side (`analyze.d2`, `analyze-flags.d2`): `Only growth_reinvestment can be red among the five checks: three stop at yellow and country exposure is always unknown. Among the hypergrowth flags, only hypergrowth_story can be red (signals without a story file).`
   - portfolio side (`portfolio.d2`; on `portfolio-mark-events.d2`, where the note is not nested in the event, "it" reads "new_red_flag", per the stage-5 review): `In practice only growth_reinvestment can fire it, or hypergrowth_story for a company with hypergrowth signals and no story file (see analyze flags).`
2. **The guard test checks the source and runs the code.** "No input produces RED" cannot be shown by sampling alone. For each never-red flag the test therefore asserts two things. First, the function's source (`inspect.getsource`) never names `FlagColor.RED`: every flag builds its `NarrativeFlag` with a literal colour, so this is a sound check. Second, a sweep of contexts and DCF results (it includes a negative-FCFF result and every boundary value of each threshold) never returns red. Never-red set: `story_margin_flag`, `beta_business_risk_flag`, `terminal_value_share_flag`, `hypergrowth_revenue_scale_flag`, `hypergrowth_terminal_roic_flag`. The test also asserts that the red-capable set is exactly `{growth_reinvestment, country_exposure, hypergrowth_story}`. Every flag *name* that `narrative_flags()` + `hypergrowth_flags()` emit, run on a hypergrowth story type with signals (so all three hypergrowth flags run), must be either never-red or red-capable. A new flag in either aggregator therefore breaks the test until someone classifies it. Each flag's name equals its function name without `_flag`.
3. **Note keys:** `narrative_flags.only_red` (`analyze.d2`), `only_red` (`analyze-flags.d2`), `events.new_red_flag.only_red` (`portfolio.d2`, with `label.near: outside-top-center` on `new_red_flag`, the same pattern as `narrative_flags.country_exposure`), and `only_red` (`portfolio-mark-events.d2`).

## Review Focus

- A reader of `portfolio-mark-events` takes the note to mean that a hypergrowth company never fires `new_red_flag` → the note names `hypergrowth_story` (Task 3 test pins "hypergrowth_story").
- Someone later makes `terminal_value_share` red above 90% (the issue's alternative) → the guard fails and names the flag (Task 1).
- Someone adds a sixth flag that can be red → the classification assertion fails (Task 1).
- Someone wires country-exposure inputs → the note's "always unknown" goes stale. The existing `_ANALYZE_GAPS["analyze-flags"]` gap test already ties that phrase to the gap note, and country exposure stays in the red-capable set, so the guard is not involved.
- A rendered SVG drops the note → `check.py` hash check plus `test_svg_keeps_every_link` (links only). Notes have no link, so this is verified by the `pipeline-render` CI job's hash check.

## Assumptions

Technical choices made in the plan review, each with the alternative it rejected:

- **A1. The copy names `hypergrowth_story` (Decision 1).** The rejected alternative is the brief's sentence verbatim. Backing:
  - The issue scopes its problem to the five flags ("Of the five narrative flags").
  - AC2 requires the statement to be "checked against the code".
  - The code shows the extra red source: `analysis.py:827` concatenates the hypergrowth flags, `analysis.py:889` stores them in `Analysis.narrative_flags`, and `marks.py:158` reads them.
  
  The brief's sentence is kept as the first clause, scoped to "the five checks".
- **A2. The flag classification is by emitted `NarrativeFlag.name`, not by a hand-listed set of functions.** There is no registry of hypergrowth flag functions, because `hypergrowth_flags()` calls them inline. Rejected alternative: listing `_FLAG_FUNCTIONS` plus three names by hand, which a new hypergrowth flag would slip past.
- **A3. The sweep is 1,296 contexts × 4 results.** Rejected alternative: the full product of the earlier list (about 207k calls).
- **A4. The source check is `"FlagColor.RED" not in inspect.getsource(flag)`.** In `narrative_flags.py`, `FlagColor.RED` appears only at lines 246 (`growth_reinvestment`), 386 (`country_exposure`) and 421 (`hypergrowth_story`). There are no aliases, no decorators, and no docstring that names it.

---

### Task 1: Guard test for the red-capable flags

**Files:**
- Test: `tests/unit/test_valuator_narrative_flags.py` (new section at the end)

**Interfaces:**
- Consumes: the public flag functions and `_FLAG_FUNCTIONS` of `bot.valuator.narrative_flags`.
- Produces: nothing used by other tasks.

- [ ] **Step 1: Write the tests**

```python
_NEVER_RED = (story_margin_flag, beta_business_risk_flag, terminal_value_share_flag,
              hypergrowth_revenue_scale_flag, hypergrowth_terminal_roic_flag)
_RED_CAPABLE = {"growth_reinvestment", "country_exposure", "hypergrowth_story"}  # NarrativeFlag.name

def test_every_flag_is_classified_by_red_capability() -> None:
    # Flags as analyze emits them: the five plus every hypergrowth flag (hypergrowth story type
    # with signals runs all of them), by NarrativeFlag.name, so a new flag in either
    # narrative_flags() or hypergrowth_flags() breaks this until it is classified.
    emitted = {f.name for f in narrative_flags(fin, asm, res, ctx) + hypergrowth_flags(fin, asm, res, ctx)}
    assert emitted == {f.__name__.removesuffix("_flag") for f in _NEVER_RED} | _RED_CAPABLE

@pytest.mark.parametrize("flag", _NEVER_RED, ids=lambda f: f.__name__)
def test_never_red_flag_source_names_no_red(flag) -> None:
    assert "FlagColor.RED" not in inspect.getsource(flag)

@pytest.mark.parametrize("flag", _NEVER_RED, ids=lambda f: f.__name__)
def test_never_red_flag_is_not_red_over_a_sweep(flag) -> None:
    # every context in the sweep × every DCF result in the sweep
    for fin, asm, res in _sweep_results():
        for ctx in _sweep_contexts():
            assert flag(fin, asm, res, ctx).color is not FlagColor.RED
```

`_sweep_contexts()` yields `NarrativeContext`s (every field has a default, so keyword construction is enough) built from the product of the following values:
- `story_type`: `None`, `"high-growth"`, `"hypergrowth"`.
- `company_operating_margin`: `None`, `0.05`, `0.30`.
- `sector_operating_margin`: `None`, `0.10`.
- `sector_beta`: `None`, `0.5`, `1.5`.
- `operating_leverage`: `None`, `3.0`.
- `company_debt_weight`: `None`, `0.9`.
- `terminal_roic`: `None`, `0.5`.
- `sector_roic`: `None`, `0.0`, `0.1`.

That makes 1,296 contexts, × 4 results × 5 flags, about 26k calls of pure functions, well under a second. The values put each flag in both its yellow branch and its unknown branch.

`_sweep_results()` reuses the module's `_financials()` (`Financials(revenue=1000.0, ...)`) and `_assumptions(**overrides)`. It covers four cases:
- the default assumptions;
- `sales_to_capital=0.1`: year-1 reinvestment is 100 / 0.1 = 1000, above NOPAT 150, so FCFF < 0;
- the fixture of `test_terminal_value_share_yellow_above_ceiling`;
- `Financials(revenue=1e12, net_debt=0.0, shares_diluted=100.0)`, whose year-10 revenue is above `_LARGEST_COMPANY_REVENUE = 750e9`.

- [ ] **Step 2: Run the tests.** `uv run pytest -q tests/unit/test_valuator_narrative_flags.py`. Expected: PASS. This is a characterization guard. To check its red state, temporarily change `terminal_value_share_flag`'s `FlagColor.YELLOW` to `FlagColor.RED`, see both parametrized tests fail for `terminal_value_share_flag`, then revert.
- [ ] **Step 3: Commit** (`test(#218): ...`).

### Task 2: Notes on the analyze boards

**Files:**
- Modify: `docs/pipeline/analyze.d2` (section 6, inside `narrative_flags`, after `hypergrowth`)
- Modify: `docs/pipeline/analyze-flags.d2` (after `always_unknown`)
- Test: `tests/unit/test_pipeline_diagram.py` (`_ANALYZE_NODES`, `_ANALYZE_TEXT`), `tests/unit/test_pipeline_subboards.py` (`_ANALYZE_TEXT["analyze-flags"]`)

- [ ] **Step 1: Failing tests.** Add `("narrative_flags.only_red", "note")` to `_ANALYZE_NODES`. Add `"narrative_flags.only_red": ["Only growth_reinvestment can be red", "three stop at yellow", "always unknown", "only hypergrowth_story can be red"]` to `_ANALYZE_TEXT` in `test_pipeline_diagram.py`. Add `"Only growth_reinvestment can be red"` and `"only hypergrowth_story can be red"` to `_ANALYZE_TEXT["analyze-flags"]` in `test_pipeline_subboards.py`.
- [ ] **Step 2: Run.** `uv run pytest -q tests/unit/test_pipeline_diagram.py tests/unit/test_pipeline_subboards.py`. Expected: the new entries FAIL.
- [ ] **Step 3: Add the notes** with the Decision 1 copy: `only_red: |md <copy> | {class: note}`.
- [ ] **Step 4: Run** the same command plus `python3 docs/pipeline/check.py`. Expected: the tests PASS, and `check.py` fails only on the stale `rendered.sha256` (fixed in Task 4).
- [ ] **Step 5: Commit** (`docs(#218): ...`).

### Task 3: Notes on the portfolio boards

**Files:**
- Modify: `docs/pipeline/portfolio.d2` (`events.new_red_flag`: add `label.near: outside-top-center` and the child note)
- Modify: `docs/pipeline/portfolio-mark-events.d2` (a top-level note after `out`, before `# Edges`)
- Test: `tests/unit/test_pipeline_diagram.py` (`_PORTFOLIO_NODES`, `_PORTFOLIO_TEXT`), `tests/unit/test_pipeline_subboards.py` (`_PORTFOLIO_TEXT["portfolio-mark-events"]`)

- [ ] **Step 1: Failing tests.** Add `("events.new_red_flag.only_red", "note")` to `_PORTFOLIO_NODES`. Add `"events.new_red_flag.only_red": ["only growth_reinvestment can fire it", "hypergrowth_story", "see analyze flags"]` to `_PORTFOLIO_TEXT`. Add `"only growth_reinvestment can fire it"` and `"hypergrowth_story"` to `_PORTFOLIO_TEXT["portfolio-mark-events"]`. Check that `test_portfolio_events_cover_every_event_type` stays green: it reads decision labels only, and a note is not a decision.
- [ ] **Step 2: Run.** Expected: the new entries FAIL.
- [ ] **Step 3: Add the notes** with the Decision 1 copy.
- [ ] **Step 4: Run** the same tests. Expected: PASS.
- [ ] **Step 5: Commit** (`docs(#218): ...`).

### Task 4: Render

- [ ] Push the branch and wait for the `pipeline-diagram` run on its head (`gh run list --branch <b> --workflow pipeline-diagram`, `gh run watch`). Download `pipeline-render` (`gh run download <id> -n pipeline-render`). Copy the four changed SVGs and `rendered.sha256` into `docs/pipeline/`. Then confirm that `git status` shows only those boards' SVGs changed, plus any others d2 re-renders identically. Run `python3 docs/pipeline/check.py` and expect it to pass, then run the full suite. Commit `docs(#218): render`.

## Grilling

- **Rounds:** one. The revision changed values and the test's mechanism, not steps or seams.
- **Questions:** 17.
- **Answers by source:** CODE 13, ISSUE 2, DOC 2, NO SOURCE 0. Three answers corrected the plan: the sweep size (Q5), the classification mechanism (Q7) and the explicit field names (Q10).
- **Assumptions:** A1 to A4 above.
- **Issues opened:** none.
