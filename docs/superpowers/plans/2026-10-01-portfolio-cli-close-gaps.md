# `bot portfolio` — close the remaining #29 gaps Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the already-wired `bot portfolio` command (da2e068) up to issue #29's acceptance criteria: an empty `alerts.md` on quiet days, suggested reviews driven by today's events, a clean CLI failure when TWS is unreachable, a strict integration test, and a clean `ruff check .`.

**Architecture:** No new modules. `bot.portfolio.report` keeps its shape (pure `build_report` reader + pure Jinja2 renderers); it gains a `Review` row type and takes today's events as input. `bot.portfolio.command.run_portfolio` passes the events it already computes into `build_report`. `bot.cli.portfolio` catches connection failures at the composition root.

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
- **Which events suggest a review.** Spec §8.3 calls the layer-A/B/C events "lo valioso": `intrinsic_value_crossed_price`, `new_red_flag`, `below_quality_gate`, `sector_recalibrated`, `new_filing`. Each produces one review line. IBKR-observed events (opened/closed/size/dividend/split/currency) are the user's own actions or bookkeeping and do not. The `concentration` *event* is skipped because the concentration rows already produce the trimming review (avoids a duplicate line for the same ticker).
- **TWS unreachable** = `ConnectionError` (incl. `ConnectionRefusedError`) or `TimeoutError` raised from `IbkrClient.connect`. Only those are caught; disk `OSError`s still surface.

## Review Focus

1. A quiet day after a busy one: `alerts.md` must be overwritten to empty, not left with yesterday's content — pinned in Task 2's integration test (run with events, then a run with none, file size 0).
2. An event for a ticker that is not in today's positions (e.g. a filing for a just-closed position) must still produce its review line — pinned in Task 3 unit test (`test_suggested_reviews_include_ticker_without_position`).
3. Several events of different types for one ticker each get their own line, in a stable order (positions' ticker order, then event order) — pinned in Task 3 unit test.
4. TWS down: exit code 1, one-line message naming host:port, no traceback, no report files written — pinned in Task 4.
5. `--history` on the second run lists both snapshot days — pinned in Task 3's integration test.

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

### Task 3: suggested reviews driven by today's events

**Files:**
- Modify: `src/bot/portfolio/report.py` (`Review`, `_suggested_reviews`, `PortfolioReport.reviews`, `build_report(..., events=...)`)
- Modify: `src/bot/reporting/templates/portfolio.md.j2` (Suggested reviews section)
- Modify: `src/bot/portfolio/command.py` (pass `events` to `build_report`)
- Test: `tests/unit/test_portfolio_report.py`, `tests/integration/test_portfolio_command.py`

**Interfaces:**
- Produces:

```python
@dataclass(frozen=True)
class Review:
    """One position the report suggests revisiting, and why."""
    ticker: str
    reason: str

# PortfolioReport gains (after `unpriced`): reviews: tuple[Review, ...] = ()

def build_report(
    conn, snapshot_date, *, include_history=False, include_concentration=False,
    concentration_threshold=DEFAULT_CONCENTRATION_THRESHOLD,
    events: Sequence[Event] = (),
) -> PortfolioReport
```

- Reason text per type (exact):
  - concentration row flagged: `f"{weight:.1%} of the portfolio, above the {threshold:.1%} concentration threshold; consider trimming."`
  - `intrinsic_value_crossed_price`, direction `above_price`: `"Intrinsic value rose above the price; revisit the valuation before adding."`; `below_price`: `"Intrinsic value fell below the price; revisit the thesis."`
  - `new_red_flag`: `f"New red narrative flag `{flag}`; check the story still holds."`
  - `below_quality_gate`: `f"Now fails the `{gate}` quality gate; revisit the thesis."`
  - `sector_recalibrated`: `f"Sector WACC moved {delta:+.2%}; re-run the valuation."`
  - `new_filing`: `f"New {filing_type} filed {filing_date}; re-run `bot analyze {ticker}`."`
- Ordering: concentration reviews first (weight desc, as rows already are), then event reviews in the order `compute_events` returned them.

- [ ] **Step 1: failing unit tests** in `tests/unit/test_portfolio_report.py`:

```python
def test_suggested_reviews_from_derived_events(conn: duckdb.DuckDBPyConnection) -> None:
    _insert(conn, D2, [("AAPL", 1, 10.0, 100.0, 1000.0, "USD")] + [
        (t, i, 10.0, 100.0, 1000.0, "USD") for i, t in enumerate("BCDEFGHI", 2)
    ])
    events = [
        Event(EventType.POSITION_OPENED, "AAPL", D2, D1, {"qty": 10.0}),
        Event(EventType.INTRINSIC_VALUE_CROSSED_PRICE, "AAPL", D2, D1,
              {"direction": "below_price", "intrinsic_value": 90.0, "price": 100.0}),
        Event(EventType.BELOW_QUALITY_GATE, "AAPL", D2, D1, {"gate": "max_net_debt_to_ebitda"}),
        Event(EventType.NEW_RED_FLAG, "B", D2, D1, {"flag": "margin_jump", "reason": "x"}),
        Event(EventType.SECTOR_RECALIBRATED, "C", D2, D1, {"prev_wacc": 0.08, "wacc": 0.095, "delta": 0.015}),
        Event(EventType.NEW_FILING, "D", D2, D1,
              {"filing_type": "10-K", "filing_date": "2026-05-01", "accession_number": "1"}),
    ]
    report = build_report(conn, D2, events=events)
    assert [(r.ticker, r.reason) for r in report.reviews] == [
        ("AAPL", "Intrinsic value fell below the price; revisit the thesis."),
        ("AAPL", "Now fails the `max_net_debt_to_ebitda` quality gate; revisit the thesis."),
        ("B", "New red narrative flag `margin_jump`; check the story still holds."),
        ("C", "Sector WACC moved +1.50%; re-run the valuation."),
        ("D", "New 10-K filed 2026-05-01; re-run `bot analyze D`."),
    ]


def test_suggested_reviews_include_ticker_without_position(conn: duckdb.DuckDBPyConnection) -> None:
    events = [Event(EventType.NEW_FILING, "GONE", D2, D1,
                    {"filing_type": "8-K", "filing_date": "2026-05-02", "accession_number": "9"})]
    report = build_report(conn, D2, events=events)
    assert [r.ticker for r in report.reviews] == ["GONE"]


def test_concentration_event_does_not_duplicate_trim_review(conn: duckdb.DuckDBPyConnection) -> None:
    _insert(conn, D2, [("AAPL", 1, 100.0, 120.0, 15000.0, "USD"), ("MSFT", 2, 10.0, 300.0, 3000.0, "USD")])
    events = [Event(EventType.CONCENTRATION, "AAPL", D2, D1, {"weight": 0.83})]
    report = build_report(conn, D2, events=events)
    assert [r.ticker for r in report.reviews] == ["AAPL", "MSFT"]
    assert all("consider trimming" in r.reason for r in report.reviews)
```

Update `test_render_portfolio_sections` to pass `reviews=(Review("AAPL", "x; consider trimming."),)` and assert `"- **AAPL**: x; consider trimming." in out`; `test_render_portfolio_no_history_section_by_default` keeps asserting `"No reviews suggested"`.

- [ ] **Step 2: tighten the integration test** `test_portfolio_writes_both_reports`: assert each of `"# Portfolio — 2026-06-01"`, `"## Positions"`, `"## Profit & loss"`, `"## Concentration"`, `"## Suggested reviews"` is in `portfolio.md`, and `"# Alerts — 2026-06-01"`, `"| Type | Ticker | Details |"`, `"position_opened"` in `alerts.md`. In `test_history_and_concentration_flags` assert `"## P&L history"`, `"## Concentration breakdown"`, `"| 2026-05-31 |"` and `"| 2026-06-01 |"`. In `test_run_portfolio_emits_valuation_events_across_two_runs` add: `body = (tmp_path / day2.isoformat() / "portfolio.md").read_text()` and assert `"Now fails the `toggle_gate` quality gate" in body` and `"Intrinsic value rose above the price" in body`.
- [ ] **Step 3:** run both test files — expected FAIL (`events` kwarg / `reviews` missing).
- [ ] **Step 4: implement.** In `report.py`: add `Review`, `_REVIEW_EVENTS` and `_suggested_reviews(concentration: Sequence[ConcentrationRow], events: Sequence[Event], *, threshold: float) -> list[Review]` per the reason table; `build_report` takes `events` and fills `reviews=tuple(...)`. In the template replace the `selectattr("flagged")` block with:

```jinja
{% if r.reviews %}
{% for review in r.reviews %}
- **{{ review.ticker }}**: {{ review.reason }}
{% endfor %}
{% else %}
- No positions exceed the concentration threshold and no events call for a review today. No reviews suggested.
{% endif %}
```

In `command.py` pass `events=events` to `build_report`.
- [ ] **Step 5:** run tests — PASS; `uv run mypy src`.
- [ ] **Step 6:** Commit `feat(#29): suggest reviews from today's derived portfolio events`.

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

(Check `config.py` for the exact `ibkr_host` / `ibkr_port` setting names and env prefix before relying on `BOT_IBKR_PORT`.)
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
- Modify: `docs/plano/estado.py` (`rep-portfolio` entry; `AUDITADO_EN` / `AUDITADO_EL` if the README's procedure requires it for this change)
- Regenerate: `python3 docs/plano/build.py && python3 docs/plano/build_estado.py`

- [ ] **Step 1:** Update the `rep-portfolio` evidence text: positions, P&L, concentration, suggested reviews from concentration and today's derived events (§8.3 layer A/B/C), optional history and breakdown; `alerts.md` always written, empty on a day without events. Point the evidence at `portfolio/report.py` line of `build_report`.
- [ ] **Step 2:** Run both builds; they must succeed.
- [ ] **Step 3:** Commit `docs(#29): record portfolio report state in the plans`.
