# Per-currency risk-free rate and GDP ceiling (ADR 0005 §4) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Value every company with the risk-free rate and nominal-GDP ceiling of its valuation currency, read from a hand-curated `config/currencies.yaml`. Retire the US risk-free scalar broadcast into `damodaran_country`. Give each coverage-gate exclusion a named reason.

**Architecture:** A pure loader (`bot.reference.currencies`) turns the YAML into an immutable `currency -> CurrencyRates` mapping. The valuator's input loaders read the company's valuation currency (the `currency` of its latest non-restated `financials_annual` row) and attach that currency's rates to `AssumptionInputs`. The resolvers use those rates instead of `damodaran_country.risk_free_rate` and the `0.04` constant. The screener's ADR 0006 coverage gate gains a third reason (`currency_uncovered`), and each of the three reasons gets its own name. The importer stops reading the `wacc.xls` pre-header scalar, and the column leaves the schema.

**Tech Stack:** Python 3.12, DuckDB, PyYAML, pydantic-settings, structlog, pytest, `uv`.

**Spec:** GitHub issue #109, the "Agent Brief" triage comment (the earlier "Human step" body is superseded by it). Context: `docs/adr/0005-currency-handling-and-valuation-currency.md` §4, `docs/adr/0006-unmeasurable-companies-leave-the-universe.md`, `CONTEXT.md`.

## Global Constraints

- File: `config/currencies.yaml`, keyed by ISO 4217 code (three upper-case letters). Each row has `risk_free_rate`, `nominal_gdp_growth`, `source` (URL), `gdp_source` (URL) and `as_of` (date). Values are decimals (`0.042`, not `4.2`).
- `Settings.currencies_path: Path = Path("./config/currencies.yaml")` (env `BOT_CURRENCIES_PATH`), the same pattern as `presets_dir`.
- Missing or malformed file → one warning and an empty mapping (spec §13.2). A malformed file is one that is unparsable, not a mapping, has a key that is not an ISO code, or is missing a field. A `risk_free_rate` outside the open interval `(-0.05, 0.30)` or a `nominal_gdp_growth` outside `(-0.05, 0.25)` raises `ValueError` at load time.
- Valuation currency = `financials_annual.currency` of the latest (`max fiscal_year`) row with `is_restated = FALSE`. A NULL currency, or no row at all, counts as uncovered. There is no USD fallback.
- Terminal growth = `min(rfr_ccy, gdp_ccy)`. The `0.04` constants (`_DEFAULT_GDP_NOMINAL` in `valuator/assumptions.py` and `valuator/analysis.py`) and the `gdp_nominal` keyword are deleted.
- When the currency is uncovered, terminal growth and any GDP-anchored revenue-growth path are `AssumptionSource.UNRESOLVED`. There is no error at resolve time, and one warning is logged per currency per load call (bulk or single).
- Coverage reasons, in precedence order (one reason per company): `industry_unmapped` (no `industry_damodaran`), `benchmark_missing` (no benchmark row, or a NULL `wacc`), `currency_uncovered`. `ScreenResult.no_coverage` keeps listing all three.
- Seeded rows: USD, EUR, JPY, GBP, CHF, CAD, AUD, CNY, INR, BRL. `risk_free_rate` is Damodaran's "Government Bond Rates and Riskfree Rates, by Currency on January 1, 2026" table (net of the rating-based default spread). `nominal_gdp_growth` is `(1 + real_2030)(1 + cpi_2030) - 1` from IMF WEO October 2026 (`NGDP_RPCH`, `PCPIPCH`; euro area = `EURO`). The one exception is USD, which keeps `0.04` so that acceptance criterion 1 holds; it is flagged in a YAML comment and in the PR. `as_of: 2026-01-01`.
- `ruff`, `mypy --strict` (`uv run mypy src`), `uv run pytest -q`, `python3 docs/plano/build.py`, `python3 docs/leccion/check.py` and `python3 docs/plano/build_estado.py` all pass.

Seed values (rfr from Damodaran, GDP from IMF):

| ccy | risk_free_rate | nominal_gdp_growth |
|---|---|---|
| USD | 0.0395 | 0.04 (flagged; IMF gives 0.0373) |
| EUR | 0.0290 | 0.0312 |
| JPY | 0.0147 | 0.0261 |
| GBP | 0.0403 | 0.0343 |
| CHF | 0.0031 | 0.0251 |
| CAD | 0.0347 | 0.0373 |
| AUD | 0.0481 | 0.0465 |
| CNY | 0.0126 | 0.0537 |
| INR | 0.0474 | 0.1107 |
| BRL | 0.1173 | 0.0557 |

## Review Focus

1. **An existing DuckDB file still has the `risk_free_rate` column.** `CREATE TABLE IF NOT EXISTS` does not drop it. `schema.sql` therefore ends with `ALTER TABLE damodaran_country DROP COLUMN IF EXISTS risk_free_rate;`, and Task 3 tests that `apply_schema` on a DB built with the old DDL removes the column.
2. **A lower-case or padded currency in `financials_annual` (`" usd"`).** The lookup normalises with `.strip().upper()` before reading the table. Task 2 tests a `"usd"` row resolving USD.
3. **A company whose only annual rows are restated, or that has none.** Its valuation currency is `None`, so the screener excludes it as `currency_uncovered` and the valuator leaves terminal growth unresolved. Tests are in Task 2 and Task 4.
4. **A manual `terminal_growth` override on an uncovered currency.** The override still wins (`MANUAL`). Task 2 tests it.
5. **Rates written as percentages (`3.95`).** The range check rejects them at load. Task 1 tests it.

---

### Task 1: Currency table loader, seeded file, settings

**Files:**
- Create: `src/bot/reference/currencies.py`, `config/currencies.yaml`, `tests/unit/test_currencies.py`
- Modify: `src/bot/config.py` (add `currencies_path` next to `presets_dir`)

**Interfaces:**
- Produces:
  - `@dataclass(frozen=True) class CurrencyRates: risk_free_rate: float; nominal_gdp_growth: float; source: str; gdp_source: str; as_of: date`
  - `type CurrencyTable = Mapping[str, CurrencyRates]`
  - `DEFAULT_CURRENCIES_PATH = Path("config/currencies.yaml")`
  - `load_currency_table(path: Path | None = None) -> CurrencyTable` (returns a `MappingProxyType`; `None` → default path)
  - `normalize_currency(code: str | None) -> str | None` (strip + upper; blank → `None`)
  - `Settings.currencies_path: Path`

- [ ] **Step 1: Failing tests** in `tests/unit/test_currencies.py`:
  - `test_seeded_file_has_the_ten_major_currencies`: `load_currency_table(REPO/"config/currencies.yaml")` keys ⊇ `{"USD","EUR","JPY","GBP","CHF","CAD","AUD","CNY","INR","BRL"}`.
  - `test_every_seeded_row_has_sources_and_as_of`: for each row, `source.startswith("https://")`, `gdp_source.startswith("https://")`, `isinstance(as_of, date)`.
  - `test_seeded_usd_and_jpy_values`: USD `== (0.0395, 0.04)`, JPY `== (0.0147, 0.0261)` (approx).
  - `test_missing_file_warns_and_is_empty` (structlog `capture_logs`, event `currencies.absent`).
  - `test_malformed_file_warns_and_is_empty`: parametrised over unparsable YAML, a list at the top level, key `"usd"`, and a missing `as_of`. Event `currencies.malformed`.
  - `test_out_of_range_rate_fails_at_load`: `risk_free_rate: 3.95` → `pytest.raises(ValueError)`. Do the same for `nominal_gdp_growth: 0.25` (the open bound).
  - `test_table_is_immutable`: item assignment raises `TypeError`.
  - `test_settings_currencies_path_default_and_override` (`monkeypatch.setenv("BOT_CURRENCIES_PATH", ...)`).
- [ ] **Step 2:** Run `uv run pytest tests/unit/test_currencies.py -q`. Expected: FAIL (module missing).
- [ ] **Step 3:** Implement the loader. Use `yaml.safe_load`; PyYAML gives `as_of` as a `date`, and a string `as_of` must be parsed with `date.fromisoformat`. Write `config/currencies.yaml` with the table above and a header comment naming both sources and the USD flag. `source` is `https://aswathdamodaran.blogspot.com/2026/02/data-update-4-for-2026-global.html`; `gdp_source` is `https://www.imf.org/external/datamapper/datasets/WEO`.
- [ ] **Step 4:** Run the tests. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(#109): curated per-currency risk-free and GDP table`.

### Task 2: Valuator resolves rfr and GDP by valuation currency

**Files:**
- Modify: `src/bot/valuator/assumptions.py`, `src/bot/valuator/analysis.py`, `src/bot/cli.py` (`_analyze_one` / `analyze`, `portfolio`), `src/bot/portfolio/marks.py`, `src/bot/portfolio/command.py`, `src/bot/screener/engine.py` (`_batch_dcf_margins` passes the table through)
- Test: `tests/unit/test_valuator_assumptions.py`, `tests/unit/test_valuation_bulk_load.py`, `tests/unit/test_valuator_analysis.py`, and every test seeding `financials_annual` for a valued company (add `currency = 'USD'`)

**Interfaces:**
- Consumes: Task 1's `CurrencyTable`, `CurrencyRates`, `load_currency_table`, `normalize_currency`.
- Produces:
  - `AssumptionInputs` gains `valuation_currency: str | None = None` and `currency_rates: CurrencyRates | None = None`.
  - `load_assumption_inputs(conn, ticker, *, currencies: CurrencyTable | None = None)` and `bulk_load_assumption_inputs(conn, tickers, *, currencies: CurrencyTable | None = None)`. `None` → `load_currency_table()`.
  - `load_valuation_input(conn, ticker, *, currencies=None)`, `bulk_load_valuation_inputs(conn, tickers, *, currencies=None)` and `analyze(..., currencies: CurrencyTable | None = None)` pass the table through.
  - `resolve_assumptions(ticker, conn, override_path=None, *, auto_story_type=None, db_inputs=None, currencies=None)`: the `gdp_nominal` parameter is removed.
  - `run_portfolio(..., currencies: CurrencyTable | None = None)` → `mark_holdings(..., currencies=...)`. The CLI passes `load_currency_table(settings.currencies_path)` to `analyze`, `screen` and `portfolio`.
  - Log event `assumptions.currency_uncovered` with `currency=` (once per distinct currency per load call).

- [ ] **Step 1: Failing tests** (`test_valuator_assumptions.py`; seed `financials_annual.currency`, pass `currencies=` an inline table built from `CurrencyRates`):
  - `test_usd_company_terminal_growth_uses_the_usd_pair`: USD (0.0395, 0.04) → `terminal_growth == 0.0395`, `RULE_BASED`.
  - `test_jpy_company_uses_the_jpy_rate_and_gdp_ceiling`: latest row `currency='JPY'`, table JPY (0.0147, 0.0261) → `terminal_growth == 0.0147`. With JPY (0.03, 0.0261) → `0.0261` (the GDP side of `min`).
  - `test_latest_annual_row_decides_the_valuation_currency`: an older row in `USD` and the latest in `JPY` resolves to JPY.
  - `test_lowercase_currency_resolves`: `'usd'` resolves to USD.
  - `test_uncovered_currency_leaves_terminal_growth_unresolved_and_warns_once`: `currency='XYZ'` → `UNRESOLVED`, `value is None`. `bulk_load_assumption_inputs` over two XYZ companies logs exactly one `assumptions.currency_uncovered`.
  - `test_no_history_revenue_growth_unresolved_when_currency_uncovered`, and with USD it is `(0.04,)*5` `RULE_BASED`.
  - `test_high_growth_fade_targets_the_currency_gdp`: JPY, high-growth, history → the path ends at 0.0261.
  - `test_manual_terminal_growth_wins_over_uncovered_currency`.
  - `test_null_or_missing_currency_is_uncovered`: a NULL currency, and a company with only restated rows.
  - Bulk/single parity: extend the existing parity test in `test_valuation_bulk_load.py` to compare `valuation_currency` and `currency_rates`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement. `_CountryRow` keeps `risk_free_rate` until Task 3; Task 2 only stops reading it. `_resolve_terminal_growth(override, rates: CurrencyRates | None)`. `_resolve_revenue_growth(historical, override, gdp: float | None, *, story_type)`: high-growth without a GDP falls through to the historical average, and no history without a GDP is `UNRESOLVED`. The bulk path adds `currency` to its existing `financials_annual` scan (the query count stays the same). The single path takes it from one `ORDER BY fiscal_year DESC LIMIT 1` query. Remove both `_DEFAULT_GDP_NOMINAL` constants and every `gdp_nominal=` call site, tests included. Update the module docstring's "nominal-GDP scalar" sentence.
- [ ] **Step 4:** Run `uv run pytest -q`. Expected: all PASS. The second-pass golden (`tests/fixtures/screener/second_pass_shortlist.golden`) changes only through terminal growth: it was `min(0.04 seeded rfr, 0.04)` and is now `min(0.0395 file USD, 0.04)`. Regenerate it the way the test file documents, and add a comment in the test saying the USD pair now comes from `config/currencies.yaml`.
- [ ] **Step 5:** Commit: `feat(#109): resolve rfr and GDP ceiling by valuation currency`.

### Task 3: Importer and schema drop the risk-free scalar

**Files:**
- Modify: `src/bot/ingest/damodaran.py` (delete `RISK_FREE_RATE_LABEL`, `parse_preheader_scalar` and the broadcast loop's rfr branch; fix the module docstring), `src/bot/storage/schema.sql`, `src/bot/valuator/assumptions.py` (`_CountryRow` loses `risk_free_rate`; both `damodaran_country` SELECTs drop it)
- Test: `tests/integration/test_damodaran_import.py`, `tests/integration/test_damodaran_live.py`, `tests/unit/test_damodaran_derived.py`, `tests/unit/test_storage_db.py`, and every test INSERT naming `risk_free_rate`

**Interfaces:**
- Consumes: Task 2 (nothing reads the column any more).
- Produces: a `damodaran_country` table without `risk_free_rate`.

- [ ] **Step 1: Failing tests:**
  - `test_damodaran_country_has_no_risk_free_rate_column` (`test_storage_db.py`): after `apply_schema`, `information_schema.columns` has no `risk_free_rate` for `damodaran_country`.
  - `test_apply_schema_drops_legacy_risk_free_rate_column`: create the table with the old DDL (including `risk_free_rate`), insert a row, run `apply_schema`, and check the column is gone and the row survives.
  - In `test_damodaran_import.py`, replace the US `risk_free_rate == 0.0395` assertion with the column-absent check. Keep the tax assertions. Replace `test_terminal_growth_is_capped_by_the_imported_risk_free_rate` with `test_terminal_growth_uses_the_currency_file_usd_rate`: import the fixtures, seed ACME with a `currency='USD'` annual row, `resolve_assumptions(..., currencies=load_currency_table(REPO/"config/currencies.yaml"))` gives `terminal_growth == 0.0395`. Its docstring says the US pin moved from the importer to the currency file (#51 → #109).
  - `test_import_never_reads_the_preheader_scalar`: `hasattr(damodaran, "parse_preheader_scalar") is False`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement. Add `ALTER TABLE damodaran_country DROP COLUMN IF EXISTS risk_free_rate;` after the `CREATE TABLE`. Remove `risk_free_rate` from every test INSERT. In the live test, drop the rfr assertion and the `damodaran.risk_free_rate.unavailable` event from its watched list.
- [ ] **Step 4:** Run `uv run pytest -q`. Expected: PASS. `tests/unit/test_cli_refresh.py` and the fixture import test (`import_damodaran_from_files` → `success`) still pass, which covers "`bot refresh --damodaran` still succeeds".
- [ ] **Step 5:** Commit: `refactor(#109): drop the US risk-free broadcast from damodaran_country`.

### Task 4: Named coverage-gate reasons and the currency gate

**Files:**
- Modify: `src/bot/screener/engine.py`, `src/bot/reporting/screen_report.py`, `src/bot/cli.py` (`screen` echo)
- Test: `tests/unit/test_screener_engine.py`, `tests/unit/test_reporting_screen.py`, `tests/integration/test_screen_cli.py`

**Interfaces:**
- Consumes: Task 1's table and `normalize_currency`, and Task 2's `currencies=` on `bulk_load_valuation_inputs`.
- Produces:
  - `class CoverageReason(StrEnum): INDUSTRY_UNMAPPED = "industry_unmapped"; BENCHMARK_MISSING = "benchmark_missing"; CURRENCY_UNCOVERED = "currency_uncovered"`, defined in `engine.py`.
  - `run_screen(..., currencies: CurrencyTable | None = None)` (`None` → `load_currency_table()`). The second pass gets the same table.
  - A `RejectedCompany` excluded by the gate carries `failed_gates == (reason.value,)`.
  - `ScreenResult.coverage_counts -> dict[CoverageReason, int]`: a property derived from `rejected`, with all three keys present.
  - Log event `screener.currency_uncovered` with `currency=` and `companies=` count, once per distinct currency per run.

- [ ] **Step 1: Failing tests:**
  - Update `test_no_coverage_companies_appear_as_rejected_by_the_coverage_gate`: NOMAP → `("industry_unmapped",)`, NOBENCH and NULLWACC → `("benchmark_missing",)`.
  - `test_uncovered_currency_is_excluded_with_its_own_reason`: a fully benchmarked company whose latest annual row is `'XYZ'` is in `no_coverage`, `rejected == ("currency_uncovered",)`, and `coverage_counts[CURRENCY_UNCOVERED] == 1`, `[BENCHMARK_MISSING] == 0`.
  - `test_jpy_company_in_the_table_is_screened`: the same company in `'JPY'` with JPY present in the table is not in `no_coverage`.
  - `test_missing_currency_file_excludes_every_company_as_currency_uncovered`: `currencies=load_currency_table(tmp_path/"absent.yaml")` puts every benchmarked company under `currency_uncovered` and logs `currencies.absent`, with no exception.
  - `test_currency_uncovered_warns_once_per_currency`: two XYZ companies → one `screener.currency_uncovered` event.
  - `test_markdown_reports_coverage_counts_by_reason` (`test_reporting_screen.py`): the header line contains `industry_unmapped 1`, `benchmark_missing 0` and `currency_uncovered 2`.
  - `test_screen_cli_prints_coverage_counts`: the CLI output contains `currency_uncovered`.
- [ ] **Step 2:** Run them. Expected: FAIL.
- [ ] **Step 3:** Implement. Add `_load_reporting_currencies(conn) -> dict[str, str | None]`, one windowed scan (`QUALIFY row_number() OVER (PARTITION BY ticker ORDER BY fiscal_year DESC) = 1`, `is_restated = FALSE`). The gate checks reasons in precedence order. The Markdown header becomes `Excluded by coverage gate (ADR 0006): N (industry_unmapped a · benchmark_missing b · currency_uncovered c)`. The CLI prints the same breakdown after `Screened ...`. Update the `RejectedCompany`/`ScreenResult` docstrings.
- [ ] **Step 4:** Run `uv run pytest -q`. Expected: PASS.
- [ ] **Step 5:** Commit: `feat(#109): name coverage-gate reasons and exclude uncovered currencies`.

### Task 5: Docs: ADR 0005, CONTEXT glossary, plano/estado/lección

**Files:**
- Modify: `docs/adr/0005-currency-handling-and-valuation-currency.md`, `docs/adr/0006-unmeasurable-companies-leave-the-universe.md` (the reason names in Consequences), `CONTEXT.md`, `docs/plano/estado.py`, `docs/leccion/index.html` (only if `check.py` complains)

- [ ] **Step 1:** In ADR 0005, change Status to: §4 Implemented (2026-10-28, #109: `config/currencies.yaml` + `bot.reference.currencies`, resolved by valuation currency in `valuator/assumptions.py`, gate in `screener/engine.py`); §1–§3 still not implemented. Note in §4 that the per-currency table is curated by hand from Damodaran's January table plus IMF GDP, not imported.
- [ ] **Step 2:** In `CONTEXT.md`, have **Coverage gate** list the three reasons, and add **Uncovered currency**: a valuation currency with no row in `config/currencies.yaml` (or unknown); the company leaves the universe with reason `currency_uncovered`. _Avoid_: missing currency.
- [ ] **Step 3:** Re-audit and update `docs/plano/estado.py`: the importer rfr entry (line ~46), `adr-0005` (~183) and the matching BRECHA (~208); the coverage-gate entries (~83, ~99, ~186) for the reason names. Set `AUDITADO_EN`/`AUDITADO_EL` to the current HEAD and `28 de octubre de 2026`.
- [ ] **Step 4:** Run `python3 docs/plano/build.py && python3 docs/plano/build_estado.py && python3 docs/leccion/check.py && uv run pytest tests/unit/test_leccion.py -q`. Expected: no errors; fix any cited symbol or line that moved.
- [ ] **Step 5:** Commit: `docs(#109): ADR 0005 §4 implemented; glossary and plans updated`.
