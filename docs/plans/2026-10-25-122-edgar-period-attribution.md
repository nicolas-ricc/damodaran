# EDGAR period attribution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Attribute every SEC `companyfacts` fact to its own `start`/`end` period instead of the filing's `fy`/`fp`, so `financials_annual` / `financials_quarterly` stop shifting two years back, and add `bot refresh --fundamentals --force` to re-import every ticker.

**Architecture:** `_collect_period_rows` in `src/bot/ingest/sec_edgar.py` is rewritten to key rows by the fact's period `end` date, accepting duration facts only inside a span window (annual 350–380 days, quarterly 80–100 days) and attaching instant facts (no `start`) to the row with the same `end`. `fiscal_year` becomes the calendar year of the period end; the quarterly table derives `fiscal_quarter` from the neighbouring annual period ends. `refresh_universe` gains a `force` flag that bypasses `_should_skip`.

**Tech Stack:** Python 3, typer CLI, duckdb, pytest, mypy --strict, ruff.

**Spec:** GitHub issue #122 (nicolas-ricc/damodaran), "EDGAR import attributes facts to the filing's fiscal year, shifting every annual series two years back".

## Global Constraints

- Annual duration window: `350 <= (end - start).days <= 380`. Quarterly duration window: `80 <= (end - start).days <= 100`. Inclusive on both ends.
- `fiscal_year` = calendar year of the period `end` date (annual rows). Do **not** use `frame`.
- Tie-break among accepted facts for the same column and the same period: latest `filed` wins; on equal `filed`, latest `accn` wins. Sort before iterating; result must not depend on API order.
- Form filters unchanged: `10-K`/`10-K/A` annual, `10-Q`/`10-Q/A` quarterly. `is_restated` = any accepted fact of the row came from a `/A` form.
- Concept fallback per column stays as today (first concept in `ANNUAL_CONCEPT_MAP[column]` that yields any *accepted* fact wins for every period). Per-period fallback is #123, not this issue.
- Facts have fields `accn, end, filed, form, fp, frame, fy, start, val`; there is no `decimals`.
- Type hints everywhere (`mypy --strict`); `uv run ruff check . && uv run mypy src && uv run pytest -q` green.
- Commits: Conventional Commits with `(#122)` scope.

## Review Focus

1. Two accepted annual periods whose `end` falls in the same calendar year (fiscal-year-end change, e.g. ends 2014-02-01 and 2014-12-31) would collide on the PK `(ticker, fiscal_year, is_restated)`: keep the row with the later `end`, log `sec_edgar.fiscal_year_collision` warning. Test in Task 1.
2. The in-progress fiscal year (quarters after the newest 10-K) has no annual period containing it: AAPL's quarter ending 2025-12-27 must become `(fiscal_year=2026, fiscal_quarter=1)`, not collide with the quarter ending 2024-12-28 `(2025, 1)`. Test in Task 2.
3. An instant fact whose `end` matches no accepted duration row (e.g. prior-year balance in a 10-Q) is dropped, never creates a row with only balance-sheet columns. Test in Task 1 (annual) and Task 2 (quarterly).
4. A 335-day transition period is rejected for annual. Test in Task 1.
5. Entries missing `end`, `val`, or with unparseable dates are skipped, not raising. Test in Task 1.

---

### Task 1: Annual period attribution

**Files:**
- Modify: `src/bot/ingest/sec_edgar.py:222-334` (`parse_company_facts`, `_collect_period_rows`)
- Test: `tests/unit/test_sec_edgar_parser.py`

**Interfaces:**
- Produces:
  - `ANNUAL_SPAN_DAYS: tuple[int, int] = (350, 380)` and `QUARTERLY_SPAN_DAYS: tuple[int, int] = (80, 100)` module constants.
  - `_collect_period_rows(ticker: str, us_gaap: dict[str, Any], *, span_days: tuple[int, int], allowed_forms: set[str]) -> dict[date, dict[str, Any]]` — rows keyed by period `end` (a `datetime.date`); each row carries the DB columns, `period_end_date` (ISO string, the key), `is_restated`, `ticker`, `currency`, `source`, and the derived fields (`_derive_financial_fields`). No `fiscal_year` yet: callers stamp it. A row exists only if at least one accepted **duration** fact has that `end`.
  - `parse_company_facts` keeps its signature; annual rows get `fiscal_year = end.year`.

- [ ] **Step 1: Update `FAKE_FACTS` and `FAKE_FACTS_RESTATEMENT`** — add `start` to every duration fact (Revenues, NetIncomeLoss): FY2023 `start="2022-09-25"` end 2023-09-30; FY2022 `start="2021-09-26"` end 2022-09-30; Q2 2024 `start="2023-12-31"` end 2024-03-30. `Assets` stays instant (no `start`). Add `accn` values. Existing assertions unchanged.

- [ ] **Step 2: Write the failing tests** (hand-built facts, `FAKE_FACTS` style)

```python
def test_mcd_shape_three_comparatives_in_one_10k():
    # one 10-K, accn "0000063908-26-000010", filed "2026-02-20", fy=2025 fp=FY, listed oldest first:
    # 2023-01-01..2023-12-31 25_494e6, 2024-01-01..2024-12-31 25_920e6, 2025-01-01..2025-12-31 26_885e6
    annual = {r["fiscal_year"]: r for r in parse_company_facts("MCD", facts).annual}
    assert sorted(annual) == [2023, 2024, 2025]
    assert annual[2025]["revenue"] == 26_885_000_000
    assert annual[2023]["revenue"] == 25_494_000_000
    assert annual[2025]["period_end_date"] == "2025-12-31"

def test_quarter_length_fy_fact_never_lands_in_annual():
    # 10-K, fp=FY, 2025-10-01..2025-12-31 (91 days) only -> annual == []

def test_transition_period_of_335_days_rejected():   # -> annual == []

def test_instant_fact_attaches_to_annual_row_with_same_end():
    # Revenues 2025-01-01..2025-12-31 + Assets (no start) end 2025-12-31 -> row[2025]["total_assets"] set

def test_instant_fact_without_matching_duration_row_is_dropped():
    # Assets end 2024-12-31 only, revenue only for 2025 -> one row, 2025, total_assets is None/absent

def test_52_53_week_year_of_371_days_accepted():
    # 2013-01-27..2014-02-02 (371 days) -> one annual row, fiscal_year 2014

def test_january_year_end_is_fiscal_year_of_end():
    # BBY 2013-02-03..2014-02-01, frame "CY2013", fy 2014 -> fiscal_year == 2014

def test_later_filed_wins_regardless_of_list_order():
    # same period in two 10-Ks: filed 2025-02-20 val A and filed 2026-02-20 val B
    # assert B wins with list order [new, old] and [old, new]

def test_equal_filed_latest_accn_wins():
    # same period, same filed, accn "...-26-000010" val A and "...-26-000011" val B -> B, both orders

def test_fiscal_year_collision_keeps_later_end(caplog or structlog capture):
    # accepted periods ending 2014-02-01 and 2014-12-31 -> one 2014 row with period_end_date "2014-12-31"

def test_malformed_entries_are_skipped():
    # entries missing end / val / with start "not-a-date" alongside one valid fact -> one row, no raise
```

- [ ] **Step 3: Run tests to verify they fail** — `uv run pytest tests/unit/test_sec_edgar_parser.py -q`; expected: the new tests FAIL (MCD returns 2025=25,494M), existing tests PASS.

- [ ] **Step 4: Implement** — In `_collect_period_rows`: for each column/concept, filter entries by form, parse `start`/`end` with `coerce_date` (from `bot.ingest.base`), classify duration (`start` present) vs instant; keep duration entries inside `span_days`; sort accepted entries by `(filed, accn)` ascending and let later ones overwrite the slot keyed `(end, db_col)`. A concept counts as "found" when it produced any accepted entry (duration or instant). After all columns: rows = ends with ≥1 duration fact; attach instant values for the same end; drop instant-only ends. `is_restated` = any accepted fact used for that row (duration or attached instant) had a form ending `/A` — track all accepted forms per `end`, not only winners (preserves `test_is_restated_true_when_amendment_in_history_even_if_later_10k_wins`). In `parse_company_facts`: stamp `fiscal_year = end.year`; on collision keep the later `end` and `log.warning("sec_edgar.fiscal_year_collision", ticker=..., fiscal_year=..., kept=..., dropped=...)`.

- [ ] **Step 5: Run tests to verify they pass** — `uv run pytest tests/unit/test_sec_edgar_parser.py tests/unit/test_sec_edgar_derived.py tests/unit/test_sec_edgar_importer.py -q` all PASS.

- [ ] **Step 6: Commit** — `git commit -m "fix(#122): attribute annual EDGAR facts by their own period"`

### Task 2: Quarterly period attribution and `fiscal_quarter`

**Files:**
- Modify: `src/bot/ingest/sec_edgar.py` (`parse_company_facts`, new `_fiscal_quarter_key`)
- Test: `tests/unit/test_sec_edgar_parser.py`

**Interfaces:**
- Consumes: `_collect_period_rows(..., span_days=QUARTERLY_SPAN_DAYS, allowed_forms={"10-Q", "10-Q/A"})` from Task 1; the annual period ends (keys of the annual dict).
- Produces: `_fiscal_quarter_key(quarter_end: date, annual_ends: list[date], fallback: tuple[int, int] | None) -> tuple[int, int] | None` returning `(fiscal_year, fiscal_quarter)`.

Algorithm for `_fiscal_quarter_key` (all day counts are `(a - b).days`, quarter length 91.3 days):
1. Next annual end `N` = smallest annual end `>= quarter_end` with `N - quarter_end <= 380`: `fiscal_year = N.year`, `fiscal_quarter = 4 - round((N - quarter_end) / 91.3)`.
2. Else previous annual end `P` = largest annual end `< quarter_end` with `quarter_end - P <= 380`: `fiscal_year = P.year + 1`, `fiscal_quarter = round((quarter_end - P) / 91.3)`.
3. Result outside 1..4, or no `N`/`P`: return `fallback` = `(fy, int(fp[1:]))` of the earliest-filed (then lowest `accn`) accepted entry for that quarter end whose `fp` is `Q1`–`Q4`; `None` if no such entry (row dropped).

`fiscal_year` of a quarter is the fiscal year it belongs to (the calendar year of that fiscal year's end), matching the annual rule and how companies label quarters ("Q1 FY2026"). Collision on `(fiscal_year, fiscal_quarter)`: keep later end, `log.warning("sec_edgar.fiscal_quarter_collision", ...)`. `_collect_period_rows` must expose the fallback `(fy, fp)` per end: add `"_first_fy_fp"` to each row (popped before return from `parse_company_facts`).

- [ ] **Step 1: Write the failing tests**

```python
def test_181_day_10q_fact_never_lands_in_quarterly():
    # 10-Q fp=Q2 2025-01-01..2025-06-30 (180 days) only -> quarterly == []

def test_quarter_ordinal_within_calendar_fiscal_year():
    # 10-K 2024-01-01..2024-12-31; 10-Q 2025-01-01..2025-03-31 and 2024-04-01..2024-06-30
    # -> {(2025, 1), (2024, 2)}

def test_in_progress_fiscal_year_quarter_for_september_filer():
    # AAPL: 10-K periods ending 2024-09-28 and 2025-09-27;
    # 10-Q 2024-09-29..2024-12-28 (fy 2025 Q1) and 2025-09-28..2025-12-27 (fy 2026 Q1)
    # -> keys (2025, 1) and (2026, 1), no collision

def test_quarter_without_annual_context_falls_back_to_first_filing_fp():
    # only 10-Qs: 2025-01-01..2025-03-31 first filed fy 2025 fp Q1 -> (2025, 1)

def test_quarterly_instant_attaches_by_end_and_prior_year_end_instant_dropped():
    # 10-Q: revenue 2025-01-01..2025-03-31, Cash end 2025-03-31 and Cash end 2024-12-31
    # -> one quarterly row, cash = the 2025-03-31 value
```

Existing `test_parse_extracts_quarterly` (Q2 ending 2024-03-30, annual end 2023-09-30 in `FAKE_FACTS`) must still yield `(2024, 2)`: rule 2, `round(182/91.3) = 2`.

- [ ] **Step 2: Run tests to verify they fail** — `uv run pytest tests/unit/test_sec_edgar_parser.py -q`.
- [ ] **Step 3: Implement** `_fiscal_quarter_key` and the quarterly branch of `parse_company_facts`.
- [ ] **Step 4: Run tests to verify they pass** — same command, all PASS.
- [ ] **Step 5: Commit** — `git commit -m "fix(#122): attribute quarterly EDGAR facts by their own period"`

### Task 3: `bot refresh --fundamentals --force`

**Files:**
- Modify: `src/bot/ingest/universe.py:314-356` (`refresh_universe`), `:661-684` (`_refresh_one`)
- Modify: `src/bot/cli.py` (`refresh` options; `_refresh_fmp_universe`)
- Test: `tests/unit/test_universe_refresh.py`, `tests/unit/test_cli_refresh_fmp.py`

**Interfaces:**
- Produces: `refresh_universe(..., force: bool = False)`; `_refresh_one(..., force: bool)`; `_refresh_fmp_universe(conn, settings, universe, limit=None, force=False)`; CLI option `force: bool = typer.Option(False, "--force", help="With --fundamentals: re-import every ticker even if its latest filing date has not advanced.")`.

- [ ] **Step 1: Write the failing tests**

```python
def test_force_reimports_ticker_whose_filing_has_not_advanced() -> None:
    # same setup as test_skips_ticker_when_remote_filing_not_advanced, force=True
    assert ("fundamentals", "AAPL") in provider.calls
    assert result.imported == 1 and result.skipped == 0

def test_force_does_not_probe_the_filing_date() -> None:
    # force=True -> no ("latest_filing_date", "AAPL") in provider.calls (check FakeProvider's call label)

def test_refresh_fundamentals_force_is_forwarded(tmp_path, monkeypatch):
    # CliRunner `refresh --fundamentals --force`, patch bot.cli.refresh_universe, assert kwargs["force"] is True
    # and without --force kwargs["force"] is False
```

- [ ] **Step 2: Run to verify fail** — `uv run pytest tests/unit/test_universe_refresh.py tests/unit/test_cli_refresh_fmp.py -q`.
- [ ] **Step 3: Implement** — `_refresh_one` skips the local-date lookup and `_should_skip` when `force`; docstring of `refresh_universe` mentions it. `--force` without `--fundamentals`/`--all` is ignored (documented in help text). Log `universe.refresh.start` unchanged.
- [ ] **Step 4: Run to verify pass.**
- [ ] **Step 5: Commit** — `git commit -m "feat(#122): bot refresh --fundamentals --force"`

### Task 4: Integration check, glossary and plans

**Files:**
- Modify: `tests/integration/test_sec_edgar_import.py`
- Modify: `CONTEXT.md` (Domain language)
- Modify: `README.md` (where `bot refresh --fundamentals` is documented, one line on `--force`)
- Modify: `docs/plano/` / `docs/leccion/` only if their checks fail (`uv run python docs/plano/build.py`, `uv run python docs/leccion/check.py`) or cite changed line numbers.

- [ ] **Step 1: Write the failing assertion** in `test_import_company_from_sec_populates_db`:

```python
newest = conn.execute(
    "SELECT fiscal_year, period_end_date FROM financials_annual "
    "WHERE ticker = 'AAPL' ORDER BY period_end_date DESC LIMIT 1"
).fetchone()
assert newest == (2025, date(2025, 9, 27))  # latest FY end in the committed cassette
```
(It should already pass after Task 1; if run before Task 1 it fails with `fiscal_year` 2026.)

- [ ] **Step 2: Glossary** — add to `CONTEXT.md` Domain language:
  `- **Fiscal year** (`fiscal_year`): the calendar year of the period's end date. An annual row is a duration fact of 350–380 days; Best Buy's year ending 2014-02-01 is fiscal_year 2014. A quarter belongs to the fiscal year it falls in, numbered by its position in it. Never the SEC `fy` field, which names the filing, nor `frame`.`
- [ ] **Step 3: Run** `uv run ruff check . && uv run mypy src && uv run pytest -q` and the plano/leccion checks; all green.
- [ ] **Step 4: Commit** — `git commit -m "docs(#122): define fiscal_year; pin AAPL newest annual period"`
