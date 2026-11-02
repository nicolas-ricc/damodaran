# Hypergrowth resolver (#196) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn a validated story file into Damodaran's ten-year growth, margin, WACC and tax paths, wire them into `resolve_assumptions` and `analyze`, and reproduce his Anthropic base case ($447.34/share) within 1%.

**Architecture:** Pure path functions and `apply_story` live in `src/bot/valuator/hypergrowth.py`. The sourced `Assumptions` bundle in `assumptions.py` gains optional story-only fields (all `None` by default, so every other story type is unchanged) and passes the DCF extensions of #193 through `to_dcf_assumptions`. `resolve_assumptions` runs the generic resolvers as today, then overlays the story when the effective story type is `hypergrowth`. `analyze` feeds the story's fixed commitments and extra cash into `Financials`.

**Tech Stack:** Python 3.12, frozen dataclasses, DuckDB, pytest, mypy `--strict`, ruff.

**Spec:** GitHub issue #196 (child of story #192). The design section of #196 is decided and is implemented as written. The calibration figures come from the plan comment on #192.

## Global Constraints

- Modules under `src/bot/valuator/` are pure: no I/O, no global state, frozen dataclasses. Module constants carry a `#:` comment explaining the value.
- `HORIZON = 10`, `_STAGE_END = 5` in `hypergrowth.py`.
- Bisection on `[-0.99, 10.0]`, 200 iterations.
- No existing `_resolve_*` function changes. `terminal_growth` and `tax_rate` stay whatever the generic resolvers produced.
- Isolation: `tests/unit/test_valuator_isolation_golden.py` passes unchanged; every pre-existing assumptions and analysis test passes unmodified, except `test_hypergrowth_with_story_file` (pins the intermediate state), which this task replaces.
- Story file money is in the raw units of `financials_annual` (not millions).
- Commits: Conventional Commits with `#196`. Gates: `uv run pytest -q`, `uv run ruff check . && uv run mypy src`, `python3 docs/pipeline/check.py`, `python3 docs/leccion/check.py`.

## Decisions taken here (not spelled out by the issue)

1. **Import cycle.** `assumptions.py` already imports `hypergrowth.py`, so `hypergrowth.py` cannot import `assumptions.py` at module level. `apply_story` annotates with `Assumptions` under `TYPE_CHECKING` and imports `AssumptionSource`/`Sourced` inside the function body. `assumptions.py` imports `StoryInputs` and `apply_story` at module level as today.
2. **Fade interpolation.** Years 6–10 of the WACC and tax paths are `start + (end - start) * k / 5` for k = 1..4, and year 10 is `end` itself. That keeps a flat path exactly flat (`end == start` adds `0.0`) and makes the last element exactly the target, which the "tax path ends exactly at the marginal rate" criterion asks for. The growth fade uses the issue's formula `c - k * (c - g) / 5`; its tests use a 1e-6 tolerance.
3. **`terminal_roic` absent from the story** leaves `Assumptions.terminal_roic = None`: the DCF keeps the sales-to-capital terminal reinvestment.
4. **`distress_proceeds_pct`** is always set by `apply_story` (from `failure_proceeds_pct_of_value`, default 0.0), so a story always uses the share-of-EV failure blend. `distress_value_per_share` is left untouched (the DCF ignores it in that mode).
5. **A story overrides generic manual keys** (`revenue_growth`, `operating_margin`, `sales_to_capital`, `cost_of_equity`, weights, `probability_of_bankruptcy`) in the same file: the issue says `apply_story` replaces them. `terminal_growth`, `tax_rate` and `pretax_cost_of_debt` from the file still apply.
6. **`analyze`** reads `bundle.fixed_commitments` and `bundle.extra_cash` as `0.0` when the field is `None` (it is `None` for every non-story company). The literal `bundle.fixed_commitments.value or 0.0` from the issue would raise on `None`.

## Assumptions

Technical decisions recorded during plan grilling (no written source; any option satisfies the issue):

- **A1.** `solve_stage_growth` refuses `terminal_growth <= -1` with a `ValueError`. Bisection needs revenue to increase with `c`, i.e. every growth factor positive. `year1_growth > -1` and `margin_converge_year` in 1..10 are already validated by #194 (`hypergrowth._RULES`), but `terminal_growth` comes from the generic resolvers, where a manual value is any finite number. Rejected alternative: clamping it silently.
- **A2.** The sector WACC fallback for `wacc_terminal` is used as published, with no currency or year check. The issue names it as the fallback, and every other sector-sourced value is used the same way. Rejected alternative: refusing a cross-region sector row.
- **A3.** Stage 3 commits the evals while they are red (the pipeline asks for it). "Every pre-existing test passes unmodified" is judged on the final branch, not on the evals commit.
- **Decisions 1–6 above** also count as technical assumptions for the PR description.

## Review Focus

1. **AAPL-shaped company with a story file** (the existing `test_story_file_without_hypergrowth_signals_is_yellow`, base revenue 430B, target 1.01T): the solve lands on a negative stage rate and the company still values. Pinned by that test, unchanged.
2. **Non-positive base revenue** (`latest_revenue` ≤ 0): `solve_stage_growth` raises `ValueError` (target unreachable), never a `ZeroDivisionError`. Test in Task 1.
3. **Latest financials row has a NULL revenue**: `latest_revenue` is `None` and `resolve_assumptions` raises `ValueError` naming the ticker, so the batch goes on. Test in Task 3.
4. **Bulk and per-ticker loaders disagree on `latest_revenue`**: both must take the latest non-restated row, ignoring restated ones. Test in Task 3 (restated row with a larger fiscal year).
5. **A non-hypergrowth company's bundle** keeps every new field `None` and its `to_dcf_assumptions()` equals today's (no `wacc_path` etc.). Test in Task 2.

---

### Task 1: Ten-year path functions

**Files:**
- Modify: `src/bot/valuator/hypergrowth.py`
- Test: `tests/unit/test_valuator_hypergrowth.py`

**Interfaces:**
- Consumes: `StoryInputs` (existing).
- Produces, all pure, each returning a `tuple[float, ...]` of `HORIZON` values except the solve:
  - `HORIZON: int = 10`, `_STAGE_END: int = 5`
  - `solve_stage_growth(base_revenue: float, story: StoryInputs, terminal_growth: float) -> float`
  - `growth_path(base_revenue: float, story: StoryInputs, terminal_growth: float) -> tuple[float, ...]`
  - `margin_path(story: StoryInputs) -> tuple[float, ...]`
  - `wacc_path(story: StoryInputs, wacc_terminal: float) -> tuple[float, ...]`
  - `tax_path(story: StoryInputs, marginal_tax_rate: float) -> tuple[float, ...]`

- [ ] **Step 1: The stage-3 tests already exist and fail** (`test_solve_stage_growth_*`, `test_growth_path_*`, `test_margin_path_*`, `test_wacc_path_*`, `test_tax_path_*`). They assert:
  - calibration story (millions, base 20,608, g 0.049): `solve_stage_growth == approx(0.42, abs=1e-6)`; `growth_path` matches `(4.00, 0.42, 0.42, 0.42, 0.42, 0.3458, 0.2716, 0.1974, 0.1232, 0.0490)` within 1e-6; revenue compounded over the path ends at 1,011,491 within 1.
  - `solve_stage_growth` raises `ValueError` matching `unreachable` for a target too high (`target_revenue_y10=1e30`), too low (`target_revenue_y10=1e-9`), and for `base_revenue` 0 and -1.
  - `solve_stage_growth` raises `ValueError` matching `terminal_growth` when `terminal_growth <= -1` (assumption A1).
  - `margin_path` equals `(0.05, 0.14, 0.185, 0.23, 0.275, 0.275, 0.275, 0.275, 0.275, 0.275)` within 1e-12; with `margin_converge_year=1`, `path[0] == 0.05` and `path[1:] == (0.275,) * 9` exactly.
  - `wacc_path(story, 0.0913)` matches `(0.0974,)*5 + (0.0962, 0.0950, 0.0937, 0.0925, 0.0913)` within 1e-4 and `path[-1] == 0.0913`; `wacc_path(story, story.wacc_start) == (story.wacc_start,) * 10` exactly.
  - `tax_path(story, 0.25) == approx((0.0,)*5 + (0.05, 0.10, 0.15, 0.20, 0.25))` and `path[-1] == 0.25` exactly; also exact last element with `effective_tax_rate=0.1, marginal=0.3`.

- [ ] **Step 2: Run them, confirm they fail**
  Run: `uv run pytest tests/unit/test_valuator_hypergrowth.py -q`
  Expected: FAIL (ImportError on the new names).

- [ ] **Step 3: Implement the five functions** in `hypergrowth.py`, after `StoryInputs`. Revenue after year 10 is `base × (1 + year1_growth) × (1 + c)^4 × ∏_{k=1..5}(1 + c − k(c − g)/5)`; it is increasing in `c`, so bisect on `[-0.99, 10.0]` for 200 iterations after refusing `terminal_growth <= -1` (A1) and checking that `target_revenue_y10` lies between the values at both ends. Otherwise raise `ValueError(f"target_revenue_y10 {target} unreachable from base revenue {base}: ...")` (the message must contain `unreachable`). `growth_path` builds from the solved `c` with the same rate formula the solve uses. `margin_path`: `target = target_margin - regulatory_drag`; year 1 `year1_margin`; year t ≤ `margin_converge_year` (t ≥ 2) `year1_margin + (target - year1_margin) * t / margin_converge_year`; `target` after. WACC/tax fades follow decision 2. Every module constant carries a `#:` comment.

- [ ] **Step 4: Run the tests**
  Run: `uv run pytest tests/unit/test_valuator_hypergrowth.py -q && uv run mypy src && uv run ruff check .`
  Expected: PASS.

- [ ] **Step 5: Commit** `feat(#196): ten-year growth, margin, WACC and tax paths from the story`

### Task 2: Sourced bundle fields, `apply_story`, calibration

**Files:**
- Modify: `src/bot/valuator/assumptions.py` (`Assumptions` dataclass and `to_dcf_assumptions`)
- Modify: `src/bot/valuator/hypergrowth.py` (`apply_story`)
- Test: `tests/unit/test_valuator_hypergrowth.py`, `tests/unit/test_hypergrowth_calibration.py`, `tests/unit/test_valuator_assumptions.py` (new tests only)

**Interfaces:**
- Consumes: Task 1 paths.
- Produces:
  - `Assumptions` gains, at the end and in this order: `wacc_path: Sourced[tuple[float, ...]] | None = None`, `tax_rate_path: Sourced[tuple[float, ...]] | None = None`, `terminal_roic: Sourced[float] | None = None`, `distress_proceeds_pct: Sourced[float] | None = None`, `fixed_commitments: Sourced[float] | None = None`, `extra_cash: Sourced[float] | None = None`, `governance_discount: Sourced[float] | None = None`, `story: StoryInputs | None = None`. Docstring entries for each.
  - `to_dcf_assumptions()` passes `wacc_path`, `tax_rate_path`, `terminal_roic`, `distress_proceeds_pct` (their `.value`) when the field is not `None`, else `None` as today.
  - `apply_story(bundle: Assumptions, story: StoryInputs, *, base_revenue: float, sector_wacc: float | None) -> Assumptions` in `hypergrowth.py`.

- [ ] **Step 1: The stage-3 tests already exist and fail:**
  - `test_apply_story_sets_story_sourced_values`: over a generic bundle with `terminal_growth=0.049` and `tax_rate=0.25` (any source), every field `apply_story` sets has `source is AssumptionSource.STORY`; `cost_of_equity.value == wacc_start`, `equity_weight.value == 1.0`, `debt_weight.value == 0.0`, `probability_of_bankruptcy.value == failure_probability`, `distress_proceeds_pct.value == failure_proceeds_pct_of_value`, `fixed_commitments.value == fixed_commitments_pv`, `extra_cash`, `governance_discount`, `terminal_roic` from the story, `story is story`; `terminal_growth`, `tax_rate`, `pretax_cost_of_debt` are the input bundle's objects.
  - `test_apply_story_wacc_terminal_falls_back_to_sector`: `story.wacc_terminal=None`, `sector_wacc=0.09` → `wacc_path.value[-1] == 0.09`.
  - `test_apply_story_raises_without_wacc_terminal`: both `None` → `ValueError` matching `wacc_terminal unresolved`.
  - `test_apply_story_raises_on_unresolved_terminal_growth` / `..._tax_rate`: `Sourced(None, UNRESOLVED)` → `ValueError` naming the field.
  - `test_apply_story_without_terminal_roic_leaves_it_none`.
  - `test_generic_bundle_has_no_story_fields` (Review Focus 5): a resolved non-story bundle has every new field `None` and `to_dcf_assumptions()` has `wacc_path is None`, `tax_rate_path is None`, `terminal_roic is None`, `distress_proceeds_pct is None`.
  - `tests/unit/test_hypergrowth_calibration.py`: the issue's fixture constants (millions), `apply_story` over a bundle with `terminal_growth=0.049`, `tax_rate=0.25`, then `dcf(Financials(revenue=20_608, net_debt=-112_389, shares_diluted=3_298.14, adjustments=3_929 - 472, fixed_commitments=472_336, extra_cash=100_000), bundle.to_dcf_assumptions())`. Asserts: paths per Task 1 tolerances; year-10 revenue 1,011,491 within 1; `terminal_value × projections[-1].discount_factor` within 0.1% of 1,398,391; `equity_value` within 1% of 1,475,406; `intrinsic_value` within 1% of 447.34; a comment explaining the computed 1,473,576 / 446.79 and the 0.12% gap (Damodaran's sheet reinvests one year ahead of revenue; this model deliberately reinvests in the same year).

- [ ] **Step 2: Run them, confirm they fail** — `uv run pytest tests/unit/test_hypergrowth_calibration.py tests/unit/test_valuator_hypergrowth.py tests/unit/test_valuator_assumptions.py -q`; expected FAIL on the new tests only.

- [ ] **Step 3: Implement** the fields, `to_dcf_assumptions` passthrough and `apply_story` (decisions 1, 3, 4). `apply_story` returns `dataclasses.replace(bundle, ...)` with `revenue_growth=growth_path(base_revenue, story, g)`, `operating_margin=margin_path(story)`, `sales_to_capital`, `cost_of_equity=wacc_start`, weights 1.0/0.0, `probability_of_bankruptcy=failure_probability`, and the new fields, all `AssumptionSource.STORY`. Error messages: `"apply_story: wacc_terminal unresolved: no sector WACC; set story.wacc_terminal"`, `"apply_story: terminal_growth unresolved"`, `"apply_story: tax_rate unresolved"`.

- [ ] **Step 4: Run** the three test files, then the isolation golden: `uv run pytest tests/unit/test_valuator_isolation_golden.py -q`. Expected: PASS.

- [ ] **Step 5: Commit** `feat(#196): apply_story overlays the story on the sourced bundle; calibration on Damodaran's sheet`

### Task 3: Wire into `resolve_assumptions` and `analyze`

**Files:**
- Modify: `src/bot/valuator/assumptions.py` (`AssumptionInputs`, both loaders, `resolve_assumptions`)
- Modify: `src/bot/valuator/analysis.py` (`analyze`)
- Test: `tests/unit/test_valuator_analysis.py` (replace `test_hypergrowth_with_story_file`, add e2e tests), `tests/unit/test_valuator_assumptions.py` (new tests only)

**Interfaces:**
- Consumes: `apply_story`, the new `Assumptions` fields.
- Produces: `AssumptionInputs.latest_revenue: float | None = None` (last field); `Analysis.financials.fixed_commitments` / `extra_cash` set from the bundle.

- [ ] **Step 1: The stage-3 tests already exist and fail:**
  - `test_latest_revenue_loaded_per_ticker_and_bulk` (Review Focus 4): seed two non-restated years and a restated row with a later fiscal year; `load_assumption_inputs(...).latest_revenue` and `bulk_load_assumption_inputs(...)[t].latest_revenue` both equal the latest non-restated revenue.
  - `test_resolve_hypergrowth_story_raises_without_latest_revenue` (Review Focus 3): latest row revenue NULL → `ValueError` matching the ticker and `revenue`.
  - `test_hypergrowth_with_story_file` (replaced) and `test_hypergrowth_story_values_anthropic_end_to_end`: a seed helper `_seed_anthropic_sheet` in raw dollars (revenue 1,020e6 then 20,608e6, EBIT −46,982e6 on the last year, interest expense so coverage < 1, total_debt 0, cash 112,389e6, shares 3,298.14e6; sector row `wacc` 0.0913, `op_margin` 0.28, `roic` 0.12, `tax_rate` 0.25), story YAML in raw units (the #194 `_STORY`) plus `terminal_growth: 0.049` and `tax_rate: 0.25`. Asserts `intrinsic_value == approx(447.34, rel=0.01)` (expected 445.74: the `adjustments` line is not an override key), `story_type == "hypergrowth"`, `revenue_growth.source` and `operating_margin.source` are `story`, `dcf_result.wacc_path is not None`, `financials.fixed_commitments == 472_336e6`, `financials.extra_cash == 100_000e6`, `len(narrative_flags) == 6`.
  - `test_hypergrowth_story_without_terminal_growth_uses_currency_rule`: same without `terminal_growth`; `terminal_growth.source is AssumptionSource.RULE_BASED`, value `0.0395` (USD `min(rfr, gdp)` from the default `config/currencies.yaml`), year-10 revenue equals `target_revenue_y10` within `rel=1e-9` (the solve absorbs the different `g`), and `intrinsic_value` is finite.
  - `test_hypergrowth_story_replaces_manual_generic_keys` (decision 5): the story YAML plus `operating_margin: 0.35` and `revenue_growth: 0.10`; both come out sourced `story`, equal to `margin_path(story)` / the solved growth path.

- [ ] **Step 2: Run them, confirm they fail** — `uv run pytest tests/unit/test_valuator_analysis.py tests/unit/test_valuator_assumptions.py -q`.

- [ ] **Step 3: Implement.** Per-ticker loader: extend the existing `SELECT currency ...` query to `SELECT currency, revenue` (no new query). Bulk loader: carry the latest row's revenue from the rows it already reads. `resolve_assumptions`: after building the generic bundle, when `story_type is StoryType.HYPERGROWTH` and `story_from_override(override, where=...)` returns a story, raise `ValueError(f"{ticker}: hypergrowth story needs the latest revenue (none in financials_annual)")` if `db_inputs.latest_revenue is None`, else return `apply_story(bundle, story, base_revenue=db_inputs.latest_revenue, sector_wacc=sector.row.wacc if sector.row is not None else None)`. `analyze`: `Financials(..., fixed_commitments=<value or 0.0>, extra_cash=<value or 0.0>)` (decision 6). Update `analyze`'s and `resolve_assumptions`' docstrings for the story branch.

- [ ] **Step 4: Run** `uv run pytest -q`, `uv run ruff check . && uv run mypy src`, `python3 docs/pipeline/check.py`, `python3 docs/leccion/check.py`. Expected: all green, isolation golden unchanged.

- [ ] **Step 5: Commit** `feat(#196): resolve_assumptions and analyze run the story for hypergrowth`

## Out of scope (owned by sibling issues)

Scenarios, governance discount in the verdict, the scale/ROIC flags and report sections (#197); ADR, spec, glossary, plans and lesson (#198); pipeline boards and TLA+ model (#199).

## Grilling

- Rounds: 1 (the revisions add tests and one guard; there is no new seam and no step was removed, so no second round).
- Questions: 18. Sources: ISSUE 9, CODE 15, DOC 0, NO SOURCE 3 (several answers cite both).
- NO SOURCE → technical assumptions A1 (terminal_growth ≤ -1 refused), A2 (sector WACC used without a currency or year check), A3 (evals commit is red by design).
- Spec ambiguities: none. Out-of-scope issues opened: none (the scale/ROIC flags, the report and the docs already belong to #197–#199).
