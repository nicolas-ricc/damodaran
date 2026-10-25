# EDGAR per-period concept resolution Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `subagent-driven-development` (`.agents/skills/`), with `test-driven-development` for new code. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolve each `ANNUAL_CONCEPT_MAP` column's XBRL concept per period instead of per column, so a company that switches revenue concepts mid-series (BBY: `SalesRevenueNet` through 2018-02-03, `Revenues` after) keeps a value for every year. Log how many annual rows still lack revenue after each import.

**Architecture:** `_collect_period_rows` in `src/bot/ingest/sec_edgar.py` loses its `break  # found a concept with data`. For each column it walks the concepts in list order. Each concept fills only the period ends that no earlier concept has filled yet, and inside one concept the latest filing still wins. The same function builds the quarterly rows, so the quarterly table changes with it. Both importers (`import_company_from_sec` and `bot.ingest.universe.import_company`) add an `annual_revenue_null` count to `run.details` and emit a structlog event.

**Tech Stack:** Python 3, duckdb, structlog, pytest, mypy --strict, ruff.

**Spec:** GitHub issue #123 (nicolas-ricc/damodaran), "EDGAR import picks one revenue concept for all years and accepts stray short-period facts". Builds on #122 (merged, plan `docs/plans/2026-10-25-122-edgar-period-attribution.md`).

## Global Constraints

- Priority = list order in `ANNUAL_CONCEPT_MAP[column]`. For each accepted period, the value comes from the first concept that has an accepted fact for that period.
- Revenue list becomes exactly: `Revenues`, `RevenueFromContractWithCustomerExcludingAssessedTax`, `SalesRevenueNet`, `RevenueFromContractWithCustomerIncludingAssessedTax`, `SalesRevenueGoodsNet`.
- Duration windows from #122 are unchanged: annual 350–380 days, quarterly 80–100 days. A fact outside its window does not count as "having a fact" for that period.
- Within the winning concept the #122 tie-break is unchanged: latest `filed` wins, then latest `accn`.
- Instant facts (phase b) follow the same per-period rule and still attach only to existing period ends.
- `is_restated` and `_first_fy_fp` for a period are computed only from facts that were actually used for that period. A losing concept's `/A` fact does not mark the row restated.
- Type hints everywhere (`mypy --strict`). `uv run ruff check . && uv run mypy src && uv run pytest -q` must be green.
- Commits: Conventional Commits with the `(#123)` scope.

## Review Focus

1. Same column, same period end, two concepts: the higher-priority concept wins even when the lower one was filed later. Test in Task 1.
2. A `/A` fact under a losing concept must not flip `is_restated` on the row. Test in Task 1.
3. A quarter where the first concept has only a 181-day YTD fact and the second has a 91-day quarter fact: the quarter gets the second concept's value. Test in Task 1.
4. A period end that only a lower-priority concept reports must still create a row (row creation is per period, not per winning concept). The X/Y test in Task 1 covers this for 2014–2016.
5. An import whose annual rows all carry revenue reports `annual_revenue_null == 0`. The key must not be missing, and zero annual rows also gives 0. Test in Task 2.

---

### Task 1: Per-period concept resolution (annual + quarterly) and extended revenue list

**Files:**
- Modify: `src/bot/ingest/sec_edgar.py` (`ANNUAL_CONCEPT_MAP` and its comment, `_collect_period_rows` phases a and b, docstring)
- Test: `tests/unit/test_sec_edgar_parser.py` (reuse the `_fact`, `_facts`, `_annual`, `_quarterly` helpers)

**Interfaces:**
- Produces: no signature changes. `_collect_period_rows(ticker, us_gaap, *, span_days, allowed_forms, row_cols=None) -> dict[date, dict[str, Any]]` keeps its contract; only the resolution rule changes.

- [ ] **Step 1: Write the failing tests** (stage-3 evals; they may already be committed as `test(#123): evals`)

```python
def test_concept_resolved_per_period_higher_priority_wins_overlap() -> None:
    # Revenues (X) annual facts ending 2017-12-31, 2018-12-31; SalesRevenueNet (Y) 2014..2016 and 2017 (overlap, different value)
    annual = _annual(facts)
    assert sorted(annual) == [2014, 2015, 2016, 2017, 2018]
    assert all(annual[y]["revenue"] is not None for y in annual)
    assert annual[2017]["revenue"] == <X value>   # X wins the overlap

def test_short_fact_under_first_concept_does_not_block_second() -> None:
    # Revenues: 2011-01-01..2011-01-31 = 249e6 (10-K); SalesRevenueNet: 2010-02-28..2011-02-26 = 49_694e6
    annual = _annual(facts)
    assert sorted(annual) == [2011]
    assert annual[2011]["revenue"] == 49_694_000_000

def test_higher_priority_concept_wins_even_if_lower_filed_later() -> None: ...
def test_losing_concept_amendment_does_not_mark_restated() -> None:
    # Revenues 10-K + SalesRevenueNet 10-K/A same period -> is_restated is False, revenue from Revenues

def test_quarterly_concept_resolved_per_period() -> None:
    # Revenues: 181-day YTD 10-Q fact ending 2025-06-30 only; SalesRevenueNet: 91-day fact ending 2025-06-30
    # plus Revenues 91-day fact ending 2025-03-31 -> both quarters have revenue, Q2 from SalesRevenueNet

def test_new_revenue_concepts_used_only_after_existing_three() -> None:
    # RevenueFromContractWithCustomerIncludingAssessedTax alone -> used; with SalesRevenueNet same period -> SalesRevenueNet wins
    # SalesRevenueGoodsNet alone -> used

def test_instant_concept_resolved_per_period() -> None:
    # LongTermDebt instants for 2024-12-31 only, LongTermDebtNoncurrent for 2025-12-31 and 2024-12-31, two duration rows
    # -> 2024 from LongTermDebt, 2025 from LongTermDebtNoncurrent

def test_bby_shaped_series_has_revenue_every_year_from_2009() -> None:
    # SalesRevenueNet annual facts for fiscal years ending 2009-02-28 .. 2018-02-03 (Best Buy calendar);
    # Revenues annual facts ending 2017-01-28, 2018-02-03 (equal values) and 2019-02-02 .. 2025-02-01;
    # stray Revenues one-month facts 2011-01-01..2011-01-31 (249e6) and 2012-01-01..2012-01-31 (189e6) in a 10-K.
    annual = _annual(facts)
    assert sorted(annual) == list(range(2009, 2026))
    assert all(r["revenue"] is not None and r["revenue"] >= 1_000_000_000 for r in annual.values())
```

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_sec_edgar_parser.py -q`. Expected: the new tests FAIL and every pre-existing test passes.

- [ ] **Step 3: Implement.** Extend the revenue list (Global Constraints). In phase a, for each column keep a `resolved: set[date]` of ends already filled by an earlier concept. For each concept, take its accepted in-window duration facts whose `end` is not in `resolved`, and apply them exactly as today: overwrite in (filed, accn) order, update `row_ends`, `forms_seen` and `first_seen`. Then add those ends to `resolved`. Remove the `break`. A column is a "duration column" if any concept gave it at least one accepted duration fact. Phase b does the same with instants over `row_ends`, for columns that are not duration columns. Rewrite the `ANNUAL_CONCEPT_MAP` comment to say "first concept with an accepted fact for that period".

- [ ] **Step 4: Run** `uv run pytest tests/unit/test_sec_edgar_parser.py -q`. Expected: all PASS.

- [ ] **Step 5: Commit** `fix(#123): resolve EDGAR concepts per period`

### Task 2: Log remaining NULL-revenue annual periods per import

**Files:**
- Modify: `src/bot/ingest/sec_edgar.py` (`import_company_from_sec`), `src/bot/ingest/universe.py` (`import_company`)
- Test: `tests/unit/test_sec_edgar_importer.py`, and a new `tests/unit/test_universe_import_company.py` using `tests/fake_provider.FakeProvider`

**Interfaces:**
- Produces: `count_null_revenue(rows: list[dict[str, Any]]) -> int` in `bot.ingest.sec_edgar`. Both importers call it on the annual rows they upsert. They set `run.details["annual_revenue_null"]` to that count and emit `log.info("ingest.annual_revenue_null", ticker=sym, source=<provider/source name>, annual_revenue_null=n, annual=<annual row count>)`.

- [ ] **Step 1: Write the failing tests**

```python
def test_import_company_from_sec_reports_null_revenue_count() -> None:
    # facts with two annual periods, one with Revenues, one with only NetIncomeLoss; real in-memory duckdb + apply_schema
    result = import_company_from_sec(conn, ticker="AAPL", user_agent="x a@b.c")  # client methods patched
    assert result.details["annual_revenue_null"] == 1
    # capture_logs: one event "ingest.annual_revenue_null" with annual_revenue_null == 1

def test_import_company_reports_null_revenue_count() -> None:   # universe.import_company + FakeProvider bundle
    assert result.details["annual_revenue_null"] == 1

def test_import_company_reports_zero_when_no_annual_rows() -> None:
    assert result.details["annual_revenue_null"] == 0
```

- [ ] **Step 2: Run** the two test files. Expected: FAIL with `KeyError: 'annual_revenue_null'`.
- [ ] **Step 3: Implement** `count_null_revenue` and wire it into both importers. Add it to the final `run.details` dict, which keeps its existing keys.
- [ ] **Step 4: Run** `uv run ruff check . && uv run mypy src && uv run pytest -q`. Expected: all green.
- [ ] **Step 5: Commit** `feat(#123): log annual periods still missing revenue`

## Manual verification (not automatable here)

- `bot refresh --fundamentals --force` against live EDGAR: BBY has non-NULL revenue on every annual row from 2009 on, and no row is below 1e9. The sandbox gets HTTP 403 from data.sec.gov, so `test_bby_shaped_series_has_revenue_every_year_from_2009` stands in for this check, using the period layout described in the issue.

## Assumptions

- **A1. Keying on `end` alone stays.** `_label_rows` collapses two annual ends in one calendar year: it keeps the later one and logs `sec_edgar.fiscal_year_collision`. A concept switch that coincides with a fiscal-year-end shift therefore gets the same handling #122 defined (`src/bot/ingest/sec_edgar.py` `_label_rows`). Rejected alternative: matching periods across concepts by a fuzzy window, which neither issue asks for.
- **A2. The duration-column rule stays.** If any concept gave a column a duration fact, phase b skips that column's instants. This keeps today's `duration_cols` rule (`sec_edgar.py` phase b, `if db_col in duration_cols: continue`). No column in the map mixes duration and instant concepts. Rejected alternative: falling back from durations to instants per period.
- **A3. `is_restated` follows the facts used.** Inside the winning concept for a period, every accepted fact's form still counts, as #122 decided (`test_is_restated_true_when_amendment_in_history_even_if_later_10k_wins`). Facts from losing concepts do not count. Rejected alternative: counting every concept, which would mark rows restated because of data that was never used.
- **A4. `row_ends` is the union across all columns,** as it is today (`sec_edgar.py`, the `row_ends` set built in phase a). An instant concept for column C attaches at any end that a duration fact of any column created.
- **A5. The count includes FMP imports.** The NULL-revenue count also runs for non-EDGAR providers through `universe.import_company`. FMP rows use the same `revenue` key (`src/bot/ingest/fmp.py:440`). Rejected alternative: counting only for EDGAR, which would need provider-specific branching in a generic importer.

## Grilling

- Rounds: 1. Questions: 16. Griller model: fable.
- Sources: ISSUE 6 (Q1, Q2, Q4, Q7 and Q15 via the acceptance criteria, Q9 partly), CODE 8 (Q5, Q9, Q10, Q11, Q12, Q13, Q16, Q6), DOC 1 (Q14, AGENTS.md), NO SOURCE resolved as technical assumptions 4 (A1 for Q3, A2 for Q5, A3 for Q6, A4 for Q16). Q8 is procedural: the stage-3 evals do not exist yet and will replace the `<X value>` placeholder with concrete values.
- Spec ambiguities: none. Follow-up issues opened: none.
- Q9 is answered by the code: `upsert_financials_annual` and `upsert_financials_quarterly` delete every row of the ticker before inserting, so a re-import fully replaces the old rows. Old data only changes after `bot refresh --fundamentals --force` (#122). That is the PR's manual verification step.
