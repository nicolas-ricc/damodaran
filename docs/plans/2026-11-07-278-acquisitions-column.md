# Store cash paid for acquisitions (#278) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `financials_annual.acquisitions` exists on fresh and existing databases and both fundamentals providers (SEC EDGAR, FMP) fill it from statements they already fetch.

**Architecture:** One `DOUBLE` column added to the `CREATE TABLE` plus an idempotent `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` migration line in `schema.sql`. EDGAR gets one `ANNUAL_CONCEPT_MAP` entry (no derivation, no sign change). FMP gets one `_CASHFLOW_FIELD_MAP` entry and a sign flip in `parse_fmp_fundamentals` beside the capex block. `upsert_financials_annual` already inserts every row key, so no storage code changes.

**Tech Stack:** Python 3, DuckDB, pytest, ruff, mypy --strict.

**Spec:** GitHub issue #278 (design decisions inherited from story #62, comment "Branch: feature/62-dilution-ma-exception").

## Global Constraints

- Column: `acquisitions DOUBLE` on `financials_annual`. Cash paid to acquire businesses, net of cash acquired, over the fiscal year. Outflow positive (same convention as `capex`). NULL when the provider reports nothing.
- Migration line: `ALTER TABLE financials_annual ADD COLUMN IF NOT EXISTS acquisitions DOUBLE;` with a comment naming #62 and the rollback (`DROP COLUMN acquisitions`), in the style of the #59 lines.
- EDGAR: `ANNUAL_CONCEPT_MAP["acquisitions"] = ["PaymentsToAcquireBusinessesNetOfCashAcquired", "PaymentsToAcquireBusinessesGross", "PaymentsToAcquireBusinessesAndInterestInAffiliates"]`, in that order. Do not add `acquisitions` to `FINANCIALS_QUARTERLY_COLS`.
- FMP: `acquisitionsNet` → `acquisitions`, stored negated. The flip lives in `parse_fmp_fundamentals` next to the capex handling, not in `_merge_statement`.
- No other column, provider, endpoint or rule change. The screener does not read the column. Nothing under `docs/pipeline/` is edited.
- `uv run pytest -q` passes; `uv run ruff check . && uv run mypy src` is clean.

## Declared technical assumption

"Quarterly rows never carry `acquisitions`" is read as: no quarterly row stored in `financials_quarterly` carries it (the table has no such column and `upsert_financials_quarterly` filters on `FINANCIALS_QUARTERLY_COLS`), and quarterly rows built from 10-K-only facts have no `acquisitions` key. The issue also says the quarterly path "must stay untouched", so the parser's in-memory quarterly dicts, which already carry non-stored helper keys such as `capex` for derivations, are not filtered further.

## Review Focus

1. A legacy database with existing `financials_annual` rows: the migration keeps the rows and leaves `acquisitions` NULL on them (Task 1 test asserts the old row survives with NULL).
2. A 10-Q acquisitions fact (three-month span) must not break the quarterly upsert or add a column to `financials_quarterly` (Task 2 test).
3. A period where only the third concept `PaymentsToAcquireBusinessesAndInterestInAffiliates` is tagged gets filled by it (Task 2 test).
4. FMP `acquisitionsNet` positive (net divestiture) is stored negative; `acquisitionsNet: null` yields no value (Task 3 tests).
5. A company where some years report acquisitions and others do not upserts in one batch: rows without the key store NULL (Task 2 round-trip uses two years, one without the fact).

---

### Task 1: Schema column and migration

**Files:**
- Modify: `src/bot/storage/schema.sql` (`financials_annual` CREATE TABLE, after `dividends_paid`; migration lines after the table)
- Test: `tests/unit/test_storage_db.py`

**Interfaces:**
- Produces: column `financials_annual.acquisitions DOUBLE`; test-module constant `_LEGACY_FINANCIALS_ANNUAL_DDL` (the `CREATE TABLE financials_annual` exactly as it stood before #278, without `acquisitions`) and helper `_financials_annual_columns(conn) -> set[str]`, reused by Tasks 2 and 3.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_storage_db.py`:
  - `test_financials_annual_has_acquisitions_column`: `connect(":memory:")`, `apply_schema`, assert `"acquisitions" in _financials_annual_columns(conn)` and its `data_type` is `DOUBLE`.
  - `test_apply_schema_adds_acquisitions_to_a_legacy_financials_annual`: execute `_LEGACY_FINANCIALS_ANNUAL_DDL`, insert `('AAPL', 2024, 'sec_edgar', capex=1.0)`, `apply_schema` twice, assert the column exists and `SELECT ticker, fiscal_year, capex, acquisitions FROM financials_annual` == `[("AAPL", 2024, 1.0, None)]`.
- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_storage_db.py` — expect the two new tests to FAIL (column missing).
- [ ] **Step 3: Implement**: add `acquisitions    DOUBLE,` after `dividends_paid` in the CREATE TABLE; after the table add

  ```sql
  -- Adds the #62 acquisitions column to existing DBs: cash paid for businesses,
  -- net of cash acquired, outflow positive. Idempotent. Rollback: DROP COLUMN acquisitions.
  ALTER TABLE financials_annual ADD COLUMN IF NOT EXISTS acquisitions DOUBLE;
  ```
- [ ] **Step 4: Run** `uv run pytest -q tests/unit/test_storage_db.py` — PASS, including `test_apply_schema_is_idempotent` and `test_schema_table_count_matches_the_shipped_schema` (still 16 tables).
- [ ] **Step 5: Commit** `feat(#278): financials_annual gains an acquisitions column`.

### Task 2: EDGAR concepts

**Files:**
- Modify: `src/bot/ingest/sec_edgar.py` (`ANNUAL_CONCEPT_MAP`, after `"capex"`)
- Test: `tests/unit/test_sec_edgar_parser.py`, `tests/unit/test_storage_db.py`, `tests/integration/test_sec_edgar_import.py`

**Interfaces:**
- Consumes: Task 1 column and test helpers.
- Produces: `parse_company_facts(...).annual` rows may carry `"acquisitions": float`.

- [ ] **Step 1: Write the failing tests** (use `_fact`, `_facts`, `_annual`, `_quarterly`):
  - `test_acquisitions_from_net_of_cash_acquired`: a 10-K duration fact `PaymentsToAcquireBusinessesNetOfCashAcquired` 2025-01-01..2025-12-31 val 1_500_000_000 plus `Revenues` for the same period → `_annual(facts)[2025]["acquisitions"] == 1_500_000_000`.
  - `test_acquisitions_gross_fills_a_period_net_does_not_cover`: Net for 2025, Gross 900 for 2024 and 2025 (Gross 2025 differs) → 2025 keeps the Net value, 2024 == 900.
  - `test_acquisitions_from_interest_in_affiliates_as_last_resort`: only the third concept for 2025 → filled.
  - `test_no_acquisitions_concept_yields_no_value`: only `Revenues` → `_annual(facts)[2025].get("acquisitions") is None`.
  - `test_quarterly_rows_do_not_carry_acquisitions_from_10k_facts`: 10-K acquisitions fact plus 10-Q three-month `Revenues` → every `_quarterly` row has no `acquisitions` key.
  - `test_a_10q_acquisitions_fact_never_reaches_financials_quarterly` (in `test_storage_db.py` or the parser file): 10-Q three-month `Revenues` and `PaymentsToAcquireBusinessesNetOfCashAcquired`; `upsert_financials_quarterly` into a fresh DB returns 1 and `financials_quarterly` has no `acquisitions` column.
  - In `test_storage_db.py`, `test_edgar_acquisitions_round_trip[fresh|migrated]` (parametrized: fresh `apply_schema`, or `_LEGACY_FINANCIALS_ANNUAL_DDL` then `apply_schema`): parse a 2024 row without and a 2025 row with acquisitions, `upsert_financials_annual`, then `SELECT fiscal_year, acquisitions ... ORDER BY fiscal_year` == `[(2024, None), (2025, 1_500_000_000.0)]`.
  - In `tests/integration/test_sec_edgar_import.py`, extend the existing cassette test: `SELECT fiscal_year, acquisitions FROM financials_annual WHERE ticker='AAPL' AND fiscal_year IN (2020, 2021)` == `[(2020, 1_524_000_000.0), (2021, 33_000_000.0)]` (values present in the cassette).
- [ ] **Step 2: Run** the three files — new tests FAIL (no key / NULL).
- [ ] **Step 3: Implement**: add the `"acquisitions"` entry with the three concepts in the given order, with a one-line comment that they are duration cash-flow facts already positive as outflows.
- [ ] **Step 4: Run** `uv run pytest -q tests/unit/test_sec_edgar_parser.py tests/unit/test_storage_db.py tests/integration/test_sec_edgar_import.py` — PASS.
- [ ] **Step 5: Commit** `feat(#278): EDGAR fills acquisitions from the PaymentsToAcquireBusinesses concepts`.

### Task 3: FMP field and sign

**Files:**
- Modify: `src/bot/ingest/fmp.py` (`_CASHFLOW_FIELD_MAP`; `parse_fmp_fundamentals` beside the capex block)
- Test: `tests/unit/test_fmp_parser.py`, `tests/unit/test_storage_db.py`

**Interfaces:**
- Consumes: Task 1 column and test helpers.
- Produces: `parse_fmp_fundamentals(...).annual` rows may carry `"acquisitions": float` (purchase positive, net divestiture negative).

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_fmp_parser.py`, in the style of `test_parse_maps_stable_dialect_dividends_paid`:
  - `test_parse_stores_acquisitions_net_as_a_positive_outflow`: `{"acquisitionsNet": -500}` FY 2023 → `acquisitions == 500`.
  - `test_parse_stores_a_net_divestiture_as_negative_acquisitions`: `{"acquisitionsNet": 200}` → `acquisitions == -200`.
  - `test_parse_without_acquisitions_net_yields_no_acquisitions`: entry without the field, and one with `"acquisitionsNet": None` → `row.get("acquisitions") is None`.
  - In `test_storage_db.py`, `test_fmp_acquisitions_round_trip[fresh|migrated]`: parse `{"acquisitionsNet": -500}` FY 2023, upsert, `SELECT acquisitions` == `[(500.0,)]`.
- [ ] **Step 2: Run** — new tests FAIL.
- [ ] **Step 3: Implement**: add `"acquisitionsNet": "acquisitions"` to `_CASHFLOW_FIELD_MAP`; in `parse_fmp_fundamentals`, right after the capex block, negate `row["acquisitions"]` when it is not None (as a float), with a comment that FMP reports the outflow negative.
- [ ] **Step 4: Run** `uv run pytest -q tests/unit/test_fmp_parser.py tests/unit/test_storage_db.py` — PASS.
- [ ] **Step 5: Commit** `feat(#278): FMP fills acquisitions from acquisitionsNet, outflow positive`.

### Final verification

- `uv run pytest -q tests/unit/test_storage_db.py tests/unit/test_sec_edgar_parser.py tests/unit/test_fmp_parser.py tests/integration/test_sec_edgar_import.py tests/unit/test_screener_engine.py`
- `uv run pytest -q`
- `uv run ruff check . && uv run mypy src`
