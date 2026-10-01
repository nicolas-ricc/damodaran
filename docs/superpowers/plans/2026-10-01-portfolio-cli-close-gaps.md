# `bot portfolio` — close the remaining #29 gaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the already-wired `bot portfolio` command (da2e068) up to issue #29's acceptance criteria: an empty `alerts.md` on quiet days, a strict integration test, a clean `ruff check .`, and a clean CLI failure when TWS is unreachable.

**Architecture:** No new modules. `bot.portfolio.report` keeps its shape (pure `build_report` reader + pure Jinja2 renderers); only `render_alerts` and `alerts.md.j2` change. `bot.cli.portfolio` catches connection failures at the composition root.

**Tech Stack:** Python 3.12, Typer, DuckDB, Jinja2, pytest, ruff, mypy --strict.

**Spec:** GitHub issue #29 (body + "Agent Brief" comment) and `docs/superpowers/specs/2026-05-25-investment-bot-design.md` §8.3–8.4.

## Global Constraints

- `alerts.md` — "only events emitted today (empty file if none)"; brief: "empty content, file present"; spec §8.4: "solo eventos nuevos (vacío si no hay)".
- `portfolio.md` — "full state (positions, P&L, concentration, suggested reviews)".
- "Reports rendered via Jinja2 templates"; "Keep rendering pure: data in → string/file out".
- "Reuse `sync_portfolio` (#26) and `compute_events` (#28); the CLI orchestrates, it does not re-implement diff logic."
- "mypy --strict + ruff clean": `uv run ruff check . && uv run mypy src`.
- Out of scope: sending notifications (#32), new event types (#28), same-day rerun duplicating events (#83), IBKR symbol vs ticker (#84).

## Decisions (technical assumptions, declared)

- **Empty means zero bytes.** With no events `render_alerts` returns `""`; the file is still written. A notifier (#32, spec §10 "módulo notifier aparte que lea alerts.md") can then use "file is empty" as "nothing to send".
- **TWS unreachable** = `ConnectionError` (incl. `ConnectionRefusedError`) or `TimeoutError` raised from `IbkrClient.connect`. Only those are caught; disk `OSError`s still surface.

## Assumptions

- **Empty alerts = zero bytes** rather than a header with a "no events" line (rejected: keep the header). Sourced by the issue ("empty file if none"), the brief ("empty content, file present") and spec §8.4 ("vacío si no hay"); the literal reading lets the notifier (#32) treat an empty file as "nothing to send".
- **TWS-unreachable handling** catches only `ConnectionError` (incl. `ConnectionRefusedError`) and `TimeoutError` around `run_portfolio` (rejected: catch `OSError`, which would swallow disk errors). ib_async raises exactly these (`ib_async/ib.py` `connectAsync`: `raise ConnectionError(...)`, `asyncio.TimeoutError` is builtin `TimeoutError` on Python >= 3.11; the repo pins >= 3.12). All IBKR calls happen in `run_portfolio` steps 1-2 (`sync_portfolio`, `sync_trades`), before any file is written, so a connection failure leaves no report behind.
- **Suggested reviews stay concentration-only** (rejected: derive them from today's §8.3 events). No source says which events suggest a review or with what action; that is a product decision, so it moved to #86.
- **`AUDITADO_EN` / `AUDITADO_EL` are not bumped** (rejected: stamp the new HEAD). `docs/plano/README.md` ties them to a full re-audit of the code; this change re-checks one entry, so stamping would claim an audit that did not happen. `build_estado.py` only warns.
- **Fallback text for "no reviews" stays as it is**; no wording change.
- **The empty case lives in `render_alerts`, not in the template** (rejected: keep an `{% if events %}` wrapper in the template). The template is private to `render_alerts`, the only entry point, so it renders only the populated case and there is one place that decides "no events → empty".

## Review Focus

1. A quiet day after a busy one: `alerts.md` must end up empty even if a stale file already sits at that path — pinned in Task 2's integration test.
2. TWS down: exit code 1, one-line message naming host:port, no traceback, no report files written — pinned in Task 4.
3. `--history` on the second run lists both snapshot days — pinned in Task 3.
4. A run whose first snapshot opens every position must show each opening in `alerts.md` as a table row, not just mention the ticker — pinned in Task 3.
5. A concentrated book must name the over-threshold position under Suggested reviews — pinned in Task 3.

---

### Task 1: ruff clean

**Files:**
- Modify: `tests/integration/test_portfolio_command.py:9-25`
- Modify: `tests/unit/test_portfolio_events.py:8-29`

- [ ] **Step 1:** Run `uv run ruff check .` — expected: 2 × I001 (the `from bot.portfolio.marks import …` line sits in the third-party block).
- [ ] **Step 2:** Move that import into the first-party block in both files (`uv run ruff check --fix tests/integration/test_portfolio_command.py tests/unit/test_portfolio_events.py` does exactly this).
- [ ] **Step 3:** `uv run ruff check . && uv run mypy src` — expected: clean.
- [ ] **Step 4:** Commit `style(#29): sort imports so ruff check passes`.

### Task 2: `alerts.md` is empty when there are no events

**Files:**
- Modify: `src/bot/portfolio/report.py` (`render_alerts`)
- Modify: `src/bot/reporting/templates/alerts.md.j2` (drop the `{% else %}` branch)
- Modify: `src/bot/portfolio/command.py` (module docstring only)
- Test: `tests/unit/test_portfolio_report.py`, `tests/integration/test_portfolio_command.py`

**Interfaces:** `render_alerts(events: list[Event], snapshot_date: date, *, generated_on: date | None = None) -> str` — unchanged signature; returns `""` when `events` is empty.

- [ ] **Step 1: failing tests.** Replace `test_render_alerts_empty_is_present_but_quiet` with:

```python
def test_render_alerts_empty_when_no_events() -> None:
    assert render_alerts([], D2, generated_on=D2) == ""
```

In the integration test `test_alerts_present_but_empty_when_no_events`, replace the body assertions with `assert alerts_md.read_text() == ""`. Add:

```python
def test_quiet_day_writes_empty_alerts_after_busy_day(
    conn: duckdb.DuckDBPyConnection, tmp_path: Path
) -> None:
    busy, quiet = date(2026, 5, 31), TODAY
    run_portfolio(
        conn, _diversified_client(), reports_dir=tmp_path, today=busy, analyze_fn=_no_analyze
    )
    assert (tmp_path / busy.isoformat() / "alerts.md").read_text() != ""
    alerts_md = tmp_path / quiet.isoformat() / "alerts.md"
    alerts_md.parent.mkdir(parents=True)
    alerts_md.write_text("stale content from an earlier run")

    run_portfolio(
        conn, _diversified_client(), reports_dir=tmp_path, today=quiet, analyze_fn=_no_analyze
    )

    assert alerts_md.read_text() == ""
```

(`_diversified_client()` is used because AAPL at ~83% in `_client()` fires `concentration` every day.)

- [ ] **Step 2:** `uv run pytest tests/unit/test_portfolio_report.py tests/integration/test_portfolio_command.py -q` — expected FAIL (header present).
- [ ] **Step 3: implement.** In `render_alerts`, return `""` early when `not events`; update its docstring ("empty string when there are no events — the file is still written, empty"). In `alerts.md.j2` remove the `{% if events %}…{% else %}No events detected today.{% endif %}` wrapper so the template only renders the populated case. Update the `command.py` module docstring line about `alerts.md`.
- [ ] **Step 4:** rerun tests — PASS.
- [ ] **Step 5:** Commit `fix(#29): write alerts.md empty on days without events`.

### Task 3: the full-cycle integration test pins every expected section

AC: "Integration test: full cycle against a **mocked `IbkrClient`** asserts both `.md` files are produced with the expected sections." Today the test accepts alternatives (`"## Profit & loss" in body or "## Profit and loss" in body`) and never checks `## Suggested reviews`, the alerts table or the history rows.

**Files:**
- Test: `tests/integration/test_portfolio_command.py`

- [ ] **Step 1: tighten** `test_portfolio_writes_both_reports`:

```python
    body = portfolio_md.read_text()
    for heading in (
        "# Portfolio — 2026-06-01",
        "## Positions",
        "## Profit & loss",
        "## Concentration",
        "## Suggested reviews",
    ):
        assert heading in body
    assert "AAPL" in body
    assert "MSFT" in body
    # AAPL is ~83% of the book: the concentration review must name it.
    assert "- **AAPL** is" in body

    alerts = alerts_md.read_text()
    assert "# Alerts — 2026-06-01" in alerts
    assert "| Type | Ticker | Details |" in alerts
    # First snapshot -> every position opens.
    assert "| position_opened | AAPL |" in alerts
    assert "| position_opened | MSFT |" in alerts
```

and `test_history_and_concentration_flags`:

```python
    body = result.portfolio_path.read_text()
    assert "## P&L history" in body
    assert "## Concentration breakdown" in body
    # Both snapshot days appear in the time series.
    assert "| 2026-05-31 |" in body
    assert "| 2026-06-01 |" in body
```

- [ ] **Step 2:** `uv run pytest tests/integration/test_portfolio_command.py -q` — these are assertions on existing behaviour; they must PASS. If one fails, it is a real gap: fix the template, not the assertion.
- [ ] **Step 3:** Commit `test(#29): pin every expected report section in the integration test`.

### Task 4: clean CLI failure when TWS is unreachable

**Files:**
- Modify: `src/bot/cli.py` (`portfolio` command)
- Test: `tests/unit/test_cli_portfolio.py`

- [ ] **Step 1: failing test:**

```python
def test_portfolio_reports_unreachable_tws(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reports_dir = _env(tmp_path, monkeypatch)

    def _refuse(self: _FakeIbkrClient) -> None:
        raise ConnectionRefusedError(111, "Connect call failed")

    monkeypatch.setattr(_FakeIbkrClient, "connect", _refuse)
    monkeypatch.setenv("BOT_IBKR_PORT", "4002")

    result = CliRunner().invoke(app, ["portfolio"])

    assert result.exit_code == 1
    assert "Cannot reach TWS / IB Gateway at 127.0.0.1:4002" in result.output
    assert not list(reports_dir.glob("*/*.md"))
```

(`src/bot/config.py:14` sets `env_prefix="BOT_"`; lines 52-56 define `ibkr_host` (default `127.0.0.1`) and `ibkr_port`. `_env()` sets no IBKR variable, and it already swaps `bot.cli.IbkrClient` for the fake (`tests/unit/test_cli_portfolio.py:95`), whose `connect` is what `sync_portfolio` calls first (`src/bot/portfolio/sync.py:162`).)
- [ ] **Step 2:** run — FAIL (exception propagates, exit code 1 but message missing).
- [ ] **Step 3: implement** in `portfolio()`: wrap the `run_portfolio(...)` call:

```python
    except (ConnectionError, TimeoutError) as exc:
        typer.echo(
            f"Cannot reach TWS / IB Gateway at {settings.ibkr_host}:{settings.ibkr_port}: {exc}. "
            "Start it with the API enabled, or set BOT_IBKR_HOST / BOT_IBKR_PORT.",
            err=True,
        )
        raise typer.Exit(code=1) from exc
```

- [ ] **Step 4:** run — PASS.
- [ ] **Step 5:** Commit `fix(#29): exit cleanly when TWS is unreachable`.

### Task 5: plans (estado / plano)

**Files:**
- Modify: `docs/plano/estado.py` (`rep-portfolio` entry only; `AUDITADO_EN` / `AUDITADO_EL` stay as they are, see Assumptions)
- Regenerate: `python3 docs/plano/build.py && python3 docs/plano/build_estado.py`

- [ ] **Step 1:** Update the `rep-portfolio` evidence text: summary, positions, P&L, concentration and suggested reviews (over-threshold positions), optional history (`--history`) and breakdown (`--concentration`); `alerts.md` always written, and empty (zero bytes) on a day without events; `bot portfolio` exits 1 with a one-line message when TWS is unreachable. Keep the evidence pointer at `portfolio/report.py` `build_report`.
- [ ] **Step 2:** Run both builds; they must succeed.
- [ ] **Step 3:** Commit `docs(#29): record portfolio report state in the plans`.

## Grilling

- Rounds: 2 (griller model: fable).
- Round 1: 18 questions. Sources: CODE 14, ISSUE 3, DOC 3 (some answers cite more than one), NO SOURCE 2. Q2 ("are suggested reviews derived from events?") had no source and was a product decision, so event-driven reviews left the plan and moved to #86 (out of scope). Q11 (inconsistent ordering rule) went away with that task. Q17 (`AUDITADO_*`) became a technical assumption.
- Round 2: 17 questions. Sources: CODE 14, ISSUE 1, DOC 3, NO SOURCE 1 (Q14, where the empty case lives: technical assumption).
- Assumptions: empty alerts = zero bytes; catch only `ConnectionError`/`TimeoutError`; suggested reviews stay concentration-only; `AUDITADO_*` not bumped; "no reviews" text unchanged; the empty case lives in `render_alerts`.
- Issues opened: #86 (suggested reviews and a detected-events section from §8.3 events).
- Status: ok.
