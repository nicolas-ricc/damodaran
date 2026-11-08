# Manual override value ranges — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A numeric value in `config/assumptions/<TICKER>.yaml` outside the range its formula can take (e.g. `tax_rate: 25`) is refused by `load_override` with the same `ValueError` shape as the type check, instead of reaching the DCF under a `manual` label.

**Architecture:** One module-level table `_OVERRIDE_RANGES` of a small frozen dataclass `_Range` sits next to `_OVERRIDE_PATH_KEYS` in `src/bot/valuator/assumptions.py`. `_check_override_values` keeps its single pass in file order: for each key, the finiteness check first, then the range check of that same key. The example file, the analyze board and its test learn the new refusal reason.

**Tech Stack:** Python 3.12, PyYAML, pytest, DuckDB, ruff, mypy --strict, d2 v0.9.0 (tala layout).

**Spec:** GitHub issue #292 (`gh issue view 292 --repo nicolas-ricc/damodaran`). Its six "Decisions (taken by the planner; do not reopen)" and its six acceptance criteria are binding. Story context: #64 (plan comment, item 2).

## Global Constraints

- Ranges (decision 1), exactly:
  - `tax_rate`, `probability_of_bankruptcy`, `equity_weight`, `debt_weight`: `0 <= x <= 1` → phrase `between 0 and 1`
  - `cost_of_equity`, `pretax_cost_of_debt`: `0 < x < 1` → `greater than 0 and less than 1`
  - `terminal_growth`: `-1 < x < 1` → `greater than -1 and less than 1`
  - `sales_to_capital`: `x > 0` → `greater than 0`
  - `distress_value_per_share`: `x >= 0` → `at least 0`
  - `operating_margin`: every element `x < 1` → `less than 1 (every element)`
  - `revenue_growth`: every element `x > -1` → `greater than -1 (every element)`
- Error text: `f"{override_path}: {key} must be {phrase}, got {value!r}"`; for a path key `value` is the whole value as written (the list, or the scalar when a scalar was given).
- Range check runs only after the same key passed the finiteness check, on `float(x)` (numeric strings included). One pass, file order: the first bad key in the file wins, whether its fault is type or range.
- Unchanged: `_resolve_weights` partition check, the `terminal_growth < wacc` check in `dcf.py`, the story-key ranges in `hypergrowth.py`, `config/assumptions/README.md` (it does not list the numeric keys' constraints).
- Board text has no digits outside words: the new reason is exactly `a numeric value outside its range`.
- `uv run ruff check . && uv run mypy src && uv run pytest -q` green; `python3 docs/pipeline/check.py` passes.

## Assumptions (declared)

- **`_Range` as a frozen dataclass, not a 4-tuple.** Decision 1 allows either; the dataclass carries `low: float | None`, `high: float | None`, `low_inclusive: bool`, `high_inclusive: bool` plus two methods (`contains(x: float) -> bool`, `phrase() -> str`) so the phrase cannot drift from the bounds. Path-ness stays in `_OVERRIDE_PATH_KEYS`; the ` (every element)` suffix is appended by `_check_override_values` for path keys.
- **Phrase derivation.** Both bounds inclusive → `between {low} and {high}`. Otherwise the present bounds joined by ` and `: low inclusive `at least {low}`, exclusive `greater than {low}`; high inclusive `at most {high}`, exclusive `less than {high}`. Numbers formatted with `:g` (`0`, `1`, `-1`). This yields exactly the seven phrases of decision 2.
- **Every numeric key has a range.** `set(_OVERRIDE_RANGES) == _OVERRIDE_KEYS - _OVERRIDE_TEXT_KEYS - _OVERRIDE_STORY_KEYS` is pinned by a test, so a new numeric key cannot silently skip the range check.
- **The example-file test lives in `tests/unit/test_valuator_assumptions.py`** (none exists today; `test_valuator_hypergrowth.py::test_example_file_documents_every_story_key` only greps for names). It uncomments every top-level numeric line (`# <key>: ...` at column 0 with `<key>` in `_OVERRIDE_RANGES`), keeps everything else (the `notes:` line is already active), writes it to `tmp_path / "EX.yaml"`, and asserts `load_override` returns all eleven numeric keys. The repo root is `Path(__file__).resolve().parents[2]`.
- **Scalar path key message.** Decision 2 fixes ` (every element)` for the two path keys without distinguishing scalar from list; a scalar path value broadcasts to every year (`assumptions.py:846-848`), so the suffix stays true and is used for both forms (rejected: a separate scalar phrase, which the issue does not list).
- **Every phrase is pinned.** `phrase()` is derived, so a direct test asserts the phrase of every entry in `_OVERRIDE_RANGES` against the seven literals of decision 2 (rejected: storing the phrase as a literal field, which could drift from the bounds).
- **The message shows the parsed YAML value.** Decision 2 fixes `got {value!r}`; a quoted `'25'` therefore reports `got '25'`, pinned in the message test.
- **Stage-3 tests are authoritative.** Pipeline stage 3 writes the Task 1-3 tests with the names and assertions listed here, before any implementation; an implementer who finds them already present keeps them as written.
- **Board re-render is local.** `PATH=/usr/local/lib/d2/d2-v0.9.0/bin:$PATH docs/pipeline/build.sh` works here (tala layout verified). Only `.svg` files whose bytes changed and `rendered.sha256` are committed; PNGs are git-ignored.

## Review Focus

- A percent written as a quoted or exponent string (`tax_rate: "25"`, `tax_rate: 2.5e1`): refused like `25`. Test: parametrised case `tax_rate: '25'` in Task 1.
- A scalar path key out of range (`operating_margin: 1.0`, not a list): refused, `got 1.0`. Test: parametrised case in Task 1.
- An integer boundary (`tax_rate: 1`, `distress_value_per_share: 0` as YAML ints): accepted. Covered by the Task 1 boundary test (`tax_rate: 1`, `distress_value_per_share: 0`).
- A list with one bad element in the middle (`revenue_growth: [0.1, -1.5, 0.1]`): refused and the message shows the whole list. Test: Task 1 asserts `got \[0\.1, -1\.5, 0\.1\]` in the message.
- The screener's second-pass DCF and `bot analyze` both resolve through `load_override` (`analysis.py:898`, `assumptions.py:914`), so one check covers both; no extra test.

---

### Task 1: Range table and range check in `_check_override_values`

**Files:**
- Modify: `src/bot/valuator/assumptions.py` (next to `_OVERRIDE_PATH_KEYS` ~line 724; `load_override` docstring ~line 751; `_check_override_values` ~line 810)
- Test: `tests/unit/test_valuator_assumptions.py` (after `test_override_numeric_string_still_applies`)

**Interfaces:**
- Produces: `_Range` (frozen dataclass, fields above, `contains(x: float) -> bool`, `phrase() -> str`); `_OVERRIDE_RANGES: dict[str, _Range]` keyed by the eleven numeric keys. Task 2 imports `_OVERRIDE_RANGES` (as `assumptions_mod._OVERRIDE_RANGES`) and `load_override`.

- [ ] **Step 1: Write the failing tests** (they may already exist from pipeline stage 3; keep them).
  - `test_override_value_outside_its_range_is_refused`, parametrised `(body, key)` with ids, over at least: `tax_rate: 25`, `tax_rate: '25'`, `probability_of_bankruptcy: 1.5`, `equity_weight: -0.1`, `debt_weight: 1.2`, `cost_of_equity: 0`, `pretax_cost_of_debt: 1`, `terminal_growth: -1`, `sales_to_capital: 0`, `distress_value_per_share: -1`, `operating_margin: [0.2, 1.0]`, `operating_margin: 1.0`, `revenue_growth: -1`. Body: `_seed_full_sector(conn)`, `_write_override`, `pytest.raises(ValueError, match=rf"ACME\.yaml: {key} must be")` around `resolve_assumptions("ACME", conn, override_path=override)`.
  - `test_override_range_error_names_the_range_and_the_value`: `tax_rate: 25` → match `r"ACME\.yaml: tax_rate must be between 0 and 1, got 25$"`; `tax_rate: '25'` → match `r"got '25'$"`; `revenue_growth: [0.1, -1.5, 0.1]` → match `r"revenue_growth must be greater than -1 \(every element\), got \[0\.1, -1\.5, 0\.1\]"`.
  - `test_override_boundary_value_is_accepted`, parametrised `(body, field, expected)`: `tax_rate: 0` → `tax_rate`, `0.0`; `tax_rate: 1` → `1.0`; `probability_of_bankruptcy: 0` → `0.0`; `distress_value_per_share: 0` → `0.0`; `operating_margin: -0.5` → `(-0.5,) * 10`; `revenue_growth: 2.0` → `(2.0,) * 10`. Asserts `getattr(result, field).value == pytest.approx(expected)` and `.source is AssumptionSource.MANUAL`.
  - `test_override_type_and_range_errors_keep_file_order`, parametrised: `"tax_rate: [0.2]\ncost_of_equity: 5\n"` → `tax_rate`; `"cost_of_equity: 5\ntax_rate: abc\n"` → `cost_of_equity`. Match `rf"ACME\.yaml: {key} must be"`.
  - `test_override_range_phrases`: `{k: r.phrase() for k, r in assumptions_mod._OVERRIDE_RANGES.items()}` equals the per-key phrase of Global Constraints, without the ` (every element)` suffix (that is added by the check).
  - `test_every_numeric_override_key_has_a_range`: `set(assumptions_mod._OVERRIDE_RANGES) == assumptions_mod._OVERRIDE_KEYS - assumptions_mod._OVERRIDE_TEXT_KEYS - assumptions_mod._OVERRIDE_STORY_KEYS`.
- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_valuator_assumptions.py -k "range or boundary or file_order"`. Expected: the refusal cases, the message test, the `cost_of_equity` ordering case and the table test FAIL (today `tax_rate: 25` resolves `MANUAL`; `_OVERRIDE_RANGES` does not exist); boundary cases PASS.
- [ ] **Step 3: Implement** `_Range` and `_OVERRIDE_RANGES` (values from Global Constraints) next to `_OVERRIDE_PATH_KEYS`, each with a `#:` comment in the file's style. In `_check_override_values`, after the existing `if not ok: raise`, look up `_OVERRIDE_RANGES[key]`; for a path key check every element of the list (or the scalar), else the scalar; on failure raise with `phrase()` plus ` (every element)` for path keys. Update the function docstring ("not a finite number, or outside its range") and add "out-of-range values" to the refusal list in `load_override`'s docstring.
- [ ] **Step 4: Run** `uv run pytest -q tests/unit/test_valuator_assumptions.py tests/unit/test_valuator_hypergrowth.py` → all pass, including unchanged `test_every_documented_override_key_is_accepted`, `test_partial_weight_override_is_honoured`, `test_override_numeric_string_still_applies`, `test_override_names_the_first_bad_value_in_file_order`. `uv run ruff check . && uv run mypy src` clean.
- [ ] **Step 5: Commit** `feat(valuator): refuse manual override values outside their range (#292)`.

### Task 2: Ranges in the example file, and the example loads

**Files:**
- Modify: `config/assumptions/_EXAMPLE.yaml.example` (the eleven numeric lines, lines 2-12)
- Test: `tests/unit/test_valuator_assumptions.py`

**Interfaces:**
- Consumes: `assumptions_mod._OVERRIDE_RANGES`, `load_override(override_path: Path | None) -> dict[str, Any]` from Task 1.

- [ ] **Step 1: Write the failing test** `test_example_file_with_every_numeric_line_uncommented_loads(tmp_path)`: build the text as described in Assumptions, `load_override(tmp_path / "EX.yaml")`, assert `set(_OVERRIDE_RANGES) <= set(result)`. Also assert, for each numeric key, that its example line's trailing comment contains the range written in the story-key style (see Step 3 table) — this is what fails today.
- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_valuator_assumptions.py -k example_file` → FAIL on the comment assertion (the load part passes already: every example value is in range).
- [ ] **Step 3: Edit the trailing comments**, appending the range after a comma, same style as the story block: `revenue_growth` `cada valor > -1`; `operating_margin` `cada valor < 1`; `sales_to_capital` `> 0`; `terminal_growth` `-1 < x < 1, y menor que el WACC`; `cost_of_equity`, `pretax_cost_of_debt` `0 < x < 1`; `equity_weight`, `debt_weight`, `tax_rate`, `probability_of_bankruptcy` `0..1`; `distress_value_per_share` `>= 0`. The test's per-key expected substring is exactly these strings. Keep the comment column aligned with the existing lines.
- [ ] **Step 4: Run** `uv run pytest -q tests/unit/test_valuator_assumptions.py tests/unit/test_valuator_hypergrowth.py` → pass.
- [ ] **Step 5: Commit** `docs(#292): the override example states the range of each numeric key`.

### Task 3: The analyze board lists the range refusal

**Files:**
- Modify: `docs/pipeline/analyze.d2:24` (node `override`)
- Modify: `tests/unit/test_pipeline_diagram.py` (`_ANALYZE_TEXT["override"]`, ~line 1620)
- Regenerated: `docs/pipeline/analyze.svg` (and any other `.svg` whose bytes change), `docs/pipeline/rendered.sha256`

- [ ] **Step 1: Write the failing test**: add `"a numeric value outside its range"` to `_ANALYZE_TEXT["override"]`.
- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_pipeline_diagram.py` → FAIL naming the missing phrase.
- [ ] **Step 3: Edit the node label**: the finite-number line becomes `a numeric value that is not a finite number (or a non-empty list of them for revenue_growth / operating_margin), a numeric value outside its range,` (same line, right after the finite-number reason, no digits).
- [ ] **Step 4: Re-render and check**: `PATH=/usr/local/lib/d2/d2-v0.9.0/bin:$PATH docs/pipeline/build.sh`, then `python3 docs/pipeline/check.py` → passes; `uv run pytest -q tests/unit/test_pipeline_diagram.py` → passes. `git status --short docs/pipeline` shows `analyze.d2`, `analyze.svg`, `rendered.sha256`; commit every `.svg` the render changed as it came out (`check.py:192` hashes only the `*.d2` sources, and CI re-renders with the pinned version and fails on a stale `rendered.sha256`).
- [ ] **Step 5: Commit** `docs(#292): the analyze board refuses an override value outside its range`.

### Final: full suite

- [ ] `uv run ruff check . && uv run mypy src && uv run pytest -q` → green.

## Grilling

One round (the revision added assertions inside existing steps and four declared assumptions; no step added or removed, same seam), griller model `fable`. 15 questions.

| # | Source | Answer |
|---|--------|--------|
| 1 | ISSUE | Criteria 1-3 → Task 1; criterion 4 → Task 1 Step 4 + Task 2; criterion 5 (board, `_ANALYZE_TEXT`, svg, `check.py`) → Task 3; criterion 6 → Final. Task 3 is decision 5 of the issue. |
| 2 | CODE + ISSUE | `assumptions.py:702-731` defines `_OVERRIDE_KEYS`, `_OVERRIDE_TEXT_KEYS`, `_OVERRIDE_STORY_KEYS`; the difference is the issue's eleven numeric keys ("The numeric keys are: ..."). |
| 3 | CODE | `_check_override_values` (`assumptions.py:810-829`) only calls `is_finite_number` (`hypergrowth.py:37-49`, returns a bool), so the range check recomputes `float()`. It runs inside `load_override`, before `_override_path_field` broadcasts a scalar (`assumptions.py:838-848`). |
| 4 | CODE + DOC | Screener second pass catches `ValueError` and falls back (`screener/engine.py:102,163`); `bot analyze` prints and goes on (`cli.py:486-506`; `analyze.d2:24` "any invalid file: cannot value, exit code 1, and the batch goes on"). No `<TICKER>.yaml` is committed in `config/assumptions/` (only `README.md`, `_EXAMPLE.yaml.example`); the refusal is the issue's goal. |
| 5 | ISSUE | Decision 2 fixes `got {value!r}`; the parsed value's repr is shown. `got '25'` added to the message test (assumption). |
| 6 | CODE | `assumptions.py:821` `bool(value) and all(...)`; test id `empty-path` (`tests/unit/test_valuator_assumptions.py:418`). |
| 7 | CODE | `hypergrowth.py:42` rejects `bool`; test id `bool` (`tax_rate: true`, test file :412). |
| 8 | ISSUE + assumption | Decision 2 lists the suffix per path key; scalar form declared under Assumptions. |
| 9 | NO SOURCE → technical assumption | `test_override_range_phrases` added. |
| 10 | CODE | `load_override` (`assumptions.py:750-779`) runs only the key, value and story checks; `_resolve_weights` runs in `resolve_assumptions`. Example weights 0.85 + 0.15. No file-name check. |
| 11 | CODE | `_EXAMPLE.yaml.example` lines 2-12 are `# <key>: ...` at column 0; story lines are indented (`#   year1_growth`); `notes:` (last line) is active. |
| 12 | CODE | `check.py:192` hashes `*.d2` only, `:226` flags a stale stamp; `.github/workflows` pipeline-diagram re-renders with `D2_VERSION` and runs `check.py`. Revert rule dropped. |
| 13 | NO SOURCE → technical assumption | Stage-3 tests are authoritative (Assumptions). |
| 14 | CODE + DOC | `#:` comments: `assumptions.py:699-735`; digit rule: `docs/pipeline/README.md:78`; Spanish comments: every comment of `_EXAMPLE.yaml.example`. |
| 15 | ISSUE | The goal is the refusal; no permissive mode is asked for. The branch is squash-merged as one commit, so Tasks 1-2 land together. |

Sources: ISSUE 5, CODE 10, DOC 2 (some answers cite two). Assumptions added: 4 (scalar path message, phrase test, parsed-value repr, stage-3 tests authoritative). Spec ambiguities: 0. Follow-up issues opened: 0.

Result: `ok`.
