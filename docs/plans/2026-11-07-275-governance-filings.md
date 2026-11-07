# Governance filings in filings_log (auditor-change 8-Ks, NT notices) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every company the EDGAR providers import gets its auditor-change 8-Ks (item 4.01) and NT 10-K/10-Q notices stored in `filings_log`, with the 8-K item numbers in a new `items` column, and a new such filing moves the incremental-skip watermark.

**Architecture:** Pure parsing in `bot.ingest.sec_edgar` (two classifiers, one row builder over `filings.recent`, the watermark widened to the same set); one nullable column on `filings_log` with an idempotent migration and a `COALESCE` merge in `upsert_filings`; `EdgarPricedProvider.fundamentals` appends the governance rows of the already-cached submissions payload to the facts rows before the existing restamp. Two d2 boards change their wording to match.

**Tech Stack:** Python 3.12, DuckDB, httpx (mocked transports in tests), pytest, mypy --strict, ruff; d2 v0.9.0 boards + `docs/pipeline/check.py`.

**Spec:** GitHub issue #275 (`gh issue view 275 --repo nicolas-ricc/damodaran`). Its eight "Decisions (taken by the planner; do not reopen)" and its acceptance criteria are binding. Story context: #61.

## Global Constraints

- Public names in `bot.ingest.sec_edgar`: `AUDITOR_CHANGE_FORMS: frozenset[str] = frozenset({"8-K", "8-K/A"})`, `AUDITOR_CHANGE_ITEM = "4.01"`, `LATE_FILING_FORMS: frozenset[str] = frozenset({"NT 10-K", "NT 10-K/A", "NT 10-Q", "NT 10-Q/A"})`, `is_auditor_change(form: str | None, items: str | None) -> bool`, `is_late_filing(form: str | None) -> bool`, `governance_filings_from_submissions(ticker: str, submissions: dict[str, Any]) -> list[dict[str, Any]]`.
- Governance row shape: `{"ticker": ticker.upper(), "filing_type": form, "filing_date": <filingDate string as given>, "accession_number": ..., "source": "sec_edgar", "items": <items or None>}`.
- Only governance filings from submissions are stored; never every 8-K.
- `filings_log.items VARCHAR`, after `accession_number`; migration `ALTER TABLE filings_log ADD COLUMN IF NOT EXISTS items VARCHAR;` right after the `damodaran_country` migrations with a comment (purpose, example `4.01,9.01`, NULL for every other row, rollback `DROP COLUMN items`).
- `upsert_filings` conflict clause: `DO UPDATE SET accession_number = excluded.accession_number, items = COALESCE(excluded.items, filings_log.items)`; `fetched_at` never updated.
- `latest_filing_date_from_submissions` keeps its name.
- No change to `bot.portfolio.events`, `bot.ingest.fmp`, `tests/fake_provider.py`, `docs/pipeline/models/refresh.tla`, the screener.
- Boards: digits only inside words such as `10-K`, except `item 4.01` on a line that carries `@const bot.ingest.sec_edgar.AUDITOR_CHANGE_ITEM`. `ticker_checked` keeps its first label line `the ticker waits for the latest-filing check` (TLA+ view label). `NT` is an all-caps token, so `test_acronyms_are_expanded` requires it in `_ACRONYMS` of `tests/unit/test_pipeline_diagram.py` as `"NT": "notification of late filing"` (SEC Form 12b-25), and the board's first use of `NT` shares its line with that expansion.
- Existing FMP, fake-provider, e2e and `tests/integration/test_sec_edgar_import.py` tests pass without edits.
- `uv run ruff check . && uv run mypy src && uv run pytest -q` green; `python3 docs/pipeline/check.py` passes.

## Assumptions

- Missing or short parallel arrays: `form`, `filingDate`, `accessionNumber`, `items` are walked by index over `form`; a missing index in any other array reads as `None` (so a payload without `items`, or with a shorter one, means "no items"). Rejected: `zip(strict=False)` over all four, which would silently drop every entry when `items` is absent.
- A JSON `null` in `items` is the same as `""`.
- Grouping (reconciles decision 2 with the acceptance criterion "two 8-K entries on the same date with items `"4.01"` and `"9.01"` yield one row with items `"4.01,9.01"`"): entries are grouped by `(form, filingDate)`; a group is stored only when at least one of its entries is an auditor change or a late filing; its items are the union over every entry of the group (the row stands for all filings of that form on that day, as the primary key does); its accession number is that of the first governance entry in payload order. Rejected: merging only governance entries, which yields `"4.01"` and fails the criterion; storing the first entry's accession even when it is not a governance filing.
- Duplicate accession numbers in `filings.recent` get no special handling: they fall into the same `(form, filingDate)` group. An `8-K` and an `8-K/A` on one day are two rows (different `filing_type`, different primary key).
- A `form` array longer than `filingDate` gives entries without a date, which `coerce_date` drops; a missing `accessionNumber` is stored as `NULL` (the column is nullable).
- Merged item tokens: stripped, empties dropped, sorted by plain string order (`"4.01" < "9.01"`), comma-joined with no spaces; when the merged set is empty the row's `items` is `None`. A single kept entry is normalised the same way (so `" 4.01 , 9.01"` is stored as `"4.01,9.01"`).
- The row keeps the date string as given in the payload (the issue says "ISO string as given"); `coerce_date` is only the drop filter.
- `fundamentals` calls `self._submissions(sym)` once (it is cached, and `lookup_company` reads the same cache), so no extra HTTP request.

## Review Focus

1. Payload with `items` shorter than `form` (a defensive read; no source says EDGAR does this): the trailing entries count as "no items" rather than raising or being skipped. Pinned in Task 1 (`test_governance_filings_tolerates_short_items_array`).
2. `items` holding JSON `null` for an NT entry: the NT row is kept with `items is None`. Pinned in Task 1 (`test_governance_filings_null_items_is_no_items`).
3. A facts-derived `8-K` row and a submissions `8-K` row with the same key in one bundle: after `import_company`, the stored row carries the items. Pinned by Task 2's two-order upsert test (no fixture holds both; the provider fixture's facts carry only a 10-K) and by Task 3's assertion that facts rows come first in `bundle.filings`.
4. A ticker that already has the governance rows stored: re-importing keeps `fetched_at`, so no spurious `new_filing` event. Pinned in Task 2 (`fetched_at` asserted in both orders).
5. An unparseable `filingDate` on an otherwise matching NT entry: dropped, and it does not move the watermark. Pinned in Task 1 (`test_governance_filings_drops_unparseable_dates`).

## Acceptance criteria and decisions → tasks

| Issue item | Task |
|---|---|
| AC 1 (fixture rows), AC 2 (no `items`, token matching, merge), AC 3 (watermark); decisions 1, 2, 5, 6 | Task 1 |
| AC 4 (schema fresh + legacy + idempotent), AC 5 (upsert merge, `fetched_at`); decision 3 | Task 2 |
| AC 6 (providers + `import_company`), AC 7 (untouched suites pass); decision 4 | Task 3 |
| AC 8 (boards, `check.py`, render, board tests); decision 7 | Task 4 |
| AC 9 (lint + full suite) | Final |
| Decision 8 (no change to `bot.portfolio.events`) | Global Constraints; nothing to build |

---

### Task 1: Classifiers, governance rows and the widened watermark

**Files:**
- Modify: `src/bot/ingest/sec_edgar.py` (constants near `_FINANCIAL_FORMS`; functions next to `latest_filing_date_from_submissions`)
- Modify: `tests/fixtures/edgar/aapl_submissions.json`
- Test: `tests/unit/test_sec_edgar_submissions.py`

**Interfaces:**
- Produces: the six public names of Global Constraints.

- [ ] **Step 1: Extend the fixture** (decision 6): `filings.recent` arrays become, in order, `form = ["10-Q", "8-K", "10-K", "8-K", "NT 10-Q"]`, `filingDate = ["2026-08-01", "2026-07-15", "2025-11-01", "2026-05-20", "2026-04-30"]`, `accessionNumber = [..existing three.., "0000320193-26-000050", "0000320193-26-000041"]`, `items = ["", "2.02,9.01", "", "4.01,9.01", ""]`.

- [ ] **Step 2: Write the failing tests** (the stage-3 evals), each building payloads with a small helper `_recent(**arrays)`:
  - `test_is_auditor_change_matches_item_token`: `True` for `("8-K", " 4.01 , 9.01")`, `("8-K", "4.01")`, `("8-K/A", "4.01")`; `False` for `("8-K", "2.02,9.01")`, `("8-K", "14.01")`, `("8-K", None)`, `("8-K", "")`, `("10-K", "4.01")`, `(None, "4.01")`.
  - `test_is_late_filing_matches_nt_forms`: `True` for each of `LATE_FILING_FORMS`; `False` for `"10-K"`, `"NT 20-F"`, `None`.
  - `test_governance_filings_from_fixture_returns_the_two_governance_rows`: exactly `[("8-K", "2026-05-20", "0000320193-26-000050", "4.01,9.01"), ("NT 10-Q", "2026-04-30", "0000320193-26-000041", None)]` as `(filing_type, filing_date, accession_number, items)`, every row `ticker == "AAPL"`, `source == "sec_edgar"`.
  - `test_governance_filings_without_items_array_keeps_only_nt_rows`.
  - `test_governance_filings_merges_items_of_same_form_and_date`: two `8-K` on `2026-05-20` with `"4.01"` (accn A) and `"9.01"` (accn B) → one row, items `"4.01,9.01"`, accession A. Also `"9.01"` (accn A) first and `"4.01"` (accn B) second → one row, items `"4.01,9.01"`, accession B (the first governance entry). Two same-day `8-K`s with `"2.02"` and `"9.01"` → no row.
  - `test_governance_filings_drops_unparseable_dates`, `test_governance_filings_tolerates_short_items_array`, `test_governance_filings_null_items_is_no_items` (Review Focus 1, 2, 5).
  - `test_every_governance_date_of_the_watermark_is_stored`: on the fixture plus `NT 10-K` `2026-09-15`, `("NT 10-K", "2026-09-15")` is among the governance rows, so the date the watermark reports is the date a stored row carries.
  - `test_latest_filing_date_counts_auditor_changes_and_late_filings`: fixture → `date(2026, 8, 1)`; plus `8-K` `2026-09-01` items `"4.01"` → `date(2026, 9, 1)`; with items `"2.02"` → `date(2026, 8, 1)`; plus `NT 10-K` `2026-09-15` → `date(2026, 9, 15)`.

- [ ] **Step 3: Run** `uv run pytest tests/unit/test_sec_edgar_submissions.py -q` — expected FAIL (ImportError on the new names).

- [ ] **Step 4: Implement** the constants, `is_auditor_change`, `is_late_filing`, `governance_filings_from_submissions` (docstring states the `filings.recent` limit: at least one year or the newest 1,000 filings; `filings.files` is not fetched), and widen `latest_filing_date_from_submissions` (reads `items` by index the same way; docstring updated). A private index-safe reader shared by both functions keeps the parallel-array walk in one place.

- [ ] **Step 5: Run** the same command — PASS; also `uv run pytest tests/unit/test_edgar_stooq_provider.py tests/unit/test_edgar_tiingo_provider.py -q` (fixture change) — PASS.

- [ ] **Step 6: Commit** `feat(ingest): classify auditor-change 8-Ks and NT notices in the EDGAR submissions index (#275)`.

### Task 2: `filings_log.items` and the merging upsert

**Files:**
- Modify: `src/bot/storage/schema.sql` (`filings_log` CREATE TABLE; migration after the `damodaran_country` ALTERs)
- Modify: `src/bot/ingest/sec_edgar.py::upsert_filings` (docstring too)
- Test: `tests/unit/test_sec_edgar_importer.py`, new `tests/unit/test_filings_log_schema.py`

**Interfaces:**
- Produces: column `filings_log.items VARCHAR`; `upsert_filings(conn, filings) -> int` writing `row.get("items")`.

- [ ] **Step 1: Write the failing tests**
  - `test_filings_log_has_items_column` (fresh `apply_schema`).
  - `test_apply_schema_adds_items_to_a_legacy_filings_log`: create the pre-change table verbatim (`ticker, filing_type, filing_date, accession_number, source, fetched_at DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY (ticker, filing_type, filing_date, source)`), insert one row, `apply_schema` twice, the column exists, the row survives with `items IS NULL`.
  - `test_upsert_filings_keeps_items_whichever_row_arrives_second` parametrised over both orders of `{no items}` / `{"items": "4.01,9.01"}` for the same `("AAPL", "8-K", date(2026, 5, 20), "edgar_tiingo")` key: `items == "4.01,9.01"` and `fetched_at` equals the value set by `UPDATE` after the first insert.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_sec_edgar_importer.py tests/unit/test_filings_log_schema.py -q` — FAIL.
- [ ] **Step 3: Implement** schema column + migration + upsert change.
- [ ] **Step 4: Run** — PASS; `uv run pytest tests/unit -q -k "schema or filings"` — PASS.
- [ ] **Step 5: Commit** `feat(ingest): filings_log carries the 8-K item numbers (#275)`.

### Task 3: Providers return and import the governance rows

**Files:**
- Modify: `src/bot/ingest/edgar_base.py::EdgarPricedProvider.fundamentals`
- Test: `tests/unit/test_edgar_stooq_provider.py`, `tests/unit/test_edgar_tiingo_provider.py`

**Interfaces:**
- Consumes: `governance_filings_from_submissions` (Task 1), `filings_log.items` + `upsert_filings` (Task 2).

- [ ] **Step 1: Write the failing tests**, in each provider module:
  - `test_fundamentals_includes_the_governance_filings`: `{(r["filing_type"], r["filing_date"], r.get("items")) for r in bundle.filings}` ⊇ `{("8-K", "2026-05-20", "4.01,9.01"), ("NT 10-Q", "2026-04-30", None)}`; those rows' `source` is the provider name; the facts row `("10-K", "2025-11-01")` is still first.
  - `test_import_company_stores_the_governance_filings`: `apply_schema` on `:memory:`, `import_company(conn, ticker="AAPL", provider=_provider())`, then the issue's query returns `{("8-K", date(2026, 5, 20), "4.01,9.01"), ("NT 10-Q", date(2026, 4, 30), None)}`.
  - In `test_edgar_stooq_provider.py` only, `test_refresh_skips_a_ticker_whose_newest_filing_is_a_stored_nt_notice`: a handler wrapping `_edgar_handler` that serves a submissions payload whose only entries are `10-K` `2025-11-01` (matching the facts row) and `NT 10-K` `2026-09-15`; after `import_company`, `latest_local_filing_date(conn, "AAPL", "edgar_stooq") == date(2026, 9, 15)` and `bot.ingest.universe._should_skip("AAPL", date(2026, 9, 15), provider)` is `True`.
- [ ] **Step 2: Run** both modules — FAIL.
- [ ] **Step 3: Implement** decision 4: `filings = parsed.filings + governance_filings_from_submissions(sym, submissions)` when `submissions = self._submissions(sym)` is not `None`, built into the `ParsedCompanyData` before `_restamp` (so restamping stays in one place).
- [ ] **Step 4: Run** both modules plus `tests/unit/test_fmp*.py tests/e2e tests/integration/test_sec_edgar_import.py` — PASS without edits to those.
- [ ] **Step 5: Commit** `feat(ingest): EDGAR providers import the governance filings (#275)`.

### Task 4: Boards

**Files:**
- Modify: `tests/unit/test_pipeline_diagram.py` (`_ACRONYMS` gains `"NT": "notification of late filing"`)
- Modify: `docs/pipeline/refresh.d2` (node `fundamentals.skip` second line; edge `fundamentals.import -> duckdb.filings_log`), `docs/pipeline/refresh-fundamentals.d2` (node `ticker_checked` second line; edge `edgar -> ticker_checked`), their `.svg`, `docs/pipeline/rendered.sha256`.

- [ ] **Step 1:** Texts (decision 7). Skip node / `ticker_checked` / edge say: newest 10-K, 10-Q or 20-F filing date (amendments too), a notification of late filing (NT 10-K, NT 10-Q) or an 8-K reporting an auditor change (item 4.01), worded so the expansion sits on the same line as the first `NT`. Each line with `item 4.01` carries `# @const bot.ingest.sec_edgar.AUDITOR_CHANGE_ITEM` (keep existing `@symbol` citations on those lines). Import edge: `"one row per form and filing date; 8-K rows carry their item numbers"`.
- [ ] **Step 2:** `PATH=/usr/local/lib/d2/d2-v0.9.0/bin:$PATH docs/pipeline/build.sh`; `python3 docs/pipeline/check.py` — passes.
- [ ] **Step 3:** `uv run pytest tests/unit/test_pipeline_diagram.py tests/unit/test_pipeline_subboards.py tests/unit/test_pipeline_models.py -q` — PASS.
- [ ] **Step 4: Commit** the test edit, the `.d2`, `.svg`, `rendered.sha256`: `docs(pipeline): the fundamentals skip check counts governance filings (#275)`.

### Final

- [ ] `uv run ruff check . && uv run mypy src && uv run pytest -q` — green.

## Grilling

- Rounds: 1 (the revision added one test and wording; no task added or removed, no seam changed).
- Questions: 18. Sources: ISSUE 7, CODE 14, DOC 1 (several answers cite more than one); NO SOURCE 4, all technical assumptions.
- Assumptions added: the `(form, filingDate)` grouping with items unioned over the group and the first governance accession (reconciles decision 2 with AC 2); duplicate accessions and `8-K`/`8-K/A` handling; missing dates and accessions in short arrays; the "trimmed arrays" claim withdrawn (defensive read only).
- Plan changes: the AC → task table; the watermark/storage consistency test (Task 1) and the skip-after-import test (Task 3); Review Focus 3 reworded.
- Spec ambiguities: none. Follow-up issues opened: none.
- Status: ok.
