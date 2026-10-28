# Flex statement redaction and type summary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `.agents/skills/subagent-driven-development/SKILL.md` to implement this plan task-by-task; implementers write code with `.agents/skills/test-driven-development/SKILL.md`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two pure functions over a Flex statement XML string, `redact_statement` and `summarize_statement`, in a new module `src/bot/ingest/ibkr_flex_capture.py`, plus a public per-element `parse_flex_row` in `ibkr_flex.py` that both the parser and the summary share.

**Architecture:** `parse_flex_row(el)` is extracted from the two loop bodies of `parse_flex_statement` (behaviour, order and log lines unchanged). The capture module walks the `ElementTree` once to rewrite account ids and money/quantity attributes (`redact_statement`), and once to count types and ask `parse_flex_row` which rows the parser keeps (`summarize_statement`). No network, settings or disk; a later task (#139) wires them into `bot flex-capture`.

**Tech Stack:** Python 3.12, `xml.etree.ElementTree`, `decimal`, `dataclasses`, `json`, pytest, mypy --strict, ruff.

**Spec:** GitHub issue #138 (nicolas-ricc/damodaran), "[M5.7b-1] Pure Flex statement redaction and type summary over the synthetic sample"; story context in #110 (plan comment, decisions 3, 5, 6).

## Global Constraints

- New module: `src/bot/ingest/ibkr_flex_capture.py`. It must not contain the string `FlexClient` anywhere, not even in a comment (`tests/unit/test_seam_enforcement.py`).
- `tests/unit/test_ibkr_flex_parser.py` passes unchanged; `parse_flex_statement(sample)` returns the same 5 `action_id`s in the same order (all `CorporateAction` rows first, then all `CashTransaction` rows).
- `REDACTED_ACCOUNT = "U0000000"`.
- Non-`FlexQueryResponse` root: `ValueError(f"expected a FlexQueryResponse, got {root.tag}")` (same wording as the parser) in `redact_statement` and `summarize_statement`.
- `parse_flex_row` on any tag other than `CorporateAction`/`CashTransaction`: `ValueError(f"not a Flex row: {el.tag}")`.
- Redacted output is exactly `'<?xml version="1.0" encoding="UTF-8"?>\n'` + fixed one-paragraph XML comment + `"\n"` + `ET.tostring(root, encoding="unicode")` + `"\n"`. Nothing that varies between runs.
- Nothing touches the network, settings or disk.
- `uv run ruff check . && uv run mypy src && uv run pytest -q` green. Commits: Conventional Commits with `(#138)` scope.

## Review Focus

1. A money attribute holding `NaN`/`Infinity`/`sNaN` parses as a `Decimal` but has no digits: `_fake_number` must return it unchanged, not crash. Test in Task 2 (`test_fake_number_leaves_non_finite_unchanged`).
2. Exponent notation (`1E+3`) parses as `Decimal` but has no `.` in its text: it must still be replaced (no real amount left behind) with an integer-shaped fake of the same digit count (`1000`). Test in Task 2 (parametrised).
3. A negative zero (`-0.00`) is zero: unchanged. A fraction below one (`-0.75`) keeps its sign: `-0.10`. Test in Task 2 (parametrised).
4. The fixed header comment must not contain `--` (illegal inside an XML comment) nor any `U`-digit token: the redacted output must re-parse with `ET.fromstring` and the account regex must find only `U0000000`. Test in Task 2 (`test_redacted_output_reparses` plus the regex test).
5. A `FlexStatement` without `fromDate`/`toDate`, or with an unparseable one, yields `None` for that bound instead of crashing. Test in Task 3 (`test_summary_dates_none_when_absent`).

## Assumptions

- Sign handling in `_fake_number`: the sign is `"-"` when the `Decimal` is negative, else `""` (a leading `+` is dropped). Rejected: echoing a literal `+`; Flex does not emit it.
- `d` (decimals) is `max(0, -Decimal(text).as_tuple().exponent)`: for plain text it equals the count of characters after the `.` (the issue's definition); for exponent notation it gives the decimals of the value (`1.5E+3` → 0, `7.5E-3` → 4). `n` is the digit count of `int(abs(Decimal(text)))`, so leading zeros (`007`) do not count. Rejected: counting characters after the `.` in the text, which gives `d=4` for `1.5E+3`.
- "Not parseable" means `decimal.InvalidOperation` from `Decimal(text)`. Text with thousands separators (`1,234.56`) is therefore left unchanged, as the issue's rule says; the #110 Flex query asks for raw numeric columns and no source shows separators.
- The summary reuses `_flex_date` by importing it from `bot.ingest.ibkr_flex` (same package, the issue says "parse the first 8 chars like `_flex_date` does"). Rejected: duplicating it. Ruff's selected rules (`pyproject.toml` `[tool.ruff.lint]`) do not flag private imports.
- `summarize_statement` calls `parse_flex_row`, which emits the parser's `ibkr_flex_row_skipped` WARNING for incomplete rows; that is accepted (the summary is the parser's own view). Whether #139 logs them twice is #139's call.
- Non-finite `Decimal` values are left unchanged, like non-numeric text.
- `summarize_statement` iterates `CorporateAction` then `CashTransaction` (same order as the parser), so `parse_flex_row` WARNING logs for skipped rows appear in the parser's order.
- Unparseable `fromDate`/`toDate` values are ignored for the min/max.

---

### Task 1: `parse_flex_row` in `ibkr_flex.py`

**Files:**
- Modify: `src/bot/ingest/ibkr_flex.py` (`parse_flex_statement`, ~lines 140-177)
- Test: `tests/unit/test_ibkr_flex_capture.py` (new; the parser test file stays unchanged)

**Interfaces:**
- Produces: `parse_flex_row(el: xml.etree.ElementTree.Element) -> CorporateActionRecord | None` (public, in `bot.ingest.ibkr_flex`).

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_ibkr_flex_capture.py` (fixture path `tests/fixtures/ibkr_flex/statement_sample.xml`):
  - `test_parse_flex_row_matches_parser`: for every `CorporateAction` then `CashTransaction` element of the sample, collect non-`None` `parse_flex_row` results; equal to `parse_flex_statement(sample)`.
  - `test_parse_flex_row_skips_non_dividend_cash`: the `transactionID="2002"` element → `None`.
  - `test_parse_flex_row_rejects_other_tags`: `parse_flex_row(ET.Element("FlexStatement"))` raises `ValueError` matching `"not a Flex row: FlexStatement"`.
- [ ] **Step 2: Run** `uv run pytest -q tests/unit/test_ibkr_flex_capture.py` → FAIL (ImportError).
- [ ] **Step 3: Implement** `parse_flex_row` by moving the two loop bodies into it (tag dispatch); `parse_flex_statement` becomes two loops calling it. Docstring states the per-tag rules.
- [ ] **Step 4: Run** `uv run pytest -q tests/unit/test_ibkr_flex_capture.py tests/unit/test_ibkr_flex_parser.py` → PASS.
- [ ] **Step 5: Commit** `refactor(#138): extract parse_flex_row`.

### Task 2: `redact_statement` and `_fake_number`

**Files:**
- Create: `src/bot/ingest/ibkr_flex_capture.py`
- Test: `tests/unit/test_ibkr_flex_capture.py`

**Interfaces:**
- Consumes: `parse_flex_statement` (tests only).
- Produces: `REDACTED_ACCOUNT: str = "U0000000"`; `redact_statement(xml: str) -> str`; private `_fake_number(value: str) -> str` (tests import it).

- [ ] **Step 1: Write the failing tests:**
  - `test_fake_number` parametrised over `75.00→10.00`, `-11.25→-10.00`, `48.50→10.00`, `4750→1000`, `-700→-100`, `300→100`, `-50→-10`, `1.00→1.00`, `0→0`, `0.75→0.10`, `""→""`, plus `-0.00→-0.00`, `-0.75→-0.10`, `1E+3→1000`, `1.5E+3→1000`, `7.5E-3→0.1000`, `007→1`, `1,234.56→1,234.56`, `abc→abc`, `" 75.00 "→10.00`.
  - `test_fake_number_leaves_non_finite_unchanged` over `NaN`, `Infinity`, `-Infinity`, `sNaN`.
  - `test_redaction_is_deterministic`: two calls equal; starts with `'<?xml version="1.0" encoding="UTF-8"?>\n'`; ends with `"\n"`.
  - `test_redaction_leaves_only_placeholder_account`: `set(re.findall(r"\bU\d{6,9}\b", redacted)) == {"U0000000"}`.
  - `test_redacted_output_reparses`: `ET.fromstring(redacted).tag == "FlexQueryResponse"`.
  - `test_redaction_preserves_records`: `parse_flex_statement(redacted)` vs original: same `(action_id, action_type, ticker, effective_date, details["description"])` in order; every redacted `account == "U0000000"`.
  - `test_redaction_preserves_sign_and_shape`: for each record pair and each key in `amount`/`proceeds`/`quantity`/`value` present in the original details, the redacted value is present, same sign (`startswith("-")`), same decimals count (`"-700"` → negative integer string, `"75.00"` → positive with 2 decimals).
  - `test_redaction_blanks_alias`: an inline `FlexQueryResponse` with `acctAlias="Mine"` on `FlexStatement` → `acctAlias=""` in the output.
  - `test_redact_rejects_other_root`: `redact_statement("<Foo/>")` raises `ValueError`.
- [ ] **Step 2: Run** → FAIL (ImportError).
- [ ] **Step 3: Implement.** `_fake_number`: strip; empty → unchanged; `Decimal` raises `InvalidOperation` or is not finite → unchanged; `== 0` (covers `0`, `-0.00`) → unchanged (original text). `redact_statement` walks `root.iter()`; `accountId` → `REDACTED_ACCOUNT`, `acctAlias` present → `""`, `amount`/`proceeds`/`value`/`quantity` → `_fake_number`. Header comment (module constant, no `--`, no `U`-digit token) states: redacted real statement captured by `bot flex-capture` for #110; account ids and money/quantity columns are fakes; symbols, conids, isins, ids, dates, types and descriptions are real. `_fake_number` per the issue: n ≥ 1 → `sign + str(10 ** (n - 1))` + (`"." + "0" * d` if d > 0); integer part 0 → `sign + "0." + "1" + "0" * (d - 1)`; see Assumptions for sign, `d`, `n`, non-finite.
- [ ] **Step 4: Run** → PASS; `uv run mypy src && uv run ruff check .` clean.
- [ ] **Step 5: Commit** `feat(#138): redact_statement`.

### Task 3: `FlexSummary` and `summarize_statement`

**Files:**
- Modify: `src/bot/ingest/ibkr_flex_capture.py`
- Test: `tests/unit/test_ibkr_flex_capture.py`

**Interfaces:**
- Consumes: `parse_flex_row` (Task 1), `redact_statement` (Task 2, tests only).
- Produces: `@dataclass(frozen=True) class FlexSummary` with fields `accounts: int` (number of `FlexStatement` elements, not distinct ids, so it survives redaction), `from_date: str | None`, `to_date: str | None`, `rows: int`, `corporate_action_types: dict[str, int]`, `cash_transaction_types: dict[str, int]`, `parsed: int`, `parsed_by_action_type: dict[str, int]`, `skipped: dict[str, int]`; method `to_json(self) -> str`; `summarize_statement(xml: str) -> FlexSummary`.

- [ ] **Step 1: Write the failing tests:**
  - `test_summary_of_sample`: `summarize_statement(sample) == FlexSummary(accounts=2, from_date="2026-09-01", to_date="2026-09-30", rows=7, corporate_action_types={"FS": 1, "RS": 1, "TC": 1}, cash_transaction_types={"Dividends": 2, "Payment In Lieu Of Dividends": 1, "Withholding Tax": 1}, parsed=5, parsed_by_action_type={"dividend": 2, "split": 2, "tc": 1}, skipped={"CashTransaction/Dividends": 1, "CashTransaction/Withholding Tax": 1})`.
  - `test_summary_survives_redaction`: `summarize_statement(redact_statement(sample)) == summarize_statement(sample)`.
  - `test_summary_dict_keys_sorted`: each dict field's `list(keys) == sorted(keys)`.
  - `test_to_json_round_trips`: `json.loads(s.to_json()) == dataclasses.asdict(s)` and `s.to_json().endswith("\n")`.
  - `test_summary_dates_none_when_absent`: inline `<FlexQueryResponse><FlexStatements><FlexStatement accountId="U1"/></FlexStatements></FlexQueryResponse>` → `from_date is None and to_date is None`, `accounts == 1`, `rows == 0`.
  - `test_summary_missing_type_counts_under_empty`: inline statement with a `CorporateAction` lacking `type` → `corporate_action_types == {"": 1}`.
  - `test_summarize_rejects_other_root`: `summarize_statement("<Foo/>")` raises `ValueError`.
- [ ] **Step 2: Run** → FAIL.
- [ ] **Step 3: Implement.** Dates: first 8 chars parsed like `_flex_date`, via `_flex_date` imported from `bot.ingest.ibkr_flex`, emitted as `date.isoformat()`; min `fromDate`, max `toDate`. `rows` counts only `CorporateAction` + `CashTransaction` elements (other sections a real statement may carry are ignored). Counts via `collections.Counter`, converted to `dict(sorted(...))`. `skipped` key `f"{el.tag}/{raw type}"`. `to_json` = `json.dumps(dataclasses.asdict(self), indent=2, sort_keys=True) + "\n"`.
- [ ] **Step 4: Run** the three test files from the issue's "How to test", then `uv run ruff check . && uv run mypy src` and `uv run pytest -q` → all green.
- [ ] **Step 5: Commit** `feat(#138): summarize_statement`.

## Grilling

- Rounds: 1 (griller model: fable). Revisions were clarifications, no step added or removed and the same seam, so no second round.
- Questions: 16. Sources: ISSUE 9 (Q1 accounts definition, Q3 zero rule, Q4 attribute list incl. #110's Flex query columns, Q5 descriptions kept, Q7 unparseable rule, Q12 skipped key, Q13 rows definition, Q15 output format, Q10 partly); CODE 5 (Q2 `_record` reads only `el`, `ibkr_flex.py:94-139`; Q8 malformed rows return `None` with WARNING, `ibkr_flex.py:109-125`; Q9 seam test scans every `src/bot/**/*.py`, `tests/unit/test_seam_enforcement.py:15-21,55-56`; Q11 log asserted in `tests/unit/test_ibkr_flex_parser.py:81-84`; Q14 `details: dict[str, str]`, `ibkr_flex.py:77`); NO SOURCE 4 → technical assumptions (Q6 exponent decimals, Q7 thousands separators, Q10 private import, Q11 double logging in #139, Q16 reversibility: the branch is unmerged and squash-merged, so an abandoned task leaves nothing on BASE).
- Assumptions added: `d` from the `Decimal` exponent; `InvalidOperation` is "not parseable"; `_flex_date` imported; WARNINGs from the summary accepted.
- Spec ambiguities: none. Follow-up issues opened: none.
