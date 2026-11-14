# Suggested reviews derive from the day's derived events Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `.agents/skills/subagent-driven-development/SKILL.md` to implement this plan task-by-task; implementers write code with `.agents/skills/test-driven-development/SKILL.md`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The `## Suggested reviews` section of `reports/YYYY-MM-DD/portfolio.md` adds one line per *derived* §8.3 event of the day (new filing, intrinsic value crossed price, new red flag, below quality gate, sector recalibrated), each with a fixed action, after the existing concentration lines.

**Architecture:** The *which* lives in code: `REVIEW_EVENT_TYPES` and the `PortfolioReport.review_events` property in `src/bot/portfolio/report.py`. The *wording* lives in `src/bot/reporting/templates/portfolio.md.j2`, which branches on `e.event_type` (a `StrEnum`, compared with its string value) and reads every payload value with `e.details.get(...)`. One new Jinja filter, `bps`, formats the WACC move.

**Tech Stack:** Python 3.12, Jinja2 (`trim_blocks`, `lstrip_blocks`), pytest, DuckDB (integration test only).

**Spec:** GitHub issue #353 (nicolas-ricc/damodaran), "feat(#86): suggested reviews derive from the day's derived events". Story context: #86 and its plan comment. Builds on #352 (`PortfolioReport.events`, already on `feature/86-portfolio-md-events`).

## Global Constraints

- `REVIEW_EVENT_TYPES: frozenset[EventType]` in `report.py` is exactly `{NEW_FILING, INTRINSIC_VALUE_CROSSED_PRICE, NEW_RED_FLAG, BELOW_QUALITY_GATE, SECTOR_RECALIBRATED}`. `CONCENTRATION` and the six IBKR-observed types are excluded.
- `PortfolioReport.review_events -> tuple[Event, ...]` is `tuple(e for e in self.events if e.event_type in REVIEW_EVENT_TYPES)`, order preserved.
- `_fmt_bps(value: Any) -> str` in `report.py`: `None` → `—`; otherwise `f"{round(float(value) * 10000):+d} bps"`. Registered as `env.filters["bps"]`.
- Section layout: concentration lines first (text unchanged), then one line per `review_events` entry, in order. When both are empty, the single line `- No positions exceed the concentration threshold and no event calls for a review. No reviews suggested.`
- Event lines, exactly (`T` = `e.ticker`; values read with `e.details.get(...)`):
  - cross, `direction == "above_price"`: `- **T**: intrinsic value crossed above price ({{ iv | money }} vs {{ price | money }}, was {{ prev_iv | money }} vs {{ prev_price | money }}) — potentially undervalued again; review whether to add.`
  - cross, `direction == "below_price"`: `- **T**: intrinsic value crossed below price ({{ iv | money }} vs {{ price | money }}, was {{ prev_iv | money }} vs {{ prev_price | money }}) — potentially overvalued; review whether to trim.`
  - `new_red_flag`: ``- **T**: new red narrative flag `{{ flag }}` ({{ reason }}) — re-read the story before trusting the valuation.``
  - `below_quality_gate`: ``- **T**: newly fails quality gate `{{ gate }}` — review whether the thesis survives it.``
  - `sector_recalibrated`: `- **T**: sector WACC moved {{ delta | bps }} ({{ prev_wacc | pct }} → {{ wacc | pct }}) — re-check the margin of safety under the new discount rate.`
  - `new_filing`: ``- **T**: new {{ filing_type }} filed {{ filing_date }} — read it and refresh the analysis with `bot analyze T`.``
- Detail keys: cross → `direction`, `prev_intrinsic_value`, `prev_price`, `intrinsic_value`, `price`; red flag → `flag`, `reason`; gate → `gate`; sector → `prev_wacc`, `wacc`, `delta`; filing → `filing_type`, `filing_date`.
- A review event with a missing detail key renders, never raises. Numeric values go through their filter (`None` → `—`); text values use `e.details.get(key, "—")` so a missing one renders `—`, not `None`.
- Docs: only the `portfolio.md` bullet of the `report.py` module docstring changes (suggested reviews come from flagged concentration and the day's derived events). Boards, `estado.py`, README are #354.
- `uv run pytest -q`, `uv run ruff check .`, `uv run mypy src` pass. Commits use the `(#353)` scope.

## Acceptance criteria

| Criterion (issue #353) | Pinned by |
|---|---|
| `REVIEW_EVENT_TYPES` is exactly the five; `review_events` filters `events` in order | `test_review_event_types_are_the_five_derived`, `test_review_events_filters_in_order` |
| Six single-event cases render their exact line, no `No reviews suggested` | `test_suggested_review_line[cross_above, cross_below, new_red_flag, below_quality_gate, sector_recalibrated, new_filing]` |
| `concentration` + six IBKR events, no flagged row → fallback line only | `test_suggested_reviews_ignore_concentration_and_ibkr_events` |
| Flagged row + `concentration` event for same ticker → one bullet (`consider trimming`) | `test_suggested_reviews_concentration_not_listed_twice` |
| Flagged row + review event → concentration line first | `test_suggested_reviews_concentration_before_events` |
| `_fmt_bps` values | `test_fmt_bps` |
| Existing `consider trimming` / `No reviews suggested` assertions unchanged | `test_render_portfolio_sections`, `test_render_portfolio_no_history_section_by_default` (untouched) |
| Integration: `portfolio.md` carries the `new_filing` action | `test_rerun_keeps_new_filing_in_alerts` (extended) |
| Suite, ruff, mypy | final step of Task 2 |

## Review Focus

- **Missing detail key.** A hand-edited or older `events_log` row lacking e.g. `delta` or `flag` must render with `—`, not crash and not print `None`. Pinned by `test_suggested_review_missing_details_render_dash` (Task 2): a `sector_recalibrated` event with `{}` details renders `sector WACC moved — (— → —)`, and a `new_red_flag` with `{}` renders ``new red narrative flag `—` (—)``.
- **Unknown cross direction.** An `intrinsic_value_crossed_price` event whose `direction` is neither value must still produce a bullet, so the section is never empty while `review_events` is non-empty. Pinned by `test_suggested_review_unknown_direction_still_listed`: the section contains `**AAPL**: intrinsic value crossed price` and no `No reviews suggested`. Copy for it: `- **T**: intrinsic value crossed price ({{ iv | money }} vs {{ price | money }}, was {{ prev_iv | money }} vs {{ prev_price | money }}) — review the valuation.`
- **Whitespace.** `trim_blocks`/`lstrip_blocks` with nested `if` branches can glue bullets together or leave blank lines inside the list. Pinned by the exact-line assertions (each expected line checked as `"\n" + line + "\n"` within the section) and by `test_suggested_reviews_concentration_before_events` asserting the two bullets are on consecutive lines.
- **Events loaded from the DB.** `load_events` builds `Event`s whose `event_type` is an `EventType`; the template compares with string values, which works for `StrEnum`. Pinned by the integration test (DB round-trip).
- **Bps rounding.** `0.012 * 10000` is `120.00000000000001`; `round` makes it `120`. Pinned by `test_fmt_bps`.

---

### Task 1: Review event selection and the `bps` filter

**Files:**
- Modify: `src/bot/portfolio/report.py` (imports `EventType`, new constant, property, `_fmt_bps`, filter registration, module docstring bullet)
- Test: `tests/unit/test_portfolio_report.py`

**Interfaces:**
- Produces: `REVIEW_EVENT_TYPES: frozenset[EventType]`; `PortfolioReport.review_events -> tuple[Event, ...]` (property); `_fmt_bps(value: Any) -> str`; Jinja filter `bps`.

- [ ] **Step 1: Write the failing tests.**
  - `test_review_event_types_are_the_five_derived`: `REVIEW_EVENT_TYPES == frozenset({EventType.NEW_FILING, EventType.INTRINSIC_VALUE_CROSSED_PRICE, EventType.NEW_RED_FLAG, EventType.BELOW_QUALITY_GATE, EventType.SECTOR_RECALIBRATED})`.
  - `test_review_events_filters_in_order`: events `[new_filing AAPL, position_opened MSFT, concentration AAPL, new_red_flag MSFT, dividend AAPL, sector_recalibrated NVDA]` → `review_events` is `(new_filing AAPL, new_red_flag MSFT, sector_recalibrated NVDA)`.
  - `test_fmt_bps`: `_fmt_bps(0.012) == "+120 bps"`, `_fmt_bps(-0.0105) == "-105 bps"`, `_fmt_bps(None) == "—"`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_portfolio_report.py -q`. Expected: ImportError on the new names.
- [ ] **Step 3: Implement** the constant, property, `_fmt_bps` and filter registration; update the module docstring `portfolio.md` bullet.
- [ ] **Step 4: Run** the same command. Expected: all pass.
- [ ] **Step 5: Commit** `feat(#353): select review events and add the bps filter`.

### Task 2: Suggested reviews render the event lines

**Files:**
- Modify: `src/bot/reporting/templates/portfolio.md.j2` (`## Suggested reviews` block only)
- Test: `tests/unit/test_portfolio_report.py`, `tests/integration/test_portfolio_command.py`

**Interfaces:**
- Consumes: `r.review_events`, filter `bps` (Task 1).

- [ ] **Step 1: Write the failing tests.** Helper `_suggested(out: str) -> str` returns the text from `## Suggested reviews` up to the next `\n## ` or end. Reuse `_report(events)` (no flagged concentration).
  - `test_suggested_review_line` parametrized over six `(Event, expected_line)` pairs, ticker `AAPL`, `D2`:
    - cross above: details `{"direction": "above_price", "prev_intrinsic_value": 90.0, "prev_price": 100.0, "intrinsic_value": 120.0, "price": 110.0}` → `- **AAPL**: intrinsic value crossed above price (120.00 vs 110.00, was 90.00 vs 100.00) — potentially undervalued again; review whether to add.`
    - cross below: `{"direction": "below_price", "prev_intrinsic_value": 120.0, "prev_price": 110.0, "intrinsic_value": 90.0, "price": 100.0}` → `- **AAPL**: intrinsic value crossed below price (90.00 vs 100.00, was 120.00 vs 110.00) — potentially overvalued; review whether to trim.`
    - red flag: `{"flag": "margin_expansion_unexplained", "reason": "target margin far above history", "baseline_snapshot_date": None}` → ``- **AAPL**: new red narrative flag `margin_expansion_unexplained` (target margin far above history) — re-read the story before trusting the valuation.``
    - gate: `{"gate": "max_net_debt_to_ebitda"}` → ``- **AAPL**: newly fails quality gate `max_net_debt_to_ebitda` — review whether the thesis survives it.``
    - sector: `{"prev_wacc": 0.08, "wacc": 0.092, "delta": 0.012}` → `- **AAPL**: sector WACC moved +120 bps (8.0% → 9.2%) — re-check the margin of safety under the new discount rate.`
    - filing: `{"filing_type": "10-K", "filing_date": "2026-05-01", "accession_number": "0000320193-26-000001"}` → ``- **AAPL**: new 10-K filed 2026-05-01 — read it and refresh the analysis with `bot analyze AAPL`.``
    Assert `"## Suggested reviews\n\n" + line + "\n"` in `out` (the bullet sits right under the heading, no stray blank line or fallback when nothing is flagged) and `"No reviews suggested" not in out`.
  - `test_suggested_reviews_ignore_concentration_and_ibkr_events`: one `concentration` + one of each IBKR type → `_suggested(out)` bullets (lines starting `- `) equal exactly `["- No positions exceed the concentration threshold and no event calls for a review. No reviews suggested."]`.
  - `test_suggested_reviews_concentration_not_listed_twice`: report with `ConcentrationRow("AAPL", 15000.0, 0.8, True)` and a `concentration` AAPL event → exactly one bullet in `_suggested(out)` contains `AAPL`, and it contains `consider trimming`.
  - `test_suggested_reviews_concentration_before_events`: flagged AAPL row + `new_filing` MSFT event → bullets are `[<AAPL consider trimming line>, <MSFT new filing line>]`, in that order.
  - `test_suggested_review_missing_details_render_dash` and `test_suggested_review_unknown_direction_still_listed` (see Review Focus).
  - Integration, `test_rerun_keeps_new_filing_in_alerts`: after the second DAY2 run, `(tmp_path / DAY2.isoformat() / "portfolio.md").read_text()` contains ``read it and refresh the analysis with `bot analyze AAPL` ``.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_portfolio_report.py tests/integration/test_portfolio_command.py -q`. Expected: the new tests fail; `test_render_portfolio_sections` and `test_render_portfolio_no_history_section_by_default` still pass.
- [ ] **Step 3: Implement** in the template: keep `flagged`; emit flagged lines, then `{% for e in r.review_events %}` with an `if/elif` on `e.event_type` (and on `direction` for crosses); `{% if not flagged and not r.review_events %}` fallback. Exact copy from Global Constraints and Review Focus.
- [ ] **Step 4: Full suite and lint.** `uv run pytest -q && uv run ruff check . && uv run mypy src`. Expected: green.
- [ ] **Step 5: Commit** `feat(#353): suggested reviews list the day's derived events`.

## Assumptions

- **Unknown cross direction gets a neutral bullet.** The issue requires that "a review event of an unexpected shape (missing detail key) must not crash rendering"; a missing `direction` is such a key. The producer only ever writes `above_price`/`below_price` (`src/bot/portfolio/events.py:381`), so the neutral line (`— review the valuation.`) is a defensive path no real run reaches. Rejected: emitting nothing, which would leave the section without a bullet and without the fallback while `review_events` is non-empty.
- **Text details default to `—`.** `{{ None }}` renders `None` in Jinja, so text keys use `e.details.get(key, "—")`; numeric keys go through `money`/`pct`/`bps`, which return `—` for `None` (`report.py` `_fmt_money`, `_fmt_pct`). The template knows which key is which because each branch names its own keys. Rejected: a generic `text` filter (one more filter for one defensive case).
- **Non-numeric numeric details are out of contract.** `_fmt_bps` calls `float(value)` like every existing `_fmt_*` filter. `events_log.details` is only ever written with `json.dumps` of the detectors' float payloads (`events.py:846-855`), so a string `delta` cannot arise from the code. Malformed JSON in that column would already fail in `load_events` (`_row_details`, `events.py:802-804`), before rendering and for `alerts.md` too; not changed here.
- **Order.** `events` arrives in `load_events` order (`ORDER BY rowid`, `events.py:871`); the issue asks for "that order" with no grouping, so neither ticker nor type is regrouped.
- **Intermediate commit.** Task 1 registers `bps` and adds `review_events` before the template uses them; neither ruff nor mypy flags a registered filter or an unused property. Both tasks land in one PR squashed into the story branch.

## Grilling

- **Rounds:** 1. One test assertion was tightened (Q14) and this Assumptions section was added; no task or step added or removed, so no second round.
- **Griller:** fable. 16 questions.
- **Sources:**
  - ISSUE: Q1 ("`events: tuple[Event, ...]` (today's logged events, in `load_events` insertion order)"), Q4 (unexpected shape "must not crash rendering"), Q8 ("a concentrated book is never listed twice"; criterion "a flagged concentration row **and** a `concentration` event for the same ticker renders exactly one bullet"), Q13 ("in that order"), Q15 (#86 "Children created": boards in #354; issue "No other docs in this task").
  - CODE: Q1 `report.py` `PortfolioReport.events` + `tests/unit/test_portfolio_report.py::test_build_report_carries_events`; Q2 `events.py:57-73`, `:381`; Q3 `events.py:337-339, 381-385, 418-420, 488, 516` and `tests/unit/test_portfolio_events.py:399,407,443-444,452,539`; Q5 `events.py:802-804` (NULL → `{}`); Q6 `report.py` `_fmt_money`/`_fmt_pct` return `_DASH` for `None`, registered in `_environment()`; Q7 `test_portfolio_report.py:233,253` are substring matches and the new fallback keeps `No reviews suggested`; Q8 `report.py` `ConcentrationRow(ticker, market_value, weight, flagged)`; Q9 `tests/integration/test_portfolio_command.py:548-561` runs DAY2 twice, and `command.py:185-188` writes `portfolio.md` on every run; Q10 `test_portfolio_report.py:291-304` builds `PortfolioReport` directly and renders through `render_portfolio`, so filters are exercised; Q12 `events.py:338` stores `filing_date.isoformat()`; Q15 `docs/pipeline/check.py:6-8` resolves symbols/tables/files only, not prose.
  - NO SOURCE: Q4 (copy), Q11, Q12 (text vs numeric), Q14, Q16 → technical assumptions above or a tightened test.
- **Follow-up issues opened:** none. **Spec ambiguities:** none.
