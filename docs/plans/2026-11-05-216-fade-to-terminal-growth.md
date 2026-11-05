# #216 Fade every growth path to terminal growth over 10 years — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The explicit forecast runs 10 years, and every non-manual revenue-growth path fades linearly from its start to the resolved terminal growth. Today only high-growth fades, its target is GDP, and the horizon is 5.

**Architecture:** `_HORIZON` goes from 5 to 10 in `src/bot/valuator/assumptions.py`. `resolve_assumptions` resolves terminal growth before revenue growth and hands the result to `_resolve_revenue_growth` as the fade target. Margin paths, the DCF, the tornado and the grid already follow the path length, so they need no new logic. The report and the web view label the growth row with both ends of the path. The goldens and docs are regenerated or reworded.

**Tech Stack:** Python 3.12, pytest, DuckDB, Jinja2, d2 (rendered in CI), TLA+ (TLC in CI).

**Spec:** issue #216, in particular the "Agent Brief" comment (the maintainer's decisions from 2026-11-05). Spec §7.3 in `docs/superpowers/specs/2026-05-25-investment-bot-design.md`.

## Global Constraints

- `_HORIZON = 10`.
- The fade target is the **resolved terminal growth** (`min(rfr, nominal GDP)` of the valuation currency, or the manual `terminal_growth`), not GDP.
- Growth path when not manual: `_linear_path(start, g_terminal, 10)`. Year 1 = start, year 10 = `g_terminal` **exactly** (bit-equal).
- Start = mean of the historical path (the existing helper; #215 will change it to the CAGR on its own). With no history, start = the currency's nominal GDP.
- Sources: high-growth with history → `story_pattern`. Other stories with history → `historical_average`. GDP start → `rule_based`. No terminal growth, or no start → `unresolved`.
- A manual growth list of length k keeps N = k with no fade. A manual scalar repeats over 10 years.
- Margins: the high-growth ramp is `_linear_path(company_margin, sector_margin, 10)`. Cyclical average and sector median are flat over 10. A manual margin list is cut or extended to N by `to_dcf_assumptions`, as today.
- Out of scope: analyst consensus (#63), story paths beyond growth such as mature-decline (#213), the shape of the sensitivity shocks (#217). `mature-decline` has no margin branch in the code yet, so "flat over 10 years" for it is the generic sector-median path.
- Conventional Commits, `mypy --strict`, ruff clean.

## Review Focus

1. **Uncovered currency with history, no manual terminal growth.** Today a high-growth or flat path falls back to the historical average. Now it is `unresolved`. The valuation already fails on `terminal_growth` first (`to_dcf_assumptions` requires it before growth), so the outcome is unchanged. Test: Task 1 `test_growth_is_unresolved_without_terminal_growth`.
2. **Manual terminal growth with an uncovered currency and history.** The fade must still run, to the manual value. Test: Task 1 `test_manual_terminal_growth_fades_even_with_an_uncovered_currency` (`currencies={}` leaves USD uncovered, override `terminal_growth: 0.02`, 10% history → `historical_average`, 10 values, last `== 0.02`).
3. **Float drift on year 10.** `start + step * 9` can miss `end` by one ulp. `_linear_path` must return `end` itself as the last element. Test: Task 1 asserts `path[-1] == g_terminal` with `==`, not `approx`.
4. **A manual 5-value growth list with an automatic margin path.** The margin path is 10 long and must be cut to 5. Test: Task 1 `test_manual_growth_list_keeps_its_length` checks `to_dcf_assumptions().operating_margin` has length 5.
5. **Old JSON sidecars with 5-year paths in the web viewer.** The label must use the sidecar's own path length (`yr 1 → yr 5`), not the constant. Test: Task 2 `test_growth_row_label_uses_the_path_length`.

---

### Task 1: Horizon 10 and fade to terminal growth

**Files:**
- Modify: `src/bot/valuator/assumptions.py`: `_HORIZON` and its comment (≈l.72-77), the module docstring (resolution order mentions consensus/historical), `_linear_path` (≈l.975), `_resolve_revenue_growth` (≈l.983) with its docstring, `_resolve_operating_margin` docstring, `resolve_assumptions` (≈l.886-910), the `_growth_path_from_revenues` / `_historical_growth_path` docstrings
- Test: `tests/unit/test_valuator_assumptions.py`, plus the existing 5-length assertions in `tests/unit/test_valuator_assumptions.py`, `tests/unit/test_currency_valuation.py:103`, `tests/unit/test_valuator_analysis.py:301-308,436`

**Interfaces:**
- Produces: `_HORIZON: int = 10`
- Produces: `_linear_path(start: float, end: float, n: int = _HORIZON) -> tuple[float, ...]`. Same contract, plus the last element is `end` itself.
- Produces: `_resolve_revenue_growth(historical: tuple[float, ...] | None, override: dict[str, Any], gdp: float | None, *, terminal_growth: float | None, story_type: StoryType | None = None) -> Sourced[tuple[float, ...] | None]`. `gdp` is only the no-history start now, never the target.
- `resolve_assumptions`: compute `terminal_growth = _resolve_terminal_growth(override, rates)` before revenue growth and pass `terminal_growth.value`.

- [ ] **Step 1: Write the failing tests** (in `test_valuator_assumptions.py`; the default currency table gives USD `g_terminal = min(0.0395, 0.04) = 0.0395`)

```python
def test_mature_stable_growth_fades_from_history_to_terminal_growth(conn) -> None:
    _seed_full_sector(conn)
    # 100 → 118 → 139.24: two YoY growths of 18% → start 0.18 (mean == CAGR here).
    _seed_financials(conn, rows=((2022, 100.0, 18.0), (2023, 118.0, 20.0), (2024, 139.24, 22.0)))
    a = resolve_assumptions("ACME", conn, auto_story_type=StoryType.MATURE_STABLE)
    path = a.revenue_growth.value
    assert a.revenue_growth.source is AssumptionSource.HISTORICAL_AVERAGE
    assert path == pytest.approx(tuple(0.18 + (0.0395 - 0.18) * i / 9 for i in range(10)))
    assert len(path) == 10 and path[-1] == a.terminal_growth.value == 0.0395

def test_high_growth_fades_to_terminal_growth_not_gdp(conn) -> None:
    # same seed as test_high_growth_revenue_path_fades_from_history_to_gdp (30% history)
    # source STORY_PATTERN, len 10, path[0] ≈ 0.30, path[-1] == 0.0395 (not 0.04)

def test_manual_terminal_growth_is_the_fade_target(conn, tmp_path) -> None:
    # override "terminal_growth: 0.02\n", 10% history → len 10, path[-1] == 0.02

def test_growth_without_history_fades_from_gdp_to_terminal_growth(conn) -> None:
    # one revenue row, currencies=_usd(rfr=0.03) → RULE_BASED, path[0] == 0.04, path[-1] == 0.03, len 10

def test_manual_terminal_growth_fades_even_with_an_uncovered_currency(conn, tmp_path) -> None:
    # currencies={} (USD uncovered), override "terminal_growth: 0.02\n", 10% history
    # → HISTORICAL_AVERAGE, len 10, path[-1] == 0.02

def test_growth_is_unresolved_without_terminal_growth() -> None:
    assert _resolve_revenue_growth((0.1,) * 10, {}, None, terminal_growth=None).source \
        is AssumptionSource.UNRESOLVED

def test_manual_growth_list_keeps_its_length(conn, tmp_path) -> None:
    # override "revenue_growth: [0.1, 0.1, 0.1, 0.1, 0.1]\n" → value == (0.1,) * 5, MANUAL
    # and len(a.to_dcf_assumptions().operating_margin) == 5

def test_manual_growth_scalar_repeats_over_ten_years(conn, tmp_path) -> None:
    # override "revenue_growth: 0.07\n" → value == (0.07,) * 10, MANUAL

def test_high_growth_margin_ramp_has_ten_points(conn) -> None:
    # seed as test_high_growth_margin_ramps_from_company_to_sector → len 10, 0.08 → 0.20

def test_linear_path_ends_exactly_on_its_target() -> None:
    assert _linear_path(0.18, 0.0395, 10)[-1] == 0.0395
```

Update the existing tests that pin the old behaviour: `(x,) * 5` margin assertions → `* 10`; `test_revenue_growth_uses_historical_average_when_no_consensus` (flat 10%) → path fades from 0.10 to 0.0395; `test_revenue_growth_without_history_falls_back_to_rule_based_gdp` → starts at GDP and ends at terminal growth; `test_high_growth_revenue_path_fades_from_history_to_gdp` → rename `..._to_terminal_growth`, end `0.0395`; `test_high_growth_fade_starts_at_the_historical_average_not_year_one` → pass `terminal_growth=0.04`.

- [ ] **Step 2: Run them, expect FAIL**

Run: `uv run pytest -q tests/unit/test_valuator_assumptions.py`
Expected: the new tests fail (length 5, GDP target, flat path).

- [ ] **Step 3: Implement** the interfaces above. Order inside `_resolve_revenue_growth`: manual → `terminal_growth is None` → unresolved → history start (story_pattern for HIGH_GROWTH, else historical_average) → GDP start (rule_based) → otherwise unresolved. Docstrings say 10 years and fade to terminal growth, and drop the "5-year horizon" wording.

- [ ] **Step 4: Fix the other suites' 5-length assertions** (`test_currency_valuation.py:103` now expects a GDP → terminal fade; `test_valuator_analysis.py` projections, grid and margin lengths). Run: `uv run pytest -q tests/unit/test_valuator_assumptions.py tests/unit/test_currency_valuation.py tests/unit/test_valuator_analysis.py`. Expected: PASS.

- [ ] **Step 5: Commit** `feat(#216): fade every growth path to terminal growth over 10 years`

### Task 2: Report and web view show the path's ends; DCF runs 10 years end to end

**Files:**
- Modify: `src/bot/reporting/analysis_report.py` (new helpers, registered as Jinja filters next to `margin_path`), `src/bot/reporting/templates/analysis.md.j2:44`, `src/bot/web/views.py:313-330,369`
- Test: `tests/unit/test_reporting_analysis.py`, `tests/unit/test_web_views.py:164,180`, `tests/unit/test_valuator_analysis.py`

**Interfaces:**
- Produces: `fmt_growth_label(path: Any) -> str`. Returns `"Revenue growth (yr 1 → yr {len(path)})"`, or `"Revenue growth (yr 1)"` for `None`/empty.
- Produces: `fmt_growth_path(path: Any) -> str`. Returns `"{fmt_pct(first)} → {fmt_pct(last)}"`, or the dash for `None`/empty. Both ends are always shown, so a flat path reads `7.0% → 7.0%`.
- Template filters `growth_label` and `growth_path`.

- [ ] **Step 1: Failing tests**
  - `test_growth_row_label_uses_the_path_length`: `fmt_growth_label((0.1,) * 5) == "Revenue growth (yr 1 → yr 5)"`; `fmt_growth_label(tuple(range(10))) == "Revenue growth (yr 1 → yr 10)"`.
  - `test_growth_path_shows_both_ends`: `fmt_growth_path((0.18, 0.0395)) == "18.0% → 4.0%"`; `fmt_growth_path(None) == "—"` (the module's `_DASH`).
  - In `test_reporting_analysis.py`: the rendered Markdown of a 10-year analysis contains `| Revenue growth (yr 1 → yr 10) |` and its DCF table has 10 year rows.
  - In `test_web_views.py`: the assumptions row label is `Revenue growth (yr 1 → yr N)` for the fixture's path length, and the totals label is `Present value of FCFF, years 1-N` with N = `len(dcf["projections"])`.
  - In `test_valuator_analysis.py`, `test_ten_year_paths_reach_dcf_tornado_and_grid`: a mature-stable analysis has `len(dcf_result.projections) == 10`, a non-empty tornado and a 5×5 grid. The grid is a multiplier grid, so it stays 5×5.
- [ ] **Step 2: Run, expect FAIL.** `uv run pytest -q tests/unit/test_reporting_analysis.py tests/unit/test_web_views.py tests/unit/test_valuator_analysis.py`
- [ ] **Step 3: Implement.** The template row becomes `| {{ path | growth_label }} | {{ path | growth_path }} | source |`. `views.py` builds the revenue-growth row's label from the path, drops `_fmt_first_year` if nothing else uses it, and computes the PV label from the number of projections. The tornado axis labels keep "(yr 1)": its swung values are year-1 only (`fmt_axis_label`).
- [ ] **Step 4: Run, expect PASS.**
- [ ] **Step 5: Commit** `feat(#216): report shows the growth path from yr 1 to yr N`

### Task 3: Regenerate the goldens

**Files:**
- Modify: `tests/fixtures/screener/second_pass_shortlist.golden`, `tests/fixtures/valuator/isolation/*.md|*.json`, docstrings of `tests/unit/test_screener_second_pass_golden.py` and `tests/unit/test_valuator_isolation_golden.py` (one note each: "regenerated for #216: 10-year horizon, growth fades to terminal growth")

- [ ] **Step 1:** `uv run pytest -q tests/unit/test_screener_second_pass_golden.py tests/unit/test_valuator_isolation_golden.py`. Expected: FAIL (paths changed).
- [ ] **Step 2:** Regenerate with the commands in each test's docstring (`GOLDEN.write_text(...)` and `regenerate()`), from the repo root.
- [ ] **Step 3:** Inspect the diff. Projections should be 10 rows, growth rows read `yr 1 → yr 10`, and the override fixture (manual scalar 0.08) shows `8.0% → 8.0%`. Re-run: PASS.
- [ ] **Step 4: Commit** `test(#216): regenerate goldens for the 10-year fade`, with a body explaining the move: the horizon goes 5 → 10 and every non-manual growth path fades linearly to terminal growth, so intrinsic values shift.

### Task 4: Docs, boards, model labels, lesson, plano

**Files:**
- Modify: `docs/pipeline/analyze.d2` (l.101 "paths over 5 years, ten for a hypergrowth story"; l.112 growth node; l.114 consensus gap: drop "and the horizon is 5 years", keep the no-consensus part; l.116 margin node "5-year path"; l.165 "5 unless a manual list differs, 10 with a story")
- Modify: `docs/pipeline/analyze-assumptions.d2` (l.59, 61: "a path over 5 years", the growth list), `docs/pipeline/analyze-dcf.d2` (l.61)
- Modify: `docs/pipeline/models/analyze.view.js` (`GrowthIsResolved`, `GrowthIsUnresolved` labels) and `docs/pipeline/models/analyze.tla` (the code-citation comments above `GrowthIsResolved` / `GrowthIsUnresolved`; `GrowthIsUnresolved` keeps its guard `currency = "uncovered"`, which is still necessary: no terminal growth needs an uncovered currency and no manual value, and no start needs no history and no GDP)
- Modify: `docs/leccion/index.html` (cap-6 table rows for high-growth, cyclical and mature-*: fade to the terminal growth over 10 years; cap-7 `data-const _HORIZON value="10"` text; `rule_based` and `historical_average` rows), `docs/plano/part-data.js:234`, `docs/plano/estado.py:114` (text says: historical average fading to terminal growth over ten years)
- Render: `docs/pipeline/*.svg` and `rendered.sha256` come from the `pipeline-diagram` CI artifact. d2 v0.9.0 is not installable in this session.

New wording (pinned, adapt the line breaks to the board):
- Growth: "revenue growth, a path over 10 years, fading in a straight line to the terminal growth (resolved first), tries in order: 1. manual → manual (a list keeps its length, no fade) 2. no terminal growth → unresolved 3. from the mean historical growth → story_pattern for high-growth, historical_average otherwise 4. no history: from nominal GDP growth → rule_based; no GDP either → unresolved".
- `GrowthIsUnresolved` label (view.js and the d2 edge's first line, kept identical): `revenue growth is unresolved [uncovered currency, and no history or no terminal growth set by hand]`.
- Every digit on a step label keeps its `@const` (`_HORIZON` is now 10). The model's step order stays: terminal growth is still a later step there. The model is one unit's abstract flow and the order changes no outcome, so the label says "resolved first" instead of the plan reordering the model.

- [ ] **Step 1:** `uv run pytest -q tests/unit/test_pipeline_diagram.py tests/unit/test_pipeline_models.py tests/unit/test_pipeline_subboards.py tests/unit/test_leccion.py tests/unit/test_leccion_check.py` passes after the edits. `python3 docs/pipeline/check.py` fails only on `rendered.sha256` until the CI render lands. `python3 docs/leccion/check.py` passes. `python3 docs/plano/build.py` passes.
- [ ] **Step 2: Commit** `docs(#216): 10-year horizon and the fade to terminal growth`
- [ ] **Step 3 (orchestrator, after a push):** download the `pipeline-render` artifact of the branch's `pipeline-diagram` run (`gh run download <id> -n pipeline-render -D <empty dir>`), copy the `*.svg` files and `rendered.sha256` into `docs/pipeline/` (never the PNGs), confirm `python3 docs/pipeline/check.py` passes, and commit `docs(#216): re-render the boards`. TLC on `analyze.cfg` runs in the `models` job of the same workflow.

## Assumptions

Technical decisions taken where the issue leaves the choice open (rejected alternative in brackets):

- The growth row's cell is `first → last` even for a flat path, so the format is the same on every row. [Collapse a flat path to one value like `fmt_margin_path`: that would hide the `→ yr N` the brief asks for.]
- The TLA model and the sub-board keep the step order (growth, then terminal growth). The growth label says terminal growth is "resolved first". `GrowthIsUnresolved` keeps the guard `currency = "uncovered"`, a necessary condition of both unresolved causes. `GrowthIsResolved` has no guard (`analyze.tla:295-298`), so the model over-approximates as it already does. [Reorder the model's steps and sub-boards: larger churn, and the order changes no outcome.]
- The start stays `fmean(historical)` over the existing flat historical path. [Switch to the CAGR here: that is #215.]
- `_linear_path` with `n == 0/1` is unchanged. No caller passes anything but `_HORIZON`; manual paths return before it (`assumptions.py:1005-1006`).
- The spec §7.3 text ("converge a GDP nominal país en y10") is not edited here; follow-up #238.

## Grilling

- Rounds: 1 (griller model: fable). The plan changed only locally: one test firmed, Assumptions added. No second round.
- Questions: 16. Sources: ISSUE 5 (Q2, Q3, Q8 in part, Q12, Q14 in part), CODE 11 (Q1 `assumptions.py:886`, rates come from `db_inputs` loaded before resolution; Q4 `sensitivity.py:157-159` scales every year by the multiplier; Q5 `assumptions.py:975-980`; Q6 `assumptions.py:212-213` extends with the last value; Q7 `analyze.tla:295-306`; Q8 `assumptions.py:210-211`, and `analysis.py:154` makes `dcf_result` non-optional, so no report or sidecar exists for a failed valuation; Q10 `test_valuator_assumptions.py:52-62`; Q11 grep for `_HORIZON` and `* 5` in `src/`: only `assumptions.py` plus `web/views.py:369` "years 1-5", now in Task 2; Q13 same as Q8; Q15 `test_pipeline_diagram.py:2611,2632` strips ordinals and `test_pipeline_models.py` matches labels with the boards; Q14 `.github/workflows/pipeline-diagram.yml` pins d2 from `D2_VERSION`), DOC 1 (Q16 spec §7.3), NO SOURCE 3: Q2 cell format, Q7 model order, Q9 uncovered test → technical assumptions above; Q16 → out of scope.
- Issues opened: #238 (spec §7.3 wording vs the terminal-growth target).
