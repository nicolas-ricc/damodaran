# Hypergrowth classifier, story-file gate and red flag Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `StoryType.HYPERGROWTH`. The classifier evaluates it before distress. A `hypergrowth` label without a `story:` section in the override falls back to `high-growth` and gets a red `hypergrowth_story` flag. Every other company values exactly as it does today.

**Architecture:** `story_types.classify` gains a first rule `_is_hypergrowth`, fed by two new optional fields on `ClassificationFinancials` and one on `SectorContext`. `analyze` reads the override once, before classification, through `load_override`, and passes the mapping into `resolve_assumptions(override=...)`. The gate lives in `assumptions._resolve_story_type`. `narrative_flags` gains a separate `hypergrowth_flags()` that `analyze` appends; the five existing flags stay untouched. Two docs that tests tie to the `StoryType` enum (lesson chapter 6 and two d2 boards) get the new label.

**Tech Stack:** Python 3.12, frozen dataclasses, DuckDB (tests in memory), pytest, structlog (`bot.utils.logging.get_logger`), d2 (rendered in CI only).

**Spec:** GitHub issue #195 (nicolas-ricc/damodaran), parent story #192. Executors read the issue body: its "Design (decided; implement as written)" section is binding.

## Global Constraints

- Modules under `src/bot/valuator/` are pure: no I/O, no global state, frozen dataclasses. Module constants carry a `#:` comment explaining the value.
- Constants, verbatim: `_HYPERGROWTH_LAST_YEAR_GROWTH = 0.50`, `_HYPERGROWTH_CAGR = 0.40`, `_HYPERGROWTH_MAX_AGE_YEARS = 15`.
- Isolation: every story type other than `hypergrowth` values exactly as it does today. Every existing test passes **unmodified**, with one exception: `tests/unit/test_valuator_analysis.py::test_analyze_returns_complete_result` keeps its `== 5` (AAPL is not hypergrowth).
- Flag copy, verbatim: red `"hypergrowth signals but no story file: default valuation is not reliable"`; yellow `"story file present but the classifier signals are absent"`. The log event is `assumptions.story_type.hypergrowth_without_story`.
- `uv run pytest -q`, `uv run ruff check . && uv run mypy src` (strict), `python3 docs/pipeline/check.py` and `python3 docs/leccion/check.py` must all be green.
- Commits: Conventional Commits with `#195`, e.g. `feat(#195): ...`.
- Never write `docs/pipeline/rendered.sha256` or the SVGs by hand. They come from the `pipeline-diagram` CI artifact (Task 5).

## Review Focus

1. **A company the classifier calls `hypergrowth` whose override sets another `story_type` manually** (e.g. `mature-stable`). The manual type must win and no fallback must happen. The reasons must say "manually overridden" (the type *was* overridden). → Task 3 test `test_manual_story_type_beats_hypergrowth_gate`, Task 4 test `test_manual_override_of_hypergrowth_says_overridden`.
2. **Zero, negative or one-point revenue history.** `_is_hypergrowth` must return False without raising: last-year growth needs the last two points positive, and the CAGR is `None` through non-positive endpoints. → Task 1 test `test_hypergrowth_needs_two_positive_points`.
3. **Unknown company or sector margin.** The rule must not fire, and the company then follows today's chain unchanged. → Task 1 test `test_hypergrowth_needs_both_margins`.
4. **An existing override file with neither `story` nor `founded_year`** (e.g. a `notes:`-only or `operating_margin:` override) on an Anthropic-shaped company. The fallback must still happen and the existing override keys must still apply. → Task 4 test `test_hypergrowth_fallback_keeps_other_override_keys`.
5. **Callers of `resolve_assumptions` that still pass only `override_path`** (the screener path and existing tests). Behaviour must be identical. When both `override` and `override_path` are given, `override` wins and the file is not read. → Task 3 test `test_override_mapping_wins_over_path`.

---

### Task 1: Classifier rule `hypergrowth`

**Files:**
- Modify: `src/bot/valuator/story_types.py`
- Test: `tests/unit/test_valuator_story_types.py` (append only)

**Interfaces:**
- Produces: `StoryType.HYPERGROWTH = "hypergrowth"` (the first member of the enum, before `HIGH_GROWTH`). `ClassificationFinancials.operating_margin: float | None = None`. `ClassificationFinancials.founded_age_years: int | None = None`. `SectorContext.operating_margin: float | None = None`. A private `_is_hypergrowth(financials, sector) -> bool`. `classify` returns `HYPERGROWTH` before the distress check.

- [ ] **Step 1: Write the failing tests** (append to the test file; reuse its `_financials` / `_sector` helpers)

```python
def _anthropic(**overrides: object) -> ClassificationFinancials:
    base: dict[str, object] = dict(
        revenue_history=(1_020.0, 20_608.0),
        earnings_history=(-5_000.0, -40_000.0),
        age_years=1,
        interest_coverage=0.1,
        altman_z=None,
        operating_margin=-2.2798,
        founded_age_years=5,
    )
    base.update(overrides)
    return ClassificationFinancials(**base)  # type: ignore[arg-type]

_AI_SECTOR = SectorContext(is_cyclical=False, operating_margin=0.28)

test_anthropic_shaped_is_hypergrowth_not_distressed            -> classify(_anthropic(), _AI_SECTOR) is StoryType.HYPERGROWTH
test_hypergrowth_with_unknown_founding_age                     -> founded_age_years=None -> HYPERGROWTH
test_decades_old_company_is_not_hypergrowth                    -> founded_age_years=40 -> DISTRESSED
test_nvda_shaped_margin_above_sector_is_not_hypergrowth        -> revenue_history=(27_000.0, 61_000.0, 130_000.0), operating_margin=0.62, interest_coverage=300.0, sector margin 0.28 -> is not HYPERGROWTH
test_45pct_last_year_grower_is_not_hypergrowth                 -> revenue_history=(100.0, 200.0, 290.0) (CAGR 70%, last year 45%) -> is not HYPERGROWTH
test_hypergrowth_thresholds_fire_at_equality (parametrized):
    last-year growth exactly 0.50 with CAGR >= 0.40: revenue_history=(100.0, 150.0) -> HYPERGROWTH
    CAGR exactly 0.40 with last year >= 0.50: revenue_history=(100.0, 98.0, 196.0) (CAGR sqrt(1.96)-1, last year 100%) -> HYPERGROWTH
    CAGR just below: revenue_history=(100.0, 98.0, 195.0) -> not HYPERGROWTH
    founded_age_years=15 -> HYPERGROWTH; founded_age_years=16 -> not HYPERGROWTH
test_hypergrowth_margin_equal_to_sector_does_not_fire          -> operating_margin=0.28, sector 0.28 -> not HYPERGROWTH
test_hypergrowth_needs_both_margins                            -> operating_margin=None -> DISTRESSED; sector operating_margin=None -> DISTRESSED
test_hypergrowth_needs_two_positive_points                     -> revenue_history=(20_608.0,) -> DISTRESSED; (0.0, 20_608.0) -> DISTRESSED; (-1.0, 20_608.0) -> DISTRESSED
```

**Float equality (decided).** `(1.96) ** 0.5 - 1` evaluates to `0.3999999999999999`, so a decimal 40% CAGR never reaches the float `0.40` through `_cagr` for any fixture written in round decimals. Both growth comparisons in `_is_hypergrowth` therefore use a tolerance: `value >= threshold - _THRESHOLD_TOLERANCE`, where `_THRESHOLD_TOLERANCE = 1e-9` is a module constant with a `#:` comment saying it absorbs float error so that "at least 40%" fires at 40%. The existing rules keep their exact comparisons (isolation).

- [ ] **Step 2: Run `uv run pytest tests/unit/test_valuator_story_types.py -q`.** Expected: the new tests FAIL (AttributeError / TypeError on the new fields).

- [ ] **Step 3: Implement.**
  - Add the three constants after `_DECLINE_CAGR`, each with a `#:` comment: last-year growth (needs two positive points), CAGR over the available history (2 points suffice), and founding age (distinct from the IPO-based `_MATURE_AGE_YEARS`).
  - Add the fields with docstring entries. `founded_age_years` is years since founding, distinct from `age_years`, which keeps feeding the high-growth rule.
  - `_is_hypergrowth`: last-year growth is `history[-1] / history[-2] - 1`, only when `len >= 2` and both points are `> 0`. Reuse `_cagr`. Margins: both known and `company < sector` (strict). Age: `founded_age_years is None or <= 15`. All four must hold.
  - `classify`: `if _is_hypergrowth(...): return StoryType.HYPERGROWTH` as the first line. Renumber the docstring's rules (hypergrowth becomes 1, distressed 2, and so on). Add `hypergrowth` to the module header's archetype list, and say there that there are now six archetypes.

- [ ] **Step 4: Run `uv run pytest tests/unit/test_valuator_story_types.py -q`.** Expected: PASS, including every pre-existing test.

- [ ] **Step 5: Commit** `feat(#195): hypergrowth classifier rule before distress`.

Note: adding an enum member makes `tests/unit/test_leccion.py` and `tests/unit/test_pipeline_diagram.py` fail until Task 5. That is expected between tasks.

---

### Task 2: `hypergrowth_story` flag

**Files:**
- Modify: `src/bot/valuator/narrative_flags.py`
- Test: `tests/unit/test_valuator_narrative_flags.py` (append; create the helpers it needs locally if absent)

**Interfaces:**
- Produces: `NarrativeContext.hypergrowth_signals: bool = False`, `NarrativeContext.story_file_present: bool = False`. `hypergrowth_story_flag(financials, assumptions, result, context) -> NarrativeFlag` (name `"hypergrowth_story"`). `hypergrowth_flags(financials, assumptions, result, context) -> tuple[NarrativeFlag, ...]`.

- [ ] **Step 1: Write the failing tests**

```
test_hypergrowth_story_red_without_story      -> signals=True, story=False -> RED, reason == "hypergrowth signals but no story file: default valuation is not reliable"
test_hypergrowth_story_yellow_without_signals -> signals=False, story=True -> YELLOW, reason == "story file present but the classifier signals are absent"
test_hypergrowth_story_green_with_both        -> signals=True, story=True -> GREEN
test_hypergrowth_flags_empty_for_other_types  -> story_type="high-growth", signals=False -> ()
test_hypergrowth_flags_on_signals             -> story_type="high-growth", signals=True -> one flag named "hypergrowth_story"
test_hypergrowth_flags_on_story_type          -> story_type="hypergrowth", signals=False, story=True -> one YELLOW flag
test_narrative_flags_still_five               -> len(narrative_flags(...)) == 5 with signals=True
```

The GREEN reason is free text; it must say that both the signals and the story file are present.

- [ ] **Step 2: Run the file.** Expected: FAIL.
- [ ] **Step 3: Implement.** Add the two fields to `NarrativeContext` (document them in its docstring), the two functions, and one sentence in the module docstring saying that the hypergrowth flag sits outside the five §7.5 flags. `narrative_flags()` and `_FLAG_FUNCTIONS` stay unchanged.
- [ ] **Step 4: Run the file.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(#195): hypergrowth_story narrative flag`.

---

### Task 3: `resolve_assumptions(override=...)` and the gate

**Files:**
- Modify: `src/bot/valuator/assumptions.py` (`resolve_assumptions`, `_resolve_story_type`)
- Test: `tests/unit/test_valuator_assumptions.py` (append; reuse its `_write_override` and its seeded `conn` fixture)

**Interfaces:**
- Consumes: `StoryType.HYPERGROWTH` (Task 1).
- Produces: `resolve_assumptions(ticker, conn, override_path=None, *, override: Mapping[str, Any] | None = None, auto_story_type=None, db_inputs=None, currencies=None)`. When `override` is not `None`, `override_path` is not read. `_resolve_story_type(override, auto_story_type) -> str | None` now returns `"high-growth"` when the label would be `"hypergrowth"` and `"story"` is not in the override, and it logs `log.info("assumptions.story_type.hypergrowth_without_story")`.

- [ ] **Step 1: Write the failing tests**

```
test_hypergrowth_without_story_falls_back_to_high_growth -> resolve_assumptions(..., auto_story_type=StoryType.HYPERGROWTH) -> story_type == "high-growth"
test_hypergrowth_with_story_keeps_label_and_generic_resolvers ->
    override = load_override(<yaml: story_type: hypergrowth + full story from tests/unit/test_valuator_hypergrowth.py::_STORY>)
    resolve_assumptions(..., override=override, auto_story_type=StoryType.HYPERGROWTH)
    -> story_type == "hypergrowth"; revenue_growth.source == AssumptionSource.HISTORICAL_AVERAGE   # pins the intermediate state (story projection is #196)
test_manual_story_type_beats_hypergrowth_gate -> override {"story_type": "mature-stable"} + auto HYPERGROWTH -> "mature-stable"
test_override_mapping_wins_over_path -> override={"operating_margin": 0.35} and override_path=<file with operating_margin: 0.10> -> operating_margin == (0.35,)*5, MANUAL
test_fallback_is_logged -> structlog.testing.capture_logs() contains event "assumptions.story_type.hypergrowth_without_story"
```

The YAML for the story file is written with `yaml.safe_dump({"story_type": "hypergrowth", "story": _STORY})`. Import `_STORY` from `tests.unit.test_valuator_hypergrowth` only if the tests package is importable that way; otherwise duplicate the dict in a module constant with a comment pointing at the original.

- [ ] **Step 2: Run the file.** Expected: FAIL.
- [ ] **Step 3: Implement.** `override = dict(override) if override is not None else load_override(override_path)`. In `_resolve_story_type`, compute the label as today, then apply the gate. Document the keyword in the docstring.
- [ ] **Step 4: Run the file plus `tests/unit/test_analyze_story_override.py`.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(#195): hypergrowth gate on the story file in resolve_assumptions`.

---

### Task 4: `analyze` wiring: override read once, signals, reasons, flags

**Files:**
- Modify: `src/bot/valuator/analysis.py`
- Test: `tests/unit/test_valuator_analysis.py` (append only)

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: `Analysis.auto_story_type: str` (the classifier's own verdict, `.value`) and `Analysis.story_file_present: bool`, declared right after `story_type`, without defaults (`analyze` is the only constructor). `narrative_flags = narrative_flags(...) + hypergrowth_flags(...)`.

- [ ] **Step 1: Write the failing tests.** Seed helper `_seed_anthropic(conn, ticker)`: `_seed_company(conn, ticker, "Software (System & Application)")`, then `UPDATE damodaran_industry SET op_margin = 0.28`. Two `financials_annual` rows (2024, 2025) with revenue `1_020.0` and `20_608.0` (×`_MILLIONS`), ebit `-2.2798 × revenue`, net income equal to ebit, interest_expense `1_000.0 × _MILLIONS`, total_debt `0`, cash `114_000.0 × _MILLIONS`, shares `3_298.14 × _MILLIONS`.

```
test_hypergrowth_without_story_values_as_high_growth_with_red_flag ->
    a = analyze("ANTH", conn)
    a.story_type == "high-growth"; a.auto_story_type == "hypergrowth"; a.story_file_present is False
    len(a.narrative_flags) == 6; a.narrative_flags[-1].name == "hypergrowth_story"; color is FlagColor.RED
    not any("manually overridden" in r for r in a.story_reasons)
    any("no story file" in r for r in a.story_reasons)
test_hypergrowth_with_story_file ->
    override yaml {story_type: hypergrowth, story: <full story>}
    a.story_type == "hypergrowth"; a.story_file_present is True; a.narrative_flags[-1] GREEN
    a.assumptions.revenue_growth.source == AssumptionSource.HISTORICAL_AVERAGE
test_founded_year_40_years_back_is_distressed -> override {founded_year: date.today().year - 40} -> a.story_type == "distressed"
test_mature_company_still_has_five_flags -> AAPL seed (seeded_conn) -> len == 5, no flag named "hypergrowth_story"
test_hypergrowth_reasons_list_the_signals -> no override: reasons contain "last-year revenue growth 1920.4%", "operating margin -228.0% below sector 28.0%", "founding year unknown", "classified as hypergrowth"
test_hypergrowth_fallback_keeps_other_override_keys -> override {operating_margin: 0.35}: story_type "high-growth", operating_margin MANUAL, flag RED
test_manual_override_of_hypergrowth_says_overridden -> override {story_type: mature-stable}: reasons[0] starts with "manually overridden" and names "hypergrowth"; flag "hypergrowth_story" present and RED (signals, no story)
```

Compute the exact last-year growth figure from the seed (`20_608 / 1_020 − 1 = 19.2039…`, formatted `.1%` → `"1920.4%"`). The issue's "1920.0%" is illustrative.

- [ ] **Step 2: Run the file.** Expected: FAIL.
- [ ] **Step 3: Implement in `analyze`:**
  - `override = load_override(override_path)` at the top, after loading the inputs.
  - `founded_age_years = _date.today().year - int(override["founded_year"])` when the key is present, else `None`.
  - Hoist the existing `company_operating_margin` computation above the classification and reuse it for both `ClassificationFinancials(operating_margin=...)` and `NarrativeContext`.
  - `SectorContext(is_cyclical=cyclical, operating_margin=sector.op_margin)`.
  - Pass `override=override` to `resolve_assumptions`, and keep `override_path` passed too, for logging parity.
  - `manual = override.get("story_type")`, `story_file_present = "story" in override`, `hypergrowth_fallback = auto_story is StoryType.HYPERGROWTH and manual is None and not story_file_present`.
  - `overridden = manual is not None and str(manual) != auto_story.value`. This is equivalent to today's expression for every non-hypergrowth case.
  - `NarrativeContext(..., hypergrowth_signals=auto_story is StoryType.HYPERGROWTH, story_file_present=story_file_present)`.
  - Extend `_story_reasons` with the keywords `operating_margin`, `sector_operating_margin`, `founded_age_years` and `hypergrowth_fallback`. For a non-hypergrowth verdict the output is byte-identical to today. For the `hypergrowth` verdict (not overridden), the reasons are:
    - `f"last-year revenue growth {g:.1%}"`
    - `f"revenue CAGR {c:.1%} over {n} years"`
    - `f"operating margin {m:.1%} below sector {s:.1%}"`
    - `f"founded {a} years ago"` or `"founding year unknown"`
    - `"classified as hypergrowth"`
    - then, when the gate fell back, `"hypergrowth signals but no story file: valued as high-growth, see the hypergrowth_story flag"`
  - Update the `Analysis` docstring (the five flags are now five, plus the hypergrowth flag when it applies) and document the two new attributes.
- [ ] **Step 4: Run `uv run pytest tests/unit/test_valuator_analysis.py tests/unit/test_analyze_story_override.py tests/unit/test_reporting_analysis_json.py -q`.** Expected: PASS.
- [ ] **Step 5: Commit** `feat(#195): analyze reads the override once and wires the hypergrowth gate`.

---

### Task 5: Enum-tied docs (lesson chapter 6, two d2 boards) and the CI render

**Files:**
- Modify: `docs/leccion/index.html` (chapter 6: the sentence listing the labels, and the rules table)
- Modify: `docs/pipeline/analyze.d2` (the `story_type.distressed` label only), `docs/pipeline/analyze-story.d2` (the `classified` node label only)
- Regenerate from CI: `docs/pipeline/*.svg`, `docs/pipeline/rendered.sha256`

- [ ] **Step 1: Run `uv run pytest tests/unit/test_leccion.py tests/unit/test_pipeline_diagram.py -q`.** Expected: FAIL on `hypergrowth` missing (after Task 1).
- [ ] **Step 2: Lesson.** Change "Las etiquetas son cinco" to "seis" and add `<code>hypergrowth</code>` with a short gloss. Add a row `0` before `distressed` with the issue's exact Spanish text, citing `_HYPERGROWTH_LAST_YEAR_GROWTH` (`value="0.5"`, shown as `50 %`), `_HYPERGROWTH_CAGR` (`value="0.4"`, `40 %`) and `_HYPERGROWTH_MAX_AGE_YEARS` (`value="15"`, `15 años`) with `<data data-const=...>` tags like the existing rows. Run `python3 docs/leccion/check.py`. It must pass; fix the line-number warnings that this edit causes.
- [ ] **Step 3: Boards.** In `analyze.d2`, the `distressed:` label becomes `"hypergrowth, then distressed: ..."`. The hypergrowth part reads: last-year growth ≥ 50%, CAGR ≥ 40%, margin below sector, founded ≤ 15 years or unknown. Add `@const` citations on that line for the three new constants. In `analyze-story.d2`, the `classified` label's ordered list gains `hypergrowth` first. Add no nodes and no edges. Read `docs/pipeline/README.md` for the digit-citation rule. Run `python3 docs/pipeline/check.py` (the render-hash check fails until Step 4; every other check must pass) and the two test files.
- [ ] **Step 4: Commit** `docs(#195): hypergrowth in lesson chapter 6 and the analyze boards`. Then push the branch. Get the run with `gh run list --branch <branch> --workflow pipeline-diagram`, `gh run watch <id>` in the foreground, then `gh run download <id> -n pipeline-render -D docs/pipeline`. Commit the SVGs and `rendered.sha256` as `docs(#195): render boards from CI`. Confirm that `python3 docs/pipeline/check.py` passes and that the following run is green.
- [ ] **Step 5: Run the full suite and lint.**
