# Re-true the pipeline boards after #109 (#162) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the six boards in `docs/pipeline/` true to the code again after PR #142 (#109, per-currency risk-free rate), so `uv run pytest -q`, `python3 docs/pipeline/check.py` and the `pipeline-diagram` workflow are green on `feature/161-pipeline-subboards`.

**Architecture:** Edit four boards (`refresh.d2`, `screen.d2`, `analyze.d2`, `portfolio.d2`) node by node; `pipeline.d2` and `site.d2` carry no stale statement (checked: no `ADR 0005`, no risk-free rate, the overview's "country risk" edges are still true) and stay as they are. Each board task first pins the new statements in `tests/unit/test_pipeline_diagram.py` (required citations, `_*_TEXT` substrings, node classes), sees them fail, then edits the board. No pipeline code changes. SVGs and `rendered.sha256` come only from the `pipeline-diagram` CI artifact (Task 5).

**Tech Stack:** d2 v0.9.0 + TALA (CI only), Python 3.12 / pytest, `docs/pipeline/check.py`.

**Spec:** GitHub issue #162 (child of story #161), `docs/pipeline/README.md` (directive syntax and conventions), ADR 0005 §4 "As implemented", ADR 0006, `CONTEXT.md` (coverage gate, uncovered currency, valuation currency).

## Global Constraints

- Do not change pipeline code (`src/`, `config/`). A board statement found wrong before #109 too is fixed and listed in the PR.
- Every `ADR 0005` mention on every board reads `ADR 0005 (Implemented)` (the status the test `_current_status("0005")` derives from the ADR). No board cites `parse_preheader_scalar` or `_DEFAULT_GDP_NOMINAL`.
- The literal `4%` goes from `analyze.d2`: no constant holds the GDP growth any more (USD's `0.04` lives in `config/currencies.yaml`, which `@const` cannot cite).
- Board conventions (README): directives in `#` comments on the line they check, never inside `|md ... |`; `class:` first attribute; every acronym expanded at first use; every digit on a step label cited or written in words; every edge labelled; gap notes start `Gap:` and name their document.
- Never hand-edit an SVG or `rendered.sha256`.
- Commits during implementation: `docs(#162): ...` for board + test edits.

## Code facts the boards must state (read at 1239a9e)

- Valuation currency = `financials_annual.currency` of the latest non-restated row (`bot.screener.engine._load_reporting_currencies`, `bot.valuator.assumptions.load_assumption_inputs`), normalised (stripped, upper-cased) by `bot.reference.currencies.normalize_currency`.
- Currency table: `config/currencies.yaml`, loaded by `bot.reference.currencies.load_currency_table`; per currency `risk_free_rate` and `nominal_gdp_growth`; absent or malformed file → empty table (every currency uncovered); no USD fallback.
- Coverage gate (`bot.screener.engine.run_screen`, `CoverageReason`): first matching reason, in order `industry_unmapped` (no `industry_damodaran`) > `benchmark_missing` (no sector benchmark row or a NULL `wacc`) > `currency_uncovered` (valuation currency not in the table, or none). The rejected row's failed rules are that one reason's name (it was the literal `coverage_gate` before #109).
- Screen report header line: `format_coverage_counts`: `Excluded by coverage gate (ADR 0006): total (industry_unmapped n · benchmark_missing n · currency_uncovered n)`; the CLI prints the same line.
- Second pass (`_batch_dcf_margins`) values with the same currency table as the gate; `mark_holdings` loads the table once per run and passes it to `analyze`.
- Terminal growth (`_resolve_terminal_growth`): manual → manual; currency covered → min(risk-free rate, nominal GDP growth) → rule_based; uncovered → unresolved (and the DCF cannot run).
- Revenue growth (`_resolve_revenue_growth`): manual; high-growth with history and a GDP figure → straight line to the currency's nominal GDP growth → story_pattern; history → historical_average; no history, GDP known → GDP each year → rule_based; neither → unresolved.
- Damodaran importer writes country rows with ERP, country risk premium, tax rate, rating, region; no risk-free rate (`schema.sql` drops the column). `--region` other than US is still refused.

## Review Focus

1. **A board text that still reads "risk-free rate" from `damodaran_country`.** Edges `damodaran.write -> duckdb.damodaran_country` (refresh) and `duckdb.damodaran_country -> assumptions.terminal_growth` (analyze) are the two places; Tasks 1 and 3 pin them with `_edge_line` assertions.
2. **The coverage reasons drawn in the wrong order.** Task 2's test asserts the three reason names appear in the gate's block in precedence order (index comparison), plus the `@enum bot.screener.engine.CoverageReason` directive makes every member value visible.
3. **An uncovered currency drawn with a fallback.** Task 3 pins "unresolved" on terminal growth and the absence of any `4%`.
4. **The portfolio gap test going silent.** Task 4 replaces the "Not implemented" trigger with the ADR's own sentence about §1–§3, so the gap disappears when that sentence does.
5. **Stale SVGs.** `check.py` compares `rendered.sha256` with the sources; Task 5 takes them from the CI run of the final sources.

---

### Task 1: Refresh board — Damodaran country rows without a risk-free rate

**Files:**
- Modify: `docs/pipeline/refresh.d2` (`damodaran.country`, its `risk_free` child, `damodaran.write.us_only`, edge `damodaran.write -> duckdb.damodaran_country`)
- Test: `tests/unit/test_pipeline_diagram.py`

**Interfaces:**
- Produces: nothing later tasks consume. Refresh gets no `currencies_yaml` node: nothing in the refresh stage reads or writes the file, so it is cited on the note only (file nodes need no edge, but an unconnected one would suggest a flow that does not exist).

- [ ] **Step 1: Write the failing tests**
  - `_REQUIRED_SYMBOLS["refresh"]`: remove `bot.ingest.damodaran.parse_preheader_scalar`, add `bot.reference.currencies.load_currency_table`.
  - `_REQUIRED_FILES["refresh"]`: add `config/currencies.yaml`.
  - `_REFRESH_NODES`: `("damodaran.country.risk_free", "gap")` becomes `("damodaran.country.risk_free", "note")`.
  - `test_refresh_gap_notes`: keep the three asserts; add `assert "ADR 0005 (Implemented)" in _refresh_block("damodaran.write.us_only")` and `assert "config/currencies.yaml" in _refresh_block("damodaran.country.risk_free")`.
  - New `test_refresh_country_rows_carry_no_risk_free_rate`: `_refresh_block("damodaran.country")` first label line set does not contain `wacc.xls`; `_edge_line(_refresh(), "damodaran.write", "duckdb.damodaran_country")` does not contain `risk-free`.
- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_pipeline_diagram.py -k refresh` — expect FAIL.
- [ ] **Step 3: Edit `refresh.d2`.**
  - `damodaran.country` label: drop the `risk-free rate: wacc.xls ...` line; add `kept per country: total equity risk premium, country risk premium, rating, region` (no `ERP` abbreviation). Directive: `@symbol bot.ingest.damodaran.parse_country_tax_rates` only.
  - `risk_free` child becomes `{class: note}`: `|md No risk-free rate is imported: it comes per currency from config/currencies.yaml, curated by hand (ADR 0005 (Implemented)). |` with trailing `# @file config/currencies.yaml @symbol bot.reference.currencies.load_currency_table`.
  - `us_only`: `ADR 0005 (Not implemented)` → `ADR 0005 (Implemented)`; text otherwise unchanged (the US-only ingest is still true).
  - Edge `damodaran.write -> duckdb.damodaran_country`: `"country risk, tax rate"`.
- [ ] **Step 4: Run** the refresh tests and `python3 docs/pipeline/check.py` — the `parse_preheader_scalar` error is gone; only the source-hash / SVG errors remain (fixed in Task 5).
- [ ] **Step 5: Commit** `docs(#162): refresh board without the imported risk-free rate`.

### Task 2: Screen board — three coverage reasons, report counts, currency table

**Files:**
- Modify: `docs/pipeline/screen.d2` (`coverage_gate.gate`, `persist_and_report.report`, `ranking.second_pass`; add file node `currencies_yaml`; edges)
- Test: `tests/unit/test_pipeline_diagram.py`

**Interfaces:**
- Produces: top-level node key `currencies_yaml` (class `file`); Task 3 uses the same key and label on analyze.

- [ ] **Step 1: Write the failing tests**
  - `_REQUIRED_ENUMS["screen"] = {"bot.screener.engine.CoverageReason"}`.
  - `_REQUIRED_SYMBOLS["screen"]`: add `bot.screener.engine.CoverageReason`, `bot.reference.currencies.load_currency_table`, `bot.screener.engine.format_coverage_counts`.
  - `_REQUIRED_FILES["screen"]`: add `config/currencies.yaml`.
  - `_SCREEN_NODES`: add `("currencies_yaml", "file")`.
  - `_SCREEN_TEXT["currencies_yaml"] = ["absent or malformed", "every currency uncovered"]`.
  - `_SCREEN_TEXT["coverage_gate.gate"] = ["industry_unmapped", "benchmark_missing", "currency_uncovered", "leaves the universe", "before any rule runs", "one reason", "missing, or not in config/currencies.yaml"]`.
  - `_SCREEN_TEXT["persist_and_report.report"]`: add `"coverage gate exclusions per reason"`.
  - `_SCREEN_TEXT["ranking.second_pass"]`: add `"config/currencies.yaml"`.
  - New `test_screen_coverage_reasons_in_precedence_order`: in `_screen_block("coverage_gate.gate")`, `index("industry_unmapped") < index("benchmark_missing") < index("currency_uncovered")`, and the enum's member order `[r.value for r in CoverageReason]` equals that same order.
  - `test_screen_dcf_seam_and_rejections`: add `_edge_line(board, "currencies_yaml", "coverage_gate.gate")` and `_edge_line(board, "currencies_yaml", "ranking.second_pass")` not `None`.
- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_pipeline_diagram.py -k screen` — expect FAIL.
- [ ] **Step 3: Edit `screen.d2`.**
  - `coverage_gate.gate` (class `decision`) label, one reason per line in precedence order: `can the company be measured? the first reason that applies:` / `industry_unmapped: no Damodaran industry (industry_damodaran)` / `benchmark_missing: no sector benchmark row, or one without a weighted average cost of capital (WACC)` / `currency_uncovered: valuation currency (currency of the newest non-restated financials_annual row)` / `missing, or not in config/currencies.yaml` / `any reason: the company leaves the universe before any rule runs,` / `recorded as rejected with that one reason` / `(architecture decision record (ADR) 0006 (Implemented))`. Directives: `@symbol bot.screener.engine.run_screen @enum bot.screener.engine.CoverageReason @symbol bot.screener.engine.CoverageReason @file config/currencies.yaml @file docs/adr/0006-unmeasurable-companies-leave-the-universe.md`.
  - `currencies_yaml` file node: `"config/currencies.yaml, risk-free rate and nominal GDP growth per currency\nabsent or malformed: empty table, every currency uncovered"` with `# @file config/currencies.yaml @symbol bot.reference.currencies.load_currency_table`; GDP must be expanded at first use on the board (`gross domestic product (GDP)`).
  - `persist_and_report.report`: last line `coverage gate exclusions per reason` with `@symbol bot.screener.engine.format_coverage_counts` added to its directives.
  - `ranking.second_pass`: add line `rates of the valuation currency from config/currencies.yaml, the table the gate used`.
  - Edges: `duckdb.financials_annual -> coverage_gate.gate: "valuation currency"`, `currencies_yaml -> coverage_gate.gate: "covered currencies"`, `currencies_yaml -> ranking.second_pass: "currency table"`; `coverage_gate.gate -> persist_and_report.persist: "any reason: rejected with that reason"`; `coverage_gate.gate -> quality_gates` stays `"no reason: measured, every rule runs"`.
- [ ] **Step 4: Run** the screen tests — PASS (except SVG/hash).
- [ ] **Step 5: Commit** `docs(#162): screen board coverage reasons and currency table`.

### Task 3: Analyze board — per-currency terminal and revenue growth

**Files:**
- Modify: `docs/pipeline/analyze.d2` (`inputs.load`, `assumptions.growth`, `assumptions.terminal_growth`; file node `currencies_yaml`; edges)
- Test: `tests/unit/test_pipeline_diagram.py` (`_REQUIRED_CONSTS`, `_REQUIRED_SYMBOLS`, `_REQUIRED_FILES`, `_ANALYZE_NODES`, `_ANALYZE_TEXT`, `_valuation_input`)

- [ ] **Step 1: Write the failing tests**
  - `_REQUIRED_CONSTS["analyze"]`: remove `bot.valuator.assumptions._DEFAULT_GDP_NOMINAL`.
  - `_REQUIRED_SYMBOLS["analyze"]`: add `bot.reference.currencies.load_currency_table`, `bot.valuator.assumptions.load_assumption_inputs`.
  - `_REQUIRED_FILES["analyze"]`: add `config/currencies.yaml`.
  - `_ANALYZE_NODES`: add `("currencies_yaml", "file")`.
  - `_ANALYZE_TEXT["inputs.load"]`: add `"valuation currency"`.
  - `_ANALYZE_TEXT["assumptions.growth"]`: replace `"4%"` with `"nominal GDP growth of the valuation currency"`, add `"unresolved"`.
  - `_ANALYZE_TEXT["assumptions.terminal_growth"] = ["min(risk-free rate, nominal GDP growth)", "valuation currency", "config/currencies.yaml", "rule_based", "unresolved"]`.
  - New `test_analyze_has_no_gdp_constant`: `"4%"` not in `_check().visible(_analyze())`.
  - New `test_analyze_terminal_growth_reads_the_currency_table`: `_edge_line(_analyze(), "currencies_yaml", "assumptions.terminal_growth")` is not `None` and `_edge_line(_analyze(), "duckdb.damodaran_country", "assumptions.terminal_growth")` is `None`.
  - Fixture `_valuation_input`: give `AssumptionInputs` `valuation_currency="USD"` and `currency_rates=CurrencyRates(0.0395, 0.04, "s", "g", date(2026, 1, 1))` (`bot.reference.currencies.CurrencyRates`), so terminal growth resolves; the four `test_analyze_share_bounds_are_inclusive` cases then pass unchanged.
- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_pipeline_diagram.py -k analyze` — FAIL on the new text, PASS on share bounds.
- [ ] **Step 3: Edit `analyze.d2`.**
  - `inputs.load`: add line `valuation currency = currency of that newest non-restated row`; add `@symbol bot.valuator.assumptions.load_assumption_inputs`.
  - `assumptions.growth` (directive: drop the `@const`, add `@file config/currencies.yaml`): `1. manual ... → manual` / `2. high-growth with history, GDP known: straight line from the mean historical growth` / `to nominal gross domestic product (GDP) growth of the valuation currency → story_pattern` / `3. mean historical growth, repeated → historical_average` / `4. no history: nominal GDP growth each year → rule_based` / `no history and an uncovered currency: unresolved` / the two historical-growth lines unchanged.
  - `assumptions.terminal_growth` (directives `@symbol bot.valuator.assumptions._resolve_terminal_growth @file config/currencies.yaml @symbol bot.reference.currencies.load_currency_table`): `terminal growth g_terminal` / `1. manual → manual` / `2. valuation currency in config/currencies.yaml:` / `min(risk-free rate, nominal GDP growth) of that currency → rule_based` / `3. uncovered currency: unresolved, so the DCF cannot run`.
  - `currencies_yaml` file node as on screen.
  - Edges: delete `duckdb.damodaran_country -> assumptions.terminal_growth`; add `currencies_yaml -> assumptions.terminal_growth: "risk-free rate and nominal GDP growth of the valuation currency"`, `currencies_yaml -> assumptions.growth: "nominal GDP growth of the valuation currency"`, `inputs.load -> assumptions: "valuation currency"` (no edge leaves `inputs.load` for `assumptions` today: its five outgoing edges go to `inputs.region`, `sensitivity.grid`, `narrative_flags`, `verdict.mos`, `sanity_check.multiples`). Pin it in `test_analyze_terminal_growth_reads_the_currency_table`: `_edge_line(_analyze(), "inputs.load", "assumptions")` is not `None`.
- [ ] **Step 4: Run** analyze tests and `test_every_step_has_purpose_and_edges`, `test_every_directive_is_valid` — PASS.
- [ ] **Step 5: Commit** `docs(#162): analyze board per-currency growth rules`.

### Task 4: Portfolio board — ADR 0005 status and the currency table in marks

**Files:**
- Modify: `docs/pipeline/portfolio.d2` (`sync.value.adr_0005`, `marks.valuation`)
- Test: `tests/unit/test_pipeline_diagram.py` (`_PORTFOLIO_GAPS`, `test_portfolio_adr_0005_gap_is_current`, `_PORTFOLIO_TEXT`, `_REQUIRED_FILES["portfolio"]`)

- [ ] **Step 1: Write the failing tests**
  - `_PORTFOLIO_GAPS["sync.value.adr_0005"] = ["ADR 0005 (Implemented)", "§1–§3", "US-only"]`.
  - `test_portfolio_adr_0005_gap_is_current`: the gap exists iff the ADR's collapsed status section contains `"still not implemented"` (the sentence about §1–§3). Keep the node key `sync.value.adr_0005`.
  - `_PORTFOLIO_TEXT["marks.valuation"]`: add `"config/currencies.yaml"`, `"once per run"`.
  - `_REQUIRED_FILES["portfolio"]`: add `config/currencies.yaml`.
- [ ] **Step 2: Run** `-k portfolio` — FAIL.
- [ ] **Step 3: Edit `portfolio.d2`.**
  - `adr_0005` gap: `|md Gap: ADR 0005 (Implemented) covers its §4 only; its §1–§3 (one currency column per concept, prices converted into the valuation currency) are still not implemented. The universe is US-only, so every close in prices_daily is in USD and no real data exercises the cross-currency branch today. |`, trailing `# @file docs/adr/0005-currency-handling-and-valuation-currency.md`.
  - `marks.valuation`: add line `currency table from config/currencies.yaml, loaded once per run` and `@file config/currencies.yaml @symbol bot.portfolio.marks.mark_holdings` on that line.
- [ ] **Step 4: Run** the whole board test file and `test_adr_mentions_carry_their_status` — only SVG/hash failures may remain.
- [ ] **Step 5: Commit** `docs(#162): portfolio board ADR 0005 status`.

### Task 5: Render in CI and commit the render (run by the controller, not a subagent)

- [ ] Push the branch; `id=$(gh run list --branch "$(git branch --show-current)" --workflow pipeline-diagram --limit 1 --json databaseId --jq '.[0].databaseId')`; `gh run watch "$id" --exit-status || true`.
- [ ] On a d2 error: `gh run view "$id" --log-failed`, fix, push, repeat.
- [ ] `gh run download "$id" -n pipeline-render -D /tmp/render`; copy `/tmp/render/*.svg` and `/tmp/render/rendered.sha256` into `docs/pipeline/`; commit `docs(#162): render boards`; push; the run on that commit must be fully green.
- [ ] Locally: `uv run pytest -q`, `uv run ruff check . && uv run mypy src`, `python3 docs/pipeline/check.py` prints `0 errors`, and `uv run bot site --out /tmp/site --base-url /damodaran/` (the `site` workflow's steps; that workflow only runs on pushes to `master`).

## Assumptions

Technical decisions taken during plan review (no source dictates them; any choice satisfies #162):

1. **Board for `load_currency_table`.** Required on refresh (the issue's Task 1 asks the refresh note to cite it), screen and analyze. Rejected: requiring it on screen only.
2. **No-currency case on the gate.** The `currency_uncovered` line says "missing, or not in config/currencies.yaml" (`normalize_currency(None)` is `None`, never a table key). Rejected: leaving it implicit as in CONTEXT.md's "Uncovered currency".
3. **Empty-table failure mode** is stated on screen's `currencies_yaml` file node ("absent or malformed: empty table, every currency uncovered"), the board where it removes companies. Rejected: a separate note node.
4. **Edge `inputs.load -> assumptions: "valuation currency"`** is added on analyze. `load_valuation_input` hands the valuation currency to the assumptions through `load_assumption_inputs`. Rejected: an edge from `duckdb.financials_annual`, which would duplicate the existing "annual rows" edge.
5. **Report text paraphrased** ("coverage gate exclusions per reason") plus the `format_coverage_counts` citation, not the header string quoted verbatim. The citation keeps the board tied to the code. Rejected: quoting the header, whose exact wording would then change with every copy edit to it.
6. **Enum order as a guard.** The board draws `run_screen`'s `if` chain. The test also asserts that `CoverageReason`'s declaration order matches it, because the enum's docstring states the same precedence (`engine.py:54-63`) and `format_coverage_counts` prints in enum order.
7. **Intermediate commits are red** on the SVG and hash tests until Task 5. The issue expects this ("Its last step fails once, on the push before the SVGs are committed"). If CI rendering cannot be made to pass, the branch stays unmerged and nothing reaches the base branch.

## Grilling

- Rounds: 1 (the revisions were local text and test additions, not a different seam, so no second round).
- Questions: 18. Sources: ISSUE 4 (Q6 branch/BASE, Q9, Q13, Q17), CODE 12 (Q1, Q2, Q3, Q5, Q7, Q8, Q10, Q11, Q12, Q14, Q15, Q16), DOC 2 (Q4, Q18 ADR status sections). Unsourced: 0 spec ambiguities, 0 out of scope; 7 technical assumptions recorded above.
- Issues opened: none.
