# Source cosmetics: dead `_SectorMultiples.erp`, railroads cyclical, grouped per-share — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the never-read `erp` field of `_SectorMultiples` (and the query columns that only fed it), classify `Transportation (Railroads)` as cyclical, and give `fmt_per_share` a thousands separator.

**Architecture:** Three independent source edits, one per task, each test-first. Task 1 narrows `_sector_multiples_from` from a `(region, erp)` tuple to the geographic region string and drops `erp` from both `damodaran_country` queries. Task 2 adds one label to a frozenset. Task 3 changes one format spec.

**Tech Stack:** Python 3.12, pytest, DuckDB, ruff, mypy --strict.

**Spec:** GitHub issue #293 (`gh issue view 293 --repo nicolas-ricc/damodaran`). Its three "Decisions (taken by the planner; do not reopen)" and its seven acceptance criteria are binding. Story context: #64 (plan comment, item 5).

## Global Constraints

- `_SectorMultiples` fields after the change: `region, pe, ev_sales, op_margin, beta_levered, roic=None` (five positional before `roic`).
- `_sector_multiples_from(company: _CompanyRow, geographic_region: str | None, sector_row: tuple[Any, ...] | None) -> _SectorMultiples`.
- `_load_sector_multiples` query: `SELECT region FROM damodaran_country WHERE country = ? ORDER BY year DESC LIMIT 1`.
- `bulk_load_valuation_inputs` query: `SELECT country, region FROM damodaran_country ... QUALIFY ...`; `country_rows: dict[str, str]` maps country to geographic region.
- `fmt_per_share` returns `f"{value:,.2f}"`; `None` still returns `"—"`; no B/M/K scaling.
- `"Transportation (Railroads)"` joins `CYCLICAL_INDUSTRIES`.
- `bot.valuator.assumptions._CountryRow` and its ERP path are not touched. The `damodaran_country.erp` column stays in the schema; test fixtures may keep inserting it.
- `docs/plans/*.md` (other than this one), `docs/pipeline/`, `docs/leccion/` unchanged.
- `uv run ruff check . && uv run mypy src && uv run pytest -q` green; `python3 docs/pipeline/check.py` and `python3 docs/leccion/check.py` pass.

## Assumptions (declared)

- **Criterion 1's grep is a word match.** `grep -n "erp" src/bot/valuator/analysis.py` also matches `enterprise_value` (`ent-erp-rise`, lines 86, 785, 800, 1043) and the comment `erp_weighted / erp_listing` (line 1004), which the issue does not ask to touch: its parenthetical fixes the meaning as "no field, no column in either `damodaran_country` query, no parameter". The executable check is `grep -nw erp src/bot/valuator/analysis.py` printing nothing. `enterprise_value` and the `erp_weighted` comment stay.
- **The region test sits beside the sanity-check tests** in `tests/unit/test_valuator_analysis.py` and imports `_CompanyRow` and `_sector_multiples_from` from `bot.valuator.analysis`, like `_SectorMultiples` today.
- **`test_valuation_bulk_load.py` has no tuple-shape expectation** (it inserts `damodaran_country` rows and compares bulk against per-ticker loads), so it is run, not edited.

## Review Focus

- A company whose country has no `damodaran_country` row: `geographic_region=None`, region falls back to `"US"`. Pinned by the `country=None` case in Task 1 and by the bulk-load parity test.
- A country with a country-level override (`COUNTRY_REGION_OVERRIDES`): `dataset_region` still sees the country, so the override wins. Unchanged code path; the bulk-load parity test covers it.
- Negative per-share values (`-1234.5`): grouping keeps the sign in front, `"-1,234.50"`. Pinned in Task 3.
- Values under 1000 render unchanged (`12.35`), so no golden report moves. Pinned by `test_analyze_model_replay.py` and the isolation goldens running unchanged.
- A cyclical label typo: `test_every_classified_industry_is_in_the_taxonomy` catches it. Pinned in Task 2.

---

### Task 1: Drop `_SectorMultiples.erp`

**Files:**
- Modify: `src/bot/valuator/analysis.py:347-411` (dataclass, `_sector_multiples_from`, `_load_sector_multiples`), `:574-589` and `:642-653` (`bulk_load_valuation_inputs`)
- Test: `tests/unit/test_valuator_analysis.py:393`, `tests/unit/test_pipeline_diagram.py:1913`

**Interfaces:**
- Produces: the signatures in Global Constraints. No other module imports these private names.

- [ ] **Step 1: Write the failing test** in `tests/unit/test_valuator_analysis.py`:

```python
def test_sector_multiples_take_the_geographic_region_only() -> None:
    company = _CompanyRow(name="X", country=None, currency="USD",
                          industry_damodaran=None, ipo_date=None)
    assert _sector_multiples_from(company, "Western Europe", None).region == "Europe"
    assert _sector_multiples_from(company, None, None).region == "US"
```

Remove `erp=None` from the `_SectorMultiples(...)` in `_check` (line 393), and change `test_pipeline_diagram.py:1913` to `analysis._SectorMultiples("US", None, None, None, None)`.

- [ ] **Step 2: Run, expect FAIL**: `uv run pytest tests/unit/test_valuator_analysis.py tests/unit/test_pipeline_diagram.py -q`. Expected: the new test fails (a string is not subscriptable as a tuple / wrong region) and the constructors fail with a missing `erp` argument.
- [ ] **Step 3: Implement.** Delete the field, take `geographic_region: str | None`, drop `erp` from both queries, store `country_rows = {r[0]: r[1] ...}`, pass the region string at both call sites. Docstring: `geographic_region` is `damodaran_country.region` for the company's country (or `None`); `sector_row` unchanged.
- [ ] **Step 4: Run, expect PASS**: `uv run pytest tests/unit/test_valuator_analysis.py tests/unit/test_valuation_bulk_load.py tests/unit/test_pipeline_diagram.py tests/unit/test_analyze_model_replay.py -q` and `grep -nw erp src/bot/valuator/analysis.py` prints nothing.
- [ ] **Step 5: Commit** `refactor(#293): drop the dead _SectorMultiples.erp field`.

### Task 2: Railroads are cyclical

**Files:**
- Modify: `src/bot/reference/sectors.py:42-72`
- Test: `tests/unit/test_reference_sectors.py::test_cyclicals_classified`

- [ ] **Step 1: Failing test**: add `"Transportation (Railroads)"` to the tuple in `test_cyclicals_classified`.
- [ ] **Step 2: Run, expect FAIL**: `uv run pytest tests/unit/test_reference_sectors.py -q` → `AssertionError: Transportation (Railroads)`.
- [ ] **Step 3: Implement**: add `"Transportation (Railroads)"` after `"Transportation"` in `CYCLICAL_INDUSTRIES` (alphabetical).
- [ ] **Step 4: Run, expect PASS** (including `test_every_classified_industry_is_in_the_taxonomy`).
- [ ] **Step 5: Commit** `fix(#293): classify Transportation (Railroads) as cyclical`.

### Task 3: Group thousands in `fmt_per_share`

**Files:**
- Modify: `src/bot/reporting/analysis_report.py:68-77`
- Test: `tests/unit/test_reporting_analysis.py:237-252`

- [ ] **Step 1: Failing tests**: in `test_per_share_values_are_not_scaled_to_thousands` assert `fmt_per_share(1500.0) == "1,500.00"`, `fmt_per_share(12.3456) == "12.35"`, `fmt_per_share(-1234.5) == "-1,234.50"`, `fmt_per_share(None) == "—"`; in `test_report_renders_per_share_values_unscaled` assert `"1,500.00" in md` and keep `"1.50K" not in md`.
- [ ] **Step 2: Run, expect FAIL**: `uv run pytest tests/unit/test_reporting_analysis.py -q` → `'1500.00' == '1,500.00'`.
- [ ] **Step 3: Implement**: `return f"{value:,.2f}"`; docstring keeps the no-scaling point and adds that it groups thousands like `fmt_money`.
- [ ] **Step 4: Run, expect PASS**, then `uv run pytest tests/unit/test_analyze_model_replay.py tests/unit/test_valuator_isolation_golden.py -q` passes with the goldens unchanged (`git status tests/fixtures` clean).
- [ ] **Step 5: Commit** `fix(#293): group thousands in fmt_per_share`.

### Final verification

- `python3 docs/pipeline/check.py && python3 docs/leccion/check.py`
- `uv run ruff check . && uv run mypy src && uv run pytest -q`
