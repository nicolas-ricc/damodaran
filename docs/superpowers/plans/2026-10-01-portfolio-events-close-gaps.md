# Portfolio Events: Close the Production Gaps (#28) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every §8.3 derived event that `compute_events` promises able to fire in production: intrinsic value crossed price, new red flag (without re-reporting), fell below a quality gate, sector recalibration, and new filing (by ingestion date).

**Architecture:** A new per-snapshot table `holding_marks` records, for each held ticker, the valuation facts the derived detectors diff: intrinsic value, price, red narrative flags, failed quality gates, and sector WACC. `mark_holdings` writes the marks for a snapshot date. It reuses the valuator entrypoint (`analyze`) and the screener's rules. `compute_events(conn, prev, curr)` becomes a pure reader again: it diffs the prev and curr marks instead of calling the valuator, so the baseline the detectors need always comes from the database. `run_portfolio` marks today's holdings before it diffs.

**Tech Stack:** Python 3.12, DuckDB, pytest, mypy --strict, ruff.

**Spec:** GitHub issue #28 (body + "Agent Brief" comment); spec §8.3 in `docs/superpowers/specs/2026-05-25-investment-bot-design.md`; gap audit in `docs/plano/estado.py` (section "salida": `ev-cruce`, `ev-huerfanos`, `ev-ruido`, `ev-ventana`).

## Global Constraints

- `compute_events(conn, prev_snapshot_date, curr_snapshot_date) -> list[Event]`: pure reader, never writes. The caller persists.
- One detector function per event type, each unit-tested in isolation, including the boundary cases for the % thresholds.
- Size change > 10%, concentration > 15%, sector WACC move > 100bps. All three boundaries are exclusive.
- Raw price moves and news produce **no** events.
- Derived events reuse `bot.valuator.analysis.analyze` and `filings_log`. They do not re-derive valuation logic.
- Out of scope: rendering and notification (#29/#32), running auto-analyze, and writing `corporate_actions` (needs the IBKR Flex service, ADR 0004).
- `uv run ruff check . && uv run mypy src` clean (mypy --strict). Suite: `uv run pytest -q`.
- Conventional commits: `feat(#28): ...`, `test(#28): ...`.

## Review Focus

1. Same-day rerun of `bot portfolio`: marks for today are replaced, not duplicated (PK `(snapshot_date, ticker)`). Pinned in Task 1.
2. A held ticker the valuator cannot value (`LookupError`/`ValueError`) still gets a mark with null valuation fields, and it emits no cross and no red flag. Pinned in Task 2.
3. A red flag that stays red across two snapshots fires exactly once. Pinned in Task 3 (integration).
4. A filing re-imported by a later refresh (same PK) keeps its original `fetched_at`, so it does not fire again. Pinned in Task 4.
5. A 10-K filed weeks ago but ingested today fires once, and does not fire again on the next run. Pinned in Task 4.

---

## File Structure

- Create `src/bot/portfolio/marks.py`: `HoldingMark`, `AnalyzeFn`, `mark_holdings`, `persist_marks`, `load_marks`.
- Modify `src/bot/storage/schema.sql`: add the `holding_marks` table.
- Modify `src/bot/screener/engine.py`: add the public `load_holding_inputs` (bulk loads `CompanyData` + benchmarks for a set of tickers).
- Modify `src/bot/portfolio/events.py`: the derived detectors take marks or plain values, `compute_events` reads marks, and the filing window uses ingestion date plus `events_log` dedupe. Remove `analyze_fn`/`prev_analyses` and the `_AnalysisLike` Protocols.
- Modify `src/bot/ingest/sec_edgar.py:469-487` (`upsert_filings`): preserve `fetched_at` on a PK match.
- Modify `src/bot/portfolio/command.py` and `src/bot/cli.py`: mark before diffing, and pass in the quality gates of the `damodaran_value` preset.
- Tests: `tests/unit/test_portfolio_marks.py` (new), `tests/unit/test_portfolio_events.py`, `tests/integration/test_portfolio_events.py`, `tests/integration/test_portfolio_command.py`, `tests/unit/test_sec_edgar_importer.py`.
- Docs: `docs/plano/estado.py` + regenerated `estado.html`/`plano.html`, and `docs/plano/views.py` notes.

---

### Task 1: `holding_marks` storage

**Files:**
- Modify: `src/bot/storage/schema.sql` (after `events_log`)
- Create: `src/bot/portfolio/marks.py`
- Test: `tests/unit/test_portfolio_marks.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class HoldingMark:
      ticker: str
      intrinsic_value: float | None = None
      price: float | None = None
      red_flags: dict[str, str] | None = None      # flag name -> reason; None = not valued
      failed_gates: tuple[str, ...] | None = None  # None = gates not evaluable
      sector_wacc: float | None = None
  def persist_marks(conn, snapshot_date: date, marks: list[HoldingMark]) -> int
  def load_marks(conn, snapshot_date: date) -> dict[str, HoldingMark]
  ```

- [ ] **Step 1: Schema.** Append to `schema.sql`:
  ```sql
  -- Per-snapshot valuation facts for each held ticker (spec §8.3). The derived
  -- portfolio events diff two snapshots' marks, so the baseline a cross or a
  -- newly red flag needs is always read back from here (#28).
  CREATE TABLE IF NOT EXISTS holding_marks (
      snapshot_date   DATE NOT NULL,
      ticker          VARCHAR NOT NULL,
      intrinsic_value DOUBLE,
      price           DOUBLE,
      red_flags       JSON,
      failed_gates    VARCHAR[],
      sector_wacc     DOUBLE,
      PRIMARY KEY (snapshot_date, ticker)
  );
  ```
- [ ] **Step 2: Failing tests** in `tests/unit/test_portfolio_marks.py`, covering:
  - a round trip that preserves every field, including `None`s and an empty `red_flags` dict;
  - `persist_marks` twice for the same date replaces the rows (count unchanged, latest values win);
  - `load_marks` for a date with no rows returns `{}`.
- [ ] **Step 3: Implement** `persist_marks`: `DELETE FROM holding_marks WHERE snapshot_date = ?`, then `executemany` INSERT, with `red_flags` passed as `json.dumps(...)` or NULL and `failed_gates` as a list or NULL. Implement `load_marks`: parse the JSON (DuckDB returns a str), and turn `failed_gates` into a tuple, or None.
- [ ] **Step 4: Run** `uv run pytest tests/unit/test_portfolio_marks.py -q` → PASS. Run mypy.
- [ ] **Step 5: Commit** `feat(#28): holding_marks table and mark persistence`.

### Task 2: `mark_holdings` — value and gate the held tickers

**Files:**
- Modify: `src/bot/screener/engine.py` (add `load_holding_inputs` after `build_company_data`)
- Modify: `src/bot/portfolio/marks.py`
- Test: `tests/unit/test_portfolio_marks.py`

**Interfaces:**
- Consumes: `HoldingMark` and `persist_marks` from Task 1.
- Produces:
  ```python
  # engine.py
  def load_holding_inputs(
      conn, tickers: Iterable[str]
  ) -> dict[str, tuple[CompanyData, IndustryBenchmarks | None]]
  # marks.py
  class AnalyzeFn(Protocol):
      def __call__(self, ticker: str, conn: duckdb.DuckDBPyConnection) -> Analysis: ...
  def mark_holdings(
      conn, snapshot_date: date, *,
      analyze_fn: AnalyzeFn | None = None,           # None -> bot.valuator.analysis.analyze
      quality_gates: Sequence[Rule] = (),
  ) -> list[HoldingMark]                              # also persists them
  ```

- [ ] **Step 1: Failing tests:**
  - `load_holding_inputs` returns entries only for tickers present in `companies`, and builds `CompanyData` like `run_screen` does. Use a seeded company with annual rows and a `damodaran_industry` row; benchmarks come from the latest year.
  - `mark_holdings` with a stub `analyze_fn` that returns an object with `dcf_result.intrinsic_value`, `current_price`, and `narrative_flags` (red + green) gives a mark with the IV, the price, and only the red flags (`{name: reason}`). The marks are persisted.
  - The `analyze_fn` raising `LookupError` gives a mark with `intrinsic_value=None`, `price=None`, and `red_flags=None`. No exception escapes.
  - A gate that fails (not skipped) appears in `failed_gates`. A gate that is skipped does not. A ticker missing from `companies` gets `failed_gates=None`.
  - `sector_wacc` equals `benchmarks.wacc`, or None when there is no benchmark.
  - Only tickers with non-zero aggregate qty in `portfolio_snapshots` for `snapshot_date` are marked.
- [ ] **Step 2: Run** them → FAIL (ImportError).
- [ ] **Step 3: Implement** `load_holding_inputs`:
  1. Call `_load_all_annual(conn)` and `_load_latest_prices(conn)` once.
  2. Load the `companies` rows with `WHERE ticker IN (...)`.
  3. Call `build_company_data` per ticker.
  4. Load benchmarks with `load_industry_benchmarks(conn, industry=company.industry, region=company.region or DEFAULT_REGION)`.

  Implement `mark_holdings`:
  1. Read the held tickers: `SELECT UPPER(ticker) FROM portfolio_snapshots WHERE snapshot_date=? GROUP BY UPPER(ticker) HAVING SUM(qty) <> 0`.
  2. Value each ticker with `analyze_fn`, catching `(LookupError, ValueError)` and logging `marks.analyze_skipped`.
  3. Evaluate the gates: `[g.name for g in quality_gates if not (r := g.evaluate(company, bench)).passed and not r.skipped]`, with `bench` set to `benchmarks or IndustryBenchmarks(industry="", region="", year=0)`.
  4. Call `persist_marks` and return the marks.
- [ ] **Step 4: Run** → PASS. Run mypy.
- [ ] **Step 5: Commit** `feat(#28): mark held tickers with valuation, gates and sector WACC`.

### Task 3: Derived detectors diff marks; `compute_events` wires all six

**Files:**
- Modify: `src/bot/portfolio/events.py`
- Test: `tests/unit/test_portfolio_events.py`, `tests/integration/test_portfolio_events.py`

**Interfaces:**
- Consumes: `HoldingMark` and `load_marks` (Task 1).
- Produces (new signatures; the other detectors are unchanged):
  ```python
  def detect_intrinsic_value_cross(prev: HoldingMark | None, curr: HoldingMark, *, snapshot_date, prev_date) -> Event | None
  def detect_new_red_flags(prev: HoldingMark | None, curr: HoldingMark, *, snapshot_date, prev_date) -> list[Event]
  def detect_below_quality_gate(prev_failed: Sequence[str] | None, curr_failed: Sequence[str] | None, ticker: str, *, snapshot_date, prev_date) -> list[Event]
  def detect_sector_recalibration(prev_wacc, curr_wacc, ticker, *, snapshot_date, prev_date, threshold=...) -> Event | None  # unchanged
  def compute_events(conn, prev_snapshot_date: date | None, curr_snapshot_date: date, *, size_change_threshold=..., concentration_threshold=...) -> list[Event]
  ```

- [ ] **Step 1: Rewrite the unit tests** for the IV cross and red flags using `HoldingMark` instead of the `_Analysis` stub. Keep the same cases: above, below, same side, no prior, missing price, and also missing IV. Red flags:
  - a persistent red flag does not fire; a newly red flag fires;
  - no prior mark → all red flags are new;
  - prior mark with `red_flags=None` → all red flags are new;
  - curr `red_flags=None` → nothing.

  Below quality gate:
  - only gates in curr and not in prev fire, one event each;
  - `prev_failed=None` → nothing (no baseline);
  - `curr_failed=None` → nothing.
- [ ] **Step 2: Rewrite the integration test.**
  - Seed `holding_marks` for PREV and CURR directly via `persist_marks`, instead of `fake_analyze`/`prev_analyses`.
  - AAPL: IV crosses above price, `story_margin` turns red, and `max_net_debt_to_ebitda` is newly failed.
  - MSFT: `sector_wacc` moves from 0.08 to 0.095.
  - Assert that each of those fires.
  - In the price-only test, seed identical marks (same red flag on both dates) and assert `[]`.
  - Add `test_persistent_red_flag_reported_once`: day 1 → day 2 → day 3. The flag is red from day 2 on, so it fires on the day-2 diff only.
- [ ] **Step 3: Run** → FAIL.
- [ ] **Step 4: Implement.**
  - Change the detectors as specified: compare `curr.intrinsic_value - curr.price` across the marks; the red-flag sets come from `red_flags.keys()`, with the detail `{"flag": name, "reason": reason}`.
  - Delete `_DCFLike`, `_AnalysisLike`, `_AnalyzeFn` and the `analyze_fn`/`prev_analyses` params.
  - In `compute_events`: load `prev_marks = load_marks(conn, prev) if prev else {}` and `curr_marks = load_marks(conn, curr)`. For each held ticker that has a curr mark, run the four derived detectors (cross, red flags, gates, recalibration) against `prev_marks.get(ticker)`.
  - Update the module and function docstrings.
- [ ] **Step 5: Run** the events tests → PASS. Run mypy.
- [ ] **Step 6: Commit** `feat(#28): derive valuation events from holding marks`.

### Task 4: New filing by ingestion date, reported once

**Files:**
- Modify: `src/bot/ingest/sec_edgar.py` (`upsert_filings`)
- Modify: `src/bot/portfolio/events.py` (`Filing`, `detect_new_filings`, `_load_filings`)
- Test: `tests/unit/test_sec_edgar_importer.py`, `tests/unit/test_portfolio_events.py`, `tests/integration/test_portfolio_events.py`

**Interfaces:**
- Produces:
  ```python
  @dataclass(frozen=True)
  class Filing:
      ticker: str; filing_type: str; filing_date: date
      accession_number: str | None; fetched_on: date
  def detect_new_filings(filings, *, held_tickers: set[str], reported: set[tuple[str, str, str]],
                         window_start: date | None, window_end: date, snapshot_date, prev_date) -> list[Event]
  ```
  `reported` holds `(ticker, filing_type, filing_date.isoformat())` triples that `events_log` already has as `new_filing`.

- [ ] **Step 1: Failing tests.**
  - `upsert_filings`: insert a filing, backdate its `fetched_at` with `UPDATE`, upsert the same PK with a new accession → the accession is updated and `fetched_at` is unchanged.
  - Detector: a filing with an old `filing_date` but `fetched_on == CURR` fires. A filing whose `fetched_on == window_start` fires (inclusive, so a same-day fetch after the previous run is not lost). A filing already in `reported` does not fire. A filing with `filing_date` and `fetched_on` both `<= window_start` does not fire. A filing with `filing_date > window_end` does not fire. With `window_start=None`, every unreported filing up to `window_end` fires.
  - Integration: run `compute_events` and `persist_events`, then run `compute_events` again for the same window → the second run has no `NEW_FILING`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.**
  - `upsert_filings`: replace DELETE+INSERT with `INSERT INTO filings_log (...) VALUES (...) ON CONFLICT (ticker, filing_type, filing_date, source) DO UPDATE SET accession_number = excluded.accession_number`.
  - Detector rule: a filing qualifies when all of these hold:
    - it is held;
    - `filing_date <= window_end`;
    - it is not in `reported`;
    - `window_start is None` or `filing_date > window_start` or `fetched_on >= window_start`.
  - `_load_filings`: select `CAST(fetched_at AS DATE)` for held tickers with `filing_date <= window_end` (no lower bound in SQL; the detector owns the window).
  - New `_load_reported_filings(conn, held_tickers)`: read `events_log WHERE event_type='new_filing'`, using `json_extract_string(details,'$.filing_type')` and `'$.filing_date'`.
- [ ] **Step 4: Run** → PASS. Run mypy.
- [ ] **Step 5: Commit** `fix(#28): new-filing events follow ingestion date and fire once`.

### Task 5: `run_portfolio` marks before diffing; CLI passes the gates

**Files:**
- Modify: `src/bot/portfolio/command.py`, `src/bot/cli.py` (`portfolio` command)
- Test: `tests/integration/test_portfolio_command.py`, `tests/unit/test_cli_portfolio.py`

**Interfaces:**
- Consumes: `mark_holdings` and `AnalyzeFn` (Task 2), and the new `compute_events` (Task 3).
- Produces: `run_portfolio(conn, client, *, reports_dir, today=None, history=False, concentration=False, analyze_fn: AnalyzeFn | None = None, quality_gates: Sequence[Rule] = ()) -> PortfolioRunResult`.

- [ ] **Step 1: Failing integration test** `test_run_portfolio_emits_iv_cross_across_two_runs`:
  - Run on day 1 with an `analyze_fn` that returns IV 90 / price 100 for AAPL.
  - Run on day 2 with IV 120 / price 100.
  - Assert that day 2 has an `intrinsic_value_crossed_price` row in `events_log` for AAPL, and that `holding_marks` has rows for both days.
  - Use a stub analysis object (dataclass with `dcf_result`, `current_price`, `narrative_flags`). Type it with a `cast`, or with a Protocol in the test.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** In `run_portfolio`, between the trades step and the diff, call `mark_holdings(conn, run_day, analyze_fn=analyze_fn, quality_gates=quality_gates)`. Then call `compute_events(conn, prev_date, run_day)`. Import `AnalyzeFn` from `bot.portfolio.marks`. In `cli.portfolio`:
  ```python
  gates = load_screener_config(settings.presets_dir / "damodaran_value.yaml").quality_gates.build()
  ```
  and pass `quality_gates=gates`. The CLI unit test must still pass: check that `presets_dir` resolves in its env, and if not, the test env needs `BOT_PRESETS_DIR` pointing at the repo `config/presets`.
- [ ] **Step 4: Run** the full suite plus lint → PASS.
- [ ] **Step 5: Commit** `feat(#28): bot portfolio marks holdings before diffing`.

### Task 6: Re-audit the plans

**Files:**
- Modify: `docs/plano/estado.py` (INVENTARIO "salida": `ev-cruce`, `ev-huerfanos`, `ev-ruido`, `ev-ventana`; BLOQUES `events`; AUDITADO_EN/EL), `docs/plano/views.py` notes if they mention the gaps.
- Regenerate: `python3 docs/plano/build.py && python3 docs/plano/build_estado.py`.

- [ ] **Step 1: Update `estado.py`.**
  - `ev-cruce`, `ev-huerfanos`, `ev-ruido` and `ev-ventana` become `hecho`, with new evidence (`portfolio/marks.py`, `portfolio/events.py` line numbers).
  - Fold `ev-vivos` so it lists ten live events.
  - `ev-corp` stays `muerto`.
  - BLOQUES `events` stays `a-medias` because of dividend/split.
  - `AUDITADO_EN` = HEAD short SHA after Task 5. `AUDITADO_EL` = "1 de octubre de 2026".
- [ ] **Step 2: Run both builds.** They must succeed.
- [ ] **Step 3: Commit** `docs(#28): re-audit portfolio events in the plans`.

---

## Self-review

- Spec coverage. Each acceptance criterion maps to a task:
  - the `events_log` schema already exists;
  - `compute_events` signature: T3;
  - one detector per type with boundary tests: existing tests plus T3/T4;
  - integration test with two snapshots plus a filing: T3/T4;
  - price-only produces no events: T3;
  - mypy and ruff: every task.
- Dividend/split stay unreachable in production. Their input table has no writer, and that is outside this issue (ADR 0004, `ibkr-corp`).
- Types: `HoldingMark` is used consistently in T1–T3. `AnalyzeFn` is defined in T2 and consumed in T5.
