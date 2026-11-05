# A distressed company's probability of bankruptcy comes from its interest coverage — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the resolved story type is `distressed` and the override has no `probability_of_bankruptcy`, `p` becomes coverage → `rating_for` → `probability_for` (source `rule_based`), the derivation rides on `Assumptions.bankruptcy_derivation`, and report §3 prints it.

**Architecture:** `_resolve_probability_of_bankruptcy` in `src/bot/valuator/assumptions.py` gains the story type, the interest coverage and the default-spread table, and returns `(Sourced[float], BankruptcyDerivation | None)`. `resolve_assumptions` gains two keywords (`interest_coverage`, `default_spreads`). `analyze` passes the coverage it already computes plus a `default_spreads` keyword. The table is threaded the way `currencies=` already is: CLI (three commands) → `run_screen` → `_batch_dcf_margins` → `analyze`, and `run_portfolio` → `mark_holdings` → `analyze`. One template line in report §3.

**Tech Stack:** Python 3.12, DuckDB, Jinja2, structlog, pytest, mypy --strict, ruff.

**Spec:** issue #246 (child of story #213). Its "Decisions" section is binding and is not reopened here.

## Global Constraints

- The chain runs only when the resolved `story_type` (manual or classifier) is `StoryType.DISTRESSED` **and** the override has no `probability_of_bankruptcy`. A manual `p` always wins: source `manual`, derivation `None`, table never loaded.
- Non-distressed stories: `p = 0.0`, `rule_based`, derivation `None`, table never loaded. Hypergrowth stays as it is (`apply_story` sets `p` from `failure_probability`).
- `distress_value_per_share` stays manual-or-0.
- Order of checks inside the chain (technical decision, see Review Focus 1): coverage `None` → "unknown" reason, **without loading the table**; then the table (loaded lazily via the module-level `load_default_spreads()` when `default_spreads is None`) is empty → "empty" reason; then no bracket → "no bracket" reason; then no probability row → "no probability" reason; else derived.
- `interest_coverage` that is NaN is treated by `rating_for` (returns `None`) and so gives the "no bracket" reason. No special case.
- `reason` strings, verbatim (Python format specs included):
  - derived: `interest coverage {coverage:.2f} → rating {rating} → {horizon_years}-year cumulative default probability {p:.1%}`
  - no coverage: `distressed, but interest coverage is unknown (no EBIT or no interest expense): p stays 0`
  - empty table: `distressed, but the default-spread table is empty (config/default_spreads.yaml absent or malformed): p stays 0`
  - no bracket: `distressed, but coverage {coverage:.2f} has no rating in the default-spread table: p stays 0`
  - no probability row: `distressed, but rating {rating} has no default probability in the table: p stays 0`
- Every fallback gives `p = 0.0`, source `rule_based`, and a derivation whose `probability` is `0.0`. `rating` is `None` except in the "no probability row" case, where it is the rating found. `horizon_years` is the table's (`None` for the empty table and for the no-coverage case, where the table is not read).
- Import in `assumptions.py` is module-level `from bot.reference.default_spreads import DefaultSpreadTable, load_default_spreads`, so tests can monkeypatch `bot.valuator.assumptions.load_default_spreads`.
- Report line, after the governance-discount `{% endif %}` and before `## 4.`, only when the derivation exists, preceded by a blank line:
  `- **Probability of bankruptcy chain:** {{ a.assumptions.bankruptcy_derivation.reason }}`
  Without the derivation the Markdown is byte-identical to today.
- The web viewer (`src/bot/web/views.py`) and everything under `docs/` except this plan are out of scope (sibling #247 owns the atlas, lesson and plano).
- Do not touch `_resolve_operating_margin` (its mature-decline branch is #244's).
- Both goldens pass **without regeneration**.
- `uv run ruff check . && uv run mypy src` clean; `uv run pytest -q` green.
- Commit subjects for the implementation: `feat(#246): a distressed company's bankruptcy probability comes from its interest coverage`, `feat(#246): report shows the coverage → rating → probability chain`. (The issue writes `#213` in these subjects; the pipeline running this issue names its commits `#246`. The PR squash title carries `#246` and closes it.)

## Review Focus

1. **Distressed by manual `story_type`, no interest expense, and a missing table file**: coverage is `None`, so the reason is "unknown" and the table is never loaded (no spurious `default_spreads.absent` warning). Pinned by `test_distressed_without_coverage_does_not_load_the_table` (Task 1).
2. **Negative coverage** (EBIT < 0, interest > 0, e.g. −0.5): it falls in the first bracket (`lower: null`), so `D` in the repo table, never a crash or a skipped chain. Pinned by `test_negative_coverage_takes_the_lowest_bracket` (Task 1) with the inline table (→ `CCC`, 0.59).
3. **One warning per CLI run, not one per ticker**: the CLI loads the table once and passes it down, so a missing file warns once however many tickers are valued. `run_screen` / `mark_holdings` forward `None` as `None` (the issue's lazy-load rule; no eager load there, which would warn even when no company is distressed). Pinned by the CLI-level test that `default_spreads.absent` is logged exactly once (Task 4).
4. **A hypergrowth story with a story file** is not touched: `p` stays the story's `failure_probability`, derivation `None`. Covered by the existing hypergrowth tests staying green and by `test_generic_bundle_has_no_story_fields` gaining `bankruptcy_derivation`.
5. **The repo table itself** is used when nothing is passed: `test_distressed_with_the_repo_table_uses_its_own_numbers` (Task 2) asserts against `load_default_spreads()`, never a hard-coded number.

---

### Task 1: The coverage → rating → probability chain in `resolve_assumptions`

**Files:**
- Modify: `src/bot/valuator/assumptions.py` (module docstring resolution-order block l.9-20; `Assumptions` docstring l.151-156 and a new last field; `resolve_assumptions` l.825-955; `_resolve_probability_of_bankruptcy` l.1192; `_resolve_distress_value_per_share` docstring l.1200-1206)
- Modify: `src/bot/valuator/dcf.py:121-124` (docstring only)
- Modify: `config/assumptions/README.md` (one line: a manual `probability_of_bankruptcy` wins over the default-spread table)
- Test: `tests/unit/test_valuator_assumptions.py`

**Interfaces:**
- Consumes: `bot.reference.default_spreads.DefaultSpreadTable`, `CoverageBracket`, `DefaultProbability`, `EMPTY_DEFAULT_SPREADS`, `load_default_spreads(path: Path | None = None) -> DefaultSpreadTable`.
- Produces:
  ```python
  @dataclass(frozen=True)
  class BankruptcyDerivation:
      interest_coverage: float | None
      rating: str | None
      horizon_years: int | None
      probability: float
      reason: str
  ```
  `Assumptions.bankruptcy_derivation: BankruptcyDerivation | None = None` (last field, set only when the chain ran).
  `resolve_assumptions(..., interest_coverage: float | None = None, default_spreads: DefaultSpreadTable | None = None)`.
  `_resolve_probability_of_bankruptcy(override, *, story_type: StoryType | None, interest_coverage: float | None, default_spreads: DefaultSpreadTable | None) -> tuple[Sourced[float], BankruptcyDerivation | None]`.

- [ ] **Step 1: Tests (written in stage 3, failing).** Inline table helper, never the repo file:
  ```python
  def _spreads() -> DefaultSpreadTable:
      # horizon 10; brackets (None, 1.0) → "CCC", (1.0, None) → "BBB"; CCC 0.59, BBB 0.075
  ```
  - `test_distressed_probability_comes_from_the_coverage_rating`: `resolve_assumptions("ACME", conn, auto_story_type=StoryType.DISTRESSED, interest_coverage=0.6, default_spreads=_spreads(), currencies=_usd())` → `p.value == 0.59`, `RULE_BASED`; derivation `== BankruptcyDerivation(0.6, "CCC", 10, 0.59, "interest coverage 0.60 → rating CCC → 10-year cumulative default probability 59.0%")`.
  - `test_manual_probability_beats_the_table`: override `probability_of_bankruptcy: 0.1\n` → `0.1`, `MANUAL`, derivation `None`.
  - `test_distressed_without_coverage_keeps_zero_and_says_why`: `interest_coverage=None` → `0.0`, `RULE_BASED`, reason == the pinned "unknown" string, `rating is None`.
  - `test_distressed_with_an_empty_table_keeps_zero_and_says_why`: `default_spreads=EMPTY_DEFAULT_SPREADS`, coverage 0.6 → `0.0`, the pinned "empty" reason.
  - `test_non_distressed_story_ignores_coverage`: `MATURE_STABLE`, coverage 0.6, the table → `0.0`, `RULE_BASED`, derivation `None`.
  - `test_distressed_loads_the_default_table_when_none_is_given`: monkeypatch `bot.valuator.assumptions.load_default_spreads` with a counting stub returning `_spreads()`: 1 call for distressed (coverage 0.6), 0 for mature-stable, 0 for distressed with a manual `p`.
  - `test_distressed_without_coverage_does_not_load_the_table` (Review Focus 1): the counting stub sees 0 calls with `interest_coverage=None`.
  - `test_negative_coverage_takes_the_lowest_bracket` (Review Focus 2): coverage −0.5 → `"CCC"`, `0.59`, reason starts with `interest coverage -0.50 → rating CCC`.
  - `test_generic_bundle_has_no_story_fields` (l.1223): add `bankruptcy_derivation` to the names that must be `None`.
- [ ] **Step 2: Run them, see them fail.** `uv run pytest -q tests/unit/test_valuator_assumptions.py` → the new tests fail (ImportError on `BankruptcyDerivation` first).
- [ ] **Step 3: Implement** the dataclass, the field, the two keywords and the resolver per the Global Constraints. `resolve_assumptions` unpacks the tuple and passes `bankruptcy_derivation=` to `Assumptions(...)`. Update the four docstrings the issue lists (the module's rule-based step now includes "a distressed company's probability of bankruptcy from interest coverage via `config/default_spreads.yaml`"; `probability_of_bankruptcy` / `distress_value_per_share` attribute docs; `_resolve_distress_value_per_share`; `dcf.Assumptions`), document the two new keywords in the `resolve_assumptions` Args, and add the README line.
- [ ] **Step 4: Run.** `uv run pytest -q tests/unit/test_valuator_assumptions.py` → PASS; `uv run mypy src` clean.
- [ ] **Step 5: Commit** `feat(#246): a distressed company's bankruptcy probability comes from its interest coverage`.

### Task 2: `analyze` passes the coverage and the table

**Files:**
- Modify: `src/bot/valuator/analysis.py:813-935` (`analyze` signature, docstring Args, the `resolve_assumptions(...)` call)
- Modify: `tests/unit/test_valuator_isolation_golden.py`, `tests/unit/test_screener_second_pass_golden.py` (docstring notes only)
- Test: `tests/unit/test_valuator_analysis.py`

**Interfaces:**
- Consumes: Task 1's `resolve_assumptions(..., interest_coverage=, default_spreads=)`, `BankruptcyDerivation`.
- Produces: `analyze(..., default_spreads: DefaultSpreadTable | None = None)`; `None` means `resolve_assumptions` loads the default file lazily.

- [ ] **Step 1: Tests (stage 3, failing).** In `test_valuator_analysis.py`, a local helper `_seed_distressed(conn, *, interest: float | None = 60.0)` reproducing the isolation golden's `_distressed` seed (company `DIST`, `Retail (General)`, the same four `(year, revenue, ebit, net_income, interest, debt, cash)` rows in millions, close 1.5) with no override. It is local because the golden module imports from this one (a back-import would be circular). The same inline `_spreads()` table as Task 1 (import it from `tests.unit.test_valuator_assumptions`).
  - `test_distressed_company_is_valued_survival_weighted`: `a = analyze("DIST", conn, default_spreads=_spreads())` → `a.assumptions.probability_of_bankruptcy.value == 0.59`, source `RULE_BASED`, and `a.dcf_result.intrinsic_value == pytest.approx(0.41 * dcf(a.financials, replace(a.assumptions.to_dcf_assumptions(), probability_of_bankruptcy=0.0)).intrinsic_value)`.
  - `test_distressed_with_the_repo_table_uses_its_own_numbers`: no `default_spreads`; `t = load_default_spreads()`; `p == t.probability_for(t.rating_for(a.assumptions.bankruptcy_derivation.interest_coverage))`, and that coverage `== pytest.approx(40 / 60)`.
  - `test_manual_distressed_without_interest_expense_says_why`: `interest=None` (NULL), override `story_type: distressed\n` → `p == 0.0`, reason == the pinned "unknown" string, and `render_analysis(a, generated_on=date(2026, 1, 1))` contains `**Probability of bankruptcy chain:** distressed, but interest coverage is unknown` (this assertion goes green in Task 3).
- [ ] **Step 2: Run, see them fail** (`analyze() got an unexpected keyword argument 'default_spreads'`).
- [ ] **Step 3: Implement**: add the keyword, pass `interest_coverage=interest_coverage, default_spreads=default_spreads` to `resolve_assumptions`. Do not recompute the coverage. Document the keyword in Args like `currencies`.
- [ ] **Step 4: Golden docstring notes.** Append to the isolation golden's docstring: `Re-run for #213 (distressed p from coverage): unchanged — the distressed fixture has a manual p.` Append to the second-pass golden's docstring: `Re-run for #213 (distressed p from coverage): unchanged — no seeded company is distressed.`
- [ ] **Step 5: Run.** `uv run pytest -q tests/unit/test_valuator_analysis.py tests/unit/test_valuator_isolation_golden.py tests/unit/test_screener_second_pass_golden.py` → PASS except the render assertion of the third test (Task 3). Goldens pass with no fixture file changed (`git status tests/fixtures` clean).
- [ ] **Step 6: Commit** (with Task 1's subject's scope, e.g. `feat(#246): analyze feeds the interest coverage to the bankruptcy chain`).

### Task 3: Report §3 prints the chain

**Files:**
- Modify: `src/bot/reporting/templates/analysis.md.j2:72-76`
- Test: `tests/unit/test_reporting_analysis.py`

**Interfaces:**
- Consumes: `Assumptions.bankruptcy_derivation` (Task 1).

- [ ] **Step 1: Tests (stage 3, failing).**
  - `test_bankruptcy_chain_line_renders_when_the_chain_ran`: `dataclasses.replace` the fixture's `analysis.assumptions` with `bankruptcy_derivation=BankruptcyDerivation(0.6, "CCC", 10, 0.59, "<derived reason>")`; the rendered Markdown contains `\n\n- **Probability of bankruptcy chain:** <derived reason>\n` and that line sits after the `| Probability of bankruptcy |` row and before `## 4. DCF detail`.
  - `test_bankruptcy_chain_line_absent_by_default`: the fixture's default render does not contain `Probability of bankruptcy chain`.
- [ ] **Step 2: Run, see the first fail.**
- [ ] **Step 3: Implement** the `{% if a.assumptions.bankruptcy_derivation is not none %}` block per Global Constraints; keep the no-derivation output byte-identical (the isolation golden proves it).
- [ ] **Step 4: Run.** `uv run pytest -q tests/unit/test_reporting_analysis.py tests/unit/test_valuator_analysis.py tests/unit/test_valuator_isolation_golden.py` → PASS.
- [ ] **Step 5: Commit** `feat(#246): report shows the coverage → rating → probability chain`.

### Task 4: Thread `default_spreads` through the screener, the portfolio and the CLI

**Files:**
- Modify: `src/bot/screener/engine.py` (`_batch_dcf_margins` l.108, its call in `run_screen` ~l.877, `run_screen` l.738)
- Modify: `src/bot/portfolio/marks.py` (`mark_holdings` l.146), `src/bot/portfolio/command.py` (`run_portfolio` l.85)
- Modify: `src/bot/cli.py` (analyze l.453 + `_analyze_one` l.465, screen l.546, portfolio l.613)
- Test: `tests/unit/test_cli_analyze.py`; extend spies/stubs in `tests/unit/test_cli_portfolio.py` / `tests/unit/test_cli.py` only if they break.

**Interfaces:**
- Consumes: `analyze(..., default_spreads=)` (Task 2); `Settings.default_spreads_path`; `load_default_spreads`.
- Produces: keyword `default_spreads: DefaultSpreadTable | None = None` on `_batch_dcf_margins`, `run_screen`, `mark_holdings`, `run_portfolio`; `_analyze_one` gains a positional `default_spreads: DefaultSpreadTable` after `currencies`.

- [ ] **Step 1: Test (stage 3, failing).** `test_analyze_with_a_missing_default_spreads_file_values_with_p_zero`: seed `AAPL` with `_seed`, then `UPDATE financials_annual SET interest_expense = …` so coverage is known; write an override with `story_type: distressed\n` and pass it with `--override`; set `BOT_DEFAULT_SPREADS_PATH` to `tmp_path / "missing.yaml"`; inside `structlog.testing.capture_logs()` run `bot analyze AAPL` → exit 0, exactly one entry with `event == "default_spreads.absent"`, and the written Markdown contains `**Probability of bankruptcy chain:** distressed, but the default-spread table is empty`.
- [ ] **Step 2: Run, see it fail** (the resolver is not reached by the CLI's table; without threading the lazy loader reads the repo file and no warning is logged).
- [ ] **Step 3: Implement.** Each layer forwards the keyword exactly as `currencies` is forwarded. `run_screen` passes it to `_batch_dcf_margins`, which passes it to `analyze(company=...)`. `mark_holdings`' default valuator closure passes it to `valuator.analyze`; `run_portfolio` passes it to `mark_holdings`. The CLI loads `load_default_spreads(settings.default_spreads_path)` once per command next to `load_currency_table(settings.currencies_path)`. Document each new keyword in its docstring like `currencies`.
- [ ] **Step 4: Run.** `uv run pytest -q` → green; `uv run ruff check . && uv run mypy src` clean; `grep -l default_spreads src/bot/cli.py src/bot/screener/engine.py src/bot/portfolio/command.py src/bot/portfolio/marks.py src/bot/valuator/analysis.py src/bot/valuator/assumptions.py` lists all six.
- [ ] **Step 5: Commit** `feat(#246): thread the default-spread table from the CLI to analyze`.
