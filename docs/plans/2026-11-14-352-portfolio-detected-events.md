# portfolio.md lists today's detected events Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `.agents/skills/subagent-driven-development/SKILL.md` to implement this plan task-by-task; implementers write code with `.agents/skills/test-driven-development/SKILL.md`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `reports/YYYY-MM-DD/portfolio.md` gains a `## Detected events` section that lists every §8.3 event logged for the day, in the same table `alerts.md` uses (spec §8.4: "resumen, posiciones actuales, eventos detectados, acciones sugeridas").

**Architecture:** `PortfolioReport` carries a new `events` tuple. `build_report` takes the events as a keyword and stores them, and `run_portfolio` passes it the `day_events` list it already hands to `render_alerts`. The `| Type | Ticker | Details |` table moves out of `alerts.md.j2` into a shared Jinja partial, `events_table.md.j2`, which both templates include. `alerts.md` stays byte-identical.

**Tech Stack:** Python 3.12, Jinja2 (`trim_blocks`, `lstrip_blocks`, `keep_trailing_newline`), DuckDB, pytest.

**Spec:** GitHub issue #352 (nicolas-ricc/damodaran), "feat(#86): portfolio.md lists today's detected events". Story context: #86 and its plan comment.

## Global Constraints

- New field `events: tuple[Event, ...] = ()` on `PortfolioReport`. The default keeps every existing keyword constructor call valid.
- `build_report(..., events: Sequence[Event] = ())` is keyword-only and stores `tuple(events)`.
- `run_portfolio` passes `events=day_events`, the same list `render_alerts` gets.
- The section is `## Detected events`, placed **between `## Concentration` and `## Suggested reviews`**.
- With events, the section holds the line `N event(s) detected today.` (`1 event`, `2 events`), a blank line, then the table. Without events it holds the single line `_No events detected today._` and no table header.
- The partial is `src/bot/reporting/templates/events_table.md.j2` and expects a variable named `events`. `alerts.md.j2` uses `{% include "events_table.md.j2" %}`, and `portfolio.md.j2` uses `{% with events = r.events %}{% include "events_table.md.j2" %}{% endwith %}`.
- `alerts.md` stays byte-identical, and stays `""` on a day with no events.
- `## Suggested reviews` is not touched (that is #353).
- Docs: change only the `portfolio.md` bullet of the `report.py` module docstring and step 5 of the `command.py` docstring. Boards, `estado.py` and the README belong to #354.
- `uv run pytest -q`, `uv run ruff check .` and `uv run mypy src` pass. Commits use the `(#352)` scope.

## Acceptance criteria

| Criterion (issue #352) | Pinned by |
|---|---|
| `build_report(conn, d, events=[...])` makes `.events` the tuple of those events. `build_report(conn, d)` makes it `()`. | `test_build_report_carries_events`, `test_build_report_events_default_empty` |
| `## Detected events` comes after `## Concentration` and before `## Suggested reviews`. | `test_render_portfolio_detected_events_position` |
| With two events: `2 events detected today.` and one row per event, formatted like the `alerts.md` rows. With one event: `1 event detected today.` | `test_render_portfolio_lists_events`, `test_render_portfolio_singular_event` |
| With no events: `_No events detected today._` and no table header. | `test_render_portfolio_no_events` |
| `render_alerts` output is unchanged. The three existing alerts tests pass without edits. | the existing tests plus `test_render_alerts_bytes_unchanged` (golden string) |
| `run_portfolio` passes the day's events to `build_report`. The integration tests assert the header and the AAPL row on the first run, and `_No events detected today._` on the quiet day. | `test_portfolio_writes_both_reports`, `test_alerts_present_but_empty_when_no_events` (both extended) |
| The suite, ruff and mypy pass. | the final step of Task 2 |

## Exact copy

The golden `alerts.md` output, captured from the current code before any change (`render_alerts(events, D2, generated_on=D2)` with `events = [Event(POSITION_OPENED, "NVDA", D2, None, {"qty": 50.0, "avg_cost": 10.0}), Event(CONCENTRATION, "NVDA", D2, None, {"weight": 0.8})]`):

```
'# Alerts — 2026-05-02\n\n_Generated 2026-05-02_\n\n2 events detected today.\n\n| Type | Ticker | Details |\n|---|---|---|\n| position_opened | NVDA | qty=50.0, avg_cost=10.0 |\n| concentration | NVDA | weight=0.8 |\n'
```

The `portfolio.md` section, with events (blank line before the heading and after it, as for the other sections):

```
## Detected events

2 events detected today.

| Type | Ticker | Details |
|---|---|---|
| position_opened | NVDA | qty=50.0, avg_cost=10.0 |
| concentration | NVDA | weight=0.8 |

## Suggested reviews
```

Without events:

```
## Detected events

_No events detected today._

## Suggested reviews
```

## Review Focus

- **Whitespace around the include.** `trim_blocks` eats the newline after a block tag, so moving the loop into a partial can drop or add a blank line, either in `alerts.md` or between the table and `## Suggested reviews`. Pinned by `test_render_alerts_bytes_unchanged` and by the exact-substring assertions in `test_render_portfolio_lists_events` / `test_render_portfolio_no_events`.
- **Event order.** Rows must keep the order they arrive in (insertion order from `load_events`). Nothing may sort them. Pinned by `test_render_portfolio_lists_events` (`position_opened` row index < `concentration` row index).
- **A `list` passed as `events`.** `run_portfolio` passes a `list`. The frozen dataclass must store a tuple so the field is immutable, as the issue's design decision prescribes (`tuple(events)`). `Event.details` is a `dict`, so neither `Event` nor the report is hashable, and nothing relies on that. Pinned by `test_build_report_carries_events` (`isinstance(report.events, tuple)`).
- **An event with empty `details`.** The row renders as `| split | X |  |`, the same as in alerts. This comes free from the shared partial and needs no test of its own.
- **The `with` scope.** In `portfolio.md.j2` the name `events` must not leak past `{% endwith %}`. The template has no other `events` name, so this is safe by construction.

---

### Task 1: Report data and the Detected events section

**Files:**
- Create: `src/bot/reporting/templates/events_table.md.j2`
- Modify: `src/bot/reporting/templates/alerts.md.j2`, `src/bot/reporting/templates/portfolio.md.j2`, `src/bot/portfolio/report.py` (`PortfolioReport`, `build_report`, module docstring)
- Test: `tests/unit/test_portfolio_report.py`

**Interfaces:**
- Produces: `PortfolioReport.events: tuple[Event, ...] = ()`. `build_report(conn, snapshot_date, *, include_history=False, include_concentration=False, concentration_threshold=..., events: Sequence[Event] = ()) -> PortfolioReport`.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_portfolio_report.py`. Use a helper `_report(events=()) -> PortfolioReport` that builds an empty report (the same fields as `test_render_portfolio_no_history_section_by_default`) with `events=tuple(events)`.
  - `test_build_report_carries_events`: insert one snapshot. `build_report(conn, D2, events=[e1, e2])` gives `.events == (e1, e2)` and `isinstance(.events, tuple)`.
  - `test_build_report_events_default_empty`: `build_report(conn, D2).events == ()`.
  - `test_render_portfolio_detected_events_position`: `out.index("## Concentration\n") < out.index("## Detected events") < out.index("## Suggested reviews")`.
  - `test_render_portfolio_lists_events`: with the two golden events, the "With events" block from Exact copy (from `## Detected events` through `## Suggested reviews`) appears verbatim in `out`.
  - `test_render_portfolio_singular_event`: one event gives `"1 event detected today." in out`.
  - `test_render_portfolio_no_events`: the "Without events" block appears verbatim, and `"| Type | Ticker | Details |" not in out`.
  - `test_render_alerts_bytes_unchanged`: `render_alerts(golden events, D2, generated_on=D2)` equals the golden string from Exact copy.

- [ ] **Step 2: Run to verify they fail.** Run `uv run pytest tests/unit/test_portfolio_report.py -q`. Expected: the new tests fail (TypeError on `events=`, or the section is missing), and `test_render_alerts_bytes_unchanged` passes.

- [ ] **Step 3: Implement.** Add the field, the keyword and `tuple(events)` (import `Sequence` from `collections.abc`). Create the partial from the current header, separator and row loop of `alerts.md.j2`, and replace those lines in `alerts.md.j2` with the include. Add the section to `portfolio.md.j2` between the end of the Concentration `{% endif %}` and `## Suggested reviews`. The count line copies `alerts.md.j2`'s expression on `r.events`. Update the `portfolio.md` bullet of the `report.py` module docstring so it mentions the detected-events section (today's logged events, the same table as `alerts.md`).

- [ ] **Step 4: Run to verify they pass.** Run `uv run pytest tests/unit/test_portfolio_report.py -q`. Expected: all tests pass, including the untouched `test_render_alerts_*`.

- [ ] **Step 5: Commit.** `feat(#352): portfolio.md renders a detected-events section`

### Task 2: run_portfolio passes the day's events

**Files:**
- Modify: `src/bot/portfolio/command.py` (the `build_report` call and step 5 of the module docstring)
- Test: `tests/integration/test_portfolio_command.py`

**Interfaces:**
- Consumes: `build_report(..., events=...)` from Task 1.

- [ ] **Step 1: Extend the tests.** In `test_portfolio_writes_both_reports`, add `"## Detected events"` to the headings tuple, and assert that `"| position_opened | AAPL |"` is in `body`. In `test_alerts_present_but_empty_when_no_events` (the second run with the same positions), assert that `"_No events detected today._"` is in `result.portfolio_path.read_text()`.

- [ ] **Step 2: Run to verify they fail.** Run `uv run pytest tests/integration/test_portfolio_command.py -q`. Expected: the first-run row assertion fails, because without wiring the section says "No events".

- [ ] **Step 3: Implement.** Pass `events=day_events` to `build_report`. In step 5 of the `command.py` docstring, say that `portfolio.md` carries a detected-events section listing the same day's logged events as `alerts.md`.

- [ ] **Step 4: Full suite and lint.** Run `uv run pytest -q && uv run ruff check . && uv run mypy src`. Expected: everything green.

- [ ] **Step 5: Commit.** `feat(#352): run_portfolio threads the day's events into portfolio.md`

## Assumptions

- **Golden alerts bytes.** The string in Exact copy was produced by running `render_alerts` on the unchanged `feature/86-portfolio-md-events` tip (45dd91b) in stage 1, and it is recorded in this plan's `plan(#352)` commit. The stage-3 eval commit adds `test_render_alerts_bytes_unchanged` *before* any template change, so the test passes on the old code first. The rejected alternative was trusting the three existing tests, but none of them compares full bytes.
- **Jinja `with`.** Jinja2 3.1.6 is installed (`uv run python -c "import jinja2; print(jinja2.__version__)"`). `{% with %}` has been built in since 2.9, and an `include` sees the variables in its enclosing scope. `test_render_portfolio_lists_events` proves it in this environment.
- **The intermediate commit.** Task 1 alone renders `_No events detected today._` from `run_portfolio`. Both tasks land in one pull request, which is squash-merged into the story branch `feature/86-portfolio-md-events`, not into `master`. So the intermediate state never ships.
- **Stale board prose.** `docs/pipeline/portfolio-alerts.d2:15,46` describe `portfolio.md` without the new section. That is #354's scope (#86 plan comment, "Children created"). `docs/pipeline/check.py` checks only that cited files and symbols exist, and every cited file still exists after this change.

## Grilling

- **Rounds:** 1. The plan gained Assumptions and one corrected sentence (the hashability claim). No task or step was added or removed, so no second round ran.
- **Griller:** fable. It asked 16 questions.
- **Sources:**
  - ISSUE: Q8 ("the quiet-day test (second run, same positions)"), Q9 (Design decisions: "The table is shared, not duplicated"), Q14 (the #86 children list puts the boards in #354).
  - CODE:
    - Q2: `alerts.md.j2:9-11`. Each row line ends in its own `\n`, and `trim_blocks` eats the newline after `{% endfor %}`. The loop moves into the partial.
    - Q3: `report.py` `render_alerts` returns `""` before any template is rendered. Covered by `test_render_alerts_empty_when_no_events`.
    - Q4: `test_portfolio_command.py:184`, "First snapshot -> every position opens", plus the AAPL alerts row.
    - Q5: `command.py:168` sets `day_events` before the `build_report` call at `:171`.
    - Q6: `alerts.md.j2:5` is `{{ events | length }} event{{ "s" if events | length != 1 else "" }}`.
    - Q7: `portfolio.md.j2` renders `## Concentration` unconditionally.
    - Q8: `_diversified_client` holds 8 positions at about 12.5%, below the 15% threshold, so there is no concentration event.
    - Q11: `report.py:30-33` already imports `Event` from `bot.portfolio.events`, which imports `marks`, not `report`. No cycle.
    - Q12: the three tests are `test_render_alerts_with_events`, `_empty_when_no_events` and `_singular_event`. None compares full bytes. The integration tests compare bytes only across re-runs.
    - Q15: `Event.details` is a `dict`, so `Event` is not hashable. The plan was corrected.
    - Q16: `events.py:871` reads with `ORDER BY rowid`.
  - NO SOURCE: Q1, Q10 and Q13. All three became technical assumptions (above).
- **Plan errors corrected:** one, the "hashable" rationale.
- **Follow-up issues opened:** none. **Spec ambiguities:** none.
