# Screener second pass: bulk valuation-input loader (#53) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the screener's default second pass value the whole shortlist with a fixed number of DB queries, however long the shortlist is.

**Architecture:** Commit `c0a9f84` already threads a pre-loaded `ValuationInput` through `analyze(company=...)` and `AssumptionInputs` through `resolve_assumptions(db_inputs=...)`, so `analyze` itself issues no queries when handed its rows. The N+1 survives one level up: `_batch_dcf_margins` builds each `ValuationInput` with `load_valuation_input(conn, ticker)`, about eleven queries per ticker. This plan adds two set-based loaders, `bulk_load_assumption_inputs` (assumptions module) and `bulk_load_valuation_inputs` (analysis module), each issuing a constant number of `WHERE ticker IN (...)` / `QUALIFY row_number()` scans. Both the per-ticker and the bulk loaders build their results from the same small pure row-to-value helpers, so the two paths cannot drift. `_batch_dcf_margins` then calls the bulk loader once.

**Tech Stack:** Python 3.12, DuckDB, pytest, mypy `--strict`, ruff.

**Spec:** GitHub issue nicolas-ricc/damodaran#53. Acceptance criteria, verbatim:
- The second pass issues **zero** per-ticker DB queries (assert via a query-counting connection wrapper or loader spy).
- An `analyze(company=<preloaded>)` entry point exists.
- The produced shortlist is byte-identical to the pre-refactor output on a fixture DB (behavior-preserving).

## Global Constraints

- Type hints everywhere; `uv run mypy src` (strict) must pass.
- Loaders stay pure in the project sense: take the connection, read only, no global state (CONTEXT.md, Conventions).
- `uv run ruff check .` must pass.
- Commits follow Conventional Commits and reference `#53`.
- Test suite: `uv run pytest -q`.
- "Zero per-ticker queries" is read as: the number of queries the second pass issues does not depend on the number of shortlisted tickers. A constant handful of set-based scans is allowed; the issue's own proposed fix ("thread a pre-loaded ValuationInput") needs the rows loaded from somewhere.

## Review Focus

1. A shortlisted ticker missing from `companies` or with no non-restated `financials_annual` rows: the bulk loader leaves it out of its result, and `_batch_dcf_margins` maps it to `None` (same as today, where `load_valuation_input` raises `LookupError`).
2. A company whose mapped Damodaran region has no industry row (cross-region fallback): the bulk path picks the same substitute row and still logs `assumptions.sector.cross_region_substitution`. Ties on `year` across regions are broken by `region` ascending in both paths (the per-ticker query had no tiebreak, so it was arbitrary before).
3. A company with no `damodaran_country` row, or `country`/`industry_damodaran` NULL: sector multiples and assumption inputs are all-`None` exactly as the per-ticker path produces.
4. A company with no non-NULL `close` in `prices_daily`: `current_price is None` in both paths.
5. An empty shortlist (`top=0`, or no survivors): the bulk loader returns `{}` and the screen completes.

Each is pinned by the equivalence test in Task 1 or Task 2 (the fixture seeds one company per case) and by Task 3's empty-shortlist test.

## File Structure

- `src/bot/valuator/assumptions.py`: add pure helpers `_growth_path_from_revenues`, `_margins_from_rows`, `_sector_row_from`, `_pick_sector`; rewrite the per-ticker loaders on top of them; add `bulk_load_assumption_inputs`.
- `src/bot/valuator/analysis.py`: add pure helpers `_latest_from_row`, `_histories_from_rows`, `_sector_multiples_from`; rewrite the per-ticker loaders on top of them; add `bulk_load_valuation_inputs`.
- `src/bot/valuator/__init__.py`: export the new public loaders if the module re-exports the per-ticker ones (check first).
- `src/bot/screener/engine.py`: `_batch_dcf_margins` uses `bulk_load_valuation_inputs`.
- `tests/unit/test_valuation_bulk_load.py` (new): bulk-vs-per-ticker equivalence and constant query count, for both loaders.
- `tests/unit/test_screener_engine.py`: second-pass query count independent of the shortlist size; per-ticker loader never called.
- `tests/unit/test_screener_second_pass_golden.py` (new) + `tests/fixtures/screener/second_pass_shortlist.golden` (new): byte-identical shortlist against output captured from the pre-refactor code.

The eval tests above are written in stage 3 (before Task 1) and committed failing; each task below turns its share green.

---

### Task 1: `bulk_load_assumption_inputs`

**Files:**
- Modify: `src/bot/valuator/assumptions.py:281-430`
- Test: `tests/unit/test_valuation_bulk_load.py`

**Interfaces:**
- Produces: `bulk_load_assumption_inputs(conn: duckdb.DuckDBPyConnection, tickers: Iterable[str]) -> dict[str, AssumptionInputs]`, keyed by upper-cased ticker; tickers absent from `companies` are omitted.

- [ ] **Step 1: Tests (from stage 3).** `test_bulk_assumption_inputs_match_per_ticker` seeds the Review Focus fixture (a plain US Software company, a Germany company whose only Software row is US, a company with `country = NULL`, one with `industry_damodaran = NULL`, one with a zero-revenue year, one with a single year of financials, one with no financials, and an unknown ticker) and asserts `bulk_load_assumption_inputs(conn, tickers) == {t: load_assumption_inputs(conn, t) for t in known}`. `test_bulk_assumption_inputs_query_count_is_constant` wraps the connection in a counting proxy and asserts the count for one ticker equals the count for all of them.

- [ ] **Step 2: Run, expect ImportError.** `uv run pytest tests/unit/test_valuation_bulk_load.py -q -k assumption`

- [ ] **Step 3: Extract pure helpers and rewrite the per-ticker loaders on them.**

```python
def _growth_path_from_revenues(revenues: Sequence[float]) -> tuple[float, ...] | None:
    if len(revenues) < 2:
        return None
    growths = [(curr - prev) / prev for prev, curr in itertools.pairwise(revenues) if prev != 0.0]
    if not growths:
        return None
    return (fmean(growths),) * _HORIZON


def _margins_from_rows(rows: Iterable[tuple[Any, Any]]) -> tuple[float, ...]:
    """``rows`` are ``(ebit, revenue)`` pairs, oldest first."""
    return tuple(float(e) / float(r) for e, r in rows if e is not None and r is not None and r != 0.0)


def _pick_sector(
    industry: str | None,
    region: str | None,
    exact: _SectorRow | None,
    fallback: tuple[_SectorRow, str] | None,
) -> tuple[_SectorRow | None, bool]:
    """Exact-region row, else the latest row for ``industry`` in any region (logged)."""
```

`_historical_growth_path` becomes a query plus `_growth_path_from_revenues`; `_operating_margin_history` a query plus `_margins_from_rows`; `_load_sector_with_fallback` loads `exact` and (only when `exact is None and industry is not None`) the fallback row, then returns `_pick_sector(...)`, which emits the existing `log.warning`. Add `, region` to the fallback query's `ORDER BY year DESC` so ties are deterministic.

- [ ] **Step 4: Add the bulk loader.** Four queries, whatever the ticker count; an empty ticker list returns `{}` without querying.

```python
def bulk_load_assumption_inputs(
    conn: duckdb.DuckDBPyConnection, tickers: Iterable[str]
) -> dict[str, AssumptionInputs]:
    wanted = sorted({t.upper() for t in tickers})
    if not wanted:
        return {}
    companies = {
        t: _Company(country=c, industry_damodaran=i)
        for t, c, i in conn.execute(
            "SELECT ticker, country, industry_damodaran FROM companies "
            "WHERE ticker IN (SELECT unnest(?::VARCHAR[]))",
            [wanted],
        ).fetchall()
    }
    countries = sorted({c.country for c in companies.values() if c.country is not None})
    country_rows = {
        r[0]: _CountryRow(region=r[1], risk_free_rate=r[2], erp=r[3], tax_rate=r[4])
        for r in conn.execute(
            "SELECT country, region, risk_free_rate, erp, tax_rate FROM damodaran_country "
            "WHERE country IN (SELECT unnest(?::VARCHAR[])) "
            "QUALIFY row_number() OVER (PARTITION BY country ORDER BY year DESC) = 1",
            [countries],
        ).fetchall()
    }
    industries = sorted({c.industry_damodaran for c in companies.values() if c.industry_damodaran})
    exact: dict[tuple[str, str], _SectorRow] = {}
    fallback: dict[str, tuple[_SectorRow, str]] = {}
    for industry, region, *values in conn.execute(
        "SELECT industry, region, wacc, cost_of_equity, cost_of_debt, op_margin, "
        "sales_to_capital, tax_rate, debt_to_equity FROM damodaran_industry "
        "WHERE industry IN (SELECT unnest(?::VARCHAR[])) "
        "ORDER BY industry, year DESC, region",
        [industries],
    ).fetchall():
        row = _SectorRow(*values)
        exact.setdefault((industry, region), row)
        fallback.setdefault(industry, (row, region))
    history: dict[str, list[tuple[Any, Any]]] = {}
    for ticker, revenue, ebit in conn.execute(
        "SELECT ticker, revenue, ebit FROM financials_annual "
        "WHERE ticker IN (SELECT unnest(?::VARCHAR[])) AND is_restated = FALSE "
        "ORDER BY ticker, fiscal_year",
        [wanted],
    ).fetchall():
        history.setdefault(ticker, []).append((revenue, ebit))
    ...  # per company: region via dataset_region, _pick_sector, the two pure helpers
```

The first row seen per `(industry, region)` in `year DESC` order is the latest one, and the first per `industry` in `year DESC, region` order matches the per-ticker fallback's new tiebreak.

- [ ] **Step 5: Run the tests and the existing assumptions tests.** `uv run pytest tests/unit/test_valuation_bulk_load.py tests/unit -q -k "assumption"`: expect PASS.

- [ ] **Step 6: Commit.** `feat(#53): bulk_load_assumption_inputs set-based loader`

### Task 2: `bulk_load_valuation_inputs`

**Files:**
- Modify: `src/bot/valuator/analysis.py:132-315`
- Test: `tests/unit/test_valuation_bulk_load.py`

**Interfaces:**
- Consumes: `bulk_load_assumption_inputs` (Task 1).
- Produces: `bulk_load_valuation_inputs(conn: duckdb.DuckDBPyConnection, tickers: Iterable[str]) -> dict[str, ValuationInput]`, keyed by upper-cased ticker; tickers absent from `companies` or with no non-restated annual financials are omitted (the cases where `load_valuation_input` raises `LookupError`).

- [ ] **Step 1: Tests (from stage 3).** `test_bulk_valuation_inputs_match_per_ticker` uses the same fixture plus a company with no price row and a company whose latest price row has `close = NULL`, and asserts equality with `{t: load_valuation_input(conn, t) for t in valuable}`; the unknown and no-financials tickers are absent from the result. `test_bulk_valuation_inputs_query_count_is_constant` compares the counting-proxy total for one ticker and for all of them.

- [ ] **Step 2: Run, expect ImportError.** `uv run pytest tests/unit/test_valuation_bulk_load.py -q -k valuation`

- [ ] **Step 3: Extract pure helpers and rewrite the per-ticker loaders on them.**

```python
def _latest_from_row(row: tuple[Any, ...]) -> _LatestFinancials:
    """``row`` is ``(revenue, ebit, net_income, interest_expense, total_debt, cash, shares_diluted, total_equity)``."""

def _histories_from_rows(
    rows: Iterable[tuple[Any, Any, Any]],
) -> tuple[tuple[float, ...], tuple[float, ...], tuple[float, ...]]:
    """``rows`` are ``(revenue, net_income, ebit)``, oldest first."""

def _sector_multiples_from(
    company: _CompanyRow,
    country_row: tuple[Any, Any] | None,
    sector_row: tuple[Any, ...] | None,
) -> _SectorMultiples:
    """``country_row`` is ``(region, erp)``; ``sector_row`` is ``(pe, ev_sales, op_margin, beta_levered)``."""
```

`_load_latest_financials`, `_load_history` and `_load_sector_multiples` keep their queries and delegate the shaping to these helpers. `_load_sector_multiples` must still issue the industry query only when `industry_damodaran` and the dataset region are both known.

- [ ] **Step 4: Add the bulk loader.** Queries: `companies` (1), `financials_annual` with every column both helpers need, ordered by `ticker, fiscal_year` (1; the last row per ticker is the latest), latest non-NULL close per ticker via `QUALIFY row_number() OVER (PARTITION BY ticker ORDER BY date DESC) = 1` (1), latest `damodaran_country (region, erp)` per country (1), latest `damodaran_industry (pe, ev_sales, op_margin, beta_levered)` per `(industry, region)` (1), plus `bulk_load_assumption_inputs` (4). An empty ticker list returns `{}` with no queries.

- [ ] **Step 5: Run.** `uv run pytest tests/unit/test_valuation_bulk_load.py tests/unit/test_reporting_analysis.py tests/unit/test_cli_analyze.py -q`: expect PASS.

- [ ] **Step 6: Commit.** `feat(#53): bulk_load_valuation_inputs set-based loader`

### Task 3: wire the bulk loader into the screener's second pass

**Files:**
- Modify: `src/bot/screener/engine.py:45,82-121` (import, `BatchValuator` comment, `_batch_dcf_margins`), and the second-pass comment in `run_screen`.
- Test: `tests/unit/test_screener_engine.py`, `tests/unit/test_screener_second_pass_golden.py`

**Interfaces:**
- Consumes: `bulk_load_valuation_inputs` (Task 2).

- [ ] **Step 1: Tests (from stage 3).**
  - `test_batch_dcf_margins_query_count_independent_of_shortlist`: counting proxy around `_batch_dcf_margins(spy, ("AAA",))` and `_batch_dcf_margins(spy, ("AAA", "BBB", "CCC", "NOPE"))`; the two counts are equal.
  - `test_run_screen_second_pass_never_calls_per_ticker_loader`: monkeypatch `bot.valuator.analysis.load_valuation_input` and `bot.valuator.assumptions.load_assumption_inputs` to raise; `run_screen(conn, _value_preset(), top=3)` still returns three valued candidates.
  - `test_batch_dcf_margins_empty_shortlist`: `_batch_dcf_margins(conn, ()) == {}`.
  - `test_second_pass_shortlist_matches_golden`: builds the golden fixture DB, runs `run_screen(conn, _value_preset(), top=5, assumptions_dir=<tmp dir with one override YAML>)`, renders `"\n".join(repr(c) for c in result.shortlist)` and compares it byte for byte with `tests/fixtures/screener/second_pass_shortlist.golden`, which stage 3 captures from the pre-refactor code.

- [ ] **Step 2: Run, expect the two query tests to FAIL** (the golden test passes before and after: it guards behavior).

- [ ] **Step 3: Implement.**

```python
def _batch_dcf_margins(
    conn: duckdb.DuckDBPyConnection,
    tickers: tuple[str, ...],
    assumptions_dir: Path | None = None,
) -> dict[str, float | None]:
    preloaded = bulk_load_valuation_inputs(conn, tickers)
    margins: dict[str, float | None] = {}
    for ticker in tickers:
        inputs = preloaded.get(ticker.upper())
        if inputs is None:
            margins[ticker] = None
            continue
        override_path = conventional_override_path(assumptions_dir, ticker)
        try:
            analysis = analyze(ticker, conn, override_path=override_path, company=inputs)
        except (LookupError, ValueError, ZeroDivisionError):
            margins[ticker] = None
            continue
        margins[ticker] = analysis.margin_of_safety
    return margins
```

Update its docstring and the `run_screen` second-pass comment to say the rows are loaded with a fixed number of set-based scans. Drop the `load_valuation_input` import from the engine if unused.

- [ ] **Step 4: Run the full suite and lint.** `uv run pytest -q && uv run ruff check . && uv run mypy src`

- [ ] **Step 5: Regenerate the plans.** `python3 docs/plano/build.py` must succeed. `estado.py` has no entry for the second-pass loader, so no status change is recorded.

- [ ] **Step 6: Commit.** `perf(#53): second pass loads the shortlist with set-based scans`
