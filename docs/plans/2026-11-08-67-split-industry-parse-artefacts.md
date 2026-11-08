# Split the parse artefacts out of `DEFAULT_INDUSTRY_COLUMN_MAP`: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every `IndustryDataset.column_map` holds only real `damodaran_industry` columns. The `D/(D+E)` header that `derive_industry_columns` consumes is declared apart from the column map as a parse artefact, so it is kept out structurally, not exempted by name.

**Architecture:** `DEFAULT_INDUSTRY_COLUMN_MAP` is replaced by two module constants: `WACC_COLUMN_MAP` (DB columns only) and `INDUSTRY_PARSE_ARTEFACT_COLUMNS` (`{"debt_weight_raw": "D/(D+E)"}`). `IndustryDataset` gains a `parse_artefacts` field (default empty) and a `header_map` property returning `column_map` plus `parse_artefacts`. `_import_files_into_run` reads every file through `header_map`. The invariant test drops its `{"debt_weight_raw"}` exemption, and a second test pins what an artefact is.

**Tech Stack:** Python 3.12, pytest, DuckDB, ruff, mypy --strict.

**Spec:** GitHub issue #67 (`gh issue view 67 --repo nicolas-ricc/damodaran`), "Remaining work" paragraph. Triage verdict "still needed" is in the Stage 0 comment on the issue.

## Global Constraints

- New public names in `src/bot/ingest/damodaran.py`: `WACC_COLUMN_MAP: dict[str, str]` and `INDUSTRY_PARSE_ARTEFACT_COLUMNS: dict[str, str]`. These are the issue's names, verbatim.
- `DEFAULT_INDUSTRY_COLUMN_MAP` is removed, with no alias. Its only importer is `tests/unit/test_damodaran_parser.py` (`grep -rn DEFAULT_INDUSTRY_COLUMN_MAP src tests scripts docs/leccion docs/pipeline docs/plano`).
- `WACC_COLUMN_MAP` keeps today's six entries in today's order, with `industry` first (`_to_normalized_rows` treats the first key as the PK): `industry`, `beta_levered`, `cost_of_equity`, `cost_of_debt`, `tax_rate`, `wacc`.
- The `parse_industry_xls` signature does not change. Its `column_map` argument stays "field → header", and callers pass `header_map`.
- Import behaviour does not change: the same rows and the same values reach `damodaran_industry`.
- `docs/superpowers/plans/*.md` (historical) and the other `docs/plans/*.md` stay unchanged.
- `uv run ruff check . && uv run mypy src && uv run pytest -q` green. `python3 docs/pipeline/check.py` and `python3 docs/leccion/check.py` pass.

## Assumptions (declared)

- **Removal, not an alias.** The issue asks to split the two maps out *of* `DEFAULT_INDUSTRY_COLUMN_MAP`. Keeping the old name as their union would leave a "DB column → header" map that still lies, which is the smell the issue exists to remove. The module docstring's "update `DEFAULT_INDUSTRY_COLUMN_MAP`" sentence is rewritten to name the two new constants.
- **The artefacts travel with the dataset.** A `parse_artefacts` field on `IndustryDataset` puts the artefact next to the file that publishes it, so a future artefact in another file needs no new code path. The default is an empty dict (`field(default_factory=dict)`, because the dataclass is frozen and takes no mutable default).
- **Registry field + property over an import-time union** (rejected: building `{**WACC_COLUMN_MAP, **INDUSTRY_PARSE_ARTEFACT_COLUMNS}` inside `_import_files_into_run`). The issue asks for the artefact to be "structurally separate rather than exempted by name"; the registry is what the invariant test iterates, so the separation has to be visible there.
- **Disjointness enforced by a test, not `__post_init__`** (rejected: a raising `__post_init__`). The registry's other structural rule, `industry` first, is also enforced by a test (`test_every_registry_column_map_starts_with_the_industry_key`, `tests/unit/test_damodaran_datasets.py:63-66`), and the registry is a module constant, so a test fails on every run that would otherwise build a bad entry.
- **`parse_industry_xls(column_map=...)` keeps its name** (rejected: renaming the parameter, which the issue does not ask for and which every caller and test would follow). Its docstring (`damodaran.py:558`) changes from "Mapping ``db_column_name -> xls_header_string``" to a row field → header mapping that may include parse artefacts, so the two meanings are written down.
- **A collection-time `ImportError` is an acceptable red** for Task 1: it fails for the reason the task fixes (the names do not exist yet).
- **The parser test is edited deliberately.** `test_parse_industry_xls_returns_rows` passes `{**WACC_COLUMN_MAP, **INDUSTRY_PARSE_ARTEFACT_COLUMNS}` and keeps its `debt_weight_raw` assertion. The issue names this edit as expected.

## Review Focus

- **The artefact silently falls out of the read map.** If `_import_files_into_run` passes `column_map` instead of `header_map`, `debt_to_equity` and `beta_unlevered` go NULL for every industry, and no current test notices: no test checks those two columns after a real import. Task 1 pins this with an import-level test on the real fixtures.
- **An artefact key that is also a real column.** It would reach the INSERT legitimately, but `derive_industry_columns` would pop it. Task 2 asserts that artefact keys and real columns are disjoint.
- **An artefact that `derive_industry_columns` does not consume.** It would reach the INSERT and fail against the table. Task 2 asserts that every declared artefact is absent from `derive_industry_columns({k: 0.2})`.
- **`industry` loses first place.** If `industry` stopped being the first key of `header_map`, the PK detection would break. The existing `test_every_registry_column_map_starts_with_the_industry_key` covers `column_map`. Task 1 makes `header_map` put `column_map` first, and the parser test (rows keyed by `industry`) exercises it.
- **Non-numeric `D/(D+E)` cells.** `_null_non_numeric_industry_cells` iterates the map it is given, so passing `header_map` still NULLs an `"NA"` artefact cell, as it does today. This path is unchanged and needs no new test.

---

### Task 1: Split the maps and read through `header_map`

**Files:**
- Modify: `src/bot/ingest/damodaran.py` (module docstring lines 1-12, the maps at 31-49, `IndustryDataset` at 82-99, the wacc registry entry at 110-115, `_import_files_into_run` at 764-786)
- Test: `tests/unit/test_damodaran_parser.py:9-41`, `tests/unit/test_damodaran_datasets.py` (new test)

**Interfaces:**
- Produces: `WACC_COLUMN_MAP: dict[str, str]`, `INDUSTRY_PARSE_ARTEFACT_COLUMNS: dict[str, str]`, `IndustryDataset.parse_artefacts: dict[str, str]` (default `{}`), and `IndustryDataset.header_map -> dict[str, str]` (a property returning `{**self.column_map, **self.parse_artefacts}`). The wacc entry is `column_map=WACC_COLUMN_MAP, parse_artefacts=INDUSTRY_PARSE_ARTEFACT_COLUMNS`.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_damodaran_parser.py`, import `WACC_COLUMN_MAP` and `INDUSTRY_PARSE_ARTEFACT_COLUMNS` instead of `DEFAULT_INDUSTRY_COLUMN_MAP`. Pass `column_map={**WACC_COLUMN_MAP, **INDUSTRY_PARSE_ARTEFACT_COLUMNS}` in `test_parse_industry_xls_returns_rows`, and keep its assertions.

In `tests/unit/test_damodaran_datasets.py`, extend `test_every_registry_column_map_starts_with_the_industry_key` so it also asserts `next(iter(dataset.header_map)) == "industry"` for every dataset, and add:

```python
def test_wacc_column_map_carries_no_parse_artefact() -> None:
    assert "debt_weight_raw" not in WACC_COLUMN_MAP
    assert INDUSTRY_PARSE_ARTEFACT_COLUMNS == {"debt_weight_raw": "D/(D+E)"}
    wacc = next(d for d in INDUSTRY_DATASETS if d.key == "wacc")
    assert wacc.column_map == WACC_COLUMN_MAP
    assert wacc.parse_artefacts == INDUSTRY_PARSE_ARTEFACT_COLUMNS
    assert list(wacc.header_map)[0] == "industry"
    assert wacc.header_map == {**WACC_COLUMN_MAP, **INDUSTRY_PARSE_ARTEFACT_COLUMNS}


def test_real_import_derives_leverage_from_the_parse_artefact() -> None:
    """D/(D+E) is read although no column_map carries it, and reaches the DB as D/E."""
    conn = _seeded_conn()
    import_damodaran_from_files(
        conn, industry_path=_WACC_FIXTURE, country_path=_CTRY_FIXTURE, region="US", year=2026
    )
    total, with_de, with_bu = conn.execute(
        "SELECT count(*), count(debt_to_equity), count(beta_unlevered) "
        "FROM damodaran_industry WHERE region = 'US' AND year = 2026"
    ).fetchone()
    assert total > 50
    assert with_de > total * 0.9
    assert with_bu > total * 0.9
```

Match the `import_damodaran_from_files` call to the way the existing `test_real_import_fills_the_columns_the_extra_datasets_publish` in that file calls it. If that test passes extra paths, the bare wacc + ctryprem call above is still enough for these two columns.

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/unit/test_damodaran_parser.py tests/unit/test_damodaran_datasets.py -q`
Expected: collection ERROR, `ImportError: cannot import name 'WACC_COLUMN_MAP'`. The leverage test may already pass on master; it is a regression guard for the next step.

- [ ] **Step 3: Implement in `src/bot/ingest/damodaran.py`**

Replace `DEFAULT_INDUSTRY_COLUMN_MAP` with `WACC_COLUMN_MAP` (the six DB columns) and `INDUSTRY_PARSE_ARTEFACT_COLUMNS`. The latter carries the comment that today sits above `debt_weight_raw`: the key is a row field `derive_industry_columns` consumes and pops, not a DB column. Add `parse_artefacts` and `header_map` to `IndustryDataset`, documented in its `Attributes:` docstring. `column_map` stays "DB column → header" and is now true. Point the wacc registry entry at the two constants. Update the `parse_industry_xls` docstring for `column_map` as declared in Assumptions. In `_import_files_into_run`, pass `column_map=_WACC_DATASET.header_map` and `column_map=dataset.header_map`. Rewrite the module docstring sentence to name `WACC_COLUMN_MAP`, `INDUSTRY_PARSE_ARTEFACT_COLUMNS` and `DEFAULT_COUNTRY_COLUMN_MAP`.

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/unit/test_damodaran_parser.py tests/unit/test_damodaran_datasets.py tests/unit/test_damodaran_derived.py -q && uv run mypy src`
Expected: all pass, mypy clean.

- [ ] **Step 5: Commit**

`git commit -m "refactor(#67): split WACC_COLUMN_MAP and INDUSTRY_PARSE_ARTEFACT_COLUMNS out of DEFAULT_INDUSTRY_COLUMN_MAP"`

### Task 2: Invariant test without the name exemption

**Files:**
- Test: `tests/unit/test_damodaran_datasets.py:111-136`

**Interfaces:**
- Consumes: `IndustryDataset.parse_artefacts` and `INDUSTRY_DATASETS` from Task 1, plus `derive_industry_columns(row: dict[str, Any]) -> dict[str, Any]`.

- [ ] **Step 1: Rewrite the invariant and add the artefact test**

In `test_no_dataset_maps_a_column_the_table_does_not_have`, delete `parse_artefacts = {"debt_weight_raw"}` and its comment. The assertion becomes `stray = set(dataset.column_map) - real_columns`. Update the docstring: there are no exemptions, because artefacts live in `parse_artefacts`. Factor the `information_schema` read into a helper `_industry_columns() -> set[str]` so both tests share it. Add:

```python
def test_parse_artefacts_are_not_columns_and_never_reach_the_upsert() -> None:
    real_columns = _industry_columns()
    for dataset in INDUSTRY_DATASETS:
        artefacts = set(dataset.parse_artefacts)
        assert not artefacts & real_columns, dataset.key
        assert not artefacts & set(dataset.column_map), dataset.key
        for field in artefacts:
            assert field not in derive_industry_columns({field: 0.2}), field
```

- [ ] **Step 2: Run**

Run: `uv run pytest tests/unit/test_damodaran_datasets.py -q`
Expected: PASS. This task changes tests only, on top of Task 1. To show the guard bites, temporarily add `"debt_weight_raw": "D/(D+E)"` back to `WACC_COLUMN_MAP` and watch the invariant fail with `wacc maps non-columns: ['debt_weight_raw']`, then revert. Run `git diff --quiet src && echo clean`: it must print `clean` before the commit.

- [ ] **Step 3: Commit**

`git commit -m "test(#67): the column-map invariant exempts nothing; artefacts are pinned on their own"`

### Final verification

- `uv run ruff check . && uv run mypy src && uv run pytest -q`
- `python3 docs/pipeline/check.py && python3 docs/leccion/check.py`
- `git grep -n DEFAULT_INDUSTRY_COLUMN_MAP -- . ':!docs/superpowers' ':!docs/plans'` prints nothing (covers README, docs/, ADRs, `.github`, scripts).

## Grilling

- Rounds: 1 (revisions were local: one docstring, one extended assertion, two verification commands; no step added or removed, same seam).
- Questions: 15. Sources: ISSUE 2 (Q1, Q2 partly), CODE 10 (Q3-Q7, Q10-Q12; Q8's checker semantics from `docs/pipeline/check.py` and `docs/leccion/check.py` docstrings), DOC 1 (Q14: AGENTS.md skill list), NO SOURCE 5 → all technical assumptions (Q1 field/property, Q2 removal, Q9 test vs `__post_init__`, Q13 parameter name, Q14 red at collection). Q7, Q8 and Q15 also led to plan fixes.
- Assumptions: see `## Assumptions (declared)`.
- Spec ambiguities: none. Follow-up issues opened: none.
- Facts checked: `parse_industry_xls` has a single caller in `src/` (`_import_files_into_run`, `damodaran.py:766-786`), with none in `scripts/`, `docs/pipeline` or `.github`. `derive_industry_columns` pops `debt_weight_raw` first and reads the other inputs with `.get` (`damodaran.py:491-509`), so `{field: 0.2}` does not raise. `wacc_sample.xls` parses to 96 rows, all 96 with a float `D/(D+E)` in `[0, 1)`. `_seeded_conn`, `_WACC_FIXTURE` and `_CTRY_FIXTURE` exist (`test_damodaran_datasets.py:27-28, 111-114`), and `import_damodaran_from_files` is keyword-only (`damodaran.py:864-870`). `_null_non_numeric_industry_cells` receives `parse_industry_xls`'s `column_map` parameter (`damodaran.py:571`). The invariant's message is `f"{dataset.key} maps non-columns: {sorted(stray)}"` (`test_damodaran_datasets.py:136`). The existing real-import test checks only margins and multiples (`:156-166`), and `test_damodaran_derived.py` tests the function, not an import.
