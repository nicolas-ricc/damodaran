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
  - `terminal_wacc(assumptions: Assumptions) -> float`, a public helper: `wacc_path[-1]` when the path is non-empty (truthiness test, so an empty path falls through to `_wacc` and `dcf`'s length check raises the `ValueError`), else `_wacc(assumptions)`. Task 3 uses it.

Damodaran inputs, copied verbatim from the issue (millions): base revenue 20,608; growth `(4.00, 0.42, 0.42, 0.42, 0.42, 0.3458, 0.2716, 0.1974, 0.1232, 0.0490)`; margins `(0.05, 0.14, 0.185, 0.23, 0.275, 0.275, 0.275, 0.275, 0.275, 0.275)`; `wacc_path = (0.0974,)*5 + (0.0962, 0.0950, 0.0937, 0.0925, 0.0913)`; `tax_rate_path = (0.0,)*5 + (0.05, 0.10, 0.15, 0.20, 0.25)`; `tax_rate = 0.25`; `sales_to_capital = 3.0` (the existing field; years 1–10 reinvest `ΔRevenue / sales_to_capital`); `terminal_growth = 0.049`; `terminal_roic = 0.15`; `probability_of_bankruptcy = 0.10`; `distress_proceeds_pct = 0.5`; `cost_of_equity = 0.0974`, `equity_weight = 1.0`, `debt_weight = 0.0`, `pretax_cost_of_debt = 0.05`. Financials: `revenue = 20_608`, `net_debt = -212_389`, `fixed_commitments = 472_336`, `extra_cash = 0.0`, `adjustments = 3_929 - 472`, `shares_diluted = 3_298.14`. Expose them as module-level helpers `damodaran_financials() -> Financials` and `damodaran_assumptions() -> Assumptions` in `tests/unit/test_valuator_dcf.py`; Task 3 imports them (the repo already imports helpers across test modules, e.g. `tests/unit/test_valuator_sensitivity.py:32`).

Bridge operand order is pinned, left to right: `enterprise_value - financials.net_debt - financials.fixed_commitments + financials.extra_cash + financials.adjustments`. Subtracting and adding `0.0` is exact in IEEE 754, so this stays bit-identical to today's `enterprise_value - net_debt + adjustments`.

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

- [ ] **Step 1: Failing tests** (Damodaran inputs via `from tests.unit.test_valuator_dcf import damodaran_assumptions, damodaran_financials`; add `test_grid_2d_with_wacc_path_has_defined_centre`, which runs `grid_2d` over growth × margin on the Damodaran inputs and checks that the centre equals `dcf(...).intrinsic_value`): `test_active_axes_all_seven_without_wacc_path` (equals `tuple(SensitivityAxis)`), `test_active_axes_drops_cost_of_debt_with_wacc_path` (six, enum order), `test_scale_cost_of_equity_scales_wacc_path` (×1.2 on every element, `pytest.approx`), `test_scale_tax_rate_scales_tax_rate_path`, `test_scale_without_paths_leaves_them_none`, `test_tornado_over_damodaran_has_six_defined_entries` (`len == 6`, no `impact is None`), `test_safe_intrinsic_none_when_growth_reaches_terminal_wacc_path`. The Damodaran inputs are built by a local helper mirroring Task 2's.
- [ ] **Step 2:** Run them. Expected: FAIL (ImportError on `active_axes`).
- [ ] **Step 3:** Implement.
- [ ] **Step 4:** `uv run pytest -q && uv run ruff check . && uv run mypy src && python3 docs/pipeline/check.py && python3 docs/leccion/check.py`. Expected: all green, golden unchanged.
- [ ] **Step 5:** Commit `feat(#193): sensitivity follows the wacc and tax paths`.

## Assumptions

Technical decisions taken without an explicit source in the issue. Each one lists the alternative that was rejected.

- **Validation stops at the four `ValueError` cases the issue lists.** A `wacc_path` element ≤ −1, a `tax_rate_path` element outside [0, 1], negative `fixed_commitments`, and `terminal_roic < terminal_growth` are not validated. Rejected alternative: extra guards. They would be new behaviour that nobody asked for, and later story-file validation (#194) owns the input ranges.
- **`terminal_wacc` uses a truthiness test**, so an empty path reaches `dcf`'s length `ValueError` instead of raising `IndexError`. Rejected alternative: `is not None`.
- **The Damodaran fixture lives in `test_valuator_dcf.py` and is imported by the sensitivity tests.** Rejected alternative: a duplicated helper, or a new `conftest.py`.
- **Float identity of the defaults is proven by the golden JSON.** `json` writes floats with `repr`, which round-trips exactly, so the projection's `==` compares every `DCFResult` float exactly. The existing DCF tests add a tolerance-based check on top. Rejected alternative: an extra `==` snapshot test of `dcf()`.

## Grilling

One round, 17 questions (griller model: fable). The plan changed only locally: it now carries the Damodaran inputs, the bridge operand order, a `terminal_wacc` edge case, a grid test and the Assumptions section. No step was added or removed, so there was no second round.

| # | Answer (source) |
|---|---|
| 1 | ISSUE: "With the defaults this is floating-point identical to today's `enterprise_value - net_debt + adjustments`". The operand order is now pinned in Task 2. The golden JSON compares floats exactly (see Assumptions). |
| 2 | CODE: `src/bot/reporting/analysis_json.py:28` uses `dataclasses.asdict(analysis)`, so the new fields appear as extra keys. ISSUE: "keys that only exist in the new document are allowed". The Markdown renderer has no `fields`/`asdict` loop (grep of `src/bot/reporting/analysis_report.py`). ISSUE: the golden must "pass unchanged at the end of the task", so a break means fixing the code, never regenerating the golden. |
| 3 | ISSUE: "Ground-truth numbers for the tests (independently computed...)" gives the full input list, now copied into Task 2. Reinvestment uses the existing `sales_to_capital` (CODE: `src/bot/valuator/dcf.py:Assumptions.sales_to_capital`, `reinvestment = (revenue - prev_revenue) / sales_to_capital`). |
| 4 | CODE: `tests/unit/test_valuator_dcf.py:29-30` builds its inputs with keywords. `tests/unit/test_valuator_sensitivity.py:92` asserts `len(entries) == len(SensitivityAxis)` on a fixture without a path, so it still gets 7. ISSUE: "`Financials` and `Assumptions` keep their positional order". |
| 5 | CODE: `dcf.py`, `distress_value_per_share: float = 0.0`. It is never `None`. The Damodaran test covers p = 0.10 in proceeds mode. |
| 6 | CODE: `src/bot/valuator/assumptions.py:623-642` (`_OVERRIDE_KEYS`, and `_OVERRIDE_PATH_KEYS` for lists). CODE: `src/bot/valuator/analysis.py:569-579` (`override_path: Path | None = None`, `*, age_years`). |
| 7 | ISSUE: "every axis in enum order, except `PRETAX_COST_OF_DEBT` when `wacc_path` is set". The six that remain all move the value: `cost_of_equity` through the path, the others through the projection. Nothing in the report hard-codes the row count. |
| 8 | ISSUE: "`scale_axis` with `COST_OF_EQUITY` also scales `wacc_path` element-wise". ISSUE (#192 plan comment, nicolas-ricc): "for a story the cost of equity *is* the all-in WACC". The label stays `cost_of_equity` (no new member, by issue). |
| 9 | CODE: `src/bot/valuator/sensitivity.py:156-166` pre-checks `_wacc` and does not catch exceptions, and the grid (`:274`) goes through `_safe_intrinsic`. A grid test was added to Task 3. |
| 10 | ISSUE lists exactly four `ValueError` cases. The rest is in Assumptions. |
| 11 | ISSUE: "the terminal year and the WACC tax shield keep using the scalar `tax_rate`". In path mode the shield is unused, because the path replaces `_wacc`. |
| 12 | CODE: `src/bot/valuator/analysis.py:632` (the only `today()`, and only on the `ipo_date` branch) and `src/bot/reporting/analysis_report.py:217` (`generated_on or date.today()`, fixed by the test). |
| 13 | CODE: `tests/__init__.py` and `tests/unit/__init__.py` exist, and `pyproject.toml:75` sets `testpaths`. `regenerate` has no `test_` prefix, so pytest does not collect it. Running it on the original tree is enforced by its own commit preceding every `src/` change. |
| 14 | CODE: `src/bot/valuator/story_types.py:39-57` (thresholds) and `src/bot/reference/sectors.py:42` (`CYCLICAL_INDUSTRIES`). The seed shapes come from `tests/unit/test_valuator_analysis.py` (`_seed`, `_seed_volatile_financials`). Each case asserts its story type. |
| 15 | DOC: CONTEXT.md, "`check.py` fails when it cites a symbol that no longer exists". No symbol is removed, and a grep finds no reference to `SensitivityAxis`/`DCFResult` in either `check.py`. |
| 16 | ISSUE: "`distress_value_per_share` is ignored in that mode"; "`enterprise_value_after_failure` ... (set only in the proceeds mode)"; "assert `terminal_value_share` is `pv_terminal / enterprise_value` (the going-concern EV)". |
| 17 | CODE: `tests/unit/test_valuator_sensitivity.py:32` imports a helper from another test module. `terminal_wacc` is public because `sensitivity.py` would otherwise import a second private name (Assumptions). |

Sources: ISSUE 9, CODE 12, DOC 1, NO SOURCE 3 (technical assumptions). Spec ambiguities: 0. Follow-up issues: none.

Result: **ok**.
