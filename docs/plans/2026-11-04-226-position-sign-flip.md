# A long → short flip is a close and an open — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When a ticker's summed quantity changes sign between two snapshots, `detect_position_changes` reports `position_closed` for the old side and `position_opened` for the new one, never `position_size_changed`; the atlas boards and the portfolio TLA+ model say so.

**Architecture:** One branch inside the "held in both" loop of `detect_position_changes` (`src/bot/portfolio/events.py:125-185`): if `before` and `after` have different signs, append the closed event then the opened event and skip the size-change rule. Same signature, no new `EventType`. The atlas is a projection: two d2 boards (`portfolio.d2`, `portfolio-events.d2`) and one model guard plus its view label (`models/portfolio.tla`, `models/portfolio.view.js`).

**Tech Stack:** Python 3.12, pytest, d2 v0.9.0 (rendered in CI), TLA+/TLC 1.7.4 (checked in CI).

**Spec:** issue #226 and its "Agent Brief" comment.

## Global Constraints

- Held in both snapshots and `sign(prev_qty) != sign(curr_qty)` → `position_closed` with `details={"prev_qty": prev}` then `position_opened` with `details={"qty": curr}`, in that order, and no `position_size_changed`.
- Same sign → today's size-change rule (`abs(change) > size_change_threshold`, strictly; default `DEFAULT_SIZE_CHANGE_THRESHOLD = 0.10`).
- No new event type. `detect_position_changes` keeps its signature and stays pure.
- Out of scope: per-account netting (positions stay summed across accounts, `_load_positions` `SUM(qty)`); currency changes (#223).
- `uv run pytest -q`, `uv run ruff check . && uv run mypy src`, `python3 docs/pipeline/check.py` pass; TLC on `portfolio.cfg` passes (CI job `models`).
- Never edit an SVG or `docs/pipeline/rendered.sha256` by hand. d2 is not on `PATH` here: the render comes from the `pipeline-render` artifact of the `pipeline-diagram` workflow after a push (as in #218, #219), or from a local d2 v0.9.0 if one can be installed.

## Decisions taken here

1. **Sign test:** `(before > 0) != (after > 0)`. Both are non-zero at that point (zero quantities are filtered out when the dicts are built), so this is exactly `sign(before) != sign(after)`.
2. **Event order within the run:** today the function emits all openings (loop over `curr`) then all closings and size changes (loop over `prev`). The flip pair is emitted from the `prev` loop, closed immediately followed by opened, so the two events of one ticker are adjacent and in the brief's order. Other tickers' order is unchanged.
3. **TLA+ model, no new step.** `portfolio-events.d2` already has 24 edges, the cap (`_MAX_EDGES` in `tests/unit/test_pipeline_subboards.py`); a new step would need a new edge and a group split. Instead `PositionOpenedFires` loses its `prev # "with_it"` guard (a held ticker the previous snapshot also held can now open: on the other side), exactly like `PositionSizeChangedFires`/`PositionSizeHolds` are already chosen nondeterministically on the quantity. The model's single `event` variable records the last event fired, which for a flip is `position_opened`. Rule `FirstRunOpensEveryPosition` is untouched and still holds (it only constrains `prev = "none"`).
4. **Labels.** View step `PositionOpenedFires`: `position opened fires [held now, not in the previous snapshot or on the other side]`. Same first line on the `window -> positions_diffed` edge; its next line: `sign flip (long ↔ short): position_closed for the old side first, then position_opened; no size change`. The `position_closed` edge gains a line `also on a sign flip, before position_opened`. `portfolio.d2`: `events.position_opened` gains `or held in both with the other sign (a flip)`; `events.position_closed` gains `or held in both with the other sign (a flip), fired first`; `events.position_size_changed`'s first line becomes `position_size_changed: held in both, same sign, and`.

## Review Focus

1. **Short position that grows or shrinks without flipping** (−100 → −150): same sign, so the size-change rule applies with `change = −0.5` (relative to `|before|`). Test in Task 1.
2. **Flip to zero** (+100 → 0): not a flip, the zero filter makes it a plain close; must stay exactly one `position_closed`. Existing `test_zero_qty_treated_as_closed` covers it.
3. **Flip under the size threshold in magnitude** (+100 → −100, `|change| = 2`; or a tiny +1 → −1): still the closed/opened pair, never `size_changed`, regardless of the threshold. Test in Task 1 with a huge threshold.
4. **Flip on one ticker alongside other events** (AAPL flips, MSFT opens, GOOG closes): AAPL's two events are adjacent, closed then opened; the other tickers' events are unchanged. Test in Task 1.
5. **Persisted pair**: both events reach `events_log` (no unique key on `event_type, ticker, date`; schema.sql:262). Covered by the existing persistence path; no extra test.

---

### Task 1: the flip in `detect_position_changes`

**Files:**
- Modify: `src/bot/portfolio/events.py:125-185` (docstring + the "held in both" branch)
- Test: `tests/unit/test_portfolio_events.py` (section "Position open / close / size change")

**Interfaces:**
- Consumes: `Position`, `Event`, `EventType`, `detect_position_changes(prev, curr, *, snapshot_date, prev_date, size_change_threshold=...)` — unchanged.
- Produces: same function, new behaviour on a sign flip.

- [ ] **Step 1: Write the failing tests** (use the file's `_pos`, `CURR`, `PREV`):
  - `test_long_to_short_flip_is_closed_then_opened`: prev `[_pos("AAPL", 100.0)]`, curr `[_pos("AAPL", -50.0)]` → `[(e.event_type, e.ticker) for e in events] == [(POSITION_CLOSED, "AAPL"), (POSITION_OPENED, "AAPL")]`; `events[0].details == {"prev_qty": 100.0}`; `events[1].details == {"qty": -50.0}`; both carry `curr_snapshot_date=CURR`, `prev_snapshot_date=PREV`.
  - `test_short_to_long_flip_is_closed_then_opened`: −100 → +20 → same pair, details `{"prev_qty": -100.0}` / `{"qty": 20.0}`.
  - `test_flip_ignores_the_size_threshold`: +1 → −1 with `size_change_threshold=1000.0` → still the closed/opened pair.
  - `test_flip_beside_other_tickers`: prev `[AAPL 100, GOOG 10]`, curr `[AAPL -50, MSFT 5]` → event multiset `{(OPENED,"MSFT"), (CLOSED,"GOOG"), (CLOSED,"AAPL"), (OPENED,"AAPL")}`, length 4, and the two AAPL events are adjacent with CLOSED first.
  - `test_size_change_15_percent_fires`: +100 → +115 → exactly one `POSITION_SIZE_CHANGED`, `change == approx(0.15)` (brief's criterion; the existing `test_size_change_at_threshold_does_not_fire` already pins +100 → +110 → none).
  - `test_short_position_size_change_keeps_the_rule`: −100 → −150 → one `POSITION_SIZE_CHANGED`, `change == approx(-0.5)`; −100 → −105 → `[]`.

- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_portfolio_events.py` — Expected: the four flip tests FAIL (a `POSITION_SIZE_CHANGED` comes out); the two same-sign tests PASS (they pin unchanged behaviour).

- [ ] **Step 3: Implement** in the `prev` loop of `detect_position_changes`: after reading `before`/`after`, if `(before > 0) != (after > 0)`, append `POSITION_CLOSED` (`details={"prev_qty": before}`) then `POSITION_OPENED` (`details={"qty": after}`) and `continue`. The `if before == 0.0: continue` guard is dead (zeros are filtered) and may stay. Docstring: add the flip sentence ("A quantity that changes sign is the old side closed and the new side opened: ``POSITION_CLOSED`` then ``POSITION_OPENED``, never a size change.").

- [ ] **Step 4: Run** `uv run pytest -q tests/unit/test_portfolio_events.py tests/integration/test_portfolio_events.py` — Expected: PASS. Then `uv run ruff check . && uv run mypy src` — clean.

- [ ] **Step 5: Commit** `fix(#226): a sign flip is position_closed then position_opened`.

### Task 2: atlas — boards and model say the flip

**Files:**
- Modify: `docs/pipeline/models/portfolio.tla` (`PositionOpenedFires`, ~line 354-361: drop `prev # "with_it"` from the guard, keep `held`; update its `(* ... *)` citation to name the sign flip)
- Modify: `docs/pipeline/models/portfolio.view.js` (`PositionOpenedFires` label, Decision 4)
- Modify: `docs/pipeline/portfolio-events.d2` (the `position opened` and `position closed` edges, Decision 4; `window` node label: `size changed above 10%` becomes `size changed above 10%, same sign; a sign flip closes then opens`)
- Modify: `docs/pipeline/portfolio.d2` (`events.position_opened`, `events.position_closed`, `events.position_size_changed`, Decision 4)
- Test: `tests/unit/test_pipeline_diagram.py` (`"events.position_opened"` / `"events.position_closed"` / `"events.position_size_changed"` phrase pins near line 2093), `tests/unit/test_pipeline_subboards.py` (`_PORTFOLIO_TEXT["portfolio-events"]`)
- Generated, never by hand: `docs/pipeline/*.svg`, `docs/pipeline/rendered.sha256`

**Interfaces:**
- Consumes: Task 1's behaviour (the labels describe it).
- Produces: nothing code consumes.

- [ ] **Step 1: Write the failing pins**: in `test_pipeline_diagram.py` add `"other sign"` to the `events.position_opened` and `events.position_closed` lists and `"same sign"` to `events.position_size_changed`; in `test_pipeline_subboards.py` add `"sign flip (long ↔ short)"` to `_PORTFOLIO_TEXT["portfolio-events"]`.
- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_pipeline_diagram.py tests/unit/test_pipeline_subboards.py tests/unit/test_pipeline_models.py` — Expected: the new pins FAIL.
- [ ] **Step 3: Edit** the four files per Decisions 3 and 4. The edge's first line must equal the view label exactly (`test_pipeline_models.py` matches them).
- [ ] **Step 4: Run** the same three test files plus `python3 docs/pipeline/check.py` — Expected: PASS except the render-hash check, which only passes once the SVGs and `rendered.sha256` are regenerated (Step 5).
- [ ] **Step 5: Render.** If `d2` v0.9.0 with TALA is on `PATH`, run `docs/pipeline/build.sh`; otherwise push the branch, download `pipeline-render` from the `pipeline-diagram` run (`gh run download <id> -n pipeline-render`), copy `portfolio.svg`, `portfolio-events.svg` and `rendered.sha256` (and any other SVG that changed) into `docs/pipeline/`. Then `python3 docs/pipeline/check.py` PASS. TLC: the `models` job of the same run must be green (`portfolio | ... 0 errors`).
- [ ] **Step 6: Commit** `docs(#226): atlas says a sign flip closes then opens` (render in its own commit `docs(#226): render` if it came from CI).
