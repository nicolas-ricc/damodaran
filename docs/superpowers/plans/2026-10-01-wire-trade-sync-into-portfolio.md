# Wire trade sync into `bot portfolio` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every `bot portfolio` run append the new IBKR executions to `trades`, so the incremental, de-duped trade log from #27 is written in real use instead of only in tests.

**Architecture:** `bot.portfolio.trades.sync_trades` (watermark on `max(executed_at)` per account, `ON CONFLICT (exec_id) DO NOTHING`) and the `trades` / `corporate_actions` tables already exist on master (59818c4) but nothing calls `sync_trades`. `run_portfolio` in `bot/portfolio/command.py` is the single orchestrator of a portfolio sync; it gains a call to `sync_trades` right after the snapshot is written, its client type widens to a Protocol that covers both the snapshot and the trade slice of `IbkrClient`, and its result carries the number of trades appended. The CLI prints that number. Corporate-action population stays deferred to #56 (Flex Web Service); the table stays empty and nothing reads it in a way that breaks when empty.

**Tech Stack:** Python 3.12, DuckDB, Typer, pytest, mypy --strict, ruff.

**Spec:** GitHub issue nicolas-ricc/damodaran#27 (body, triage brief, and the "corporate actions need IBKR Flex" addendum).

## Global Constraints

- Type hints everywhere; `uv run mypy src` (strict) and `uv run ruff check .` clean.
- Unit tests use a mocked `IbkrClient`; no live TWS socket in tests.
- `trades` is append-only; de-dup on broker execution id (`exec_id`).
- Watermark is `max(executed_at)` from `trades`, passed as `since` to the client's `trades()`.
- Corporate actions: table exists, population deferred (#56); absence of data must not crash.
- Out of scope: reconciling trades against positions, realized P&L (#29), event emission (#28).
- Commits: Conventional Commits.

## Review Focus

1. Running `bot portfolio` twice on the same day: the second run must append zero trades and leave the count unchanged (TWS re-returns the session's fills). Pinned in Task 1.
2. A day with no executions at all: run must succeed with `trades_inserted == 0`. Pinned in Task 1.
3. A fill for a symbol that is no longer a position (bought and sold the same day): it must still be recorded, because trades are independent of the snapshot. Pinned in Task 1.
4. A second run on a later day sends the stored watermark as `since`, not `None`. Pinned in Task 1.
5. `trades()` raising (socket dropped mid-run): the error propagates (no swallowing) and the snapshot already written for the day stays; a re-run is idempotent for both tables. Not separately tested: propagation is the default behaviour and idempotency is covered by item 1 and the existing snapshot tests.

---

### Task 1: `run_portfolio` syncs trades

**Files:**
- Modify: `src/bot/portfolio/command.py`
- Test: `tests/integration/test_portfolio_command.py`

**Interfaces:**
- Consumes: `bot.portfolio.trades.sync_trades(conn, client: TradeSource) -> TradeSyncSummary` (fields `accounts: int`, `inserted: int`); `bot.portfolio.trades.TradeSource`; `bot.portfolio.sync.PortfolioSource`.
- Produces:
  - `bot.portfolio.command.PortfolioClient(PortfolioSource, TradeSource, Protocol)` — the client type `run_portfolio` now takes.
  - `PortfolioRunResult.trades_inserted: int` — new field (place it after `events`).

- [ ] **Step 1: Write the failing tests**

In `tests/integration/test_portfolio_command.py`, give `_FakeIbkrClient` a `fills` constructor argument (default empty) and a `trades()` method that records the `since` it got and returns the fills unfiltered (the sync layer de-dupes):

```python
    def __init__(
        self,
        positions: list[PortfolioPosition],
        cash: list[CashBalance],
        fills: list[TradeExecution] | None = None,
    ) -> None:
        self._positions = positions
        self._cash = cash
        self._fills = fills or []
        self.connected = False
        self.since_calls: list[datetime | None] = []

    def trades(
        self, account_id: str, since: datetime | None = None
    ) -> list[TradeExecution]:
        self.since_calls.append(since)
        return list(self._fills)
```

Add a `_fill(exec_id, symbol, when)` helper building a `TradeExecution` for account `DU1`, and these tests:

```python
def test_run_portfolio_appends_new_trades(conn, tmp_path):
    fills = [
        _fill("E1", "AAPL", datetime(2026, 6, 1, 14, 0, tzinfo=UTC)),
        _fill("E2", "TSLA", datetime(2026, 6, 1, 15, 0, tzinfo=UTC)),  # not a position
    ]
    client = _FakeIbkrClient([_position("AAPL", 1, 10.0, 100.0)], [], fills)
    result = run_portfolio(conn, client, reports_dir=tmp_path, today=TODAY)
    assert result.trades_inserted == 2
    rows = conn.execute("SELECT exec_id FROM trades ORDER BY exec_id").fetchall()
    assert rows == [("E1",), ("E2",)]
    assert client.since_calls == [None]


def test_run_portfolio_same_day_rerun_does_not_duplicate_trades(conn, tmp_path):
    fills = [_fill("E1", "AAPL", datetime(2026, 6, 1, 14, 0, tzinfo=UTC))]
    run_portfolio(conn, _FakeIbkrClient([], [], fills), reports_dir=tmp_path, today=TODAY)
    again = _FakeIbkrClient([], [], fills)
    result = run_portfolio(conn, again, reports_dir=tmp_path, today=TODAY)
    assert result.trades_inserted == 0
    assert conn.execute("SELECT count(*) FROM trades").fetchone() == (1,)
    assert again.since_calls == [datetime(2026, 6, 1, 14, 0, tzinfo=UTC)]


def test_run_portfolio_without_fills_records_no_trades(conn, tmp_path):
    result = run_portfolio(conn, _FakeIbkrClient([], []), reports_dir=tmp_path, today=TODAY)
    assert result.trades_inserted == 0
    assert conn.execute("SELECT count(*) FROM trades").fetchone() == (0,)
```

(Annotate parameters with the types the file already uses: `duckdb.DuckDBPyConnection`, `Path`.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest -q tests/integration/test_portfolio_command.py`
Expected: the three new tests FAIL with `AttributeError: 'PortfolioRunResult' object has no attribute 'trades_inserted'`.

- [ ] **Step 3: Implement**

In `src/bot/portfolio/command.py`:

```python
from typing import TYPE_CHECKING, Protocol

from bot.portfolio.sync import PortfolioSource, sync_portfolio
from bot.portfolio.trades import TradeSource, sync_trades


class PortfolioClient(PortfolioSource, TradeSource, Protocol):
    """The read-only IBKR slice a full portfolio run needs: snapshot + fills."""
```

Add `trades_inserted: int` to `PortfolioRunResult` after `events`. Change `run_portfolio`'s `client` annotation to `PortfolioClient`. After step 1 (`sync_portfolio(...)`), add:

```python
    # 2. Append the executions newer than the stored watermark (de-duped).
    trades = sync_trades(conn, client)
```

renumber the following step comments, pass `trades_inserted=trades.inserted` to the result, add `trades_inserted=trades.inserted` to the `portfolio_report_written` log call, and update the module docstring's numbered list (new step 2: trades via `sync_trades`) and the `client` arg doc.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest -q tests/integration/test_portfolio_command.py && uv run mypy src && uv run ruff check .`
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add src/bot/portfolio/command.py tests/integration/test_portfolio_command.py
git commit -m "feat(#27): bot portfolio appends new IBKR executions to trades"
```

### Task 2: CLI reports the trades appended

**Files:**
- Modify: `src/bot/cli.py` (the `portfolio` command, ~line 533-569)
- Test: `tests/unit/test_cli_portfolio.py`

**Interfaces:**
- Consumes: `PortfolioRunResult.trades_inserted: int` from Task 1.

- [ ] **Step 1: Write the failing test**

Give `_FakeIbkrClient` in `tests/unit/test_cli_portfolio.py` a `trades(self, account_id: str, since: datetime | None = None) -> list[TradeExecution]` returning one `TradeExecution` (account `DU1`, exec_id `E1`, symbol `AAPL`, executed `2026-06-01 14:00 UTC`). Add:

```python
def test_portfolio_records_trades(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _env(tmp_path, monkeypatch)
    result = CliRunner().invoke(app, ["portfolio"])
    assert result.exit_code == 0, result.output
    assert "Recorded 1 new trade(s)" in result.output
    conn = connect(tmp_path / "bot.duckdb")
    assert conn.execute("SELECT exec_id FROM trades").fetchall() == [("E1",)]
    conn.close()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest -q tests/unit/test_cli_portfolio.py`
Expected: new test FAILS on the missing "Recorded" line.

- [ ] **Step 3: Implement**

In `portfolio()` in `src/bot/cli.py`, after the "Synced snapshot" echo:

```python
    typer.echo(f"Recorded {result.trades_inserted} new trade(s)")
```

and add "appends the executions newer than the last stored one to ``trades``" to the command docstring.

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest -q tests/unit/test_cli_portfolio.py && uv run mypy src && uv run ruff check .`
Expected: PASS, clean.

- [ ] **Step 5: Commit**

```bash
git add src/bot/cli.py tests/unit/test_cli_portfolio.py
git commit -m "feat(#27): bot portfolio prints the trades it recorded"
```

### Task 3: Docs and status plan follow the code

**Files:**
- Modify: `src/bot/portfolio/sync.py` (module docstring: trades are no longer "out of scope (#27)"; CLI wiring is done)
- Modify: `src/bot/portfolio/__init__.py` (package docstring: drop "(later) trades")
- Modify: `docs/plano/estado.py` (entries `ibkr-trades`, `tablas`, and the BRECHAS line "Cree que M5 sincroniza operaciones.")

- [ ] **Step 1: Edit**

- `sync.py` docstring last sentence → "Diffing snapshots and trade sync live beside this module (#28, #27); CLI wiring is in :mod:`bot.portfolio.command` (#29)."
- `__init__.py` → `"""M5 — portfolio sync, snapshots, trades and diffing."""`
- `estado.py`:
  - `ibkr-trades`: state `"hecho"`, evidence `"portfolio/trades.py:63; portfolio/command.py"`, note: "run_portfolio lo llama en cada bot portfolio, después del snapshot: marca de agua incremental por cuenta, deduplicación por id de ejecución. Tests unitarios con cliente simulado y de integración sobre run_portfolio. Solo ve los fills de la sesión de TWS: el historial se acumula corrida a corrida."
  - `tablas` note: "Catorce se escriben; corporate_actions sigue sin escritor (Flex, #56). Tres columnas quedan siempre nulas: reinvestment_rate, payout_ratio e isin."
  - Delete the BRECHAS tuple `("Cree que M5 sincroniza operaciones.", ...)`.
  - Leave `AUDITADO_EN` / `AUDITADO_EL` alone: this is a targeted update of the entries this change touched, not a full re-audit.

- [ ] **Step 2: Verify**

Run: `python3 docs/plano/build.py && python3 docs/plano/build_estado.py && uv run pytest -q && uv run mypy src && uv run ruff check .`
Expected: both builds succeed (outputs are gitignored), suite green.

- [ ] **Step 3: Commit**

```bash
git add src/bot/portfolio/sync.py src/bot/portfolio/__init__.py docs/plano/estado.py
git commit -m "docs(#27): status plan and docstrings reflect wired trade sync"
```
