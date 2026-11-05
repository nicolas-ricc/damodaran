# One revenue CAGR everywhere (#215): implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: use subagent-driven-development to implement this plan task by task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The story classifier, the historical growth path, the report reasons and the screener all read revenue growth from a single `bot.utils.finance.cagr(series) -> float | None`.

**Architecture:** `cagr` returns `None` when the rate is undefined and never returns a complex number. `story_types._cagr` is deleted. `_growth_path_from_revenues` projects `cagr(revenues)` flat and drops the arithmetic mean of year-over-year growths. Every caller handles `None` explicitly. The atlas boards and the lesson stop saying "mean".

**Tech Stack:** Python 3.12, pytest, DuckDB, d2 v0.9.0 (atlas render).

**Spec:** issue #215, specifically its "Agent Brief" comment (decision recorded on 2026-11-05: CAGR in both places).

## Global Constraints

- `cagr(series)` returns `None` when there are fewer than 2 points or when the first or last value is ≤ 0. Otherwise it returns `(last/first)^(1/(n−1)) − 1`. It never returns a complex number.
- `grep -rn "def _cagr\|fmean(growths" src` returns nothing.
- The path shape (flat, or the fade of #216) is not this issue's concern. Fiscal-year gaps (#125) are out of scope.
- `mypy --strict` (`uv run mypy src`), `uv run ruff check .`, `python3 docs/pipeline/check.py` and `uv run pytest -q` all pass.
- Conventional commits, `(#215)` scope.

## Review Focus

1. **A positive base with a negative last value**, e.g. `(100, -50, -20)`. The old `cagr` returned a complex number here, and a complex number breaks the screener's percentile sort. The new `cagr` returns `None`, and the screener's growth metric becomes `0.0`. Pinned in Task 1 (unit test and screener test).
2. **A last value of exactly 0.** The old `cagr` returned `-1.0` for it; the new one returns `None` (growth metric `0.0`). Pinned in Task 1.
3. **The hypergrowth reasons branch.** `_hypergrowth_reasons` formats the CAGR with `:.1%`, so a `None` must never reach that f-string. Pinned in Task 1.
4. **The bulk loader vs the per-ticker loader.** Both call `_growth_path_from_revenues` and must give the same CAGR path. Pinned in Task 2 (both paths tested with 100, 150, 100, 150).
5. **The high-growth fade.** The fade starts at `fmean(historical)`, which is the CAGR now that the path is flat. This is unchanged by design (#216 owns it), and the existing fade test keeps passing.

## Assumptions

- **Per-commit gate.** Each task's commit passes pytest, mypy and ruff. `docs/pipeline/check.py` (the render hash) is required only from Task 3 on, because Task 1's directive edits change the hashed sources and only Task 3 re-renders. The PR is squash-merged, so no red commit reaches `master`. Rejected: rendering in Task 1 and again in Task 3, which is two renders for one change.
- **The `historical_average` label stays.** A CAGR is the geometric average of yearly growth, so the label (`AssumptionSource.HISTORICAL_AVERAGE`, `src/bot/web/views.py:72` "historical average") stays accurate. Rejected: renaming it, which would change persisted and displayed strings the issue does not ask to change.
- **The lesson wording is updated as well as the atlas.** The brief names only the atlas, but `docs/leccion/index.html:623,667,705` describes the same computation as "promedio" and would otherwise contradict the code.

---

### Task 1: `cagr` becomes `float | None`, and every reader of revenue CAGR uses it

**Files:**
- Modify: `src/bot/utils/finance.py` (`cagr`)
- Modify: `src/bot/valuator/story_types.py` (delete `_cagr` at lines 143-155; `_is_hypergrowth` and `classify` call `bot.utils.finance.cagr`)
- Modify: `src/bot/valuator/analysis.py` (`_story_reasons` around line 685, `_hypergrowth_reasons` around line 706)
- Modify: `src/bot/screener/engine.py:655-657` (`_growth_metric`)
- Modify: `tests/unit/test_pipeline_diagram.py` (lines 175 and 304: `bot.valuator.story_types._cagr` → `bot.utils.finance.cagr`), plus the `@symbol bot.valuator.story_types._cagr` directives in `docs/pipeline/analyze.d2:81` and `docs/pipeline/analyze-story.d2:44` → `@symbol bot.utils.finance.cagr`. Deleting `_cagr` would otherwise break that test and `check.py`'s symbol check in this commit. The render hash stays stale until Task 3.
- Test: `tests/unit/test_utils_finance.py` (new), `tests/unit/test_revenue_cagr_single_source.py` (new)

**Interfaces:**
- Produces: `bot.utils.finance.cagr(series: tuple[float, ...] | Sequence[float]) -> float | None`. Annotate it with `Sequence[float]` from `collections.abc` so Task 2 can pass a list.
- `bot.screener.engine._growth_metric(company: CompanyData) -> float` keeps its type.

- [ ] **Step 1: Write the failing tests.** In `tests/unit/test_utils_finance.py`:
  - `cagr((100.0, -50.0)) is None` and `cagr((100.0, -50.0, -20.0)) is None`. Also assert `not isinstance(..., complex)` on these.
  - `cagr((0.0, 10.0)) is None`, `cagr((10.0,)) is None`, `cagr(()) is None`, `cagr((100.0, 0.0)) is None`.
  - `cagr((100.0, 121.0)) == pytest.approx(0.21)`.
  - `cagr((100.0, 150.0, 100.0, 150.0)) == pytest.approx(1.5 ** (1 / 3) - 1)`, which is ≈ 0.1447.
  - `cagr((100.0, -50.0, 121.0)) == pytest.approx(0.1)`: only the endpoints matter, as the spec says. A negative middle year is #125's territory, not this issue's.

  In `tests/unit/test_revenue_cagr_single_source.py` (criterion 3: one history fed to all three readers):
  - `test_one_history_one_number`, parametrized over `(100, 150, 100, 150)` and `(100, 110, 121)`:
    - `rate = cagr(h)`.
    - `_growth_metric(CompanyData(ticker="X", name="X", revenue_history=h)) == rate`.
    - `_story_reasons(StoryType.MATURE_STABLE, h, None, overridden=False)[0] == f"historical revenue CAGR {rate:.1%} over {len(h) - 1} years"`.
    - `classify(ClassificationFinancials(revenue_history=h, earnings_history=()), SectorContext())` is `StoryType.MATURE_STABLE` for both (rate < 0.15). This proves the classifier does not use the 22.2% mean.
  - `test_high_growth_threshold_reads_cagr`: `h = (100.0, 150.0, 100.0, 150.0)` with `age_years=5` classifies as `MATURE_STABLE`, while `(100.0, 120.0, 140.0, 160.0)` (CAGR ≈ 0.17) classifies as `HIGH_GROWTH`.
  - `test_undefined_history_is_undefined_everywhere`, parametrized over `(100.0, -50.0, -20.0)`, `(0.0, 10.0)` and `(10.0,)`:
    - `_growth_metric(...) == 0.0`.
    - `_story_reasons(...)[0] == "too little revenue history for a reliable growth signal"`.
    - `classify(...)` is `StoryType.MATURE_STABLE`.
  - `test_hypergrowth_reasons_cite_the_shared_cagr`: `_story_reasons(StoryType.HYPERGROWTH, (100.0, 200.0, 400.0), None, overridden=False, founded_age_years=3)` contains `f"revenue CAGR {cagr((100.0, 200.0, 400.0)):.1%} over 2 years"`.

- [ ] **Step 2: Run them and check they fail.** `uv run pytest tests/unit/test_utils_finance.py tests/unit/test_revenue_cagr_single_source.py -q` fails: the old `cagr` returns `0.0`/complex/`-1.0` where the tests expect `None`, and the undefined-history `_story_reasons` case for `(100, -50, -20)` crashes or prints a complex number.

- [ ] **Step 3: Implement.**
  - `cagr` returns `None` for `len < 2`, `first <= 0` or `last <= 0`. Otherwise it returns `float((last / first) ** (1.0 / periods)) - 1.0`. Update the docstring: undefined means `None`, never `0.0`, and no complex result is possible.
  - `story_types`: `from bot.utils.finance import cagr`. Delete `_cagr`. Rename the local variables called `cagr` in `_is_hypergrowth` and `classify` to `rate` so they do not shadow the import.
  - `_story_reasons`: `rate = cagr(revenue_history)`. If `rate is None`, use the "too little revenue history…" line; otherwise keep the existing CAGR line. Drop the duplicated `len >= 2 and [0] > 0` guard.
  - `_hypergrowth_reasons`: emit the `revenue CAGR …` line only when the rate is not `None`; otherwise emit "too little revenue history for a reliable growth signal". The classifier makes `None` unreachable here, but the type allows it.
  - `_growth_metric`: `rate = cagr(...)`, then `return rate if rate is not None else 0.0`. Docstring: a missing growth signal counts 0, the same rule as the missing ROE in `_quality_metric` (the screener's existing missing-signal rule). Comment the behaviour change: previously a positive base with a last value ≤ 0 gave `-1.0` (last = 0) or a complex/negative number; now it gives `0.0`.

- [ ] **Step 4: Run the touched tests.** `uv run pytest tests/unit/test_utils_finance.py tests/unit/test_revenue_cagr_single_source.py tests/unit/test_valuator_story_types.py tests/unit/test_screener_engine.py tests/unit/test_valuator_analysis.py tests/unit/test_pipeline_diagram.py tests/unit/test_screener_second_pass_golden.py -q` passes, and `uv run mypy src` is clean. The existing pins stay green unchanged: `test_valuator_story_types.py:172` (`(100, -50)` → mature-stable) and `test_valuator_analysis.py:637` ("revenue CAGR 1920.4% over 1 years"). The golden stays green too, because its series are geometric and positive.

- [ ] **Step 5: Commit.** `fix(#215): one cagr returning None when undefined`

### Task 2: the historical growth path uses CAGR; regenerate the golden

**Files:**
- Modify: `src/bot/valuator/assumptions.py:628-659` (`_growth_path_from_revenues`, `_historical_growth_path` docstring, `_resolve_revenue_growth` docstring). Remove the now-unused `itertools` import if nothing else uses it; `fmean` stays (it is used elsewhere).
- Modify: `tests/fixtures/screener/second_pass_shortlist.golden` (regenerate with the command in `tests/unit/test_screener_second_pass_golden.py`'s docstring), plus a docstring note in that test.
- Test: `tests/unit/test_valuator_assumptions.py`

**Interfaces:**
- Consumes: `bot.utils.finance.cagr(series: Sequence[float]) -> float | None` (Task 1).
- `_growth_path_from_revenues(revenues: Sequence[float]) -> tuple[float, ...] | None` keeps its signature.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_valuator_assumptions.py`:
  - `test_revenue_growth_path_is_the_cagr_not_the_mean_of_yearly_growth`: seed rows `(2021, 100, 18), (2022, 150, 27), (2023, 100, 18), (2024, 150, 27)` using the existing `_seed_full_sector` and `_seed_financials`. `resolve_assumptions("ACME", conn)` gives source `HISTORICAL_AVERAGE`, and every year equals `pytest.approx(1.5 ** (1 / 3) - 1)` (≈ 0.1447), which is not 0.2222.
  - The same assertion through both loaders: `load_assumption_inputs(conn, "ACME").historical_growth_path` (per-ticker, `-> AssumptionInputs`) and `bulk_load_assumption_inputs(conn, ["ACME"])["ACME"].historical_growth_path` (`-> dict[str, AssumptionInputs]`).
  - `test_revenue_growth_with_a_non_positive_last_revenue_has_no_history`: rows `(2023, 100, 18), (2024, -10, -5)` with `_usd()` currencies give source `RULE_BASED`, because the history counts as undefined.

- [ ] **Step 2: Run them and check they fail.** `uv run pytest tests/unit/test_valuator_assumptions.py -q -k "cagr or non_positive"` fails with 0.2222 vs 0.1447.

- [ ] **Step 3: Implement.** `_growth_path_from_revenues`: `rate = cagr(revenues)`, return `None` if it is `None`, else `(rate,) * _HORIZON`. Docstring: flat path at the revenue CAGR (`bot.utils.finance.cagr`), `None` when that is undefined. The `_historical_growth_path` and `_resolve_revenue_growth` docstrings say "historical revenue CAGR" instead of "average year-over-year growth". The enum label `historical_average` keeps its name.

- [ ] **Step 4: Regenerate the golden.** Never hand-edit it. Use the command in the test's docstring. `git diff tests/fixtures/screener/second_pass_shortlist.golden` lists which tickers moved and by how much. The seeded series are geometric, so CAGR equals the mean up to floating point and only last-digit drift is expected. Append a one-line note to the test docstring ("regenerated for #215: growth path is CAGR"). Record the moved tickers and why in the commit body. If a ticker changes rank, keep the code (the behaviour change is deliberate) and say so in the commit body.

- [ ] **Step 5: Run.** `uv run pytest -q` passes in full, `grep -rn "def _cagr\|fmean(growths" src` is empty, and mypy and ruff are clean.

- [ ] **Step 6: Commit.** `fix(#215): growth path projects the revenue CAGR`, with a body listing the moved tickers.

### Task 3: atlas boards and lesson say CAGR

**Files:**
- Modify: `docs/pipeline/analyze.d2`:
  - line 112: "mean historical growth" → "historical growth (CAGR)"; the last lines become "historical growth = revenue CAGR = (last ÷ first)^(1 ÷ (years − 1)) − 1, at least two years, first and last > 0"
- Modify: `docs/pipeline/analyze-assumptions.d2:59`: "mean historical growth" → "historical revenue CAGR"
- Modify: `docs/pipeline/screen.d2:185`: "growth = 0 when fewer than two years or first ≤ 0" → "growth = 0 when fewer than two years, or first or last ≤ 0"
- Modify: `docs/leccion/index.html` lines 623, 667, 705: "promedio histórico" → "tasa anual compuesta histórica de las ventas" (or the closest natural wording); keep the `historical_average` label
- Re-render: `docs/pipeline/build.sh` with d2 v0.9.0. Install it with `curl -fsSL https://d2lang.com/install.sh | sh -s -- --version v0.9.0 --method standalone --prefix "$HOME/.local"`, the same command CI uses. This updates the SVGs and `rendered.sha256`.

- [ ] **Step 1: Check the starting state.** `python3 docs/pipeline/check.py` fails on the stale `rendered.sha256` left by Task 1's directive edits.
- [ ] **Step 2: Edit the boards and the lesson**, as listed above.
- [ ] **Step 3: Render and check.** Run `docs/pipeline/build.sh`, then `python3 docs/pipeline/check.py` and `python3 docs/leccion/check.py`, then `uv run pytest tests/unit/test_pipeline_diagram.py tests/unit/test_pipeline_subboards.py tests/unit/test_pipeline_models.py -q`. All pass.
- [ ] **Step 4: Commit.** `docs(#215): atlas and lesson say revenue CAGR`

## Grilling

One round, 18 questions; the revisions (moving a symbol edit between tasks, fixing a function name, adding one test) did not change the seam, so there was no second round.

Answers by source: ISSUE 4, CODE 11, DOC 1, NO SOURCE 2 (both technical assumptions; there were no spec ambiguities and nothing out of scope).

1. **Red intermediate commits.** NO SOURCE, so this is a technical assumption: "Per-commit gate" under Assumptions. The `test_pipeline_diagram.py` symbol fix and the `@symbol` directive edits moved into Task 1.
2. **No fifth caller.** CODE: `grep -rn cagr src` finds only `screener/engine.py:657`, `valuator/analysis.py:687,706` and `story_types.py:180,246`.
3. **Acceptance criteria to tasks.** ISSUE (Agent Brief): "cagr((100, -50)) is None…" → Task 1. "100, 150, 100, 150 … ≈ 0.1447" → Task 2. "one test that feeds one history to all three" → Task 1. "golden … regenerated" → Task 2. "grep … returns nothing" → Task 2, Step 5. "Pipeline check, ruff, mypy and the full suite" → Task 3, Step 3 plus the full suite. The atlas wording comes from the brief's "Atlas: analyze.d2 … say CAGR. Re-render." line → Task 3.
4. **Golden at Task 1.** CODE: `tests/unit/test_screener_second_pass_golden.py` seeds `rev = 1e9 * (1 + growth) ** offset`, which is positive and geometric, so `_growth_metric` does not change. The golden test was added to Task 1's Step 4.
5. **Old pins.** CODE: `test_valuator_story_types.py:172` (`(100, -50)` → mature-stable) still holds. `test_valuator_analysis.py:637` (one period, positive) still holds. `test_valuator_assumptions.py:245` (100 → 110 → 121, where the mean equals the CAGR, 10%) still holds. No test pins a sawtooth series or `-1.0`.
6. **Geometric series and the threshold for moves.** CODE: same seeding line as in 4. Any diff is accepted as deliberate and listed in the commit body. Never hand-edit; regenerate. DOC: the test's docstring says "Regenerate it the same way only when a deliberate behavior change is intended."
7. **Order of the revenues.** CODE: `assumptions.py:656` has `ORDER BY fiscal_year` (per-ticker) and `assumptions.py:472` has `ORDER BY ticker, fiscal_year` (bulk).
8. **The -10 revenue test.** CODE: `schema.sql:98` `revenue DOUBLE` has no check constraint, and `assumptions.py:653-655` filters only `revenue IS NOT NULL`. The old mean gives -1.1 → `historical_average`, so the test is red before Step 3.
9. **`classify((0, 10))` order.** CODE: `story_types.py:239-244` evaluates hypergrowth (needs `history[-2] > 0`, false here), then distressed (`altman_z` and `interest_coverage` are None by default), then cyclical (`is_cyclical=False` by default). The CAGR is None → `MATURE_STABLE` (line 247-249).
10. **Thresholds.** CODE: `_HIGH_GROWTH_CAGR` and `_MATURE_AGE_YEARS` are in `story_types.py`, used at lines 251-253. `_is_hypergrowth` also needs both margins known and the company's below the sector's (lines 183-188). The hypergrowth reasons test calls `_story_reasons` with `StoryType.HYPERGROWTH` directly, without `classify`, so those signals are not needed.
11. **`_story_reasons` parameters and strings.** CODE: `analysis.py:651-661`: the third positional parameter is `age_years`, and the `founded_age_years` keyword exists. The strings are verbatim at `analysis.py:688` and `690`.
12. **None, and None → 0.0 in the screener.** ISSUE (Agent Brief, nicolas-ricc): "A single `bot.utils.finance.cagr(series) -> float | None`" and "the screener applies its existing missing-signal rule". CODE: `screener/engine.py:651` `roe = company.roe if company.roe is not None else 0.0`.
13. **`(100, -50, 121)` is defined.** ISSUE: "returns None for fewer than 2 points or a first or last value ≤ 0; otherwise (last/first)^(1/(n−1)) − 1". Pinned by a new Task 1 test.
14. **The `historical_average` label.** NO SOURCE, so this is a technical assumption: "The label stays" under Assumptions.
15. **Loader signatures.** CODE: `assumptions.py:364` `load_assumption_inputs(conn, ticker) -> AssumptionInputs` and `assumptions.py:413` `bulk_load_assumption_inputs(conn, tickers) -> dict[str, AssumptionInputs]`. The plan was corrected.
16. **The render and the lesson check.** CODE: `build.sh` hashes the `.d2` sources (`cat ./*.d2 | sha256sum`), not the SVGs, so the hash does not depend on the platform. `docs/leccion/check.py` exists, and the hedge was removed.
17. **Importing private names in tests.** CODE: `tests/unit/test_screener_engine.py:16-22` imports `_CompanyRow`, `_load_companies` and `_resolve_region`.
18. **Golden fallback and the `check.py` gate.** ISSUE: "Pipeline check, ruff, mypy and the full suite pass." CODE: `.github/workflows/pipeline-diagram.yml:34` runs `python3 docs/pipeline/check.py`. If the golden moves, keep the code and regenerate the fixture; never hand-edit it.

Assumptions: the per-commit gate, keeping the `historical_average` label, and the lesson wording. No follow-up issues were opened.
