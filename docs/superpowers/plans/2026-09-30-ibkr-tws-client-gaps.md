# IBKR TWS client — closing the #25 gaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the existing read-only `IbkrClient` (`src/bot/ingest/ibkr.py`, landed in 87f9ca5) fully in line with the authoritative #25 brief, and record the ADR as implemented.

**Architecture:** The client already exists and passes its 14 unit tests. This plan does not restructure it. It pins the connection-lifecycle behaviour the brief requires (reconnect after a drop, and connection errors surface to the caller), fixes the timezone handling of `trades(..., since=...)`, adds a guard that `ibapi` never becomes a dependency, and marks ADR 0004 as implemented, as CONTEXT.md requires.

**Tech Stack:** Python 3.12, `ib_async` 2.x (`ib-async>=2.1.0`), pytest, mypy `--strict`, ruff.

**Spec:** GitHub issue nicolas-ricc/damodaran#25, specifically the comment "Brief superseded — switched from Client Portal API to TWS API". That comment is authoritative; the original issue body (Client Portal / Docker / OAuth) is obsolete. Binding docs: `CONTEXT.md`, `docs/adr/0004-tws-api-via-ib-async.md`.

## Audit of the brief against master

| Acceptance criterion | State on master | Plan |
|---|---|---|
| `ib_async` is a dependency and `ibapi` is not | Met (`pyproject.toml`, `uv.lock`) but unguarded | Task 3 adds a regression test |
| Configurable host/port/clientId, default `127.0.0.1:7496`; four read-only methods; no order surface | Met, and tested | — |
| Connection lifecycle (connect/disconnect, reconnect on drop) lives in the client | Lazy reconnect exists (`_ensure_connected`) but is untested; the connect-failure path is untested | Task 1 |
| README: TWS running and logged in, host/port/clientId, "Read-Only API" | Met (`README.md` "Portfolio sync — Interactive Brokers (M5)") | — |
| Unit tests against mocked `ib_async` | Met | — |
| Manual smoke: `accounts()` against the live TWS | Human step, cannot run in CI | Listed as manual verification in the PR |
| mypy --strict + ruff clean | Met | Kept green by every task |

Additional defect found in the audit: `trades()` pushes `since` into `ExecutionFilter.time` as `since.strftime("%Y%m%d-%H:%M:%S")`, taking the wall-clock time of whatever zone `since` carries. IBKR's reference for `ExecutionFilter.Time` only says "Time from which the executions will be returned yyyymmdd hh:mm:ss. Only those executions reported after the specified time will be returned", and states no timezone. Whenever the zone TWS applies differs from the zone of `since`, the server-side pre-filter starts too late and silently drops fills that the exact client-side filter would have kept. A naive `since` raises a bare `TypeError` deep inside the comparison with the UTC-aware `execution.time`. Task 2 fixes both.

## Global Constraints

- Use `ib_async` (PyPI `ib-async>=2.1.0`). Never depend on IBKR's `ibapi`.
- Defaults are `127.0.0.1:7496` with clientId `1`. All three are configurable through `BOT_IBKR_HOST`, `BOT_IBKR_PORT` and `BOT_IBKR_CLIENT_ID`.
- The public method signatures `accounts()`, `positions(account_id)`, `cash_balances(account_id)` and `trades(account_id, since)` stay identical, because #26–#29 (`portfolio/sync.py`, `portfolio/trades.py`) depend on them.
- There is no order placement, modification or cancellation surface.
- CI never opens a socket. Tests use the `FakeIB` in `tests/unit/test_ibkr_client.py`.
- `uv run ruff check . && uv run mypy src` stays clean. The full suite (`uv run pytest -q`) stays green.

## Review Focus

1. TWS is not running or refuses the socket: `ib.connect` raises `ConnectionRefusedError`. The caller must see that error and must not get an empty list (Task 1).
2. TWS restarts or the socket drops between two calls: the next read reconnects transparently with the same host/port/clientId and `readonly=True` (Task 1).
3. `since` is timezone-aware but not UTC (for example `-03:00`, the maintainer's zone): no fill after the instant may be lost, and the boundary stays exact (Task 2).
4. `since` is naive: the method fails fast with a clear `ValueError`, before any socket call (Task 2).
5. A future dependency bump pulls `ibapi` in transitively: CI must fail (Task 3).

---

### Task 1: Pin the connection lifecycle (reconnect after a drop, connect errors propagate)

**Files:**
- Test: `tests/unit/test_ibkr_client.py` (append)
- Modify: `src/bot/ingest/ibkr.py`, only if a test exposes a gap. The expectation is that `_ensure_connected` already satisfies both tests.

**Interfaces:**
- Consumes: `IbkrClient(host, port, client_id, *, ib)`, `FakeIB` (existing test double).
- Produces: nothing new.

- [ ] **Step 1: Write the tests**

```python
def test_reconnects_after_connection_drop(fake_ib: FakeIB) -> None:
    """If TWS drops the socket between calls, the next read reconnects transparently."""
    fake_ib._managed = ["U1"]
    client = IbkrClient(host="127.0.0.1", port=7497, client_id=5, ib=fake_ib)
    assert client.accounts() == ["U1"]

    fake_ib._connected = False  # TWS restarted / socket dropped
    fake_ib.connect_args = None

    assert client.accounts() == ["U1"]
    assert fake_ib.connect_args == {
        "host": "127.0.0.1",
        "port": 7497,
        "clientId": 5,
        "readonly": True,
    }


def test_connect_failure_propagates(fake_ib: FakeIB) -> None:
    """TWS not running: the socket error reaches the caller instead of an empty result."""

    def refuse(**kwargs: Any) -> None:
        raise ConnectionRefusedError("TWS not listening")

    fake_ib.connect = refuse  # type: ignore[method-assign]
    client = IbkrClient(ib=fake_ib)
    with pytest.raises(ConnectionRefusedError):
        client.accounts()
```

- [ ] **Step 2: Run them**

Run: `uv run pytest tests/unit/test_ibkr_client.py -q -k "drop or failure"`
Expected: PASS. Both behaviours already exist; these tests pin them. If either fails, fix `IbkrClient._ensure_connected` / `connect` minimally so it passes.

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_ibkr_client.py
git commit -m "test(#25): pin IbkrClient reconnect-on-drop and connect-failure behaviour"
```

### Task 2: Filter `trades(since=...)` client-side only and reject a naive `since`

**Files:**
- Modify: `src/bot/ingest/ibkr.py`: `IbkrClient.trades`, `_build_exec_filter`, and remove `_EXEC_FILTER_TIME_FMT`.
- Test: `tests/unit/test_ibkr_client.py`: append new tests and update `test_trades_passes_account_to_exec_filter`.

**Interfaces:**
- Consumes: existing `IbkrClient.trades(self, account_id: str, since: datetime | None = None) -> list[TradeExecution]`. The signature is unchanged.
- Produces: same signature. A naive `since` now raises `ValueError`. `_build_exec_filter(account_id: str) -> object` no longer takes `since`.

- [ ] **Step 1: Write the failing tests**

Replace the body of `test_trades_passes_account_to_exec_filter` so that it asserts the account is scoped server-side and the time is not:

```python
def test_trades_passes_account_to_exec_filter(client: IbkrClient, fake_ib: FakeIB) -> None:
    client.trades("U1", since=datetime(2026, 1, 1, tzinfo=UTC))
    assert fake_ib.exec_filter is not None
    assert fake_ib.exec_filter.acctCode == "U1"
    # TWS documents no timezone for ExecutionFilter.time, so the since boundary is
    # applied client-side only; a server-side time could silently drop fills.
    assert fake_ib.exec_filter.time == ""
```

Append:

```python
def test_trades_since_non_utc_keeps_exact_boundary(client: IbkrClient, fake_ib: FakeIB) -> None:
    buenos_aires = timezone(timedelta(hours=-3))
    before = datetime(2026, 3, 1, 12, 59, tzinfo=UTC)
    after = datetime(2026, 3, 1, 13, 1, tzinfo=UTC)
    fake_ib._fills = [
        SimpleNamespace(
            contract=_contract(conId=1, symbol="X", secType="STK", currency="USD"),
            execution=SimpleNamespace(
                execId=exec_id, acctNumber="U1", side="BOT", shares=1.0, price=1.0,
                time=t, permId=1,
            ),
            time=t,
        )
        for exec_id, t in (("before", before), ("after", after))
    ]
    out = client.trades("U1", since=datetime(2026, 3, 1, 10, 0, tzinfo=buenos_aires))
    assert [t.exec_id for t in out] == ["after"]


def test_trades_rejects_naive_since(client: IbkrClient, fake_ib: FakeIB) -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        client.trades("U1", since=datetime(2026, 3, 1))
    assert not fake_ib.isConnected()  # failed before touching the socket
```

(Add `timedelta, timezone` to the existing `from datetime import ...` line.)

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run pytest tests/unit/test_ibkr_client.py -q -k "exec_filter or non_utc or naive"`
Expected: `test_trades_passes_account_to_exec_filter` FAILS (time is `20260101-00:00:00`), and `test_trades_rejects_naive_since` FAILS (no `ValueError`). `test_trades_since_non_utc_keeps_exact_boundary` already passes; it guards the client-side boundary.

- [ ] **Step 3: Implement**

In `IbkrClient.trades`, as the first statement:

```python
        if since is not None and since.tzinfo is None:
            raise ValueError("since must be timezone-aware")
```

Change the call to `exec_filter = _build_exec_filter(account_id)`, and change the helper to:

```python
def _build_exec_filter(account_id: str) -> object:
    """Build an ``ib_async.ExecutionFilter`` scoped to the account."""
    from ib_async import ExecutionFilter

    return ExecutionFilter(acctCode=account_id)
```

Delete `_EXEC_FILTER_TIME_FMT` and its comment. Update the `trades` docstring: `since` is applied client-side only (exact, timezone-aware), because TWS documents no timezone for `ExecutionFilter.time`, and it must be timezone-aware.

- [ ] **Step 4: Run the file**

Run: `uv run pytest tests/unit/test_ibkr_client.py -q && uv run mypy src && uv run ruff check .`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add src/bot/ingest/ibkr.py tests/unit/test_ibkr_client.py
git commit -m "fix(#25): apply trades() since boundary client-side only; reject naive since"
```

### Task 3: Guard the dependency rule and mark ADR 0004 implemented

**Files:**
- Create: `tests/unit/test_ibkr_dependencies.py`
- Modify: `docs/adr/0004-tws-api-via-ib-async.md` (Status section)

**Interfaces:**
- Consumes: `pyproject.toml`, `uv.lock` at the repo root (`Path(__file__).resolve().parents[2]`).
- Produces: nothing.

- [ ] **Step 1: Write the test**

```python
"""The IBKR client speaks the TWS wire protocol through ib_async only (ADR 0004)."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _locked_packages() -> set[str]:
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    return {pkg["name"] for pkg in lock["package"]}


def test_ib_async_is_a_declared_dependency() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert any(dep.startswith("ib-async") for dep in project["dependencies"])


def test_ibapi_is_not_locked() -> None:
    assert "ib-async" in _locked_packages()
    assert "ibapi" not in _locked_packages()
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/unit/test_ibkr_dependencies.py -q`
Expected: PASS (the rule holds today; this is a regression guard).

- [ ] **Step 3: Update ADR 0004's status**

Replace the Status body with:

```markdown
Accepted (2026-08-09). Supersedes [ADR 0003](0003-client-portal-api-over-tws.md).
Implemented (2026-09-30, #25: read-only client in `src/bot/ingest/ibkr.py`,
configured by `BOT_IBKR_HOST`/`BOT_IBKR_PORT`/`BOT_IBKR_CLIENT_ID`;
`tests/unit/test_ibkr_dependencies.py` keeps `ibapi` out of the lock file).
```

`docs/plano/estado.py` needs no change: the `ibkr-pos` row is already `hecho`, and the `a-medias` status of `ibkr` comes from trade wiring and corporate actions, both outside #25.

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_ibkr_dependencies.py docs/adr/0004-tws-api-via-ib-async.md
git commit -m "docs(#25): mark ADR 0004 implemented; guard ibapi out of the lock"
```

## Assumptions

Technical decisions taken during plan grilling. Each one satisfies the brief whichever way it goes, and each is listed in the PR.

- **The `since` boundary is client-side only** (Task 2). IBKR's `ExecutionFilter.Time` reference states no timezone, and the TWS docs portal could not be reached to settle it. Rejected alternative: convert `since` to UTC for the server filter. That would be correct only if TWS reads the string as UTC, and it drops fills otherwise. The cost of the chosen option is negligible, because the socket only returns the recent session's executions (ADR 0004, "Trade history is session-limited").
- **A naive `since` raises `ValueError`.** Rejected alternative: assume UTC. The only production caller, `portfolio/trades.py:89`, passes a UTC-aware watermark (`_watermark` re-attaches `UTC`), so nothing breaks.
- **Connect errors propagate unchanged, whatever their type** (`ConnectionRefusedError`, `TimeoutError`, `ConnectionError` for error 326 "client id in use"). `ib_async`'s `connectAsync` already calls `self.disconnect()` in its `except BaseException` path, so the client stays reconnectable. No retry or backoff is added: the brief asks for reconnect on drop, not retry policy.
- **"CI never opens a socket" is a convention.** It is enforced by injecting `FakeIB` through `IbkrClient(..., ib=...)`, not by a socket guard in `conftest.py`.
- **The manual verification in the PR covers `accounts()` and `trades(since=...)`** against the live TWS.
- **The dependency test reads `uv.lock`**, which is committed (`git ls-files uv.lock`) and is `version = 1` with top-level `[[package]]` tables.

## Out of scope (per the brief)

- Order placement, modification or cancellation.
- DB persistence (#26) and corporate actions (Flex, #27).
- The live `accounts()` smoke test: a human step, listed as manual verification in the PR.

## Grilling

Rounds run: 2 (the griller ran as `fable`). Questions: 16 in round 1 and 16 in round 2, 32 in total.

Sources used for the answers:
- **CODE:** 22. Examples: `src/bot/ingest/ibkr.py:183-185` (`_ensure_connected` consults `self._ib.isConnected()` on every call); `ibkr.py:251` (`executed_at < since` skips, so a fill at exactly `since` is kept and the watermark's own fill is re-seen and deduped on `exec_id`, per `portfolio/trades.py:1-8`); `tests/unit/test_ibkr_client.py:41-72` (`FakeIB` defines `_connected`, `_managed`, `connect_args`, `exec_filter=None`, and `connect` records kwargs and sets `_connected=True`); ib_async `ib.py:410-412` (`isConnected` -> `client.isReady()`); ib_async `connectAsync` (`except BaseException: self.disconnect(); raise`); ib_async `objects.py:86-94` (`ExecutionFilter.time: str = ""`, the same value the existing `test_trades_without_since_returns_all` already sends); ib_async `decoder.py:468-474` (`ex.time` is a tz-aware `datetime`); `pyproject.toml` `[tool.mypy] packages = ["bot"]` (tests are not type-checked, so the `type: ignore` comments in tests are inert); a grep for `.trades(` finds one production caller, `portfolio/trades.py:89`, passing an aware watermark; a grep for `_EXEC_FILTER_TIME_FMT` / `_build_exec_filter` finds uses only in `ibkr.py`; `docs/plano/estado.py:55-60` (the `ibkr-pos` row is `hecho`, `ibkr-trades` is `muerto`, `ibkr-corp` is `falta`).
- **DOC:** 6. CONTEXT.md, "If a stage implements an ADR, say so in the ADR"; ADR 0006 Status format "Accepted (date). Implemented (date, where)", which the ADR 0004 edit copies; ADR 0004 "Trade history is session-limited"; IBKR `ExecutionFilter.Time` reference (states no timezone).
- **ISSUE:** 2. Owner's brief: "Do **not** depend on IBKR's `ibapi`"; "Connection lifecycle (connect/disconnect, reconnect on drop) lives in the client".
- **NO SOURCE:** 2 technical assumptions (see below), 0 spec ambiguities, 0 out of scope.

Assumptions added: the six in `## Assumptions`, plus the two below.
- Error 326 ("client id in use"): `ib_async` has no special handling for it (no match in its source). Whether it arrives as a raised error or asynchronously, the client adds no handling, because retry policy is not asked for.
- Manual verification pass criterion: with TWS logged in, `accounts()` prints the real account ids, and `trades(acct, since=<today 00:00 local, aware>)` lists today's fills, if any. The live run is not used to settle how TWS interprets `ExecutionFilter.time`, because Task 2 removes the dependency on it.

Issues opened: none.

Status: ok.
