# Damodaran country data: read the PRS-scored second table — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `parse_country_xls` returns both tables of the `ERPs by country` sheet (157 Moody's-rated countries plus 21 PRS-scored ones, 178 rows on the fixture), each read with its own columns, with `erp_basis` recording which table a row came from.

**Architecture:** The split happens in `parse_country_xls` on the raw sheet rows: the main header (`_find_header_row`), then a second header found by its PK cell; each segment becomes records keyed by its own header (a helper extracted from `_load_to_records`) and is normalized by the unchanged `_to_normalized_rows` with its own column map and an `erp_basis` constant. Two nullable columns (`prs_score`, `erp_basis`) join `damodaran_country`, with idempotent `ADD COLUMN IF NOT EXISTS` for existing DBs. Boards and the status-plan card that state the truncation change with the code.

**Tech Stack:** Python 3.12, DuckDB 1.5, openpyxl/xlrd, pytest, mypy --strict, ruff; d2 v0.9.0 boards + `docs/pipeline/check.py`; `docs/plano/estado.py`.

**Spec:** GitHub issue #59 (`gh issue view 59 --repo nicolas-ricc/damodaran`). Its ten "Decisions (taken by the planner; do not reopen)" are binding.

## Global Constraints

- New columns: `prs_score DOUBLE`, `erp_basis VARCHAR`; values exactly `'moodys_rating'` and `'prs_score'`.
- Module constants in `bot.ingest.damodaran`: `ERP_BASIS_MOODYS = "moodys_rating"`, `ERP_BASIS_PRS = "prs_score"`, `PRS_COUNTRY_COLUMN_MAP = {"country": "Country", "prs_score": "PRS Composite Risk Score", "erp": "ERP", "country_risk_premium": "CRP"}`.
- `Default Spread` is not stored.
- PRS rows carry `region = None` and `rating = None`, set explicitly as keys.
- `_to_normalized_rows` keeps its truncation (industry path); only its docstring changes.
- Log events: `damodaran.country.tables_read` (info, `rated=`, `prs=`), `damodaran.country.prs_duplicate` (warning, `country=`); title row dropped with a debug log.
- Files allowed to change: `src/bot/ingest/damodaran.py`, `src/bot/storage/schema.sql`, tests, `docs/pipeline/refresh.d2`, `docs/pipeline/refresh-damodaran.d2` and their `.svg` + `rendered.sha256`, `docs/plano/estado.py`, the `_resolve_tax_rate` docstring in `src/bot/screener/engine.py`, and this plan.
- Boards: counts in words, no digits; expand PRS (Political Risk Services) at first use on each board. `country_read` keeps first line `the country rows are read` (TLA+ label).
- Valuator, screener and e2e tests pass without edits.
- `uv run ruff check . && uv run mypy src && uv run pytest -q` green; `python3 docs/pipeline/check.py` passes.

## Assumptions

- `tests/integration/test_damodaran_import.py::test_import_fills_country_tax_rates_and_no_risk_free_column` asserts `with_tax / total >= 0.95`. With 178 rows and only Russia of the 21 PRS countries on the tax sheet, the ratio becomes 158/178 ≈ 0.89. The assertion is narrowed to the Moody's rows (`WHERE erp_basis = 'moodys_rating'`, all 157 carry a rate on the fixture, so `>= 0.95` holds) and its comment no longer cites the title row. This is a test edit in an integration test of the importer, which the spec allows ("tests" may change; only valuator/screener/e2e must not).
- The second header is searched only after the main header and only in the PK column index; a sheet without one yields first-table rows only (the existing minimal xlsx in `test_damodaran_importer.py`).
- "Title row" = a first-table row whose every mapped non-PK value is `None` after normalization. Applied to the first table only (the spec's decision 5).
- A "blank" PK cell is `None` or a value whose `str(...).strip()` is `""` (xlrd returns `""` for empty cells, openpyxl `None`). The second-header search tests a cell only when it is not blank, so `str(None) == "None"` can never match. Rejected: `str(cell).strip()` on raw cells.
- The title-row debug event is named `damodaran.country.title_row_dropped` (the issue only says "with a debug log"); rejected: no event name.
- The PK column is `next(iter(column_map))`, the existing contract of `_to_normalized_rows` and `IndustryDataset.column_map` ("`industry` must be first"). A custom map whose first key is not the PK is unsupported, as today.
- Empty sheet: `rows` empty, or no body row under the main header → the existing `damodaran.country.empty_file` warning and `[]` (the header-only importer test relies on the empty result; `_import_files_into_run` sets `partial`).
- The 0.95 tax-coverage narrowing is part of the stage-3 evals commit (it holds on the current code, 157/157 vs 157/158), so no intermediate commit is red because of it.
- `upsert_country_rows` lives in `src/bot/ingest/damodaran.py`, which may change; it already uses the union of row keys with `r.get(c)`, so heterogeneous keys are fine and no change there is expected.

## Review Focus

1. A sheet with no second header (minimal importer xlsx): exactly the first-table rows, no PRS rows, `erp_basis == "moodys_rating"` on each. Pinned in Task 2 (synthetic single-table test) and by the unchanged importer tests.
2. A PRS row duplicating a first-table country: first table wins, warning logged, no PK collision on insert. Pinned in Task 2.
3. The legend rows below the second table (blank PK, rating codes in column B) never become rows: the second table ends at the first blank PK. Pinned in Task 2 (fixture count 178 and no numeric region / no `"Country"` row).
4. A DB created before this change: `apply_schema` adds both columns, keeps rows, second run no-op. Pinned in Task 1.
5. A header-only country sheet still yields `[]` with `damodaran.country.empty_file` and a `partial` run. Pinned by existing `test_import_damodaran_from_files_partial_when_country_empty`.

---

### Task 1: Schema columns and migration

**Files:**
- Modify: `src/bot/storage/schema.sql:27-40`
- Test: `tests/unit/test_damodaran_country_schema.py`

**Interfaces:**
- Produces: `damodaran_country.prs_score DOUBLE`, `damodaran_country.erp_basis VARCHAR`.

- [ ] **Step 1: Write the failing tests**

```python
def test_damodaran_country_has_erp_provenance_columns() -> None:
    conn = connect(":memory:")
    apply_schema(conn)
    assert {"prs_score", "erp_basis"} <= _columns(conn)


def test_apply_schema_adds_erp_provenance_columns_to_a_legacy_table() -> None:
    conn = connect(":memory:")
    conn.execute(  # the pre-#59 CREATE TABLE
        "CREATE TABLE damodaran_country (country VARCHAR NOT NULL, year INTEGER NOT NULL, "
        "erp DOUBLE, country_risk_premium DOUBLE, tax_rate DOUBLE, "
        "rating VARCHAR, region VARCHAR, PRIMARY KEY (country, year))"
    )
    conn.execute("INSERT INTO damodaran_country (country, year, erp) VALUES ('Brazil', 2026, 0.09)")
    apply_schema(conn)
    apply_schema(conn)
    assert {"prs_score", "erp_basis"} <= _columns(conn)
    assert conn.execute(
        "SELECT country, erp, prs_score, erp_basis FROM damodaran_country"
    ).fetchall() == [("Brazil", 0.09, None, None)]
```

- [ ] **Step 2:** `uv run pytest tests/unit/test_damodaran_country_schema.py -q` → the two new tests FAIL.
- [ ] **Step 3:** Add both columns to `CREATE TABLE`; after `ALTER TABLE damodaran_country DROP COLUMN IF EXISTS risk_free_rate;` add `ADD COLUMN IF NOT EXISTS prs_score DOUBLE;` and `ADD COLUMN IF NOT EXISTS erp_basis VARCHAR;` under a comment in the existing style (what, idempotent, rollback `DROP COLUMN`).
- [ ] **Step 4:** Same command → PASS.
- [ ] **Step 5:** Commit `feat(#59): erp_basis and prs_score columns on damodaran_country`.

### Task 2: Parser reads both tables

**Files:**
- Modify: `src/bot/ingest/damodaran.py` (constants near `DEFAULT_COUNTRY_COLUMN_MAP`; `_load_to_records` → helper; `_to_normalized_rows` docstring; `parse_country_xls`)
- Test: `tests/unit/test_damodaran_parser.py`, `tests/unit/test_damodaran_importer.py`

**Interfaces:**
- Consumes: Task 1 columns (for the importer test).
- Produces: `ERP_BASIS_MOODYS`, `ERP_BASIS_PRS`, `PRS_COUNTRY_COLUMN_MAP`; `_records_from_rows(header_raw: list[Any], body: list[list[Any]]) -> list[dict[str, Any]]` (dedup/sanitize header, key each body row; `_load_to_records` calls it); `parse_country_xls` signature unchanged, every returned row carries `erp_basis`; PRS rows carry `prs_score`, `region=None`, `rating=None`.

- [ ] **Step 1: Write the failing tests**

In `test_damodaran_parser.py`, replace `test_country_parse_stops_at_the_second_table` with `test_country_parse_reads_both_tables`:

```python
rows = parse_country_xls(FIXTURES / "ctryprem_sample.xls", year=2026, column_map=DEFAULT_COUNTRY_COLUMN_MAP)
assert len(rows) == 178
assert sum(r["erp_basis"] == "moodys_rating" for r in rows) == 157
assert sorted(r["country"] for r in rows if r["erp_basis"] == "prs_score") == sorted([
    "Algeria", "Brunei", "Gambia", "Guinea", "Guinea-Bissau", "Guyana", "Haiti", "Iran",
    "Korea, D.P.R.", "Liberia", "Libya", "Madagascar", "Malawi", "Myanmar", "Russia",
    "Sierra Leone", "Somalia", "Sudan", "Syria", "Yemen, Republic", "Zimbabwe",
])  # hand-read from rows 167-187 of the fixture
countries = {r["country"] for r in rows}
assert "Frontier Markets (no sovereign ratings)" not in countries
assert "Country" not in countries
# no region parses as a number (keep the existing loop)
by = {r["country"]: r for r in rows}
alg = by["Algeria"]
assert alg["erp"] == pytest.approx(0.10057659756375703)
assert alg["country_risk_premium"] == pytest.approx(0.058276597563757034)
assert alg["prs_score"] == 67.0
assert alg["erp_basis"] == "prs_score"
assert alg["region"] is None and alg["rating"] is None
abu = by["Abu Dhabi"]
assert abu["region"] == "Middle East" and abu["rating"] == "Aa2"
assert abu["erp"] == pytest.approx(0.0486906451636496)
assert abu["erp_basis"] == "moodys_rating" and abu["prs_score"] is None
```

(`abu["prs_score"] is None` requires the first-table rows to carry the key or `.get`: use `abu.get("prs_score") is None`.)

`test_country_parse_synthetic_two_tables_drops_title_and_duplicate(tmp_path, caplog-or-structlog capture)`: openpyxl sheet `ERPs by country` with rows: main header `Country | Africa | Moody's rating | Total Equity Risk Premium | Country Risk Premium`; `United States, North America, Aaa, 0.05, 0.0`; `Brazil, Latin America, Ba2, 0.09, 0.04`; title `Frontier Markets (no sovereign ratings)` with blanks; second header `Country | PRS Composite Risk Score | ERP | CRP | Default Spread`; `Algeria, 67, 0.10, 0.058, 0.038`; `Brazil, 60, 0.12, 0.07, 0.05`; blank row; legend row `None, "A1", 59.9`. Assert countries in order `["United States", "Brazil", "Algeria"]`; Brazil keeps `erp == 0.09`, `erp_basis == "moodys_rating"`; a `damodaran.country.prs_duplicate` warning with `country="Brazil"` is emitted (captured with `structlog.testing.capture_logs`, as `tests/unit/test_cli_analyze.py` does).

`test_country_parse_single_table_sheet_has_only_rated_rows(tmp_path)`: the importer's minimal two-row sheet → 2 rows, both `erp_basis == "moodys_rating"`.

In `test_damodaran_importer.py`: after `import_damodaran_from_files` on the minimal xlsx, `SELECT erp_basis FROM damodaran_country` is `moodys_rating` for every row (existing tests otherwise unchanged).

- [ ] **Step 2:** `uv run pytest tests/unit/test_damodaran_parser.py tests/unit/test_damodaran_importer.py -q` → new tests FAIL.
- [ ] **Step 3: Implement.** In `parse_country_xls`:
  1. `rows, picked = _load_rows(path, sheet_name)`; empty → existing `damodaran.country.empty_file` warning, `[]`.
  2. `header_idx = _find_header_row(rows)`; `pk_header = column_map[next(iter(column_map))]`; `pk_col` = index in `rows[header_idx]` whose stripped str equals `pk_header` (absent → no second table).
  3. `second_idx` = first `i > header_idx` with `str(rows[i][pk_col]).strip() == pk_header`, else `None`.
  4. First segment `rows[header_idx+1 : second_idx]` (to end if `None`); normalize with `column_map`, constants `{"year": year, "erp_basis": ERP_BASIS_MOODYS}`; drop rows whose every non-PK mapped value is `None` (debug `damodaran.country.title_row_dropped`).
  5. Second segment: rows after `second_idx` up to (excluding) the first row with a blank PK cell; records keyed by `rows[second_idx]`; normalize with `PRS_COUNTRY_COLUMN_MAP`, constants `{"year": year, "erp_basis": ERP_BASIS_PRS, "region": None, "rating": None}`; drop PRS rows whose country is in the first segment, warning `damodaran.country.prs_duplicate`.
  6. `log.info("damodaran.country.tables_read", rated=..., prs=...)`; return first + second.
  Reword the `_to_normalized_rows` docstring: the truncation still guards industry files; the country parser reads the second table itself.
- [ ] **Step 4:** Same command → PASS; also `uv run pytest tests/unit/test_damodaran_datasets.py tests/unit/test_damodaran_derived.py -q` PASS.
- [ ] **Step 5:** Commit `feat(#59): parse the PRS-scored country table with its own columns`.

### Task 3: Import of the real fixtures

**Files:**
- Test: `tests/integration/test_damodaran_import.py`

**Interfaces:**
- Consumes: Tasks 1–2.

- [ ] **Step 1: Write the failing test** `test_import_stores_the_prs_scored_countries`: `_imported_conn()`; `COUNT(*) == 178`; Algeria `erp ≈ 0.10057659756375703`, `erp_basis == 'prs_score'`, `prs_score == 67.0`, `tax_rate IS NULL`; Russia `tax_rate == pytest.approx(0.2)`; the `refresh_log` row for `damodaran` has status `success`. Narrow the 0.95 tax-coverage assertion to `erp_basis = 'moodys_rating'` (see Technical assumptions).
- [ ] **Step 2:** Fails before Task 2 (written in stage 3 with the other evals), passes after.
- [ ] **Step 3:** No production code: Task 2 delivers it. If `upsert_country_rows` fails on the PRS rows, fix there.
- [ ] **Step 4:** `uv run pytest tests/integration/test_damodaran_import.py -q` → PASS.
- [ ] **Step 5:** Commit with Task 2 or alone `test(#59): ...`.

### Task 4: Docs, boards and render

**Files:**
- Modify: `docs/pipeline/refresh.d2` (`files` note, `country` node), `docs/pipeline/refresh-damodaran.d2` (`country_read`), `docs/plano/estado.py` (card `da-parse`), `src/bot/screener/engine.py` (`_resolve_tax_rate` docstring), `docs/pipeline/*.svg` changed by the render, `docs/pipeline/rendered.sha256`.

- [ ] **Step 1:** Exact copy (spec decision 10):
  - `refresh.d2` `files` note, ctryprem lines: `- ctryprem.xls, sheet 'ERPs by country': country, region, rating,` / `total equity risk premium, country risk premium, PRS (Political Risk Services) score, ERP basis.` (wrap as the note does; the stage-3 test pins `country risk premium, PRS (Political Risk Services) score, ERP basis` after whitespace normalization, so keep that phrase on one line).
  - `refresh.d2` `country` node second line: `sheet 'ERPs by country', two tables: the Moody's-rated countries, then the unrated countries scored by PRS (Political Risk Services), each read with its own columns; erp_basis says which`; its `kept per country` line ends `..., rating, region, PRS score, ERP basis`.
  - `refresh-damodaran.d2` `country_read`: `the country rows are read\nsheet 'ERPs by country', two tables: the Moody's-rated countries, then the unrated countries scored by PRS (Political Risk Services), each read with its own columns; erp_basis says which`. The old `sheet picked by keyword: ERPs by country` line is replaced by the two-table sentence (spec: "gets the same two-table sentence as its second line").
  - `estado.py` `da-parse`: `Industria, país y columnas derivadas. Lee las dos tablas del archivo de país, cada una con sus propias columnas: los países con calificación de Moody's y los no calificados con puntaje PRS; erp_basis registra de cuál viene cada fila.`
  - `engine.py` `_resolve_tax_rate`: `a country absent from that sheet (most of the PRS-scored countries) is NULL and falls back to the default.`
- [ ] **Step 2:** `PATH=/usr/local/lib/d2/d2-v0.9.0/bin:$PATH docs/pipeline/build.sh`; `python3 docs/pipeline/check.py` → 0 errors.
- [ ] **Step 3:** Stage-3 evals already pin the copy: `test_refresh_text[damodaran.country]`, `test_refresh_text[damodaran.download]`, `test_refresh_subboard_text[refresh-damodaran]`, `test_estado_da_parse_reads_both_country_tables`, and `PRS` in `_ACRONYMS`. Run `uv run pytest tests/unit/test_pipeline_diagram.py tests/unit/test_pipeline_subboards.py tests/unit/test_pipeline_models.py tests/unit/test_hypergrowth_docs.py -q` → PASS.
- [ ] **Step 4:** Commit `docs(#59): boards and status plan read both country tables` with the `.d2`, changed `.svg`, `rendered.sha256`, `estado.py`, `engine.py`.

## Grilling

- Rounds: 1 (griller model: fable). Revisions were additive (assumptions, one pinned list), no seam changed, so no second round.
- Questions: 18. Sources: ISSUE 7 (Q1, Q4, Q5, Q10, Q15, Q16 partly, Q18 partly), CODE 14 (Q1–Q3, Q6–Q8, Q11, Q13, Q14, Q16, Q17; several questions cite both), NO SOURCE 5, all technical assumptions (Q9 blank definition, Q11 empty rule, Q12 event name, Q6 custom map, Q18 commit order).
- Verified on the fixture: `Country` appears in the PK column only at rows 7 and 166; the 21 PRS names are the list pinned in Task 2; none duplicates a first-table country; only `Russia` is on the tax sheet (no near-miss spellings for the other twenty); DuckDB 1.5.3 accepts `ADD COLUMN IF NOT EXISTS` twice.
- Assumptions: see `## Assumptions`.
- Issues opened: none (nothing out of scope; #271 already covers the US/United States join).
