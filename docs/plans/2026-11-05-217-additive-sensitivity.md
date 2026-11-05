# Additive ±1pp sensitivity for rate axes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The tornado and the 2-D grid move rate assumptions by additive percentage points and keep `sales_to_capital` multiplicative, and every surface (Markdown, HTML, JSON sidecar, site, atlas) labels the shock it applied.

**Architecture:** `bot.valuator.sensitivity` gains a `ShockKind` per `SensitivityAxis` and a kind-aware `shift_axis` that replaces `scale_axis`. `TornadoEntry` carries its kind and `Grid2D` carries steps and kind per axis. The reporting layer formats a step from `(value, kind)`, so labels never assume one convention. The site reads the new sidecar fields and falls back to the old ones for sidecars written before #217.

**Tech Stack:** Python 3.12, pytest, Jinja2, matplotlib, Plotly, d2 v0.9.0 (atlas), TLA+ (models).

**Spec:** GitHub issue #217 ("Sensitivity ±20% is multiplicative…"), Agent Brief comment (maintainer decision 2026-11-05).

## Global Constraints

- Additive axes: `revenue_growth`, `operating_margin`, `tax_rate`, `terminal_growth`, `cost_of_equity`, `pretax_cost_of_debt`. Multiplicative: `sales_to_capital`.
- Tornado: additive ends are base −0.01 / +0.01. Multiplicative ends are ×0.8 / ×1.2.
- Grid steps: additive `(-0.01, -0.005, 0.0, 0.005, 0.01)`, multiplicative `(0.8, 0.9, 1.0, 1.1, 1.2)`.
- A path axis shifts every year by the same pp. `COST_OF_EQUITY` also shifts `wacc_path`, and `TAX_RATE` also shifts `tax_rate_path`, by the same step (same coupling as today).
- Labels: additive steps read `-1.0pp … +1.0pp` (one decimal, explicit sign, ASCII minus as the current `fmt_mult` uses). Multiplicative steps read `×0.8 … ×1.2`.
- Out of domain → `None` (no value, ranked last in the tornado, empty grid cell): `terminal_growth ≥ terminal WACC` (as today), tax rate (or any `tax_rate_path` element) outside `[0, 1)`, `cost_of_equity ≤ 0`, `pretax_cost_of_debt ≤ 0`, any `wacc_path` element `≤ 0`. Any other `ValueError` from `dcf` still surfaces.
- JSON sidecar `schema_version` stays `1`. Out of scope: configurable shock sizes, new axes.
- `mypy --strict`, ruff and the full suite (`uv run pytest -q`) stay green. `valuator/` targets 100% coverage.

## Assumptions

These are technical assumptions, decided and declared. Each names the rejected alternative.

- **Name.** `scale_axis` becomes `shift_axis(assumptions, axis, step)`. `step` is a pp delta for an additive axis and a factor for a multiplicative one. The old name is removed, together with its export in `bot.valuator.__init__`.
- **Kind on the enum.** `SensitivityAxis.kind` is a property returning `ShockKind`. `ShockKind` is a `StrEnum` with values `"additive"` / `"multiplicative"`, so it serialises as a plain string in the sidecar.
- **Public step tables.** `tornado_steps(kind) -> tuple[float, float]` and `grid_steps(kind) -> tuple[float, float, float, float, float]` are the single source the reporting layer formats from. The constants behind them are `_TORNADO_SHIFT = 0.01`, `_TORNADO_LOW = 0.8`, `_TORNADO_HIGH = 1.2`, `_GRID_SHIFTS`, `_GRID_MULTIPLIERS`.
- **Grid2D fields.** `row_multipliers` / `col_multipliers` are replaced by `row_steps`, `col_steps`, `row_kind`, `col_kind`. A grid holding additive steps under a field called "multipliers" would mislead every reader. Sidecars written before #217 have `row_multipliers` and no kind; the site reads them as multiplicative steps. That keeps `schema_version` 1 with old sidecars still readable, which is the same approach `analysis_json` documented for #219. `TornadoEntry` gains `kind` (an additive field in the sidecar). An old tornado entry without `kind` reads as multiplicative.
- **Domain guard scope.** The guards beyond `g ≥ WACC` apply only to the axes a scenario actually moved, i.e. those whose step is not the identity (`0.0` additive, `1.0` multiplicative). The new guards therefore never touch the grid centre, even when a hand-written override sits on a domain edge (for example `pretax_cost_of_debt: 0`). The `g ≥ WACC` guard stays unconditional, as today. In production a base with `g ≥ WACC` never reaches the sensitivity, because `analyze` runs `dcf` on the base first (`analysis.py:937`) and that raises (`dcf.py:265`). Rejected alternative: guarding every scenario on every field, which would blank the centre of such an override.

- **Coupled paths shift by the same pp.** A `wacc_path` is a story's all-in discount rate: it replaces the built-up WACC (`dcf.py` `Assumptions.wacc_path`), so on that path the cost-of-equity axis *is* the discount rate. Shifting it by the same pp is the additive analogue of today's same-factor scaling (`sensitivity.py:15-17`). Rejected alternative: an equity-weighted shift, which would invent a weighting the path never had.
- **The tax guard lives in sensitivity, not in `dcf`.** `dcf` validates no tax rate today (`dcf.py:243-269`). The `[0, 1)` and `≤ 0` rules are a sensitivity wrapper only, and `dcf` semantics do not change.
- **`fmt_step(…, kind)` coerces with `ShockKind(kind)`**, so an unknown kind string raises `ValueError`. In the site, `_renderable` (`site.py:108-118`) catches `KeyError`/`ValueError` and skips that sidecar, as it does for any malformed one. For the same reason the site reads `grid["row_multipliers"]` by index on the fallback path: a sidecar with neither key raises `KeyError` and is skipped. Rejected alternative: formatting unknown kinds silently.
- **Signed zero.** The centre step reads `+0.0pp` / `×1.0`, continuing today's `+0%` (`fmt_mult`, golden `isolation/*.md` line 66). The constant is the literal `0.0`, so it is never `-0.0`.
- **Commits per task with a red downstream suite.** Tasks 1–3 change a shared dataclass, so the suite turns green only after Task 3. Stage 3 commits failing evals by design. The branch is squash-merged, so `master` never sees a red commit. Rejected alternative: one big commit, which would leave nothing for the per-task reviewer to review.
- **Scope of the prose docs.** The lesson and the plano are updated because CONTEXT.md says to: "update both when finishing one" (the plans) and that the lesson's `check.py` polices cited symbols. The spec §7.4 is the source of truth (CONTEXT.md "Source of truth") and would otherwise say ±20%.

## Review Focus

1. Negative base growth (−0.05): "high" is the optimistic end (−0.04), so the tornado bar must not invert. Pinned in Task 1.
2. A sidecar written before #217 (no `kind`, `row_multipliers`): the site must still build and label it `×0.8 … ×1.2`. Pinned in Task 3.
3. A story with `wacc_path` and `tax_rate_path`: the coupled paths shift by the same pp, and `pretax_cost_of_debt` stays out of the active axes. Pinned in Task 1.
4. The grid centre equals the headline MoS exactly when one grid axis is additive and the other multiplicative. Pinned in Task 1.
5. An override whose base already sits on a domain edge (`pretax_cost_of_debt: 0.0`): the centre cell still has a value. Pinned in Task 1.

---

### Task 1: Kind-aware shocks in `bot.valuator.sensitivity`

**Files:**
- Modify: `src/bot/valuator/sensitivity.py`, `src/bot/valuator/__init__.py`, `src/bot/valuator/analysis.py` (the `tornado` attribute docstring, line ~116)
- Test: `tests/unit/test_valuator_sensitivity.py`

**Interfaces:**
- Produces:
  - `class ShockKind(StrEnum)` with members `ADDITIVE = "additive"` and `MULTIPLICATIVE = "multiplicative"`
  - `SensitivityAxis.kind -> ShockKind` (property): `MULTIPLICATIVE` for `SALES_TO_CAPITAL` only
  - `tornado_steps(kind: ShockKind) -> tuple[float, float]`: `(-0.01, 0.01)` or `(0.8, 1.2)`
  - `grid_steps(kind: ShockKind) -> tuple[float, float, float, float, float]`
  - `shift_axis(assumptions: Assumptions, axis: SensitivityAxis, step: float) -> Assumptions`
  - `TornadoEntry(axis, kind, low_value, high_value, intrinsic_low, intrinsic_high, impact)`, where `kind: ShockKind` comes right after `axis`
  - `Grid2D(axis_a, axis_b, row_kind: ShockKind, col_kind: ShockKind, row_steps: tuple[5 floats], col_steps: tuple[5 floats], cells, reference_price=None)`
  - all exported from `bot.valuator` (`ShockKind`, `shift_axis`, `tornado_steps`, `grid_steps`). `scale_axis` is removed.

- [ ] **Step 1: Write the failing tests.** Replace the `scale_axis` tests with `shift_axis` equivalents and add the following (use the module's existing `_financials()` / `_assumptions()` helpers, passing `dataclasses.replace` overrides):
  - `test_growth_one_percent_tornado_ends_are_zero_and_two_percent`: base growth path `(0.01,)*5` → the `REVENUE_GROWTH` entry has `low_value ≈ 0.00`, `high_value ≈ 0.02`, `kind is ShockKind.ADDITIVE`.
  - `test_negative_growth_low_end_is_more_negative`: growth `(-0.05,)*5` → `low_value ≈ -0.06`, `high_value ≈ -0.04`.
  - `test_sales_to_capital_stays_multiplicative`: `sales_to_capital=2.0` → ends `1.6` / `2.4`, `kind is ShockKind.MULTIPLICATIVE`.
  - `test_shift_axis_moves_every_year_of_a_path_by_the_same_pp`: a non-flat path `(0.30, 0.25, 0.20, 0.15, 0.10)` shifted by `-0.01` gives `(0.29, 0.24, 0.19, 0.14, 0.09)`.
  - `test_shift_axis_couples_wacc_path_and_tax_rate_path`: `COST_OF_EQUITY` +0.01 adds 0.01 to every `wacc_path` element, and `TAX_RATE` −0.01 subtracts 0.01 from every `tax_rate_path` element.
  - `test_shift_axis_does_not_mutate_input`.
  - `test_axis_kinds`: every axis except `SALES_TO_CAPITAL` is `ADDITIVE`.
  - `test_grid_steps_per_kind`: `grid_2d(…, REVENUE_GROWTH, SALES_TO_CAPITAL)` has `row_kind ADDITIVE`, `row_steps ≈ (-0.01, -0.005, 0, 0.005, 0.01)`, `col_kind MULTIPLICATIVE`, `col_steps ≈ (0.8, 0.9, 1.0, 1.1, 1.2)`.
  - `test_grid_centre_equals_base_margin_of_safety_exactly`: with `reference_price=50.0`, for a mixed pair (additive × multiplicative) and for an additive pair, `cells[2][2].margin_of_safety == dcf(fin, base).intrinsic_value / 50.0` (exact `==`, no tolerance).
  - `test_terminal_growth_plus_one_pp_at_wacc_is_none_and_ranked_last`: pick a `terminal_growth` such that `+0.01 ≥ terminal_wacc` while the base is below it. The `TERMINAL_GROWTH` entry has `intrinsic_high is None`, `impact is None`, and is the last entry.
  - `test_tax_rate_995_plus_one_pp_is_none_not_a_crash`: `tax_rate=0.995` → the `TAX_RATE` entry's `intrinsic_high is None`, `intrinsic_low` is a float, and the entry is last.
  - `test_cost_of_capital_shifted_to_zero_is_none`: `pretax_cost_of_debt=0.005` → `intrinsic_low is None`. Likewise `cost_of_equity=0.005` with a `wacc_path` containing `0.005`.
  - `test_base_on_domain_edge_keeps_a_valued_centre`: `pretax_cost_of_debt=0.0`, grid over `PRETAX_COST_OF_DEBT` × `OPERATING_MARGIN` → `cells[2][2].intrinsic_value == dcf(fin, base).intrinsic_value`, and rows 0–2 (steps ≤ 0) are `None` except the centre row.
  - Keep `test_grid_centre_matches_the_headline_margin_of_safety` (the existing test that compares against `analyze`'s headline MoS) passing unchanged.
  - `test_other_value_errors_still_surface`: rewrite the existing equivalent so it still holds (for example `shares_diluted=0` raises `ValueError` through `tornado`).
  - Update the existing ±20% tests (margin ends, grid multipliers, the diverging-cells test) to the new values.

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_valuator_sensitivity.py -q`. Expected: FAIL (ImportError on `ShockKind` / `shift_axis`).

- [ ] **Step 3: Implement.** `shift_axis` applies `value + step` (additive) or `value * step` (multiplicative), element-wise for path axes and for the coupled `wacc_path` / `tax_rate_path`. Change `_safe_intrinsic(financials, assumptions, moved: Collection[SensitivityAxis])` to return `None` for `g ≥ terminal_wacc`, and for the moved axes only: `TAX_RATE` with `tax_rate` (or any `tax_rate_path` element) outside `[0, 1)`; `COST_OF_EQUITY` with `cost_of_equity ≤ 0` or any `wacc_path` element `≤ 0`; `PRETAX_COST_OF_DEBT` with `≤ 0`. An axis counts as moved when its step is not the identity of its kind. `tornado` and `grid_2d` take their steps from `tornado_steps(axis.kind)` / `grid_steps(axis.kind)`. Rewrite the module docstring, the `TornadoEntry` / `GridCell` / `Grid2D` docstrings and the `_safe_intrinsic` docstring so they describe ±1pp versus ×0.8/×1.2 and the new guards. Leave nothing that says "±20%" for every axis.

- [ ] **Step 4: Run** `uv run pytest tests/unit/test_valuator_sensitivity.py -q && uv run mypy src`. Expected: PASS. Other suites that build `TornadoEntry`/`Grid2D` or read `row_multipliers` fail until Tasks 2–3; that is expected.

- [ ] **Step 5: Commit** `feat(#217): additive ±1pp shocks for rate axes`.

### Task 2: Report, HTML and JSON sidecar labels

**Files:**
- Modify: `src/bot/reporting/analysis_report.py`, `src/bot/reporting/templates/analysis.md.j2`, `src/bot/reporting/html.py`, `src/bot/reporting/analysis_json.py` (module docstring only)
- Regenerate: `tests/fixtures/valuator/isolation/*.md|*.json` with the `regenerate()` helper in `tests/unit/test_valuator_isolation_golden.py`. This is a deliberate behaviour change; add a docstring line naming #217.
- Test: `tests/unit/test_reporting_analysis.py`, `tests/unit/test_reporting_html.py`, `tests/unit/test_reporting_analysis_json.py`

**Interfaces:**
- Consumes: Task 1's `ShockKind`, `tornado_steps`, `TornadoEntry.kind`, `Grid2D.row_steps/col_steps/row_kind/col_kind`.
- Produces (in `bot.reporting.analysis_report`):
  - `fmt_step(value: float | None, kind: ShockKind | str) -> str`: additive `-0.01` → `"-1.0pp"`, `0.0` → `"+0.0pp"`, `0.005` → `"+0.5pp"`; multiplicative `0.8` → `"×0.8"`, `1.0` → `"×1.0"`; `None` → the dash
  - `fmt_shock(kind: ShockKind | str) -> str`: `"-1.0pp / +1.0pp"` or `"×0.8 / ×1.2"`, built from `tornado_steps`
  - `fmt_mult` is removed (Task 3 switches its last caller)

- [ ] **Step 1: Write the failing tests.**
  - `test_fmt_step_labels` covers the values above.
  - `test_tornado_table_shows_each_rows_shock`: the rendered §5 has the header `| Assumption | Shock | Intrinsic @ low | Intrinsic @ high | Impact |`. The `sales_to_capital` row contains `×0.8 / ×1.2` and the `revenue_growth (yr 1)` row contains `-1.0pp / +1.0pp`. The section heading no longer says `±20%`, and a convention line says rates move ±1 percentage point (every year of a path) and `sales_to_capital` ×0.8 / ×1.2.
  - `test_grid_table_labels_match_kind`: for a grid with an additive row axis and a multiplicative column axis, the header row is `-1.0pp | -0.5pp | +0.0pp | +0.5pp | +1.0pp` and the column labels are `×0.8 … ×1.2`, or the reverse for the opposite assignment.
  - HTML: the heatmap fragment contains `"-1.0pp"` and `"×1.2"` for such a grid, and contains no `"-20%"`. `tornado_chart_png` still returns PNG bytes. Update `test_reporting_html.py`'s hand-built `TornadoEntry`/`Grid2D` to the new fields.
  - JSON: a tornado entry carries `"kind"` ∈ {`"additive"`, `"multiplicative"`}; `grid` carries `row_steps`, `col_steps`, `row_kind`, `col_kind`; `schema_version == 1`.

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_reporting_analysis.py tests/unit/test_reporting_html.py tests/unit/test_reporting_analysis_json.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement.** Register `fmt_step` as the template filter `step` and `fmt_shock` as `shock`, replacing the `mult` filter. `_grid_table` labels with `fmt_step(step, kind)`. In `html.py`, replace `_pct_delta` with `fmt_step` and set the tornado x-label to `Intrinsic value per share (rates ±1pp, sales_to_capital ×0.8 / ×1.2)`, built from `fmt_shock` / `tornado_steps` and not hard-coded. Update the docstrings that say ±20%. In the `analysis_json` docstring, add the #217 paragraph: grids carry `row_steps`/`col_steps` with `row_kind`/`col_kind`, tornado entries carry `kind`, and older sidecars carry `row_multipliers`/`col_multipliers` with no kind (all multiplicative).

- [ ] **Step 4: Regenerate the isolation goldens** with the `regenerate()` command in that module's docstring. Then `git diff --stat tests/fixtures/valuator/isolation` should touch only §5 of the `.md` files and the `tornado`/`grid` blocks of the `.json` files. Confirm that `tests/unit/test_screener_second_pass_golden.py` and its fixtures are untouched and passing (`git status` shows no change there).

- [ ] **Step 5: Run** `uv run pytest tests/unit/test_reporting_analysis.py tests/unit/test_reporting_html.py tests/unit/test_reporting_analysis_json.py tests/unit/test_valuator_isolation_golden.py tests/unit/test_screener_second_pass_golden.py -q`. Expected: PASS.

- [ ] **Step 6: Commit** `feat(#217): report, HTML and sidecar label the shock kind`.

### Task 3: Site detail view

**Files:**
- Modify: `src/bot/web/views.py`, `src/bot/web/svg.py` (`tornado_table`), `src/bot/web/templates/detail.html` (the two ledes)
- Test: `tests/unit/test_web_views.py`, `tests/unit/test_web_svg.py`, `tests/unit/test_web_site_review.py`

**Interfaces:**
- Consumes: `fmt_step`, `fmt_shock` (Task 2).
- Produces: `TornadoBar(label, low, high, shock: str = "")`. `ScenarioGrid.row_labels/col_labels` are now built with `fmt_step`.

- [ ] **Step 1: Write the failing tests.**
  - `test_scenario_grid_labels_follow_kind`: a sidecar built from a current analysis → `row_labels`/`col_labels` are the `fmt_step` labels of its grid kinds (e.g. `("-1.0pp", …, "+1.0pp")` for `cost_of_equity`).
  - `test_pre_217_sidecar_reads_as_multiplicative`: take the payload, rename `grid.row_steps`/`col_steps` to `row_multipliers`/`col_multipliers`, and drop `row_kind`/`col_kind` and every tornado `kind`. `detail_view` does not raise, the labels are `("×0.8", "×0.9", "×1.0", "×1.1", "×1.2")`, and every `TornadoBar.shock == "×0.8 / ×1.2"`. The site build (`_renderable`) keeps this analysis.
  - `test_tornado_bar_carries_shock`: a current sidecar → the `revenue_growth (yr 1)` bar has `shock == "-1.0pp / +1.0pp"`.
  - `test_sidecar_without_grid_steps_is_skipped`: drop both `row_steps` and `row_multipliers` → `_renderable` returns `None` for that entry (no crash). The same holds for a tornado `kind` of `"bogus"`.
  - `tornado_table` renders a non-empty `shock` next to the label (for example `<span class="shock">-1.0pp / +1.0pp</span>`) and renders nothing extra for an empty one. Update the `"-20%"` label fixtures in `test_web_svg.py` / `test_web_site_review.py` to the new label style.
  - The rendered detail page's Drivers and Scenarios ledes no longer say "20%" for every input. They say rates move by one percentage point and `sales_to_capital` by 20%.

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_web_views.py tests/unit/test_web_svg.py tests/unit/test_web_site_review.py -q`. Expected: FAIL.

- [ ] **Step 3: Implement.** In `views.py`, read `grid.get("row_steps", grid.get("row_multipliers"))` and `grid.get("row_kind", "multiplicative")` (and the same for columns), and read each tornado entry's `t.get("kind", "multiplicative")`. Name the fallback once, as a module constant with a comment pointing at #217. Update the ledes in `detail.html`.

- [ ] **Step 4: Run** the three test files, then `uv run pytest -q`. Expected: PASS except the pipeline-board tests that Task 4 owns.

- [ ] **Step 5: Commit** `feat(#217): site labels the shock per input and per grid axis`.

### Task 4: Atlas, model labels and prose docs

**Files:**
- Modify: `docs/pipeline/analyze.d2` (`sensitivity.tornado`, `sensitivity.grid`), `docs/pipeline/analyze-sensitivity.d2` (`valued -> tornado_done`, `tornado_done -> grid_done`), `docs/pipeline/analyze-dcf.d2` (`valued -> tornado_done`), `docs/pipeline/models/analyze.view.js` (`TheTornadoIsRun` label), `tests/unit/test_pipeline_diagram.py` (the required-constant sets that list `_TORNADO_LOW`, `_TORNADO_HIGH` and `_GRID_MULTIPLIERS`: add `_TORNADO_SHIFT` and `_GRID_SHIFTS`), and the rendered `docs/pipeline/*.svg` plus `rendered.sha256`
- Modify (prose that would otherwise lie): `docs/superpowers/specs/2026-05-25-investment-bot-design.md` §7.4 tornado line, `docs/leccion/index.html` (the tornado/grid bullets), `docs/plano/part-data.js` and `docs/plano/views.py` (the "±20%" tornado texts), in the language each file is written in

**Interfaces:**
- Consumes: the constant names of Task 1 (`_TORNADO_SHIFT`, `_TORNADO_LOW`, `_TORNADO_HIGH`, `_GRID_SHIFTS`, `_GRID_MULTIPLIERS`) and `shift_axis` (replacing the board's `@symbol …scale_axis`).

- [ ] **Step 1: Write the failing test.** In `tests/unit/test_pipeline_diagram.py`, add `bot.valuator.sensitivity._TORNADO_SHIFT` and `bot.valuator.sensitivity._GRID_SHIFTS` to the two required-constant sets, and add a text test asserting that `analyze.d2`'s tornado label and `analyze-sensitivity.d2`'s `valued -> tornado_done` label contain `1 percentage point` and `sales_to_capital`. Run it; expected FAIL.

- [ ] **Step 2: Rewrite the labels.** Tornado: rate axes ± 1 percentage point (a path axis every year), `sales_to_capital` × 0.8 and × 1.2, one at a time. Swing = |intrinsic value at the high end − at the low end|, widest first. An end with g_terminal ≥ WACC, a tax rate outside [0, 1) or a cost of capital ≤ 0: no value, ranked last. Keep the WACC-path and `tax_rate_path` lines, with "scales" changed to "shifts". Grid: steps −1, −0.5, 0, +0.5, +1 percentage point on a rate axis and 0.8 … 1.2 on `sales_to_capital`. An out-of-domain cell (same three causes) is empty. Cite `@const` for the new constants and `@symbol bot.valuator.sensitivity.shift_axis`. The `analyze.view.js` `TheTornadoIsRun` label must equal the first line of a drawn sub-board edge label (`test_step_labels_are_drawn` in `tests/unit/test_pipeline_models.py`), so keep it identical to the first line of the `valued -> tornado_done` edges. Expand acronyms the way the board tests require.

- [ ] **Step 3: Render.** Run `docs/pipeline/build.sh` with d2 v0.9.0 (install with `curl -fsSL https://d2lang.com/install.sh | sh -s -- --version v0.9.0 --method standalone --prefix "$HOME/.local"` if it is missing). If d2 cannot be installed, push and take the SVGs from the `pipeline-render` artifact of the `pipeline-diagram` workflow (README step 4).

- [ ] **Step 4: Verify.** `python3 docs/pipeline/check.py` exits 0. `python3 docs/leccion/check.py` and `python3 docs/plano/build.py` succeed. Run `docs/pipeline/models/check.sh` if TLC is available locally; otherwise CI's `models` job is the check. `uv run pytest -q`, `uv run ruff check .` and `uv run mypy src` all pass.

- [ ] **Step 5: Commit** `docs(#217): atlas, model labels and docs describe the additive shocks`.

## Grilling

- Rounds: 1. The plan was revised with assumptions and three extra tests, with no new seam, so there was no second round. Griller model: fable.
- Questions: 17. By source: CODE 13, ISSUE 2, DOC 1, and 4 resolved as technical assumptions. Some answers cite more than one source.
- Assumptions added: coupled paths shift by the same pp; the tax guard lives in sensitivity, not `dcf`; unknown kinds raise and the sidecar is skipped; signed zero `+0.0pp`; per-task commits with a red downstream suite; scope of the prose docs.
- Spec ambiguities: none. Issues opened: none.
