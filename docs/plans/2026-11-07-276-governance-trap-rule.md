# auditor_changes_and_late_filings trap detector — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-add the spec §6.4 governance trap detector `auditor_changes_and_late_filings`, fed by the auditor-change and late-filing rows of `filings_log`, in the three presets, the screen engine (screen and portfolio marks), the screen boards and the lesson table.

**Architecture:** A pure rule over three new `CompanyData` fields (`as_of`, `auditor_change_dates`, `late_filing_dates`); the engine fills them from one bulk query over `filings_log`, classified with the `bot.ingest.sec_edgar` classifiers, and sets them to `None` outside the US dataset region so the rule skips (and a skipped trap detector stays eliminatory, ADR 0006). Presets, golden, boards and lesson follow because tests pin them to the rule list.

**Tech Stack:** Python 3.12, DuckDB, pytest, mypy --strict, ruff; d2 v0.9.0 boards (`docs/pipeline/build.sh`, `check.py`); the lesson's `check.py`.

**Spec:** GitHub issue #276 (`gh issue view 276 --repo nicolas-ricc/damodaran`). Its eleven "Decisions (taken by the planner; do not reopen)" and its acceptance criteria are binding; exact strings (reasons, labels, lesson row) are copied from there. Story context: #61.

## Global Constraints

- Rule: `class AuditorChangesAndLateFilings(Rule)` in `src/bot/screener/rules.py`, right after `ShareCountNotDiluting`; `name = "auditor_changes_and_late_filings"`; `__init__(self, window_years: int = 2)`; module constant `DAYS_PER_YEAR = 365`.
- Reasons, verbatim: skip `"no SEC filing history: auditor changes and late filings are unknown outside the US"`; auditor `f"auditor change reported on {newest:%Y-%m-%d} (8-K item 4.01), within the last {window_years} years"`; late `f"late-filing notice on {newest:%Y-%m-%d} (NT 10-K/10-Q), within the last {window_years} years"`; pass `f"no auditor change or late-filing notice in the last {window_years} years of SEC filings"`. `newest` is the newest *recent* date of that kind.
- Verdict order: both `None` → skip; recent auditor change → fail; recent late filing → fail; else pass. One `None` field is treated as empty.
- Recent: `company.as_of is None` or `(company.as_of - d).days <= DAYS_PER_YEAR * window_years`. A date after `as_of` (negative days) counts as recent.
- `CompanyData` new fields, appended after `operating_cashflow` in the trap-detection group: `as_of: date | None = None`, `auditor_change_dates: tuple[date, ...] | None = None`, `late_filing_dates: tuple[date, ...] | None = None`, each with a docstring line as in decision 2. `from datetime import date` added to `types.py`.
- Engine: `_GovernanceFilings(auditor_changes: tuple[date, ...], late_filings: tuple[date, ...])` frozen dataclass; `_load_governance_filings(conn) -> dict[str, _GovernanceFilings]`; `build_company_data(..., governance: _GovernanceFilings | None = None)`; `run_screen` and `load_holding_inputs` load the map once each.
- Presets: the three files append `- name: auditor_changes_and_late_filings` / `params: {window_years: 2}` with comment `# 8-K item 4.01 or NT 10-K/10-Q in the last 2 years`, in the same YAML style as their neighbours.
- No change to `docs/pipeline/models/screen.tla`, `docs/plano/`, lesson prose paragraphs, `tests/e2e/test_pipeline.py`, `tests/integration/test_screen_cli.py`, `tests/unit/test_portfolio_marks.py`.
- `uv run ruff check . && uv run mypy src && uv run pytest -q` green; `python3 docs/pipeline/check.py` and `python3 docs/leccion/check.py` exit 0.

## Assumptions (declared)

- **Acronym expansion on the boards.** `tests/unit/test_pipeline_diagram.py::test_acronyms_are_expanded` requires `SEC` and `NT` to share their first-use line with their expansion ("Securities and Exchange Commission", "notification of late filing"). Neither board expands them today, so the decided labels of decisions 7 and 8 fail that test verbatim. The labels keep every decided word and add only the expansions: `SEC` becomes `Securities and Exchange Commission (SEC)` on its first use and `NT` is preceded by `a notification of late filing` (the wording `refresh.d2` already uses), e.g. screen.d2 line 1 `no auditor change (8-K item 4.01) and no notification of late filing (NT 10-K, NT 10-Q)`, line 2 `in the last 2 years of Securities and Exchange Commission (SEC) filings, read from filings_log`. Rejected: adding the tokens to `_ACRONYMS_EXEMPT` (a weakening the AC forbids).
- **Dates.** DuckDB returns `DATE` as `datetime.date`; `_load_governance_filings` coerces with `bot.ingest.base.coerce_date` only if a value is not already a `date` (mirrors `_load_latest_prices`).
- **`as_of` source.** `CompanyData.as_of` is the `as_of` argument `build_company_data` already receives (the newest market-cap row's date, `_PriceSnapshot.as_of`), as decision 4 says.
- **Lesson line numbers.** Engine citations in `docs/leccion/index.html` already drift (warnings only); the rule citation gets its exact line; other lines this change moves (`rules.py` none, since the class is appended last; `engine.py` ones) are refreshed so `check.py` prints no new warning.

## Review Focus

1. A filing dated after `as_of` (prices older than the filings fetch): counts as recent, fails. Pinned in Task 1 (`test_auditor_rule_future_filing_counts_as_recent`).
2. A filing exactly `DAYS_PER_YEAR * window_years` days before `as_of`: recent (inclusive bound). Pinned in Task 1 (`test_auditor_rule_window_bound_is_inclusive`).
3. Several adverse dates, some old: the reason names the newest recent one. Pinned in Task 1 (`test_auditor_rule_reason_names_newest_date`).
4. Duplicate rows for one date (an `8-K` and an `8-K/A` the same day, or two sources): one date in the tuple. Pinned in Task 2 (`test_governance_dates_deduplicated_and_sorted`).
5. A held ticker in the portfolio-marks path gets the same tuples as the screen. Pinned in Task 2 (`test_load_holding_inputs_carries_governance_dates`).

## Acceptance criteria → tasks

| Issue item | Task |
|---|---|
| AC 1 (registry, rule tests), decisions 1, 3, 10; `CompanyData` fields (decision 2) | Task 1 |
| AC 2 (engine tests incl. `run_screen` rejection), decisions 4, 11 | Task 2 |
| AC 3 (presets, config tests), AC 4 (golden), decisions 5, 6 | Task 3 |
| AC 5 (boards, view.js, render, board tests), AC 6 (lesson), decisions 7, 8, 9 | Task 4 |
| AC 7 (untouched suites), AC 8 (lint + suite) | Final verification |

Stage 3 of the pipeline writes every test named below first, failing, in one commit; each task then makes its own tests pass.

---

### Task 1: The rule and its `CompanyData` inputs

**Files:**
- Modify: `src/bot/screener/types.py` (trap-detection group, imports)
- Modify: `src/bot/screener/rules.py` (after `ShareCountNotDiluting`)
- Test: `tests/unit/test_screener_trap_detection.py`, `tests/unit/test_screener_rules.py`

**Interfaces:**
- Produces: `CompanyData.as_of`, `.auditor_change_dates`, `.late_filing_dates`; `AuditorChangesAndLateFilings(window_years: int = 2)`; `bot.screener.rules.DAYS_PER_YEAR = 365`.

- [ ] **Step 1: Tests** (`as_of = date(2026, 5, 29)` in all but the `as_of=None` case):
  - `test_auditor_rule_registered`: `get_rule("auditor_changes_and_late_filings") is AuditorChangesAndLateFilings`.
  - `test_auditor_rule_skips_without_filing_history`: both `None` → `skipped is True`, `passed is False`, reason equals the skip string.
  - `test_auditor_rule_fails_on_recent_auditor_change`: auditor date 2025-05-29, late `()` → `passed is False`, `skipped is False`, `"auditor change" in reason`, `"2025-05-29" in reason`.
  - `test_auditor_rule_passes_on_old_auditor_change`: 2023-05-29 → passed.
  - `test_auditor_rule_fails_on_recent_late_filing`: late 2025-05-29 → fail, `"late-filing" in reason`.
  - `test_auditor_rule_passes_with_empty_history`: both `()` → passed, reason equals the pass string with `2`.
  - `test_auditor_rule_without_as_of_counts_any_filing`: `as_of=None`, auditor `(date(2010,1,1),)` → fail.
  - `test_auditor_rule_wider_window_catches_old_change`: `window_years=5`, 2023-05-29 → fail.
  - `test_auditor_rule_one_field_none_other_recent_fails`: auditor `None`, late recent → fail, not skipped.
  - Review Focus 1–3 tests as named above (future date 2026-06-15 → fail; exactly 730 days before → fail; auditor dates `(2019-01-01, 2025-01-10, 2025-11-03)` → reason contains `2025-11-03`).
  - In `test_screener_rules.py`, replace `test_auditor_rule_is_gone_and_fails_loudly` with `test_auditor_rule_is_registered`: name in `registered_rules()` and `get_rule(...) is AuditorChangesAndLateFilings`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_screener_trap_detection.py tests/unit/test_screener_rules.py -q` → FAIL (import error).
- [ ] **Step 3: Implement** the fields and the rule. Docstring states: data gap is a skip, never a pass; the skip is eliminatory (ADR 0006); a US company imported through FMP sees empty tuples and passes vacuously (story #61 decision 5).
- [ ] **Step 4: Run** the same command → PASS; `uv run mypy src` clean.
- [ ] **Step 5: Commit** `feat(#276): auditor_changes_and_late_filings rule`.

### Task 2: Engine feeds the rule for the screen and the portfolio marks

**Files:**
- Modify: `src/bot/screener/engine.py`
- Test: `tests/unit/test_screener_engine.py`

**Interfaces:**
- Consumes: Task 1 fields; `bot.ingest.sec_edgar.AUDITOR_CHANGE_FORMS`, `LATE_FILING_FORMS`, `is_auditor_change(form, items)`, `is_late_filing(form)`.
- Produces: `_GovernanceFilings`, `_load_governance_filings(conn)`, `build_company_data(..., governance=...)`.

- [ ] **Step 1: Tests** (helper `_seed_filing(conn, ticker, form, filing_date, items=None, source="sec_edgar")` inserting into `filings_log`; companies seeded with `_seed_one` (TST, "United States", price 2026-05-29)):
  - `test_build_company_data_reads_auditor_change`: `8-K` items `'4.01,9.01'` on 2025-11-03 → `auditor_change_dates == (date(2025,11,3),)`, `late_filing_dates == ()`, `as_of == date(2026,5,29)` (built from `_load_governance_filings(conn).get("TST")` and the price snapshot as `run_screen` does).
  - `test_build_company_data_ignores_plain_8k_and_10q`: `8-K` items NULL + `10-Q` → both `()`.
  - `test_build_company_data_reads_late_filing`: `NT 10-Q` → in `late_filing_dates`.
  - `test_build_company_data_governance_none_outside_us`: the Germany company of `test_build_company_data_roic_uses_country_tax_rate`, with an `NT 10-K` row → both fields `None`.
  - `test_build_company_data_without_governance_is_empty_in_us`: `governance=None`, US → both `()`.
  - `test_governance_dates_deduplicated_and_sorted`: `8-K` 4.01 and `8-K/A` 4.01 same day, plus an older `8-K` 4.01 from source `fmp` → two dates, ascending.
  - `test_load_holding_inputs_carries_governance_dates`: same tuples as the screen path for TST.
  - `test_run_screen_rejects_a_company_with_a_recent_late_filing`: `_seed_sector`, `_seed_company(conn, "TST")`, `NT 10-K` on 2026-02-27 → `"TST"` in `{r.ticker for r in result.rejected}` and `"auditor_changes_and_late_filings"` in its `failed_gates`; with `_value_preset()`, `valuator=None`. Also assert the company is a candidate without the row (control, separate DB via a second test or inline before inserting).
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_screener_engine.py -q` → new tests FAIL.
- [ ] **Step 3: Implement.** Query: `SELECT ticker, filing_type, filing_date, items FROM filings_log WHERE filing_type IN (...)` with the union of the two form sets as parameters; classify in Python; `sorted(set(...))` per kind. In `build_company_data`, resolve the region once into a local and reuse it for `CompanyData.region`.
- [ ] **Step 4: Run** the engine tests, `tests/unit/test_portfolio_marks.py`, `tests/integration/test_screen_cli.py` → PASS.
- [ ] **Step 5: Commit** `feat(#276): engine feeds governance filings to the screen and marks`.

### Task 3: Presets and golden

**Files:**
- Modify: `config/presets/damodaran_value.yaml`, `deep_value.yaml`, `qarp.yaml`
- Modify: `tests/unit/test_screener_config.py` (`== 6`)
- Regenerate: `tests/fixtures/screener/second_pass_shortlist.golden`

- [ ] **Step 1:** `test_preset_lists_all_three_layers` pins `len(config.trap_detection.rules) == 6`, plus `config.trap_detection.rules[-1].name == "auditor_changes_and_late_filings"` and its params `{"window_years": 2}` (use the rule-spec attributes the config module exposes).
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_screener_config.py tests/unit/test_screener_extra_presets.py -q` → FAIL.
- [ ] **Step 3:** Append the rule to the three presets.
- [ ] **Step 4:** Run the golden test → FAIL; regenerate with the snippet in the golden test's docstring; `git diff` of the golden must only append `'auditor_changes_and_late_filings'` to each `passed_gates` tuple.
- [ ] **Step 5: Run** config, extra-presets, golden, e2e tests → PASS. Commit `feat(#276): the three presets run the governance trap detector`.

### Task 4: Boards and lesson

**Files:**
- Modify: `docs/pipeline/screen.d2`, `screen-traps.d2`, `pipeline.d2`, `models/screen.view.js`
- Re-render: `docs/pipeline/*.svg`, `*.png`, `rendered.sha256` (via `build.sh`)
- Modify: `tests/unit/test_pipeline_diagram.py`, `tests/unit/test_pipeline_subboards.py` (only the edits of decisions 7 and 8)
- Modify: `docs/leccion/index.html`

- [ ] **Step 1:** Test edits: `_REQUIRED_TABLES["screen"]` gains `"filings_log"`; `_SCREEN_NODES` swaps `("trap_detection.auditor", "gap")` for `("trap_detection.auditor_changes_and_late_filings", "decision")`; `test_screen_gap_notes` drops the auditor assertion; `_SCREEN_TEXT["screen-traps"]` gains `"2 years"`. Run the four pipeline/lesson test files → FAIL (rule missing from sub-board, lesson param missing).
- [ ] **Step 2:** Board edits of decisions 7 and 8 with the acronym expansions of the Assumptions section; `screen-traps.d2` reaches exactly 24 edges; `"the five trap detectors pass"` → `"the six trap detectors pass"` (three edges + `screen.view.js`).
- [ ] **Step 3:** `PATH=/usr/local/lib/d2/d2-v0.9.0/bin:$PATH docs/pipeline/build.sh`; `python3 docs/pipeline/check.py` → exit 0.
- [ ] **Step 4:** Lesson row of decision 9 verbatim after `share_count_not_diluting`; citation `<li>` for `bot.screener.rules.AuditorChangesAndLateFilings` with its real line after `ShareCountNotDiluting`'s; refresh `engine.py` citation lines this change moved. `python3 docs/leccion/check.py` → exit 0.
- [ ] **Step 5: Run** `uv run pytest tests/unit/test_pipeline_diagram.py tests/unit/test_pipeline_subboards.py tests/unit/test_pipeline_models.py tests/unit/test_leccion.py -q` → PASS. Commit `docs(#276): screen boards and lesson table show the governance trap detector`.

### Final verification

- [ ] `uv run ruff check . && uv run mypy src && uv run pytest -q` → green.
