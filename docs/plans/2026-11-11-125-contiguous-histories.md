# Contiguous Fiscal-Year Histories Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every history that feeds `cagr` (and the other consecutive-year consumers) holds only the most recent run of consecutive fiscal years with non-NULL values, so growth is never computed across a hole.

**Architecture:** One pure helper, `latest_contiguous_run`, lives in `bot.utils.finance` next to `cagr`. It takes `(fiscal_year, value)` pairs, oldest first, and returns the values of the latest unbroken run. A missing year (no row) and a NULL value both break the run. All the history builders call it: the valuator's `_histories_from_rows` (single-ticker and batch), the assumptions' historical growth path (single-ticker and batch), and the screener's `build_company_data`. `cagr` is unchanged.

**Tech Stack:** Python 3.12+, DuckDB, pytest, mypy --strict, ruff.

**Spec:** GitHub issue #125, triage comment "Agent Brief" (the contiguous-window decision).

## Global Constraints

- `cagr` keeps its signature and behaviour ("Changing `cagr` to take fiscal years or a span" is out of scope).
- No interpolation or backfilling of missing years.
- Histories stay `tuple[float, ...]`, oldest first (`ValuationInput.revenue_history` / `income_history` / `ebit_history`, `CompanyData.revenue_history`).
- When the run is shorter than two points, the existing reason string `"too little revenue history for a reliable growth signal"` is used.
- `uv run pytest -q`, `uv run ruff check .` and `uv run mypy src` pass.
- Do not rename `build_company_data`: `tests/unit/test_leccion.py` and `tests/unit/test_pipeline_diagram.py` cite it.

## Decisions

- **"Most recent run"** means the run that ends at the latest fiscal year with a non-NULL value. Trailing NULL years are skipped; they do not empty the history. Example: 2016, 2017 and 2018 present with 2019 NULL gives 2016-2018.
- **Runs are per series.** Revenue, net income and EBIT each get their own run, as they already get their own NULL-dropping today.
- **The assumptions module is in scope.** `_historical_growth_path` and `bulk_load_assumption_inputs` feed revenue into `cagr` for the DCF growth start. The brief's summary ("Histories fed to `cagr` ... must only contain consecutive fiscal years") covers them, and `test_valuation_bulk_load.py` requires the single-ticker and batch loaders to stay equal.
- **Margin histories are left alone** (`op_margin_history` in the screener, `_margins_from_rows` in assumptions). They are not fed to `cagr` and are not listed in the brief.

## Assumptions

Technical decisions taken during plan grilling. No source dictates them; any of the options would satisfy the issue.

- **Each task leaves the full suite green.** Task 2 adds `GAPPY`/`HOLED` to the shared bulk fixtures. The assumption loaders stay equal to each other until Task 3 changes both together. Rejected alternative: one big commit.
- **Duplicate fiscal years are not handled specially.** `financials_annual` has `PRIMARY KEY (ticker, fiscal_year, is_restated)` and every call site filters `is_restated = FALSE`, so there is at most one row per year. Rejected alternative: deduplicating inside the helper.
- **The screener's `_growth_metric` keeps mapping an undefined CAGR to `0.0`** (its existing documented behaviour, `engine.py:732-738`). Rejected alternative: excluding such companies from the ranking. The brief only asks for "no inflated growth".
- **The `RevenueNotDeclining` trap gate now sees the contiguous run.** A company with a hole in its last four years fails it as "insufficient revenue history". This follows from "the screener's histories follow the same rule". Rejected alternative: a separate gap-tolerant history for that rule.

## Review Focus

1. **Latest year NULL**: if the latest revenue is NULL, the history is the run before it, not empty. Pinned in Task 1 (`test_trailing_null_is_skipped`).
2. **Restated rows**: they are excluded by SQL before the run is computed, so a restated 2025 row must not extend the run. The existing `RESTATED` fixture in `test_valuation_bulk_load.py` covers this once the new tickers are added (Task 2/3 equality tests).
3. **Rows out of year order**: the helper must not rely on input order beyond "oldest first". The loaders keep `ORDER BY fiscal_year`. The existing `OOO` bulk fixture covers this.
4. **One-point run reaching the hypergrowth reasons**: `_hypergrowth_reasons` indexes `[-2]`. It is only reached when `_is_hypergrowth` is true, which requires `len(history) >= 2`. No change needed, but do not remove that guard.
5. **Revenue and EBIT runs ending in different years** feed `_operating_leverage`. This already happened before this change and stays as is (out of scope).

---

### Task 1: `latest_contiguous_run` helper

**Files:**
- Modify: `src/bot/utils/finance.py`
- Test: `tests/unit/test_utils_finance.py`

**Interfaces:**
- Produces: `latest_contiguous_run(points: Iterable[tuple[int, float | None]]) -> tuple[float, ...]`. `points` are `(fiscal_year, value)`, oldest first. It returns the values (as `float`) of the latest run of consecutive fiscal years whose value is not `None`, oldest first, and `()` when every value is `None` or `points` is empty.

- [ ] **Step 1: Write the failing tests**

```python
def test_years_apart_yield_only_the_latest_point() -> None:
    run = latest_contiguous_run([(2013, 100.0), (2019, 300.0)])
    assert run == (300.0,)
    assert cagr(run) is None

def test_null_in_the_middle_keeps_only_the_years_after_it() -> None:
    run = latest_contiguous_run(
        [(2015, 100.0), (2016, 110.0), (2017, None), (2018, 200.0), (2019, 220.0)]
    )
    assert run == (200.0, 220.0)
    assert cagr(run) == pytest.approx(0.1)  # one period

def test_contiguous_series_is_unchanged() -> None:
    assert latest_contiguous_run([(2020, 1.0), (2021, 2.0), (2022, 4.0)]) == (1.0, 2.0, 4.0)

def test_trailing_null_is_skipped() -> None:
    assert latest_contiguous_run([(2016, 1.0), (2017, 2.0), (2018, 3.0), (2019, None)]) == (1.0, 2.0, 3.0)

def test_no_values_yield_an_empty_run() -> None:
    assert latest_contiguous_run([]) == ()
    assert latest_contiguous_run([(2020, None), (2021, None)]) == ()
```

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_utils_finance.py -q`. Expected: FAIL (ImportError).
- [ ] **Step 3: Implement** `latest_contiguous_run` in `src/bot/utils/finance.py`. Walk the points once, start a new run when a value is `None` or the year is not the previous year + 1, and keep the last non-empty run. Use a short docstring in the module's style.
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(#125): latest_contiguous_run helper`.

### Task 2: Valuator histories (single-ticker and batch)

**Files:**
- Modify: `src/bot/valuator/analysis.py` (`_load_history`, `_histories_from_rows`, the financials scan in `bulk_load_valuation_inputs`)
- Test: `tests/unit/test_valuation_bulk_load.py`, `tests/unit/test_valuator_analysis.py`

**Interfaces:**
- Consumes: `latest_contiguous_run` (Task 1).
- Produces: `_histories_from_rows(rows: Iterable[tuple[Any, Any, Any, Any]])`, where rows are `(fiscal_year, revenue, net_income, ebit)`, oldest first. It returns the same triple of tuples as before.

- [ ] **Step 1: Write the failing tests**
  - In `test_valuation_bulk_load.py`, add two tickers to `VALUABLE` and seed them in `_seed`:
    - `GAPPY` with `[(2013, 1_000.0, 200.0, False), (2019, 3_000.0, 600.0, False)]`
    - `HOLED` with `[(2015, 1_000.0, 200.0, False), (2016, 1_100.0, 220.0, False), (2017, None, 240.0, False), (2018, 2_000.0, 260.0, False), (2019, 2_200.0, 280.0, False)]`
    - The existing `test_bulk_valuation_inputs_match_per_ticker` now covers equality for them (AC: identical histories).
  - New test `test_valuation_histories_keep_only_the_latest_contiguous_run`: after `_seed`, `load_valuation_input(conn, "GAPPY").revenue_history == (3_000.0,)` and `load_valuation_input(conn, "HOLED").revenue_history == (2_000.0, 2_200.0)`, and `HOLED`'s `ebit_history` is all five EBIT values (the EBIT run has no hole).
  - New test in `test_valuator_analysis.py`, `test_gappy_revenue_reports_too_little_history`: seed a company whose revenue exists only for 2013 and 2019, using the file's existing seed helpers. Run `analyze` and assert that `"too little revenue history for a reliable growth signal"` is in `result.story_reasons`. If the story is overridden, the reasons differ, so do not pass an override path.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_valuation_bulk_load.py tests/unit/test_valuator_analysis.py -q`. Expected: the new assertions FAIL (GAPPY history is `(1000.0, 3000.0)`).
- [ ] **Step 3: Implement.** `_load_history` selects `fiscal_year, revenue, net_income, ebit`. The batch scan in `bulk_load_valuation_inputs` adds `fiscal_year` to its SELECT, and `_latest_from_row` still receives exactly its eight columns, so add `fiscal_year` as the last column and slice it off for `_latest_from_row`. `_histories_from_rows` builds each series with `latest_contiguous_run`. Update its docstring (drop "NULLs are dropped per series").
- [ ] **Step 4: Run** the same command. Expected: PASS.
- [ ] **Step 5: Commit** `fix(#125): valuator histories keep the latest contiguous run`.

### Task 3: Assumptions historical growth path (single-ticker and batch)

**Files:**
- Modify: `src/bot/valuator/assumptions.py` (`_historical_growth_path`, the history scan in `bulk_load_assumption_inputs`)
- Test: `tests/unit/test_valuation_bulk_load.py`, `tests/unit/test_valuator_assumptions.py`

**Interfaces:**
- Consumes: `latest_contiguous_run` (Task 1). Uses the `GAPPY` and `HOLED` fixtures from Task 2.
- Produces: nothing new. `_growth_path_from_revenues(revenues: Sequence[float])` keeps its signature, and the callers pass it the contiguous run.

- [ ] **Step 1: Write the failing test** `test_assumption_growth_path_ignores_gaps` (in `test_valuation_bulk_load.py`, which already has the fixtures): `load_assumption_inputs(conn, "GAPPY").historical_growth_path is None`, and `load_assumption_inputs(conn, "HOLED").historical_growth_path == pytest.approx((0.1,) * len(path))`, meaning the flat path at 10%. `test_bulk_assumption_inputs_match_per_ticker` covers the batch path.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_valuation_bulk_load.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.** `_historical_growth_path` selects `fiscal_year, revenue` without the `revenue IS NOT NULL` filter, so a NULL breaks the run, and passes `latest_contiguous_run(rows)`. The batch scan carries `fiscal_year` in each history entry, and the revenue argument becomes `latest_contiguous_run((y, r) for y, r, _ in rows)`. The margins call keeps its current input `(ebit, revenue)` pairs.
- [ ] **Step 4: Run** `uv run pytest tests/unit/test_valuation_bulk_load.py tests/unit/test_valuator_assumptions.py -q`. Expected: PASS.
- [ ] **Step 5: Commit** `fix(#125): historical growth path ignores gappy years`.

### Task 4: Screener histories

**Files:**
- Modify: `src/bot/screener/engine.py` (`_AnnualRow`, `_load_all_annual`, `_tuple`, `build_company_data`)
- Test: `tests/unit/test_screener_engine.py`

**Interfaces:**
- Consumes: `latest_contiguous_run` (Task 1).
- Produces: `_AnnualRow` gains `fiscal_year: int` as its **first** field. `_load_all_annual` selects `ticker, fiscal_year, revenue, ...`. `_tuple` is deleted.

- [ ] **Step 1: Write the failing tests**
  - Update `_annual_row_with_acquisitions(acquisitions)` to take `fiscal_year` as well and pass it first. `test_build_company_data_acquisitions_history_drops_missing_years` becomes `..._keeps_the_run_after_a_missing_year`, with years 2020-2022 and acquisitions `(100.0, None, 300.0)`, and expects `(300.0,)`.
  - New `test_build_company_data_gappy_revenue_has_no_growth`: annual rows for 2013 and 2019 (revenue 1000 and 3000) give `cd.revenue_history == (3000.0,)`, and `_growth_metric(cd) == 0.0`.
  - New `test_build_company_data_histories_follow_the_contiguous_run`: years 2015-2019 with revenue NULL in 2017 give `revenue_history` with the 2018-2019 values. Rows with `operating_cashflow`, `shares_diluted` and `acquisitions` populated in all five years keep all five.
  - New `test_revenue_not_declining_fails_a_gappy_history`: the 2013/2019 company from the gappy test, evaluated by `RevenueNotDeclining()` (`bot.screener.rules`), fails with a reason starting `"insufficient revenue history: 1 years"`. This pins the trap gate reading the contiguous run.
  - Update every other `_AnnualRow(...)` construction in the test file to pass a `fiscal_year`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_screener_engine.py -q`. Expected: FAIL.
- [ ] **Step 3: Implement.** Add the field, select it, delete `_tuple`, and build `revenue_history`, `ocf_history`, `share_history` and `acquisitions_history` with `latest_contiguous_run((r.fiscal_year, r.<field>) for r in annual)`. `op_margin_history` is unchanged.
- [ ] **Step 4: Run** `uv run pytest -q`, then `uv run ruff check . && uv run mypy src`. Expected: all pass.
- [ ] **Step 5: Commit** `fix(#125): screener histories keep the latest contiguous run`.

## Grilling

- Rounds: 1. The plan did not change substantially: one test pin and an Assumptions section were added, and no seam changed.
- Model: fable. Questions: 17.
- Sources: CODE 14, ISSUE 3 (questions 1, 10 and 15 cite the triage Agent Brief), DOC 1 (CONTEXT.md, Conventional Commits). Some answers cite more than one source.
- NO SOURCE: 4 questions. All are technical assumptions (see `## Assumptions`). No spec ambiguities.
- Follow-up issues opened: none.
