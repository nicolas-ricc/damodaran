# Scenarios, governance verdict, hypergrowth flags and report sections (#197) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish the hypergrowth valuation as a reader sees it. That means the worst/base/best scenario range (worst and best within 5% of Damodaran's −$373B and $4.04T), the governance discount in the verdict, the `hypergrowth_revenue_scale` and `hypergrowth_terminal_roic` flags, and the Markdown/HTML/JSON report sections that show the story inputs with source `story`.

**Architecture:** `sensitivity.py` gains `ScenarioResult` and `scenario_range`, which runs one plain `dcf()` per case. `hypergrowth.py` gains `scenario_cases`, which builds base-first `(Financials, DCFAssumptions)` cases from the bundle and its scenarios. The sourced bundle carries `scenarios`, set by `resolve_assumptions`. `narrative_flags.py` adds the two flags, emitted by `hypergrowth_flags()` only for the `hypergrowth` story type. `analysis.py` wires in the scenarios, the governance-discounted margin of safety, the sector ROIC and the terminal ROIC. `analysis.md.j2` gains sections that are each guarded by `{% if %}`, so every other story type renders byte-identically.

**Tech Stack:** Python 3.12, frozen dataclasses, DuckDB, Jinja2, pytest, mypy `--strict`, ruff.

**Spec:** GitHub issue #197 (a child of story #192). Its "Design (decided; implement as written)" section is binding. Read it alongside this plan.

## Global Constraints

- Modules under `src/bot/valuator/` are pure: no I/O, no global state, frozen dataclasses. Each module constant carries a `#:` comment explaining its value.
- `_LARGEST_COMPANY_REVENUE = 750e9` (in the financials' currency units) and `_ROIC_SECTOR_MULTIPLE = 2.0` live in `narrative_flags.py`.
- Flag order after the five §7.5 flags: `hypergrowth_story`, `hypergrowth_revenue_scale`, `hypergrowth_terminal_roic`. `narrative_flags()` still returns exactly five.
- With a governance discount of 0, `margin_of_safety` must be floating-point identical to today's `intrinsic_value / price`.
- The grid and the tornado stay on the raw DCF value.
- `schema_version` stays 1. New fields are additive and have defaults.
- Isolation: `tests/unit/test_valuator_isolation_golden.py` passes **unchanged**, with Markdown byte-identical for every non-hypergrowth story type.
- Chapter numbers and existing headings of the report stay unchanged.
- Commits are Conventional Commits with `#197`. Gates: `uv run pytest -q`, `uv run ruff check . && uv run mypy src`, `python3 docs/pipeline/check.py`, `python3 docs/leccion/check.py`.

## Decisions taken here (not spelled out by the issue)

1. **`sector_wacc` and `base_revenue` in `analyze`** come from `inputs.assumption_inputs.sector.wacc` (or `None` when there is no sector row) and `inputs.assumption_inputs.latest_revenue`. These are the same values `resolve_assumptions` passed to `apply_story` for the base story.
2. **`Assumptions.scenarios`** is a plain `dict` (so that `dataclasses.asdict` recurses into it). It is `None` when the file has no `scenarios:` section. `parse_scenarios` already refuses an empty section, so `{}` never reaches the bundle. Outside a hypergrowth story it stays `None`.
3. **Scenario refusal.** If `apply_story` refuses a scenario (for example an unreachable `target_revenue_y10`), `scenario_cases` re-raises it as `ValueError(f"scenario {name}: {exc}")`. `bot analyze` then fails that ticker alone, as #180 requires. The batch goes on.
4. **`Analysis.governance_discount`** is `bundle.governance_discount.value`, or `0.0` when the field is `None`. `intrinsic_value_after_governance` is always set, so a non-story company gets `intrinsic × 1.0`, which equals the intrinsic value. The JSON golden allows the new keys.
5. **`NarrativeContext.terminal_roic`** is `bundle.terminal_roic.value` (or `None`). `sector_roic` is `_SectorMultiples.roic`.
6. **Where "raw DCF value" is documented:** the §1 governance line ends with "(tornado, grid and scenarios use the raw value)".
7. **Existing tests that change on purpose:** a `hypergrowth` story type now gets three hypergrowth flags, so tests that pinned six flags or `narrative_flags[-1].name == "hypergrowth_story"` for a hypergrowth story type are updated in Task 2. Those tests are `test_hypergrowth_with_story_file`, `test_hypergrowth_story_values_anthropic_end_to_end` and `test_story_file_without_hypergrowth_signals_is_yellow` in `tests/unit/test_valuator_analysis.py`. Signals-only companies keep six flags.
8. **Flag reason amounts** are written as billions (`f"{revenue / 1e9:,.0f}B"`), because the valuator cannot import the reporting formatters.

## Review Focus

1. **A scenario whose revenue target is unreachable:** `analyze` raises a `ValueError` that names the scenario. It never crashes with anything else. Test in Task 1.
2. **A hypergrowth story without a `scenarios:` section:** `Analysis.scenarios == ()` and the report has no "Scenario range". Tests in Task 3 and Task 4.
3. **A hypergrowth story with a governance discount but no price:** the report shows the governance line and "margin of safety cannot be computed", and `margin_of_safety` is `None`. Test in Task 4.
4. **Negative scenario equity (worst ≈ −372B):** it renders with a minus sign (`-…B`) and a negative per-share value, with no error from the formatter. Test in Task 4.
5. **A sidecar written before this change** (no `scenarios` or `governance_discount` keys): `bot site` still builds it and does not skip it. This is checked by the verification step in Task 4.

## Assumptions

Technical decisions recorded during plan grilling (no written source; any option satisfies the issue):

- **A1. Scenarios are applied over the bundle that already carries the base story.** `apply_story` (`src/bot/valuator/hypergrowth.py`, `apply_story`) replaces every story-driven field, and leaves only `terminal_growth`, `tax_rate`, `pretax_cost_of_debt`, `distress_value_per_share`, `story_type` and `notes` untouched. Those six are the generic resolver's values in both bundles, so applying the scenario to the pre-story bundle or to the storied bundle gives the same `DCFAssumptions`. Rejected alternative: keeping a copy of the pre-story bundle, which adds a field with no behavioural difference.
- **A2. Scenario cases are built in `analyze`, not in `resolve_assumptions`.** The issue says `Analysis.scenarios` is "filled by `analyze`", and `Financials` exists only in `analyze`. Rejected alternative: building them in the resolver, which would have to build `Financials` too.
- **A3. The margin-of-safety label under a governance discount** is "Margin of safety (on the value after governance discount)". The issue asks only that it be "labelled as measured on it". Rejected alternative: a separate second margin line.
- **A4. The terminal-ROIC reasons show both ROICs and the 2× threshold**, formatted with `:.1%`. The issue fixes only the rule. Rejected alternative: showing the threshold alone.
- **A5. The reporting tests build the `Analysis` through `analyze` on a seeded DuckDB.** This is the pattern of the existing `analysis` fixture in `tests/unit/test_reporting_analysis.py`. Rejected alternative: a hand-built `Analysis`, which no reporting test uses today.
- **A6. `Assumptions.scenarios` is a plain `dict` on a frozen dataclass.** No code hashes the sourced bundle: there is no `lru_cache`, set or dict key over it in `src/bot`, so the generated `__hash__` is never called. `dataclasses.asdict` (`src/bot/reporting/analysis_json.py`) recurses into the dict of `StoryInputs`.
- **A7. Stage 3 commits the evals while they are red**, as the pipeline asks. "Passes unchanged" for the golden is judged on the final branch.
- **Decisions 1–8 above** also count as technical assumptions for the PR description.

---

### Task 1: Scenario cases and the scenario range

**Files:**
- Modify: `src/bot/valuator/sensitivity.py`, `src/bot/valuator/hypergrowth.py`, `src/bot/valuator/assumptions.py`
- Test: `tests/unit/test_valuator_sensitivity.py`, `tests/unit/test_valuator_hypergrowth.py`, `tests/unit/test_hypergrowth_calibration.py`, `tests/unit/test_valuator_assumptions.py`

**Interfaces:**
- Consumes: `apply_story`, `StoryInputs`, `story_from_override` (existing). `dcf`, `Financials`, `dcf.Assumptions` (existing).
- Produces:
  - `sensitivity.ScenarioResult` (frozen): `name: str`, `intrinsic_value: float`, `equity_value: float`, `enterprise_value: float`.
  - `sensitivity.scenario_range(cases: Mapping[str, tuple[Financials, Assumptions]]) -> tuple[ScenarioResult, ...]`. It returns one result per case in mapping order, each from a plain `dcf()`.
  - `hypergrowth.scenario_cases(bundle: Assumptions, scenarios: Mapping[str, StoryInputs], *, base_revenue: float, sector_wacc: float | None, financials: Financials) -> dict[str, tuple[Financials, DCFAssumptions]]`. It puts `"base"` first, as `(financials, bundle.to_dcf_assumptions())`. Each scenario follows in mapping order, as `(replace(financials, fixed_commitments=s.fixed_commitments_pv, extra_cash=s.extra_cash), apply_story(bundle, s, ...).to_dcf_assumptions())`.
  - The sourced `Assumptions` gains `scenarios: Mapping[str, StoryInputs] | None = None` (the last field). `resolve_assumptions` sets it from `story_from_override(...)[1]` when that is non-empty.

- [ ] **Step 1: Write the failing tests**
  - `test_scenario_range_keeps_mapping_order`: two cases named `"b"` and `"a"` built from any valid DCF fixture. The result names are `("b", "a")`, and each `intrinsic_value`, `equity_value` and `enterprise_value` equals that case's `dcf()`.
  - `test_scenario_cases_base_first_then_file_order`: the keys are `["base", "worst", "best"]` for a scenarios dict `{"worst": ..., "best": ...}`, and `cases["base"] == (financials, bundle.to_dcf_assumptions())`.
  - `test_scenario_changing_commitments_changes_that_case_financials`: one scenario with `fixed_commitments_pv=1.0` and `extra_cash=2.0`. That case's `Financials` has `fixed_commitments == 1.0` and `extra_cash == 2.0`, and the base `Financials` is unchanged.
  - `test_scenario_unreachable_target_names_the_scenario`: a scenario with `target_revenue_y10` that cannot be reached raises `ValueError`, with a message matching `"scenario worst"`.
  - Calibration, in `test_hypergrowth_calibration.py` (millions): `bundle = _calibrated()[0]` (the bundle with the base story already applied, as `analyze` receives it from `resolve_assumptions`), and `scenarios = {"worst": replace(CAL_STORY, target_revenue_y10=200_000, target_margin=0.10, sales_to_capital=1.0, wacc_start=0.0988, regulatory_drag=0.10), "best": replace(CAL_STORY, target_revenue_y10=1_500_000, target_margin=0.40, sales_to_capital=4.0, wacc_start=0.0779, regulatory_drag=0.0)}`. Run `scenario_range(scenario_cases(bundle, scenarios, base_revenue=CAL_BASE_REVENUE, sector_wacc=None, financials=CAL_FINANCIALS))`. Assert worst `equity_value == approx(-373_000, rel=0.05)` (computed −371,991), best `== approx(4_040_000, rel=0.05)` (computed 4,076,137), and that base `equity_value` exactly equals `_calibrated()[1].equity_value`.
  - `test_resolve_sets_scenarios_from_the_story_file` (assumptions tests): a hypergrowth override with `story` and `scenarios` gives `bundle.scenarios` the keys `["worst", "best"]` as `StoryInputs`. Without a `scenarios:` section it is `None`. For a non-hypergrowth company it is `None`.

- [ ] **Step 2: Run them and see them fail**, with `uv run pytest -q tests/unit -k "scenario"`. They should fail with import or attribute errors.

- [ ] **Step 3: Implement** the three interfaces above. `hypergrowth.py` imports `Financials` and `Assumptions as DCFAssumptions` from `bot.valuator.dcf` at module level (`dcf.py` does not import `hypergrowth`). Update the module docstrings of `sensitivity.py` and `hypergrowth.py` with one line each.

- [ ] **Step 4: Run the tests and see them pass**, then run `uv run pytest -q tests/unit/test_valuator_isolation_golden.py`. Both should be green.

- [ ] **Step 5: Commit** with `feat(#197): scenario cases and the scenario range`.

### Task 2: Revenue-scale and terminal-ROIC flags

**Files:**
- Modify: `src/bot/valuator/narrative_flags.py`
- Test: `tests/unit/test_valuator_narrative_flags.py`, `tests/unit/test_valuator_analysis.py` (Decision 7)

**Interfaces:**
- Produces:
  - `NarrativeContext` gains `terminal_roic: float | None = None` and `sector_roic: float | None = None`.
  - `hypergrowth_revenue_scale_flag(financials, assumptions, result, context) -> NarrativeFlag` with name `"hypergrowth_revenue_scale"`. It is yellow when `result.projections[-1].revenue > _LARGEST_COMPANY_REVENUE`, with the reason `f"year-10 revenue {r/1e9:,.0f}B exceeds the largest company revenue today (~750B)"`. Otherwise it is green, with a reason saying the revenue is within that figure.
  - `hypergrowth_terminal_roic_flag(...) -> NarrativeFlag` with name `"hypergrowth_terminal_roic"`. It is unknown when either ROIC is `None`. It is yellow when `terminal_roic > _ROIC_SECTOR_MULTIPLE * sector_roic`, and green otherwise.
  - `hypergrowth_flags()` returns `(story, revenue_scale, terminal_roic)` when `context.story_type == "hypergrowth"`. It returns `(story,)` when only `hypergrowth_signals` is set, and `()` otherwise.

- [ ] **Step 1: Write the failing tests**
  - The revenue-scale flag is yellow at `750e9 + 1` and green at exactly `750e9`. Build a `DCFResult` whose last projection carries that revenue.
  - The terminal-ROIC flag, with `sector_roic=0.12`, is yellow at `terminal_roic=0.24 + 1e-9` and green at exactly `0.24`. It is unknown with `sector_roic=None`, and also unknown with `terminal_roic=None`.
  - `hypergrowth_flags` returns three flags, with names in the order above, for `story_type="hypergrowth"`. It returns exactly one (`hypergrowth_story`) for `hypergrowth_signals=True, story_type="high-growth"`. `narrative_flags()` still returns five.
  - Update the three analysis tests of Decision 7. The flag count becomes `8`, and the flag is found by name (`next(f for f in a.narrative_flags if f.name == "hypergrowth_story")`) instead of `[-1]`.

- [ ] **Step 2: Run them and see them fail**, with `uv run pytest -q tests/unit/test_valuator_narrative_flags.py`.

- [ ] **Step 3: Implement** the flags and update the module docstring. The docstring should now say that `hypergrowth_flags` emits up to three flags.

- [ ] **Step 4: Run them and see them pass**, with `uv run pytest -q tests/unit/test_valuator_narrative_flags.py tests/unit/test_valuator_analysis.py tests/unit/test_valuator_isolation_golden.py`.

- [ ] **Step 5: Commit** with `feat(#197): hypergrowth revenue-scale and terminal-ROIC flags`.

### Task 3: `analyze` wiring: scenarios, governance verdict, sector ROIC

**Files:**
- Modify: `src/bot/valuator/analysis.py`
- Test: `tests/unit/test_valuator_analysis.py`

**Interfaces:**
- Consumes: Task 1 (`scenario_cases`, `scenario_range`, `ScenarioResult`, `bundle.scenarios`) and Task 2 (the `NarrativeContext` ROIC fields).
- Produces:
  - `_SectorMultiples.roic: float | None`, read from `damodaran_industry.roic` in both `_load_sector_multiples` and `bulk_load_valuation_inputs`.
  - New `Analysis` fields, appended last with defaults: `scenarios: tuple[ScenarioResult, ...] = ()`, `governance_discount: float = 0.0`, `intrinsic_value_after_governance: float = 0.0`.
  - `margin_of_safety = intrinsic_value_after_governance / price`, where `intrinsic_value_after_governance = dcf_result.intrinsic_value * (1 - governance_discount)`.

- [ ] **Step 1: Write the failing tests** (they use `_seed_anthropic_sheet`, which already sets `roic = 0.12`).
  - `test_hypergrowth_scenarios_governance_and_flags`: the YAML is `_STORY` (with `governance_discount: 0.20`) plus `scenarios` worst/best in raw units (calibration values ×1e6, worst drag 0.10), plus `terminal_growth: 0.049` and `tax_rate: 0.25`, and a price is seeded in `prices_daily`. Assert `[s.name for s in a.scenarios] == ["base", "worst", "best"]`, `a.governance_discount == 0.20`, `a.margin_of_safety == a.intrinsic_value_after_governance / a.current_price`, `a.intrinsic_value_after_governance == a.dcf_result.intrinsic_value * 0.8`, and `len(a.narrative_flags) == 8`. The `hypergrowth_terminal_roic` flag should be green, which proves that `sector_roic` 0.12 reached the context, and its reason should mention `12.0%` (the reasons format both ROICs with `:.1%`).
  - In the same test: `a.scenarios[0].equity_value == a.dcf_result.equity_value` and `a.scenarios[0].intrinsic_value == a.dcf_result.intrinsic_value` (the base row is the headline DCF).
  - `test_hypergrowth_without_scenarios_has_no_range`: `_sheet_yaml` with no scenarios gives `a.scenarios == ()`.
  - `test_bulk_loader_carries_sector_roic`: `bulk_load_valuation_inputs(conn, ["ANTH"])["ANTH"].sector.roic == 0.12`, which equals `load_valuation_input(conn, "ANTH").sector.roic`.
  - `test_mature_company_margin_unchanged`: for AAPL, `a.governance_discount == 0.0` and `a.margin_of_safety == a.dcf_result.intrinsic_value / a.current_price`, compared with exact `==`.

- [ ] **Step 2: Run them and see them fail**, with `uv run pytest -q tests/unit/test_valuator_analysis.py`.

- [ ] **Step 3: Implement** using Decisions 1, 4 and 5. Update the `Analysis` docstring (new attributes, and `margin_of_safety` measured on the value after the governance discount).

- [ ] **Step 4: Run them and see them pass**, with `uv run pytest -q tests/unit/test_valuator_analysis.py tests/unit/test_valuator_isolation_golden.py tests/unit/test_screener_second_pass_golden.py`.

- [ ] **Step 5: Commit** with `feat(#197): scenarios, governance discount and sector ROIC in analyze`.

### Task 4: Report sections (Markdown, HTML, JSON)

**Files:**
- Modify: `src/bot/reporting/templates/analysis.md.j2`
- Test: `tests/unit/test_reporting_hypergrowth.py` (new; one fixture rendered through all three reports)

**Interfaces:**
- Consumes: the `Analysis` of Task 3. The `money`, `per_share`, `pct` and `margin_path` filters exist already.
- Produces, as template additions that are each inside `{% if %}`:
  - §1. When `a.governance_discount > 0`: `- **Intrinsic value after governance discount ({{ pct }}):** {{ per_share }} (tornado, grid and scenarios use the raw value)`. The margin-of-safety line reads `- **Margin of safety (on the value after governance discount):** …` in that case only. The raw value line stays.
  - §1. When `a.dcf_result.wacc_path` is set: `- **WACC path (story):** {{ a.dcf_result.wacc_path | margin_path }}` replaces the "computed from the components" line.
  - §3. One row per field that is not `None`: `| WACC path | margin_path | source |`, `| Tax-rate path | margin_path | source |`, `| Terminal ROIC | pct |`, `| Failure proceeds (% of value) | pct |`, `| Fixed commitments | money |`, `| Extra cash | money |`, `| Governance discount | pct |`. Each row shows the field's `source` (`story`).
  - §4. When `enterprise_value_after_failure is not none`: `- **Operating assets after failure risk:** money`. When non-zero: `- **Fixed commitments (added to debt):** money` and `- **Extra cash:** money`.
  - §5. When `a.scenarios` is non-empty, a `### Scenario range` block goes under the tornado table. It holds one sentence ("The worst and best scenarios come from the story file's `scenarios:` section; base is the story itself."), then the table `| Scenario | Equity value | Per share |` with `money` and `per_share`.

- [ ] **Step 1: Write the failing tests.** Build the Task 3 analysis with a shared helper or fixture: `_seed_anthropic_sheet` plus the full YAML with scenarios and a price.
  - The Markdown contains `"Scenario range"`, `"| base |"`, `"| worst |"`, `"| best |"`, `"WACC path (story): "` (the bold markers sit around the label, so match on `"WACC path (story):"`), a row matching the regex `r"\| .* \| story \|"`, `"after governance discount"`, `"Operating assets after failure risk"` and `"Fixed commitments"`. The worst row's equity starts with `-`.
  - `render_analysis_html(a)` contains the same strings and `<img`, and `len(a.tornado) == 6`.
  - `render_analysis_json(a, generated_on=...)` parses. Its `schema_version == 1`, `analysis.scenarios` has three items whose names are base, worst and best, and `analysis.governance_discount == 0.2`.
  - A hypergrowth story with no scenarios has no `"Scenario range"`.
  - A hypergrowth story with `governance_discount` and no price contains `"after governance discount"` and `"margin of safety cannot be computed"`.

- [ ] **Step 2: Run them and see them fail**, with `uv run pytest -q tests/unit/test_reporting_analysis.py tests/unit/test_reporting_html.py tests/unit/test_reporting_analysis_json.py`.

- [ ] **Step 3: Implement** the template additions. With `trim_blocks` and `lstrip_blocks` on, check the blank lines by running the golden.

- [ ] **Step 4: Verify.** `uv run pytest -q` should be fully green, and so should `uv run ruff check . && uv run mypy src`, `python3 docs/pipeline/check.py` and `python3 docs/leccion/check.py`. `rm -rf /tmp/site-check && uv run bot site --out /tmp/site-check --reports-dir reports --base-url /` should exit 0 and log no `web.sidecar_skipped` event (`src/bot/web/index.py:43-44`). `reports/` holds 46 committed sidecars that predate this change.

- [ ] **Step 5: Commit** with `feat(#197): hypergrowth report sections`.

## Grilling

- Rounds: 1. The revisions were small (one clarified fixture, one added assertion and the Assumptions section), so no second round was run.
- Questions: 17. Answered with ISSUE: 6 (Q5, Q8, Q12, Q13, Q14, Q17). Answered with CODE: 9 (Q2 golden docstring, Q3 `assumptions.py` and `dcf.py` defaults, Q4 `analysis_json.py` `asdict`, Q6 no hashing, Q7 `parse_scenarios` merges over the base, Q9 `cli.py:479-488` and `test_cli_analyze.py:426`, Q10 `schema.sql:15` and the seed, Q11 `web/index.py:43`, Q16 the reporting fixture). NO SOURCE → technical assumption: 4 (Q1→A1, Q13 part→A3, Q15→A4, Q16→A5; Q6 is recorded as A6).
- Spec ambiguities: none. Out of scope: none, so no issues were opened.
