# `portfolio.md` names the unresolved holdings (#340) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `portfolio.md` carries a "Not in the universe" callout naming every held broker symbol that the resolver could not map to a universe ticker.

**Architecture:** `build_report` gains `symbols: SymbolMap | None = None` (`None` = `load_symbol_map(conn, held_symbols(conn, snapshot_date), {})`) and fills `PortfolioReport.unresolved` with the symbols of `symbols.unresolved` that are held (aggregated `qty != 0`) on the snapshot, sorted. The template renders the callout right after the unpriced one. `run_portfolio` passes the map it already builds.

**Tech Stack:** Python 3.12, DuckDB, Jinja2, pytest, mypy --strict, ruff.

**Spec:** GitHub issue #340 (parent story #84; shared decisions quoted in #340's body). Vocabulary (Broker symbol, Universe ticker) is defined in #340's body, not in `CONTEXT.md`.

## Global Constraints

- The portfolio's identity stays the broker symbol: the positions table, totals and concentration are unchanged; only the new field and callout are added.
- `PortfolioReport.unresolved: tuple[str, ...] = ()` (default keeps every existing constructor call valid).
- Ignored symbols (`~` overrides, `SymbolMap.ignored`) are never listed.
- Callout copy, verbatim (symbols joined with `, `):
  `> ⚠ Not in the universe: BRK B, FOO — no valuation, quality gates or filing events for these holdings. Map each one to its universe ticker in config/broker_symbols.yaml, or set it to ~ to mark it as intentionally outside the universe.`
- `build_report` stays a pure reader (no writes, no logging).
- `mypy --strict` types; in-memory DuckDB + `apply_schema` in tests; Conventional Commits with `(#340)`.
- `uv run pytest -q`, `uv run ruff check .`, `uv run mypy src` pass.
- `tests/unit/test_pipeline_diagram.py` checks the order of calls in `run_portfolio`'s source: only add a keyword argument to the existing `build_report(` call, do not move it.

## Assumptions (technical, declared)

1. "Held" means the aggregated position of `_load_position_rows` has `qty != 0.0` (the issue: "positions with `qty != 0`"). A symbol whose legs net to zero is not listed even if unresolved.
2. Membership is checked on the upper-cased, stripped position ticker against `symbols.unresolved` (which `resolve_symbols` stores stripped and upper-cased); the listed spelling is the one in `symbols.unresolved`.
3. An explicit `symbols` map is trusted as given: a held symbol absent from it is not listed (it is neither in `unresolved` nor computed again). `run_portfolio` always builds its map from `held_symbols` of the same snapshot, so in practice every held symbol is in it.
4. Docs boards (`docs/pipeline/*.d2`, `docs/plano/`) are not updated, as the #84 plan states; nothing they cite is renamed.
5. Task 1 lands before Task 2 in the same PR. Between the two commits, `run_portfolio` would list `~`-ignored symbols (the default map has no overrides); that state never reaches the base branch alone. Rejected alternative: one combined commit, which loses the separate test cycle.
6. No rerun assertion on `portfolio.md` is added: the issue does not ask for one, and the file is rewritten from the DB on each run.

## Review Focus

1. A held symbol that is ignored (`overrides={"BRK B": None}`) is not listed. Pinned by `test_build_report_ignored_symbol_not_unresolved` (Task 1).
2. A zero-quantity unresolved row on the snapshot is not listed. Pinned by `test_build_report_zero_qty_not_unresolved` (Task 1).
3. Several unresolved symbols come out sorted and comma-separated in the callout. Pinned by `test_render_portfolio_lists_unresolved_sorted` (Task 1).
4. The positions table keeps the broker symbol for an unresolved holding. Pinned by `test_build_report_unresolved_keeps_positions_and_totals` (Task 1).
5. A same-day re-run writes the callout again. Not pinned by a test: `build_report` re-reads the snapshot and `run_portfolio` rebuilds the map on every run (`src/bot/portfolio/command.py:170`), and no existing #83 rerun test reads `portfolio.md`; see Assumption 6.

---

### Task 1: `PortfolioReport.unresolved`, `build_report(symbols=...)`, the callout

**Files:**
- Modify: `src/bot/portfolio/report.py` (module docstring; `PortfolioReport`; `build_report`)
- Modify: `src/bot/reporting/templates/portfolio.md.j2` (after the `r.unpriced` block)
- Test: `tests/unit/test_portfolio_report.py`

**Interfaces:**
- Consumes: `bot.portfolio.symbols.SymbolMap`, `load_symbol_map(conn, symbols, overrides) -> SymbolMap`, `held_symbols(conn, snapshot_date) -> list[str]`, `resolve_symbols(symbols, known, overrides) -> SymbolMap`.
- Produces: `PortfolioReport.unresolved: tuple[str, ...] = ()`; `build_report(conn, snapshot_date, *, include_history=False, include_concentration=False, concentration_threshold=DEFAULT_CONCENTRATION_THRESHOLD, symbols: SymbolMap | None = None) -> PortfolioReport`.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_portfolio_report.py` (helper `_company(conn, ticker)` running `INSERT INTO companies (ticker, name, source) VALUES (?, ?, 'sec_edgar')`):
  - `test_build_report_share_class_resolves`: snapshot `D2` rows `("BRK B", 1, 10.0, 300.0, 3500.0, "USD")`, `("AAPL", 2, 10.0, 100.0, 1300.0, "USD")`; companies `BRK-B`, `AAPL`. `build_report(conn, D2).unresolved == ()`.
  - `test_build_report_lists_unresolved`: same rows, company `AAPL` only. `.unresolved == ("BRK B",)`.
  - `test_build_report_ignored_symbol_not_unresolved`: same rows, company `AAPL` only, `symbols = load_symbol_map(conn, ["BRK B", "AAPL"], {"BRK B": None})`; `build_report(conn, D2, symbols=symbols).unresolved == ()`.
  - `test_build_report_zero_qty_not_unresolved`: rows `("ZZZ", 1, 0.0, 10.0, 0.0, "USD")`, `("AAPL", 2, 10.0, 100.0, 1300.0, "USD")`, company `AAPL`. `.unresolved == ()`.
  - `test_build_report_unresolved_keeps_positions_and_totals`: rows as in the second test; build once with company `AAPL` only and assert `[p.ticker for p in report.positions] == ["AAPL", "BRK B"]`; assert `total_market_value == pytest.approx(4800.0)`, `total_cost_basis == pytest.approx(4000.0)` and `{c.ticker for c in report.concentration} == {"AAPL", "BRK B"}`.
  - `test_render_portfolio_shows_unresolved_callout`: a `PortfolioReport` like the one in `test_render_portfolio_shows_unpriced_notice` with `positions=(PositionRow("BRK B", 10.0, 300.0, 3500.0, "USD"),)`, `unpriced=()`, `unresolved=("BRK B",)`. Output contains `"Not in the universe: BRK B"` and `"config/broker_symbols.yaml"`.
  - `test_render_portfolio_no_unresolved_callout`: same report with `unresolved=()`: `"Not in the universe" not in out`.
  - `test_render_portfolio_lists_unresolved_sorted`: `unresolved=("BRK B", "FOO")`: the exact callout line from Global Constraints is in the output.

- [ ] **Step 2: Run them, verify they fail**
  Run: `uv run pytest tests/unit/test_portfolio_report.py -q`
  Expected: the new tests FAIL (`unexpected keyword argument 'unresolved'` / `'symbols'`, missing attribute).

- [ ] **Step 3: Implement**
  - `PortfolioReport.unresolved: tuple[str, ...] = ()` after `unpriced`.
  - `build_report(..., symbols: SymbolMap | None = None)`: when `None`, `symbols = load_symbol_map(conn, held_symbols(conn, snapshot_date), {})`; `held = {p.ticker.strip() for p in positions if p.qty != 0.0}`; `unresolved = tuple(s for s in symbols.unresolved if s in held)` (already sorted). Document the parameter in the docstring.
  - Template: right after the `{% if r.unpriced %}` block, a `{% if r.unresolved %}` block with a blank line then the callout line, same join loop as the unpriced callout.
  - Module docstring: one sentence saying `portfolio.md` names the held broker symbols that do not resolve to a universe ticker in a "Not in the universe" callout.

- [ ] **Step 4: Run the tests, verify they pass**
  Run: `uv run pytest tests/unit/test_portfolio_report.py -q && uv run ruff check . && uv run mypy src`
  Expected: PASS, no lint or type errors.

- [ ] **Step 5: Commit** `feat(#340): portfolio report names unresolved holdings`

### Task 2: `run_portfolio` hands its map to `build_report`

**Files:**
- Modify: `src/bot/portfolio/command.py` (step 5 `build_report(` call; module docstring step 5 mentions the callout)
- Test: `tests/integration/test_portfolio_command.py`

**Interfaces:**
- Consumes: `build_report(..., symbols=...)` from Task 1; `_book`, `_company`, `_no_analyze`, `TODAY` already in the test module.
- Produces: nothing new.

- [ ] **Step 1: Write the failing tests** in `tests/integration/test_portfolio_command.py`, in the #339 section:
  - `test_unresolved_holding_named_in_portfolio_md`: `_company(conn, "MSFT")`; `result = run_portfolio(conn, _book("ZZZ Q", "MSFT"), reports_dir=tmp_path, today=TODAY, analyze_fn=_no_analyze)`; `md = result.portfolio_path.read_text()`; assert `"Not in the universe: ZZZ Q" in md` and `"| ZZZ Q |" in md`.
  - `test_resolved_holding_writes_no_callout`: same with `_company(conn, "ZZZ-Q")` too; assert `"Not in the universe" not in md`.
  - `test_ignored_override_writes_no_callout`: `_company(conn, "MSFT")`, `symbol_overrides={"ZZZ Q": None}`; assert `"Not in the universe" not in md`. This one only passes once `run_portfolio` forwards its map (the default map in `build_report` has no overrides).

- [ ] **Step 2: Run them, verify the override test fails**
  Run: `uv run pytest tests/integration/test_portfolio_command.py -q`
  Expected: `test_ignored_override_writes_no_callout` FAILS (callout present); the other two may already pass via the default map (that is fine: they pin the AC).

- [ ] **Step 3: Implement** `symbols=symbols` in the existing `build_report(` call of `run_portfolio`; module docstring step 5: `portfolio.md` names the unresolved holdings.

- [ ] **Step 4: Run the full suite**
  Run: `uv run pytest -q && uv run ruff check . && uv run mypy src`
  Expected: all pass.

- [ ] **Step 5: Commit** `feat(#340): run_portfolio passes its symbol map to the report`

## Grilling

- Rounds: 1 (revisions were wording and assumptions only, no step added or removed, so no second round).
- Questions: 15. Sources: ISSUE 4, CODE 11, DOC 0, NO SOURCE 2 (both technical assumptions: 5 and 6 above).
- Answers worth keeping:
  - Upper-casing: Flex ingest stores `symbol.upper()` (`src/bot/ingest/ibkr_flex.py:142`); `_load_position_rows` builds `ticker=str(ticker).upper()` (`src/bot/portfolio/report.py`); `resolve_symbols` stores `strip().upper()` (`src/bot/portfolio/symbols.py`).
  - Sort: `unresolved=tuple(sorted(unresolved))` (`src/bot/portfolio/symbols.py`), typed `tuple[str, ...]`.
  - `held_symbols` has no quantity filter (`SELECT DISTINCT UPPER(ticker) ... WHERE snapshot_date = ?`), hence the `qty != 0` filter on positions and `test_build_report_zero_qty_not_unresolved`.
  - `load_symbol_map` only queries `companies`; it reads no file and does not log, so `build_report` stays a pure reader.
  - Same snapshot: `run_portfolio` builds the map with `held_symbols(conn, snapshot_date)` and calls `build_report(conn, snapshot_date, ...)` with the same variable (`src/bot/portfolio/command.py:170-196`).
  - Empty snapshot: `held_symbols` returns `[]`, `resolve_symbols([])` an empty map; `test_build_report_empty_snapshot` runs that default path.
  - `test_portfolio_run_steps_match_code` only compares `source.index(...)` positions (`tests/unit/test_pipeline_diagram.py:2248-2262`).
  - Callout copy, glyph, path and `~`: ISSUE Scope 3 verbatim; the unpriced callout uses the same `> ⚠` form (`portfolio.md.j2`).
- Follow-up issues opened: none.
