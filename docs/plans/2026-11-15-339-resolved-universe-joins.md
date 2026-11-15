# Portfolio joins on the resolved universe ticker (#339) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Valuation, quality gates, the assumptions override path and the `filings_log` join of the portfolio monitor use the universe ticker that `bot.portfolio.symbols` resolves, while every portfolio row keeps the broker symbol.

**Architecture:** `mark_holdings` and `compute_events` each gain `symbols: SymbolMap | None = None` (`None` = `load_symbol_map(conn, held, {})`, normalisation only). They translate at the seams only: `symbols.ticker(sym)` before `analyze_fn`, `conventional_override_path` and `load_holding_inputs`; in `compute_events`, `filings_log` is queried by resolved ticker and each filing is fanned back out to the broker symbols that resolve to it. `run_portfolio` builds one `SymbolMap` after the sync, passes it to both, and warns `portfolio_symbols_unresolved`.

**Tech Stack:** Python 3.12, DuckDB, structlog, pytest, mypy --strict, ruff.

**Spec:** GitHub issue #339 (parent story #84; shared decisions are quoted in #339's body). Vocabulary in `CONTEXT.md` (Broker symbol, Universe ticker).

## Global Constraints

- The portfolio's identity stays the broker symbol: `portfolio_snapshots.ticker`, `holding_marks.ticker`, `events_log.ticker`, `Event.ticker` are never rewritten.
- Corporate actions and `events_log` lookups are broker-to-broker joins: not resolved. `detect_new_filings`, `_load_reported_filings`, `_load_corporate_actions` and the mark-diff loop are unchanged.
- An ignored or unresolved symbol goes through unchanged (`SymbolMap.ticker` falls through) and ends with unknown fields, as today.
- `mypy --strict` types; in-memory DuckDB + `apply_schema` in tests; Conventional Commits with `(#339)`.
- `uv run pytest -q`, `uv run ruff check .`, `uv run mypy src` pass.
- `tests/unit/test_pipeline_diagram.py::test_portfolio_run_steps_match_code` checks the order of `sync_trades(`, `mark_holdings(`, `compute_events(` in `run_portfolio`'s source: keep that order.

## Assumptions (technical, declared)

1. **Filing fan-out covers every held symbol, not only `symbols.resolved`.** The reverse map is `{symbols.ticker(s): [s, ...] for s in held_tickers}`. For a resolved symbol this is exactly the issue's "reverse mapping from `symbols.resolved`"; for an unresolved one `ticker(s) == s`, so a holding absent from `companies` keeps today's `new_filing` events (`tests/integration/test_portfolio_events.py::test_new_filing_reported_once` seeds a filing for `T00` with no `companies` row and must keep passing: AC6).
2. One `analyze_fn` call per broker symbol, even when two broker symbols resolve to the same ticker (no caching: the issue says "for each held broker symbol").
3. The `filings_log` query keeps `UPPER(ticker) IN (...)`, so a lower-case filing ticker still matches.

## Review Focus

1. Two held broker symbols resolving to one ticker (`BRK B`, `BRK.B`): each gets its own mark and its own `new_filing` event, once. Pinned by `test_two_broker_symbols_for_one_ticker_each_get_the_filing` (Task 2).
2. An explicit `symbols` map that does not contain a held symbol: falls through as itself, no crash. Pinned by `test_mark_holdings_symbol_absent_from_the_map_falls_through` (Task 1).
3. An ignored symbol (override `None`) is never reported as unresolved. Pinned by `test_ignored_symbol_is_not_reported_unresolved` (Task 3).
4. A symbol that already equals its universe ticker: identical behaviour to today. Covered by the existing suites (AC6).
5. A held symbol with zero quantity is not marked. Covered by `test_mark_holdings_skips_zero_qty`.

---

### Task 1: `mark_holdings` values and gates on the universe ticker

**Files:**
- Modify: `src/bot/portfolio/marks.py` (module docstring; `mark_holdings`)
- Test: `tests/unit/test_portfolio_marks.py`

**Interfaces:**
- Consumes: `bot.portfolio.symbols.SymbolMap`, `load_symbol_map(conn, symbols, overrides)`, `resolve_symbols(symbols, known, overrides)`.
- Produces: `mark_holdings(conn, snapshot_date, *, analyze_fn=None, quality_gates=(), assumptions_dir=None, currencies=None, default_spreads=None, symbols: SymbolMap | None = None) -> list[HoldingMark]`.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_portfolio_marks.py`:
  - `test_mark_holdings_values_a_share_class_on_the_universe_ticker`: `_hold(conn, "BRK B")`, `_seed_company(conn, "BRK-B")`, `_analyze_with({"BRK-B": _Analysis("BRK-B", _DCF(120.0), current_price=100.0)})` wrapped to record the tickers it is called with; `mark_holdings(conn, DAY, analyze_fn=..., quality_gates=[MinMarketCap(minimum_usd=1e12)])`. Assert calls `== ["BRK-B"]`; the `holding_marks` row (`SELECT ticker, intrinsic_value, red_flags, failed_gates FROM holding_marks`) has `ticker == "BRK B"`, `intrinsic_value == 120.0`, `red_flags` not NULL, `failed_gates` not NULL.
  - `test_mark_holdings_override_routes_the_valuator_and_assumptions_file`: `symbols = resolve_symbols(["APPLE"], {"AAPL"}, {"APPLE": "AAPL"})` (equivalently `load_symbol_map(conn, ["APPLE"], {"APPLE": "AAPL"})` after seeding), `_hold(conn, "APPLE")`, `_seed_company(conn, "AAPL")`, `tmp_path / "AAPL.yaml"` written, `bot.valuator.analysis.analyze` monkeypatched as in `test_mark_holdings_values_with_the_conventional_override`; `mark_holdings(conn, DAY, assumptions_dir=tmp_path, symbols=symbols)`. Assert `seen == {"AAPL": tmp_path / "AAPL.yaml"}`, `set(load_marks(conn, DAY)) == {"APPLE"}`, and `SELECT DISTINCT ticker FROM portfolio_snapshots` is `[("APPLE",)]`.
  - `test_mark_holdings_symbol_absent_from_the_map_falls_through`: `_hold(conn, "ZZZ")`, `symbols = resolve_symbols([], set(), {})`, recording fake `analyze_fn` raising `LookupError`; assert it was called with `"ZZZ"` and the mark is `HoldingMark(ticker="ZZZ")`.

- [ ] **Step 2: Run them, verify they fail**
  Run: `uv run pytest tests/unit/test_portfolio_marks.py -q`
  Expected: the three new tests FAIL (unexpected keyword `symbols` / analyze called with `BRK B`).

- [ ] **Step 3: Implement in `src/bot/portfolio/marks.py`**
  Add keyword `symbols: SymbolMap | None = None` to `mark_holdings`. After `held = _held_tickers(conn, snapshot_date)`: `if symbols is None: symbols = load_symbol_map(conn, held, {})`. `inputs = load_holding_inputs(conn, {symbols.ticker(s) for s in held})`. In the loop over `sym in held`: `ticker = symbols.ticker(sym)`; `analyze_fn(ticker, conn, price_as_of=snapshot_date)`; `inputs.get(ticker)` for the gates; `HoldingMark(ticker=sym, ...)`. The default valuator closure needs no change: it already builds `conventional_override_path(assumptions_dir, ticker)` from the ticker it receives. Log `marks.analyze_skipped` with both `symbol=sym` and `ticker=ticker`. Document `symbols` in the docstring, and add one paragraph to the module docstring: holdings are keyed by broker symbol; valuation, gates and the `<TICKER>.yaml` override use the universe ticker from `bot.portfolio.symbols`; an unresolved or ignored symbol is used as is.

- [ ] **Step 4: Run the file, then the full suite**
  Run: `uv run pytest tests/unit/test_portfolio_marks.py -q && uv run pytest -q`
  Expected: all PASS.

- [ ] **Step 5: Commit** `feat(#339): mark_holdings values and gates on the resolved universe ticker`

### Task 2: `compute_events` joins `filings_log` on the universe ticker

**Files:**
- Modify: `src/bot/portfolio/events.py` (module docstring; `_load_filings`; `compute_events`)
- Test: `tests/integration/test_portfolio_events.py`

**Interfaces:**
- Consumes: `SymbolMap`, `load_symbol_map`, `resolve_symbols` from `bot.portfolio.symbols`.
- Produces: `compute_events(conn, prev_snapshot_date, curr_snapshot_date, *, size_change_threshold=..., concentration_threshold=..., symbols: SymbolMap | None = None) -> list[Event]`.

- [ ] **Step 1: Write the failing tests** in `tests/integration/test_portfolio_events.py`:
  - `test_share_class_holding_gets_the_universe_filing_once`: both snapshots hold `BRK B` (plus enough other rows to stay below concentration, as `test_new_filing_reported_once` does with `T00..T09`, here `BRK B` + `T01..T09`); `INSERT INTO companies (ticker, name, source) VALUES ('BRK-B', 'Berkshire', 'fmp')`; `_insert_filing(conn, "BRK-B", "10-K", CURR, "k", fetched_on=CURR)`; `persist_marks(conn, CURR, [HoldingMark("BRK B")])`. `first = compute_events(conn, PREV, CURR)` → `[(e.event_type, e.ticker) for e in first] == [(EventType.NEW_FILING, "BRK B")]`; `persist_events(conn, first)`; second `compute_events` → `[]`.
  - `test_two_broker_symbols_for_one_ticker_each_get_the_filing`: holdings `BRK B`, `BRK.B` (+ `T02..T09`), company `BRK-B`, one `BRK-B` filing in window. Explicit `symbols=load_symbol_map(conn, ["BRK B", "BRK.B"], {})`. Assert the `NEW_FILING` tickers are `["BRK B", "BRK.B"]` (sorted), and after `persist_events` a rerun returns `[]`.
  - `test_override_maps_the_filing_back_to_the_broker_symbol`: holdings `APPLE` (+ `T01..T09`), company `AAPL`, `AAPL` filing in window, `symbols=load_symbol_map(conn, ["APPLE"], {"APPLE": "AAPL"})`; assert one `NEW_FILING` with `ticker == "APPLE"`; without `symbols` (default map) there is none.

- [ ] **Step 2: Run them, verify they fail**
  Run: `uv run pytest tests/integration/test_portfolio_events.py -q`
  Expected: the three new tests FAIL.

- [ ] **Step 3: Implement in `src/bot/portfolio/events.py`**
  `compute_events` gains `symbols: SymbolMap | None = None`; `None` → `load_symbol_map(conn, held_tickers, {})`. Build `by_ticker: dict[str, list[str]]` mapping `symbols.ticker(s)` → sorted broker symbols, over every `s` in `held_tickers` (Assumption 1). `_load_filings(conn, set(by_ticker), window_end)` stays the query it is (it already upper-cases `filings_log.ticker`); then for each filing emit `dataclasses.replace(filing, ticker=sym)` for every `sym in by_ticker.get(filing.ticker.upper(), [])`, and pass that list to the unchanged `detect_new_filings(..., held_tickers=held_tickers, reported=_load_reported_filings(conn, held_tickers), ...)`. Put the fan-out in a small private helper (`_filings_for_held(conn, held_tickers, symbols, window_end) -> list[Filing]`) so `compute_events` keeps reading as a list of detector calls. Document `symbols` in the `compute_events` docstring, and add one paragraph to the module docstring: events are keyed by broker symbol; only the `filings_log` join is resolved to the universe ticker and fanned back out per broker symbol; corporate actions, `events_log` and marks stay broker-to-broker.

- [ ] **Step 4: Run the file, then the full suite**
  Run: `uv run pytest tests/integration/test_portfolio_events.py -q && uv run pytest -q`
  Expected: all PASS (including `test_new_filing_reported_once`, `test_compute_events_end_to_end`).

- [ ] **Step 5: Commit** `feat(#339): compute_events joins filings_log on the resolved universe ticker`

### Task 3: `run_portfolio` resolves once and reports the unresolved symbols

**Files:**
- Modify: `src/bot/portfolio/command.py` (`run_portfolio` step 4 and docstrings)
- Test: `tests/integration/test_portfolio_command.py`

**Interfaces:**
- Consumes: `mark_holdings(..., symbols=...)` (Task 1), `compute_events(..., symbols=...)` (Task 2), `load_symbol_map`, `held_symbols` from `bot.portfolio.symbols`.
- Produces: log event `portfolio_symbols_unresolved` (WARNING, key `symbols: list[str]`).

- [ ] **Step 1: Write the failing tests** in `tests/integration/test_portfolio_command.py`:
  - `test_share_class_holding_is_valued_and_gets_its_filing`: a `_FakeFlexClient` holding `_position("BRK B", 1, 10.0, 300.0)` and `_position("MSFT", 2, 10.0, 300.0)`; `companies` rows `BRK-B`, `MSFT`; `_insert_filing(conn, "BRK-B", "10-K", TODAY, fetched_at=TODAY)`; `analyze_fn` that returns `_Analysis(ticker, _DCF(150.0), current_price=100.0)` for `BRK-B` and `MSFT` and raises `LookupError` otherwise. After `run_portfolio(conn, client, reports_dir=tmp_path, today=TODAY, analyze_fn=...)`: `SELECT intrinsic_value FROM holding_marks WHERE ticker = 'BRK B'` is `(150.0,)`, and `alerts.md` contains `"| new_filing | BRK B |"`.
  - `test_unresolved_symbol_is_logged`: client holding `ZZZQ` and `MSFT`, `companies` has only `MSFT`; under `capture_logs()`, exactly one `portfolio_symbols_unresolved` entry with `log_level == "warning"` and `symbols == ["ZZZQ"]`.
  - `test_fully_resolved_run_logs_no_unresolved`: same as the previous with `companies` rows for both: no `portfolio_symbols_unresolved` entry.
  - `test_ignored_symbol_is_not_reported_unresolved`: client holding `ZZZQ`, `MSFT`, `companies` has `MSFT`, `symbol_overrides={"ZZZQ": None}`: no `portfolio_symbols_unresolved` entry.

- [ ] **Step 2: Run them, verify they fail**
  Run: `uv run pytest tests/integration/test_portfolio_command.py -q`
  Expected: the share-class and unresolved tests FAIL.

- [ ] **Step 3: Implement in `src/bot/portfolio/command.py`**
  In step 4, before `mark_holdings(`: `symbols = load_symbol_map(conn, held_symbols(conn, snapshot_date), symbol_overrides)`; `if symbols.unresolved: log.warning("portfolio_symbols_unresolved", symbols=list(symbols.unresolved))`; pass `symbols=symbols` to `mark_holdings` and `compute_events`. Update the `symbol_overrides` arg doc (it now also feeds valuation, gates and the filings join) and point 4 of the module docstring.

- [ ] **Step 4: Run the file, then the full suite and lint**
  Run: `uv run pytest -q && uv run ruff check . && uv run mypy src`
  Expected: all PASS, including `tests/unit/test_pipeline_diagram.py`.

- [ ] **Step 5: Commit** `feat(#339): run_portfolio resolves held symbols once for marks and events`
