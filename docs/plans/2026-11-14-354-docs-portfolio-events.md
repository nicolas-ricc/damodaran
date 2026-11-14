# Boards and status plan describe detected events and event-derived reviews — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The portfolio board, the portfolio-alerts sub-board and the `rep-portfolio` card of the status plan say what `portfolio.md` now contains: a `## Detected events` section and suggested reviews derived from the day's derived §8.3 events (#352, #353). The SVGs, `rendered.sha256` and `estado.html` are regenerated from them.

**Architecture:** Documentation only, on top of `feature/86-portfolio-md-events`. The code is already there:
`PortfolioReport.events` and `review_events`, `REVIEW_EVENT_TYPES` (`src/bot/portfolio/report.py:45-53`, the five types `new_filing`, `intrinsic_value_crossed_price`, `new_red_flag`, `below_quality_gate`, `sector_recalibrated`), the `bps` filter (`report.py:352`), the `## Detected events` block and the per-event review lines (`src/bot/reporting/templates/portfolio.md.j2`), the shared table partial `src/bot/reporting/templates/events_table.md.j2` (included by `portfolio.md.j2` and `alerts.md.j2`), and `run_portfolio` passing `events=day_events` to `build_report` (`src/bot/portfolio/command.py:170-178`). The module docstrings of `report.py` and `command.py` already describe both behaviours, so they do not change.

**Tech Stack:** d2 v0.9.0 (TALA, pinned by `docs/pipeline/D2_VERSION`, on `PATH` here), Python 3 build scripts under `docs/plano/`, pytest.

**Spec:** GitHub issue #354 (parent story #86, its plan comment fixes the per-event wording).

## Global Constraints

- The **first line** of `reports.portfolio` (`portfolio.d2`) and of `portfolio_written` (`portfolio-alerts.d2`) stays as is (matched against the model's `states`/`steps` labels). No edge's first line changes. `docs/pipeline/models/` is not touched.
- `flagged above 15%` stays on the source line that carries `@const bot.portfolio.events.DEFAULT_CONCENTRATION_THRESHOLD`. New text cites **no new digits**: counts in words, no `10-K`, no `bps` amounts, no `§8.3` (`test_every_step_has_purpose_and_edges` flags any number on a step's line that its directives do not cite).
- The substrings already pinned stay: `_PORTFOLIO_TEXT["reports.portfolio"]` in `tests/unit/test_pipeline_diagram.py:2152` and `_PORTFOLIO_TEXT["portfolio-alerts"]` in `tests/unit/test_pipeline_subboards.py:587`.
- `portfolio-alerts.d2` stays at or under `_MAX_EDGES = 24` edges (19 today, 21 after).
- Render only with `docs/pipeline/build.sh`. Never edit an SVG or `rendered.sha256` by hand. PNGs stay git-ignored.
- `AUDITADO_EN` / `AUDITADO_EL` in `docs/plano/estado.py` do not change.
- `README.md` does not change: its `bot portfolio` section never mentions `portfolio.md`, it describes `alerts.md` and notifications only (`README.md:259-275`; `grep -n portfolio.md README.md` is empty). The issue says to leave it in that case.

### Exact wording

The board lines use the words of the template's actions (`portfolio.md.j2`) and of the parent plan's decisions 1-3.

`reports.portfolio`: insert, after `flagged above 15%`, the lines

```
detected events: all of today's events, IBKR-observed included, the same table as alerts.md
suggested review: each flagged position, consider trimming,
then one per derived event, with its action: new filing, read it and run bot analyze;
intrinsic value crossed price, review whether to add or trim; new red flag, re-read the story;
below quality gate, review the thesis; sector recalibrated, re-check the margin of safety
IBKR-observed events never suggest a review
```

replacing the current `suggested review: each flagged position, consider trimming` line. `--history: …` stays last.

`portfolio_written`: replace its last line (`suggested review: each flagged position, consider trimming`) with the same six lines.

`estado.py` card `rep-portfolio` evidence text: replace the first sentence with

> Resumen, posiciones, P&L, concentración, eventos detectados y revisiones sugeridas. La sección de eventos detectados lista todos los eventos del día, los de IBKR incluidos, con la misma tabla que alerts.md (y "No events detected today" en un día sin eventos). Las revisiones sugeridas son primero las posiciones sobre el umbral (considerar recortar) y después una por cada evento derivado del día, con su acción: nuevo filing (leerlo y correr bot analyze), valor intrínseco que cruzó el precio (evaluar comprar más o recortar), nueva bandera roja (releer la historia), por debajo de una compuerta de calidad (revisar la tesis) y sector recalibrado (volver a mirar el margen de seguridad). Los eventos observados en IBKR nunca sugieren una revisión. Con --history agrega la historia y con --concentration el desglose.

The rest of the text (from `alerts.md se escribe siempre…`) is unchanged. The pointer `portfolio/report.py:241` becomes `portfolio/report.py:262` (`def build_report` moved with #352/#353).

## Acceptance criteria → tasks

- `python3 docs/pipeline/check.py` passes: Task 3.
- The three pipeline test files pass: Tasks 1, 2, 3.
- Both boards name the detected-events section, the five derived events, and that IBKR-observed events never suggest a review; `events_table.md.j2` cited with `@file` on the alerts sub-board: Tasks 1, 2.
- `rep-portfolio` describes both behaviours, `estado.html` regenerated, `build.py` exits 0: Task 4.
- Full suite, ruff, mypy: Task 4, last step.

## Review Focus

1. A rendered SVG that lacks the new text while `rendered.sha256` is fresh passes `check.py`. Task 3 adds a test that reads the two SVGs.
2. Re-rendering every board must change only `portfolio.svg`, `portfolio-alerts.svg` and `rendered.sha256`. Any other SVG in the diff means a wrong d2 or seed. Task 3 checks `git status`.
3. `estado.html` can be forgotten after editing `estado.py` (no test compares them today). Task 4's test checks that the HTML carries the card's new text.
4. A digit slipped into a step line (say `10-K`) fails the uncited-number audit only on `portfolio.d2` (a step), not on `portfolio-alerts.d2` (`portfolio_written` is a decision). The wording above has no digit on either board.
5. The `estado.py` line pointer drifts silently. Task 4's test checks that the cited line of `report.py` is `def build_report`.

---

### Task 1: `reports.portfolio` on `portfolio.d2`

**Files:**
- Modify: `docs/pipeline/portfolio.d2:148`
- Test: `tests/unit/test_pipeline_diagram.py` (`_PORTFOLIO_TEXT["reports.portfolio"]`, line 2152)

**Interfaces:** the wording in Global Constraints.

- [ ] **Step 1 (stage-3 eval, committed failing in `test(#354): evals`):** `_PORTFOLIO_TEXT["reports.portfolio"]` gains `"detected events"`, `"the same table as alerts.md"`, `"new filing"`, `"intrinsic value crossed price"`, `"new red flag"`, `"below quality gate"`, `"sector recalibrated"`, `"IBKR-observed events never suggest a review"`.
- [ ] **Step 2:** `uv run pytest -q tests/unit/test_pipeline_diagram.py -k "portfolio_text"` → FAIL on `reports.portfolio`.
- [ ] **Step 3:** edit the label per Global Constraints.
- [ ] **Step 4:** `uv run pytest -q tests/unit/test_pipeline_diagram.py` → PASS (render-dependent tests of Task 3 aside).
- [ ] **Step 5:** commit `docs(#354): the portfolio board describes detected events and event-derived reviews`.

### Task 2: `portfolio_written` and the events-table partial on `portfolio-alerts.d2`

**Files:**
- Modify: `docs/pipeline/portfolio-alerts.d2` (node `portfolio_written`, line 17; Files and Edges sections)
- Test: `tests/unit/test_pipeline_subboards.py` (`_PORTFOLIO_TEXT["portfolio-alerts"]`, line 587; new test)

**Interfaces:** the wording in Global Constraints. New file node key `events_table`.

- [ ] **Step 1 (stage-3 eval):** `_PORTFOLIO_TEXT["portfolio-alerts"]` gains the same eight phrases as Task 1. New test `test_portfolio_alerts_cites_the_events_table_partial`: the board text contains `@file src/bot/reporting/templates/events_table.md.j2`, and `edges(text)` holds `events_table -> portfolio_written` and `events_table -> alerts_written`, both labelled `layout`.
- [ ] **Step 2:** `uv run pytest -q tests/unit/test_pipeline_subboards.py -k "portfolio"` → both FAIL.
- [ ] **Step 3:** edit `portfolio_written` per Global Constraints. Under `# Files` add `events_table: "src/bot/reporting/templates/events_table.md.j2" {class: file}  # @file src/bot/reporting/templates/events_table.md.j2`. After `alerts_template -> alerts_written: "layout"` add `events_table -> portfolio_written: "layout"` and `events_table -> alerts_written: "layout"`.
- [ ] **Step 4:** `uv run pytest -q tests/unit/test_pipeline_subboards.py tests/unit/test_pipeline_models.py` → PASS.
- [ ] **Step 5:** commit `docs(#354): the alerts sub-board describes detected events and cites the events table`.

### Task 3: re-render

**Files:**
- Modify (generated): `docs/pipeline/portfolio.svg`, `docs/pipeline/portfolio-alerts.svg`, `docs/pipeline/rendered.sha256`
- Test: `tests/unit/test_pipeline_diagram.py`, new `test_event_derived_reviews_are_rendered`

- [ ] **Step 1 (stage-3 eval):** `test_event_derived_reviews_are_rendered`, parametrised over `portfolio` and `portfolio-alerts`: `"IBKR-observed events never suggest a review"` and `"the same table as alerts.md"` are in `html.unescape((_PIPELINE / f"{stem}.svg").read_text(encoding="utf-8"))` (use the module's existing path constant for `docs/pipeline`).
- [ ] **Step 2:** run it → FAIL for both.
- [ ] **Step 3:** `docs/pipeline/build.sh`.
- [ ] **Step 4:** `git status --short docs/pipeline` lists only the two SVGs and `rendered.sha256`; `python3 docs/pipeline/check.py` → `0 errors`; the three pipeline test files pass.
- [ ] **Step 5:** commit `docs(#354): re-render the portfolio boards`.

### Task 4: the `rep-portfolio` card of the status plan

**Files:**
- Modify: `docs/plano/estado.py:154-155`, generated `docs/plano/estado.html`
- Test: new `tests/unit/test_estado_rep_portfolio.py`

- [ ] **Step 1 (stage-3 eval):** the new test loads `docs/plano/estado.py` with `importlib.util.spec_from_file_location` and finds the tuple whose id is `rep-portfolio` across `INVENTARIO.values()` (each value is `(title, subtitle, cards)`, a card is `(id, name, state, evidence, note)`).
  - `test_rep_portfolio_describes_detected_events_and_reviews`: the note contains `eventos detectados`, `misma tabla que alerts.md`, `nuevo filing`, `valor intrínseco`, `bandera roja`, `compuerta de calidad`, `sector recalibrado`, `nunca sugieren una revisión`.
  - `test_rep_portfolio_points_at_build_report`: the evidence is `portfolio/report.py:N` and line N of `src/bot/portfolio/report.py` starts with `def build_report(`.
  - `test_estado_html_carries_the_rep_portfolio_note`: `html.escape(note)` is in `docs/plano/estado.html` (the module escapes with `html.escape`, `estado.py:14`).
- [ ] **Step 2:** `uv run pytest -q tests/unit/test_estado_rep_portfolio.py` → the three FAIL.
- [ ] **Step 3:** edit the card per Global Constraints; `python3 docs/plano/build_estado.py`; `python3 docs/plano/build.py`.
- [ ] **Step 4:** the new tests pass; `git status --short docs/plano` lists only `estado.py` and `estado.html`; `uv run pytest -q && uv run ruff check . && uv run mypy src` pass.
- [ ] **Step 5:** commit `docs(#354): the status plan describes detected events and event-derived reviews`.

## Assumptions

- **No `events_log -> portfolio_written` edge.** `portfolio.md` now reads the day's logged events, but `alerts.md` reads the same list and the board draws no `events_log` edge into either: the flow `logged -> portfolio_written` carries it. The issue asks for the two `layout` edges only. Rejected: adding a store edge to one report but not the other.
- **`estado.html` regeneration keeps the stale-audit banner.** `build_estado.py` prints the warning that 49 commits touched `src/` after `90f717c`; the committed HTML already carries the banner (`class="viejo"`), and the issue forbids bumping `AUDITADO_EN`. Re-running it on the base branch produces no diff, so the only change will be the card.
- **`build.py` rewrites nothing.** On the base branch it exits 0 and leaves the tree clean; it is run as a check only.
- **Intermediate commits can be red** (stage 3 commits failing tests; `check.py` flags a stale hash between Tasks 1-2 and 3). The pull request is squash-merged.
