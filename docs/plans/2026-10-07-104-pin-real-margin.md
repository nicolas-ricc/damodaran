# Pin the screener's real margin of safety — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add tests that fail when the screener's second pass silently falls back to `PLACEHOLDER_MARGIN_OF_SAFETY` because the imported Damodaran files stopped yielding a resolvable DCF.

**Architecture:** Tests only, no `src/` change. The e2e pipeline test gains two assertions on the shared DB after `screen` (stored `mos_score` and a direct `_dcf_margin_of_safety` call). `test_damodaran_datasets.py` gains a unit test that imports the real fixtures and resolves DCF assumptions for a Software company, plus a permanent negative control that blanks `op_margin` and expects the `unresolved` error.

**Tech Stack:** Python 3.12, pytest, DuckDB, `uv`.

**Spec:** GitHub issue #104 (nicolas-ricc/damodaran). Context: #50, ADR 0006.

## Global Constraints

- Do not change `_dcf_margin_of_safety`'s fallback semantics (`src/bot/screener/engine.py:65-79`); the issue adds tests only.
- Import `PLACEHOLDER_MARGIN_OF_SAFETY` from `bot.screener.ranking`; never hard-code `0.5`.
- No network: fixtures only (`tests/fixtures/damodaran/*_sample.xls`).
- `uv run pytest -q`, `uv run ruff check .` and `uv run mypy src` stay clean.

## Review Focus

1. DuckDB file lock: the CLI (`CliRunner`) opens its own connection on `db_path`; the test's `conn` must be closed while the CLI runs and reopened to read. Task 1 opens a connection after `screen`, reads, and closes it before `analyze`.
2. `mos_score` could be NaN/inf or negative if the DCF degenerates; the e2e assertion checks `math.isfinite` and `> 0`, not just `!= placeholder`.
3. The screen persists one row per candidate per run; the query must select GOODCO's row with `passed`, so a rejected row cannot satisfy it.
4. The unit test must exercise the *imported* sector row, not a hand-seeded one: it must not call `_seed_industry`/`_seed_country`.
5. A guard that cannot fail is worthless: the negative control (Task 2) is kept as a permanent test so the failure mode stays proven, not just verified once by hand.

---

### Task 1: E2E pins GOODCO's real margin of safety

**Files:**
- Modify: `tests/e2e/test_pipeline.py` (imports; new block between step 2 and step 3 of `test_pipeline_end_to_end`)

**Interfaces:**
- Consumes: `bot.screener.ranking.PLACEHOLDER_MARGIN_OF_SAFETY: float`; `bot.screener.engine._dcf_margin_of_safety(conn, ticker) -> float | None`; table `screener_candidates(ticker, mos_score, passed, ...)`.
- Produces: nothing other tasks use.

- [ ] **Step 1: Add the assertions** right after the step-2 screen assertions (`assert "Excluded (no sector benchmark, ADR 0006): 1" in screen_md`) and before step 3:

```python
    # The second pass ran the real DCF, not the placeholder fallback (#104): a
    # Damodaran header rename that NULLs op_margin/sales_to_capital would leave
    # every candidate at the placeholder while the shortlist still looks healthy.
    conn = connect(db_path)
    mos_row = conn.execute(
        "SELECT mos_score FROM screener_candidates WHERE ticker = 'GOODCO' AND passed"
    ).fetchone()
    direct_mos = _dcf_margin_of_safety(conn, "GOODCO")
    conn.close()
    assert direct_mos is not None
    assert mos_row is not None
    mos_score = mos_row[0]
    assert mos_score != PLACEHOLDER_MARGIN_OF_SAFETY
    assert isinstance(mos_score, float) and math.isfinite(mos_score) and mos_score > 0
```

Imports to add: `import math`; `from bot.screener.engine import _dcf_margin_of_safety`; `from bot.screener.ranking import PLACEHOLDER_MARGIN_OF_SAFETY` (keep ruff's isort order).

The direct call is asserted first so that, when the valuator breaks, the test fails on the valuator's result rather than on the ranking symptom.

- [ ] **Step 2: Run** `uv run pytest tests/e2e/test_pipeline.py -q` — expected PASS (current code values GOODCO).

- [ ] **Step 3: Prove it can fail.** Temporarily, in `_seed_damodaran_from_fixtures` after the import, run `conn.execute("UPDATE damodaran_industry SET op_margin = NULL WHERE industry = ?", [_SECTOR])` and drop the `op_margin is not None` assertion; rerun; expected FAIL at `assert direct_mos is not None`. Revert.

- [ ] **Step 4: Commit** `test(#104): pin GOODCO's real margin of safety in the e2e pipeline`.

### Task 2: Unit test over the imported fixtures, with negative control

**Files:**
- Modify: `tests/unit/test_damodaran_datasets.py` (imports; two tests after `test_real_import_fills_the_columns_the_extra_datasets_publish`)

**Interfaces:**
- Consumes: `bot.valuator.assumptions.resolve_assumptions(ticker, conn) -> Assumptions` and `Assumptions.to_dcf_assumptions()` (raises `ValueError("assumption 'x' is unresolved ...")`); helpers `_seed_company(conn, *, ticker="ACME", country="United States", industry_damodaran=...)` and `_seed_financials(conn, *, ticker="ACME", rows=((fy, revenue, ebit), ...))` from `tests.unit.test_valuator_assumptions` (importable: `tests/` and `tests/unit/` are packages and the e2e test already imports `tests.fake_provider`).
- Produces: nothing other tasks use.

- [ ] **Step 1: Write the tests**

```python
_SOFTWARE = "Software (System & Application)"


def _imported_software_company() -> duckdb.DuckDBPyConnection:
    """Real fixtures imported, plus one Software company with three years of history."""
    conn = _seeded_conn()
    result = import_damodaran_from_files(
        conn,
        industry_path=_WACC_FIXTURE,
        country_path=_CTRY_FIXTURE,
        region="US",
        year=2026,
        extra_industry_paths=dict(_EXTRA_FIXTURES),
    )
    assert result.status == "success", result.error_message
    _seed_company(conn, industry_damodaran=_SOFTWARE, country="United States")
    _seed_financials(
        conn, rows=((2023, 100.0, 18.0), (2024, 110.0, 20.0), (2025, 121.0, 22.0))
    )
    return conn


@pytest.mark.skipif(not _ALL_FIXTURES_PRESENT, reason="dataset fixtures absent")
def test_imported_files_resolve_a_full_dcf_for_a_software_company() -> None:
    """#50's criterion 2 against the imported files, not hand-seeded sector rows."""
    conn = _imported_software_company()
    resolve_assumptions("ACME", conn).to_dcf_assumptions()
    conn.close()


@pytest.mark.skipif(not _ALL_FIXTURES_PRESENT, reason="dataset fixtures absent")
def test_a_blanked_sector_margin_leaves_the_dcf_unresolved() -> None:
    """Negative control: the guard above can fail the way #50's bug would make it."""
    conn = _imported_software_company()
    conn.execute(
        "UPDATE damodaran_industry SET op_margin = NULL WHERE industry = ?", [_SOFTWARE]
    )
    with pytest.raises(ValueError, match="unresolved"):
        resolve_assumptions("ACME", conn).to_dcf_assumptions()
    conn.close()
```

Imports to add: `from bot.valuator.assumptions import resolve_assumptions`; `from tests.unit.test_valuator_assumptions import _seed_company, _seed_financials`.

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_damodaran_datasets.py -q` — expected PASS for both (probe on master: op_margin 0.33, sales_to_capital 1.54; blanked → `assumption 'operating_margin' is unresolved`).

- [ ] **Step 3: Prove the positive test can fail.** Temporarily add the `UPDATE ... op_margin = NULL` line inside the positive test; rerun; expected FAIL with `ValueError: assumption 'operating_margin' is unresolved`. Revert.

- [ ] **Step 4: Full checks** `uv run pytest -q && uv run ruff check . && uv run mypy src`.

- [ ] **Step 5: Commit** `test(#104): resolve a full DCF from the imported Damodaran fixtures`.
