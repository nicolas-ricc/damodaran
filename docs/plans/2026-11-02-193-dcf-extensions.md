# DCF extensions behind defaults + isolation golden — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the pure two-stage DCF express Damodaran's hypergrowth sheet (WACC path, tax path, terminal ROIC, fixed commitments, extra cash, failure proceeds) behind defaults that reproduce today's arithmetic, after pinning today's end-to-end outputs with a golden.

**Architecture:** Task 1 freezes the Markdown report and JSON sidecar of six `analyze` runs (one per story type plus an override case) on the pre-change commit. Task 2 adds defaulted fields to `Financials`, `Assumptions` and `DCFResult` in `src/bot/valuator/dcf.py`. The pre-existing code path runs unchanged when every new field holds its default. Task 3 makes `src/bot/valuator/sensitivity.py` path-aware without adding a `SensitivityAxis` member.

**Tech Stack:** Python 3, frozen dataclasses, pytest, DuckDB in-memory, ruff, mypy strict.

**Spec:** GitHub issue #193 (sub-issue of #192; the parent's plan comment carries the calibration table these numbers come from).

## Global Constraints

- `Financials` and `Assumptions` keep their positional field order. Every new field is appended with a default.
- Defaults reproduce today's maths: with no new field set, `dcf()` returns a float-identical `DCFResult` (only the two new `DCFResult` fields are added, both `None`).
- `src/bot/valuator/` modules are pure: no I/O, no global state, frozen dataclasses. Module constants carry a `#:` comment.
- No new `SensitivityAxis` member.
- Every existing test in `tests/unit/test_valuator_dcf.py` and `tests/unit/test_valuator_sensitivity.py` passes **unmodified**.
- The isolation golden is committed before any `src/` change and passes unchanged at the end.
- Gates: `uv run pytest -q`, `uv run ruff check . && uv run mypy src`, `python3 docs/pipeline/check.py`, `python3 docs/leccion/check.py`.
- Commits: Conventional Commits with `#193`.

## Review Focus

1. **A WACC path with its terminal element at or below `terminal_growth`.** Expected: `ValueError` from `dcf`, and `None` from `_safe_intrinsic` (no crash in the tornado or the grid). Test: `test_wacc_path_terminal_at_or_below_growth_raises` (Task 2) and `test_safe_intrinsic_none_when_growth_reaches_terminal_wacc_path` (Task 3).
2. **A path with an intermediate year that diverges but a terminal element that converges** (for example a year-3 WACC below g). This is valid, because only the perpetuity needs `g < wacc`. Covered by the Damodaran test, whose year-1 growth (400%) is far above every WACC.
3. **`distress_proceeds_pct` set while `probability_of_bankruptcy == 0`.** Expected: equity equals the going-concern equity and `enterprise_value_after_failure == enterprise_value`. Test: `test_proceeds_mode_with_zero_probability_is_going_concern` (Task 2).
4. **`wacc_path` set and the scalar WACC components inconsistent with it.** Expected: the path wins everywhere (discounting, terminal value, `DCFResult.wacc`). The scalar `_wacc` is not consulted for the convergence check. Covered by the Damodaran test (`debt_weight=0`, so no inconsistency is hidden) and by `test_wacc_path_ignores_scalar_components` (Task 2).
5. **Sidecar or report gaining the new `DCFResult` fields.** Expected: the golden still matches, because the projection allows extra JSON keys but the Markdown must stay byte-identical. Pinned by Task 1's golden.

---

### Task 1: Isolation golden (captured on the pre-change commit)

**Files:**
- Create: `tests/unit/test_valuator_isolation_golden.py`
- Create: `tests/fixtures/valuator/isolation/<case>.md` and `<case>.json` for each of the six cases, plus `<case>.yaml` override files where needed.

**Interfaces:**
- Consumes: `bot.storage.db.apply_schema`, `bot.valuator.analysis.analyze(ticker, conn, override_path, *, age_years=...)`, `bot.reporting.analysis_report.render_analysis(analysis, generated_on=date(2026, 1, 1))`, `bot.reporting.analysis_json.render_analysis_json(analysis, generated_on=date(2026, 1, 1))`.
- Produces: module-level `CASES: tuple[str, ...]`, `_run(case: str) -> Analysis`, `_project(golden: object, actual: object) -> None` (asserts), `FIXTURES: Path`.

Cases (ticker = case slug, upper-cased):
- `mature_stable`: the AAPL-shaped seed of `test_valuator_analysis.py::_seed`.
- `high_growth`: revenue CAGR ≈ 20%, `age_years=10` passed explicitly, never `ipo_date`.
- `cyclical`: an industry in `CYCLICAL_INDUSTRIES` with volatile net income and at least 4 years of margins.
- `distressed`: interest coverage below 1, with override YAML `probability_of_bankruptcy: 0.2`, `distress_value_per_share: 3.0`.
- `mature_decline`: shrinking revenue.
- `override`: a mature-stable company with override YAML carrying list paths for `revenue_growth` and `operating_margin`, plus `equity_weight`, `tax_rate` and `notes`.

Each case asserts its expected `analysis.story_type`, so a fixture that drifts into another story type fails loudly.

- [ ] **Step 1:** Write the module with seeds, `_run`, and two parametrised tests: `test_markdown_matches_golden(case)`, which compares `render_analysis(...)` to `<case>.md` byte for byte, and `test_json_projects_onto_golden(case)`, which applies `_project` recursively. Every golden key must exist with an equal value, lists must have equal length and compare element-wise, and extra keys are allowed. The module docstring gives the regeneration command, `uv run python -c "from tests.unit.test_valuator_isolation_golden import regenerate; regenerate()"`, plus the capture commit. Add `regenerate()`, which writes the fixtures.
- [ ] **Step 2:** Run `regenerate()` on the unmodified tree. Then run `uv run pytest tests/unit/test_valuator_isolation_golden.py -q`. Expected: PASS.
- [ ] **Step 3:** Commit `test(#193): isolation golden captured before the DCF changes` as its own commit.

### Task 2: DCF extensions

**Files:**
- Modify: `src/bot/valuator/dcf.py`
- Test: `tests/unit/test_valuator_dcf.py` (append only)

**Interfaces:**
- Produces (exact):
  - `Financials.fixed_commitments: float = 0.0`, `Financials.extra_cash: float = 0.0`
  - `Assumptions.wacc_path: tuple[float, ...] | None = None`, `Assumptions.tax_rate_path: tuple[float, ...] | None = None`, `Assumptions.terminal_roic: float | None = None`, `Assumptions.distress_proceeds_pct: float | None = None`
  - `DCFResult.enterprise_value_after_failure: float | None = None`, `DCFResult.wacc_path: tuple[float, ...] | None = None`
  - `terminal_wacc(assumptions: Assumptions) -> float`, a public helper: `wacc_path[-1]` when set, else `_wacc(assumptions)`. Task 3 uses it.

Semantics (from the issue):
- `wacc_path` gives a cumulative factor `1/Π_{i≤t}(1+wacc_path[i])` per year, reported as `discount_factor`. Terminal value = `FCFF_{N+1}/(wacc_path[-1]-g)`, and `pv_terminal = TV × discount_factor_N`. `DCFResult.wacc = wacc_path[-1]`. The convergence check uses the terminal WACC.
- `tax_rate_path[t]` is used for year-`t` NOPAT. The terminal year and the WACC tax shield use the scalar `tax_rate`.
- With `terminal_roic`, terminal reinvestment = `terminal_nopat × g / terminal_roic`.
- With `distress_proceeds_pct`: `ev_after = EV(1−p) + EV·pct·p`, `equity = ev_after − net_debt − fixed_commitments + extra_cash + adjustments`, `intrinsic = equity / shares`. `distress_value_per_share` is ignored. With `None`, the per-share blend stays as today.
- Going-concern bridge: `EV − net_debt − fixed_commitments + extra_cash + adjustments`.
- `terminal_value_share = pv_terminal / enterprise_value` (going-concern EV).
- `ValueError` cases: `len(wacc_path) != horizon`, `len(tax_rate_path) != horizon`, `terminal_roic <= 0`, `distress_proceeds_pct` outside `[0, 1]`.

Implementation rule: when `wacc_path is None`, keep `discount_factor = 1.0 / (1.0 + wacc) ** year` and `pv_terminal = terminal_value / (1.0 + wacc) ** horizon` literally. Use the cumulative product only when the path is set. This is what keeps the defaults float-identical.

- [ ] **Step 1: Failing tests** (append to `tests/unit/test_valuator_dcf.py`):
  - `test_damodaran_base_case`: inputs from the issue. Assert year-10 revenue `1_011_491 ± 1`, `sum(p.present_value)` `422_725 rel 1e-3`, `pv_terminal` (`terminal_value × projections[-1].discount_factor`) `1_398_392 rel 1e-3`, `enterprise_value_after_failure` `1_730_061 rel 1e-3`, `equity_value` `1_473_576 rel 1e-3`, `intrinsic_value` `446.79 rel 1e-3`, `terminal_value_share == pv_terminal / enterprise_value`, `wacc == 0.0913`, `wacc_path` echoed.
  - `test_flat_wacc_path_matches_scalar` (`(wacc,)*N`, all fields `abs 1e-9` relative to the value).
  - `test_flat_tax_rate_path_matches_scalar`.
  - `test_full_proceeds_gives_going_concern_equity`, parametrised over p ∈ {0, 0.3, 1}.
  - `test_proceeds_mode_with_zero_probability_is_going_concern`.
  - `test_fixed_commitments_lower_equity_one_for_one`, `test_extra_cash_raises_equity_one_for_one`.
  - `test_wacc_path_ignores_scalar_components`.
  - `test_wacc_path_terminal_at_or_below_growth_raises`.
  - `test_new_fields_invalid_raise`, parametrised over the four `ValueError`s (wacc_path length, tax_rate_path length, terminal_roic ∈ {0, −0.1}, proceeds ∈ {−0.01, 1.01}).
  - `test_defaults_leave_new_result_fields_none`.
- [ ] **Step 2:** `uv run pytest tests/unit/test_valuator_dcf.py -q`. Expected: the new tests FAIL (TypeError on unknown fields) and the old tests pass.
- [ ] **Step 3:** Implement in `dcf.py`. Update the module docstring and the field docstrings.
- [ ] **Step 4:** `uv run pytest tests/unit/test_valuator_dcf.py tests/unit/test_valuator_isolation_golden.py -q`. Expected: PASS.
- [ ] **Step 5:** Commit `feat(#193): DCF wacc/tax paths, terminal ROIC, commitments, failure proceeds`.

### Task 3: Sensitivity over paths

**Files:**
- Modify: `src/bot/valuator/sensitivity.py`
- Test: `tests/unit/test_valuator_sensitivity.py` (append only)

**Interfaces:**
- Consumes: `terminal_wacc` from Task 2, and the new `Assumptions` fields.
- Produces: `active_axes(assumptions: Assumptions) -> tuple[SensitivityAxis, ...]`.

Semantics:
- `scale_axis(..., COST_OF_EQUITY, m)` scales `cost_of_equity` and also `wacc_path` element-wise when it is set. `scale_axis(..., TAX_RATE, m)` scales `tax_rate` and also `tax_rate_path` when it is set. Otherwise the behaviour stays as today.
- `active_axes`: every axis in enum order, except `PRETAX_COST_OF_DEBT` when `wacc_path` is set.
- `tornado` iterates `active_axes(base_assumptions)`.
- `_safe_intrinsic` returns `None` when `terminal_growth >= terminal_wacc(assumptions)`.

- [ ] **Step 1: Failing tests:** `test_active_axes_all_seven_without_wacc_path` (equals `tuple(SensitivityAxis)`), `test_active_axes_drops_cost_of_debt_with_wacc_path` (six, enum order), `test_scale_cost_of_equity_scales_wacc_path` (×1.2 on every element, `pytest.approx`), `test_scale_tax_rate_scales_tax_rate_path`, `test_scale_without_paths_leaves_them_none`, `test_tornado_over_damodaran_has_six_defined_entries` (`len == 6`, no `impact is None`), `test_safe_intrinsic_none_when_growth_reaches_terminal_wacc_path`. The Damodaran inputs are built by a local helper mirroring Task 2's.
- [ ] **Step 2:** Run them. Expected: FAIL (ImportError on `active_axes`).
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** `uv run pytest -q && uv run ruff check . && uv run mypy src && python3 docs/pipeline/check.py && python3 docs/leccion/check.py`. Expected: all green, golden unchanged.
- [ ] **Step 5:** Commit `feat(#193): sensitivity follows the wacc and tax paths`.
