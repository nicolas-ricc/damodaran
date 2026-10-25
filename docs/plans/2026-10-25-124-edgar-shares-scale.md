# EDGAR share-count scale correction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rescale annual `shares_diluted` values a filer tagged in thousands or millions when the scale is unambiguous, and have `analyze` refuse to value a company whose latest share count is still implausible.

**Architecture:** A pure helper `_rescale_shares_diluted` in `src/bot/ingest/sec_edgar.py` runs at the end of `parse_company_facts` over the annual rows, comparing each value with the median of the ticker's other annual values; the number of corrections travels on `ParsedCompanyData.shares_rescaled` into the `refresh_log` details written by both import paths (`import_company_from_sec` and `universe.import_company`). `analyze` in `src/bot/valuator/analysis.py` gains a bounds check next to its existing "cannot value" checks; `bot analyze` already turns that `ValueError` into a per-ticker failure.

**Tech Stack:** Python 3, structlog, duckdb, typer, pytest, mypy --strict, ruff.

**Spec:** GitHub issue #124 (nicolas-ricc/damodaran), "EDGAR import stores filer scale errors verbatim (MCD diluted shares 732.3 instead of 732,300,000)".

## Global Constraints

- Rescale `shares_diluted` in **annual** rows only (`financials_annual`); quarterly rows are untouched.
- Comparator: median of the ticker's **other** annual `shares_diluted` values in the same parse (non-null, excluding the row under test). Fewer than 3 other values: no correction.
- `r = median / value`. If `1e6 / 2 <= r <= 1e6 * 2`: multiply by `1e6`. Else if `1e3 / 2 <= r <= 1e3 * 2`: multiply by `1e3`. Else unchanged. Bounds inclusive.
- Each `r` is computed from the **original** parsed values, never from a value already corrected in the same pass (order-independent).
- Values `<= 0` are skipped (left unchanged; the valuator already refuses them) and never divided by.
- Every correction logs a structlog **warning** `sec_edgar.shares_rescaled` with keys `ticker`, `fiscal_year`, `original`, `factor`.
- The count of corrections goes in `refresh_log` details under the key `shares_rescaled` (an int, `0` when none).
- Valuator guard bounds: refuse when latest `shares_diluted < 1_000_000` or `> 100_000_000_000`. Message: `f"{ticker}: implausible diluted share count {shares:,.1f} (outside 1,000,000 to 100,000,000,000) — cannot value"`, raised as `ValueError` like the neighbouring checks.
- Type hints everywhere (`mypy --strict`); `uv run ruff check . && uv run mypy src && uv run pytest -q` green.
- Commits: Conventional Commits with `(#124)` scope.

## Review Focus

1. A majority of years mis-scaled (e.g. 3 of 5 at 7xx.x): the median of others mixes scales; the rule must still never inflate a correct value (r < 1 for correct values, never in a band). Test in Task 1.
2. A `None` share value in one year: ignored as comparator and left `None`. Test in Task 1.
3. A non-positive value (CEG's `0.0`): left unchanged, no division error. Test in Task 1.
4. The bulk `bot refresh --fundamentals` path (`EdgarProviderBase._restamp` rebuilds `ParsedCompanyData`) must not drop `shares_rescaled` before it reaches `universe.import_company`. Test in Task 2.
5. The guard fires before any DCF computation and on the batched screener path (`analyze(company=...)`), not only through the CLI. Test in Task 3 calls `analyze` directly.

## Assumptions

Technical decisions taken during plan grilling (none changes what a user sees beyond the issue's specification):

- Factor-2 bands are inclusive (`5e5 <= r <= 2e6`, `500 <= r <= 2000`). Rejected: exclusive bounds — the issue says "within a factor of 2" and the MCD-like mixed-median case sits near the lower edge.
- Every `r` is computed from the original parsed values. Rejected: iterative correction, which makes the result depend on row order.
- Values `<= 0` and `None` are neither corrected nor used as comparators. Rejected: counting zeros in the median (CEG's `0.0` would drag it down).
- The correction count travels as `ParsedCompanyData.shares_rescaled` (plain mutable dataclass, `src/bot/ingest/provider.py:17`). Rejected: re-deriving the count from logs, or a separate return value that changes `parse_company_facts`' signature for both callers.
- `refresh_log` details get `shares_rescaled` on both import paths (`sec_edgar.import_company_from_sec` and `universe.import_company`, the one `bot refresh --fundamentals` uses). Rejected: only the first — the issue names it, but the bulk refresh is how MCD is re-imported.
- The guard's bounds are module constants in `analysis.py`. Rejected: configuration settings — nothing asks for them to be tunable.

---

### Task 1: Rescale mis-scaled annual share counts at parse time

**Files:**
- Modify: `src/bot/ingest/provider.py` (`ParsedCompanyData`)
- Modify: `src/bot/ingest/sec_edgar.py` (`parse_company_facts`, new `_rescale_shares_diluted`)
- Test: `tests/unit/test_sec_edgar_parser.py`

**Interfaces:**
- Produces: `ParsedCompanyData.shares_rescaled: int = 0` (new last field, default keeps every other adapter unchanged).
- Produces: `_rescale_shares_diluted(ticker: str, rows: list[dict[str, Any]]) -> int` — mutates `rows` in place, returns the number of corrections.
- `parse_company_facts` calls it on `annual_rows` and sets `shares_rescaled` on the returned object.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_sec_edgar_parser.py`. Build facts with a helper that emits one `WeightedAverageNumberOfDilutedSharesOutstanding` 10-K duration entry (`start` = end − 364 days, `form` "10-K", `filed` after `end`) per `(end_year, val)`, unit `"shares"`, plus a `Revenues` entry per year so rows exist.
  - `test_shares_scaled_in_millions_are_rescaled`: years 2019–2023 with 750.1e6, 741.3e6, 751.8e6, 732.3, 721.9 → after parse, by fiscal_year the last two are `pytest.approx(732_300_000)` and `pytest.approx(721_900_000)`, the first three unchanged; `parsed.shares_rescaled == 2`; `capture_logs()` holds exactly two events `sec_edgar.shares_rescaled` with `log_level == "warning"`, `ticker == "MCD"`, `factor == 1_000_000`, `original` 732.3 / 721.9 and their fiscal_year.
  - `test_shares_scaled_in_thousands_are_rescaled`: 750_100_000 ×3 years then 741_300.0 → last becomes `741_300_000`, factor `1_000`.
  - `test_share_split_is_left_unchanged`: 3.0e9, 3.0e9, 3.0e9, 3.0e8, 3.0e8 → all unchanged, `shares_rescaled == 0`.
  - `test_value_15000x_off_is_left_unchanged`: 750e6 ×4 then 50_000.0 → unchanged, count 0.
  - `test_fewer_than_three_other_years_no_correction`: 750.1e6, 741.3e6, 732.3 → unchanged, count 0.
  - `test_majority_misscaled_never_inflates_correct_values`: 750.1e6, 741.3e6, 732.3, 721.9, 716.4 → the two correct values unchanged (and no row ends above 1e12). The three small ones each have `r` ≈ 5.06e5–5.17e5 (median of others = mean of one correct and one mis-scaled value), inside the inclusive ×1e6 band, so assert they become `732_300_000`, `721_900_000`, `716_400_000` — the test pins this near-the-edge behaviour on purpose.
  - `test_none_and_zero_shares_are_ignored`: 750e6 ×4, one year with no share fact (None) and one with `0.0` → None stays None, 0.0 stays 0.0, count 0.

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_sec_edgar_parser.py -q -k shares`
Expected: FAIL (`shares_rescaled` attribute missing / values unchanged).

- [ ] **Step 3: Implement** `ParsedCompanyData.shares_rescaled` and `_rescale_shares_diluted` per the Global Constraints. Use `statistics.median`. Snapshot the original values before mutating anything. Factor constants as module-level `_SHARE_SCALE_FACTORS = (1_000_000, 1_000)` (checked in that order) and `_MIN_SHARE_COMPARATORS = 3`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/unit/test_sec_edgar_parser.py -q`
Expected: PASS (whole file, existing tests included).

- [ ] **Step 5: Commit** — `feat(#124): rescale mis-scaled EDGAR diluted share counts`

### Task 2: Count corrections in the import log

**Files:**
- Modify: `src/bot/ingest/sec_edgar.py` (`import_company_from_sec` details)
- Modify: `src/bot/ingest/edgar_base.py` (`_restamp` carries `shares_rescaled`)
- Modify: `src/bot/ingest/universe.py` (`import_company` details)
- Test: `tests/unit/test_edgar_stooq_provider.py`, `tests/unit/test_universe*.py` or `tests/integration/test_sec_edgar_import.py` — whichever file already tests each function; follow its stubbing style.

**Interfaces:**
- Consumes: `ParsedCompanyData.shares_rescaled` (Task 1).
- Produces: `refresh_log.details["shares_rescaled"]: int` on successful runs of both importers.

- [ ] **Step 1: Write the failing tests**
  - `test_import_company_from_sec_records_shares_rescaled`: monkeypatch `parse_company_facts` (or the client fetch) so the parse yields `shares_rescaled=2`; assert `result.details["shares_rescaled"] == 2` and the `refresh_log` row's details JSON carries it.
  - `test_restamp_keeps_shares_rescaled`: `EdgarProviderBase._restamp` (via an `EdgarStooqProvider` instance) on a `ParsedCompanyData(..., shares_rescaled=3)` returns `shares_rescaled == 3`; `fundamentals()` bundle's `annual.shares_rescaled == 3`.
  - `test_import_company_records_shares_rescaled`: `universe.import_company` with a fake provider whose bundle's `annual.shares_rescaled == 1` → `result.details["shares_rescaled"] == 1`.
- [ ] **Step 2: Run them to verify they fail** — `uv run pytest -q -k shares_rescaled` → FAIL (KeyError / 0).
- [ ] **Step 3: Implement** — add `"shares_rescaled": parsed.shares_rescaled` to `import_company_from_sec` details and `"shares_rescaled": bundle.annual.shares_rescaled` to `universe.import_company` details; pass `shares_rescaled=parsed.shares_rescaled` in `_restamp`.
- [ ] **Step 4: Run** `uv run pytest -q -k "shares_rescaled or sec_edgar or universe or edgar_stooq"` → PASS.
- [ ] **Step 5: Commit** — `feat(#124): count share rescales in refresh_log details`

### Task 3: Valuator guard on implausible share counts

**Files:**
- Modify: `src/bot/valuator/analysis.py` (`analyze`, next to the "missing/non-positive diluted shares" check; module constants `MIN_PLAUSIBLE_SHARES = 1_000_000.0`, `MAX_PLAUSIBLE_SHARES = 100_000_000_000.0`)
- Modify (fixtures only): every test seeding `financials_annual` / `ValuationInput` for `analyze` with shares below 1e6 — today `tests/unit/test_cli_analyze.py`, `test_valuator_analysis.py`, `test_reporting_analysis.py`, `test_screener_engine.py`, `test_cli_site.py`, `test_damodaran_derived.py` (27 tests fail when the guard is added).
- Test: `tests/unit/test_valuator_analysis.py`, `tests/unit/test_cli_analyze.py`

**Interfaces:**
- Produces: `ValueError` from `analyze` with the message in Global Constraints.

- [ ] **Step 1: Write the failing tests**
  - `test_analyze_refuses_implausible_share_count` (parametrised over `732.3`, `999_999.0`, `100_000_000_001.0`): seed a company whose latest `shares_diluted` is the value → `pytest.raises(ValueError, match="implausible diluted share count")`.
  - `test_analyze_accepts_share_count_at_bounds` (parametrised `1_000_000.0`, `100_000_000_000.0`): does not raise.
  - `test_analyze_refuses_implausible_shares_and_continues_batch` in `test_cli_analyze.py`: seed `MCD` with latest `shares_diluted = 732.3` and `AAPL` normal; `bot analyze MCD AAPL` → `exit_code == 1`, stderr/output contains `MCD: cannot value` and `implausible diluted share count`, `AAPL.md` written, no `MCD.md`.
- [ ] **Step 2: Run them to verify they fail** — `uv run pytest -q -k implausible` → FAIL.
- [ ] **Step 3: Implement the guard** after the non-positive check, before `Financials(...)`.
- [ ] **Step 4: Fix fixtures.** Money is formatted with B/M breakpoints (`src/bot/reporting/analysis_report.py:59`), so a printed amount may change suffix as well as magnitude; that is the only kind of assertion edit allowed. Run `uv run pytest -q`; for each test failing on the new error, scale that fixture's monetary columns **and** `shares_diluted` by the same factor (`1_000` or `1_000_000`) so per-share values, margins and ratios are unchanged. Only absolute-money assertions (enterprise value, net debt, revenue as printed) may change, by the same factor; per-share and ratio assertions must not be edited. Never weaken an assertion.
- [ ] **Step 5: Run** `uv run pytest -q` → all green.
- [ ] **Step 6: Commit** — `feat(#124): refuse to value implausible diluted share counts`

### Task 4: Docs and full verification

**Files:**
- Modify: `CONTEXT.md` only if a domain term is added (none expected).
- Run: `python3 docs/plano/build.py`, `python3 docs/leccion/check.py`.

- [ ] **Step 1:** `python3 docs/plano/build.py && python3 docs/leccion/check.py` → both succeed (no stale symbol). Commit regenerated output if it changed.
- [ ] **Step 2:** `uv run ruff check . && uv run mypy src && uv run pytest -q` → green.
- [ ] **Step 3: Manual verification (live network, not CI):** `bot refresh --fundamentals --force` (with MCD in the universe) then `bot analyze MCD` → intrinsic value per share within 10× of price and the JSON sidecar written. Record the outcome in the PR description.

## Grilling

- Rounds: 1 (griller model: fable). The plan changed only by clarification, so no second round.
- Questions: 15. Sources: ISSUE 8 (Q1, Q3 rule, Q4, Q12, Q13, Q2 the force refresh, Q14 criteria), CODE 11 (Q2 `upsert_financials_annual` deletes then inserts per ticker `sec_edgar.py:523-541`; `scripts/weekly.sh:24-26`; Q5 `analysis_report.py:59`; Q6 `FINANCIALS_QUARTERLY_COLS` has no `shares_diluted`, only `financials_annual` is read `screener/engine.py:265`, `valuator/analysis.py:183`; Q7 `analysis.py:641-642`, `cli.py:470-475`, `cli.py:443-445`; Q8 `_label_rows` keys one row per fiscal_year `sec_edgar.py:282-314`; Q9 constructors `edgar_base.py:138`, `fmp.py:573`, `tests/fake_provider.py:18`; Q10 `tests/integration/test_e2e_edgar_stooq.py:40`, `tests/unit/test_sec_edgar_importer.py:43`; Q11 `tests/unit/test_sec_edgar_parser.py:384`; Q15 `cli.py:474`), DOC 1 (Q14 `docs/leccion/README.md`: check.py fails when a cited symbol vanishes; `CONTEXT.md` "Working with the plans"). Some questions cite more than one source type.
- Assumptions: see `## Assumptions` (6).
- Spec ambiguities: none. Issues opened: none.
- Note (Q2): existing databases keep MCD's `732.3` until a forced re-import (`bot refresh --fundamentals --force`, from #122); until then the guard refuses MCD, which is the issue's chosen policy. The weekly `refresh --all` skips tickers with no newer filing, so the forced refresh is an operator step, done here as manual verification.
