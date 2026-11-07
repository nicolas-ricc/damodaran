# `bot show --fetch` through the provider port — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `bot show TICKER --fetch` imports a missing ticker through `_make_provider(settings)` + `bot.ingest.universe.import_company`, so the stored row gets `industry` and `industry_damodaran`; `import_company_from_sec` is deleted and its tests are moved, not dropped.

**Architecture:** `show` reuses the composition root (`_make_provider`) and the provider-port importer that `bot refresh --fundamentals` already uses; the industry mapping is resolved by `universe._company_row` with `provider.industry_mapping_key`. The SEC-only importer becomes dead and is removed; `parse_company_facts`, `SecEdgarClient`, the `upsert_*` helpers and `count_null_revenue` stay.

**Tech Stack:** Python 3.12, Typer, DuckDB, pytest + pytest-vcr (record mode `none`), mypy --strict, ruff.

**Spec:** GitHub issue #58 (`gh api repos/nicolas-ricc/damodaran/issues/58 --jq .body`), "Design decisions (taken, do not reopen)" and "Acceptance criteria".

## Global Constraints

- `show --fetch` imports with exactly: `with closing(_make_provider(settings)) as provider: result = import_company(conn, ticker=ticker, provider=provider, mapping_path=settings.industry_mapping_path)`.
- No SIC lookup added to `sec_edgar.py`; no second mapping table.
- `import_company_from_sec` no longer exists: `grep -rn import_company_from_sec src tests` returns nothing.
- Do not touch the `"sec_edgar"` stamp in `parse_company_facts`.
- No new cassette is recorded; the existing one is renamed (`git mv`).
- Wording: the `--fetch/--no-fetch` help and the two `typer.echo` messages say "the configured data provider" instead of "SEC EDGAR".
- No ADR change.
- `uv run pytest -q` and `uv run ruff check . && uv run mypy src` pass.

## Review Focus

1. The provider cannot find the ticker (e.g. EDGAR has no CIK): `import_company` returns an error `IngestResult`; `show` must print `Failed to import NEW: ...` and exit 1, not crash. Pinned in Task 1 (`test_show_missing_ticker_reports_provider_failure`).
2. The provider is closed after the import even on failure (`closing`). Pinned in Task 1 (both show tests assert `provider.closed`).
3. `--no-fetch` on a missing ticker still exits 2 without building a provider. Pinned in Task 1 (`test_show_no_fetch_does_not_build_provider`).
4. `BOT_DATA_PROVIDER=fmp` with an empty key: `_make_provider` already exits 1 with its own message; nothing new to do, not pinned.
5. Remaining prose that names the deleted function (`universe.import_company` docstring, `tests/integration/test_fmp_import.py` docstring) must not point at a symbol that no longer exists. Covered by the grep in Task 2.

---

### Task 1: `show --fetch` imports through the provider port

**Files:**
- Modify: `src/bot/cli.py` (imports; `show` command around lines 323–356)
- Test: `tests/unit/test_cli_show.py`

**Interfaces:**
- Consumes: `bot.cli._make_provider(settings) -> MarketDataProvider`; `bot.ingest.universe.import_company(conn, *, ticker, provider, mapping=None, mapping_path=None) -> IngestResult`; `tests.fake_provider.FakeProvider`; `bot.ingest.provider.CompanyInfo`.
- Produces: nothing later tasks call; after this task `bot.cli` no longer imports `import_company_from_sec`.

- [ ] **Step 1: Rewrite `test_show_missing_ticker_triggers_sec_import`** (keep its name). Build `provider = FakeProvider(companies={"NEW": CompanyInfo(ticker="NEW", name="NEW Inc", exchange=None, exchange_short_name=None, country="US", currency="USD", sector=None, industry="Electronic Computers", is_actively_trading=True, ipo_date=None)})`, set `provider.industry_mapping_key = "edgar"`, `patch("bot.cli._make_provider", return_value=provider)`. Assert: `exit_code == 0`; `"NEW Inc" in stdout`; reopening the DB, `SELECT industry, industry_damodaran, source FROM companies WHERE ticker='NEW'` == `("Electronic Computers", "Computers/Peripherals", "fake")`; `provider.closed`. Do not patch `import_company`.
- [ ] **Step 2: Add `test_show_missing_ticker_reports_provider_failure`**: `FakeProvider(fail_with={"NEW": ValueError("Ticker NEW not found")})`, patched in as above. Assert `exit_code == 1`, `"Failed to import NEW"` in the output (stderr is mixed into `result.output` by `CliRunner`), `provider.closed`.
- [ ] **Step 3: Add `test_show_no_fetch_does_not_build_provider`**: patch `bot.cli._make_provider` with a `MagicMock`; invoke `["show", "NEW", "--no-fetch"]`; assert `exit_code == 2` and the mock was not called.
- [ ] **Step 4: Run** `uv run pytest -q tests/unit/test_cli_show.py` — Expected: Step 1 and 2 tests FAIL (the CLI still calls `import_company_from_sec`, which hits the network/fails differently).
- [ ] **Step 5: Implement** in `show`: replace the `import_company_from_sec` call with the Global Constraints snippet (import `import_company` from `bot.ingest.universe` in the existing import block; drop the `bot.ingest.sec_edgar` import). Wording: help `"If the ticker isn't in the DB, fetch it from the configured data provider first."`; messages `f"{ticker} not in DB (use --fetch to import from the configured data provider)."` and `f"{ticker} not in DB — fetching from the configured data provider..."`.
- [ ] **Step 6: Run** `uv run pytest -q tests/unit/test_cli_show.py` — Expected: PASS.
- [ ] **Step 7: Commit** `feat(#58): show --fetch imports through the provider port`.

### Task 2: retire `import_company_from_sec`, move its tests, update the wording

**Files:**
- Modify: `src/bot/ingest/sec_edgar.py` (delete `import_company_from_sec`; `upsert_company` docstring; drop imports only that function used, e.g. `refresh_run`/`IngestResult` if unused afterwards)
- Modify: `src/bot/ingest/edgar_base.py` (`_restamp` docstring)
- Modify: `src/bot/ingest/universe.py` (`import_company` docstring: drop "Mirrors `import_company_from_sec`")
- Modify: `tests/integration/test_fmp_import.py` (module docstring naming the deleted function)
- Modify: `docs/plano/estado.py` (`sec-import` row)
- Test: `tests/integration/test_sec_edgar_import.py`, `tests/unit/test_sec_edgar_importer.py`
- Rename: `tests/fixtures/cassettes/sec_edgar/test_import_company_from_sec_populates_db.yaml` → `test_parse_company_facts_from_cassette_populates_db.yaml`

**Interfaces:**
- Consumes: `SecEdgarClient(user_agent=...)` (context manager) with `lookup_cik(ticker) -> str | None` and `fetch_company_facts(cik) -> dict`; `parse_company_facts(ticker, facts) -> ParsedCompanyData`; `upsert_company`, `upsert_financials_annual`, `upsert_financials_quarterly`, `upsert_filings`; `bot.ingest.base.transaction(conn)`; `bot.ingest.universe.import_company`.
- Produces: none.

- [ ] **Step 1: Integration test.** `git mv` the cassette to the new name. Rename the test to `test_parse_company_facts_from_cassette_populates_db` (keep `@pytest.mark.integration` and `@pytest.mark.vcr`); it does by hand: `with SecEdgarClient(user_agent="Tester t@example.com") as client: cik = client.lookup_cik("AAPL"); facts = client.fetch_company_facts(cik)`, `parsed = parse_company_facts("AAPL", facts)`, then inside `with transaction(conn):` the four upserts. Replace `result.is_success()` / `rows_affected > 0` with `assert cik == "0000320193"` and the upsert counts being > 0 (sum). Keep the companies, annual count, newest `(2025, date(2025, 9, 27))`, filings assertions; drop the `refresh_log` one.
- [ ] **Step 2: Unit tests.** In `tests/unit/test_sec_edgar_importer.py` delete `test_import_company_from_sec_reports_null_revenue_count`, `test_import_company_from_sec_records_shares_rescaled`, `_annual_fact`, `_mcd_shares_facts`, and the now-unused `MINIMAL_FACTS`, `_make_mock_conn`, unused imports. Port `test_import_company_returns_result_even_when_log_insert_fails` to `bot.ingest.universe.import_company`: `conn = duckdb.connect(":memory:")`, `apply_schema(conn)`, `FakeProvider(companies={"AAPL": CompanyInfo(... industry=None ...)})`, patch `bot.ingest.base._log_refresh` to raise `RuntimeError`; assert `isinstance(result, IngestResult)`, `result.source == "fake"`, `result.status == "success"` (the logging failure is swallowed by `refresh_run`; the import itself succeeded). Rewrite the module docstring to describe what remains (the ported log-failure test, `upsert_company` merge, `upsert_filings` `fetched_at`).
- [ ] **Step 3: Run** `uv run pytest -q tests/unit/test_sec_edgar_importer.py tests/integration/test_sec_edgar_import.py` — Expected: PASS (these tests no longer depend on the function).
- [ ] **Step 4: Delete** `import_company_from_sec` from `sec_edgar.py` and imports only it used.
- [ ] **Step 5: Wording.** `upsert_company` docstring: explain merge-preserve without calling `bot show --fetch` a `sec_edgar`-stamped path (a provider that does not carry a column must not wipe it). `_restamp` docstring: `parse_company_facts` stamps the raw `"sec_edgar"` source; drop the clause about `bot show --fetch` keeping its own provenance. `universe.import_company` docstring: drop the "Mirrors" sentence, keep the rest. `test_fmp_import.py` docstring: say it mirrors the provider-port contract instead. `estado.py` `sec-import` row: text says `bot show --fetch` now goes through `universe.import_company` like `refresh` (through `_make_provider`), so its row carries `industry`/`industry_damodaran`; the location column drops the deleted function's line (`ingest/sec_edgar.py:<line of upsert_company>`). Spanish, matching the file.
- [ ] **Step 6: Verify** `grep -rn import_company_from_sec src tests docs/plano docs/leccion docs/pipeline README.md` → no output (historical plans under `docs/plans/` and `docs/superpowers/` stay as they are); `uv run pytest -q`; `uv run ruff check . && uv run mypy src` → all pass.
- [ ] **Step 7: Commit** `refactor(#58): retire import_company_from_sec, move its tests`.

## Assumptions

- The ported log-failure test asserts `status == "success"` rather than `status in {"success", "error"}`: the old assertion was true for every result and pinned nothing beyond "no exception". Rejected: keeping the tautology.
- The `estado.py` location column keeps `ingest/sec_edgar.py:<upsert_company line>`; that line sits above the deleted function, so it does not shift. No check validates those line numbers (`docs/plano/build_estado.py` only warns on `src/` drift). Rejected: dropping the location.
- The verification grep is widened to `docs/plano docs/leccion docs/pipeline README.md`; dated plans and specs are history and keep the old name. Rejected: rewriting history docs.

## Grilling

- Rounds: 1 (revisions were local: one assertion tightened, one grep widened; no step added or removed, same seam).
- Questions: 18. Sources: ISSUE 7, CODE 15, DOC 1 (some answers cite more than one); NO SOURCE 3, all technical assumptions (above).
- Spec ambiguities: none. Follow-up issues opened: none.
