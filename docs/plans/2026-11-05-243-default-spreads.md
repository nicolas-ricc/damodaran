# Default-spread tables (coverage → rating → default probability) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A curated `config/default_spreads.yaml` and a pure loader `bot.reference.default_spreads.load_default_spreads` that turn an interest coverage into a synthetic rating and that rating into a 10-year cumulative default probability, with `Settings.default_spreads_path` pointing at the file.

**Architecture:** A copy of the `config/currencies.yaml` + `bot.reference.currencies.load_currency_table` + `Settings.currencies_path` pattern. The loader parses YAML with a duplicate-key-rejecting `SafeLoader`. It degrades to `EMPTY_DEFAULT_SPREADS` with one warning when the file is absent or malformed, and raises `ValueError` naming the path for values that parse but are out of range or inconsistent. Nothing calls the loader yet: a sibling task (#246) wires it into the valuator.

**Tech Stack:** Python 3.12, PyYAML, structlog, pydantic-settings, pytest (`structlog.testing.capture_logs`).

**Spec:** issue #243 (parent story #213, decisions 1–3 of the planner comment).

## Global Constraints

- Do not touch `src/bot/valuator`, the CLI, the report or `docs/` (except this plan).
- Copy `_UniqueKeyLoader` and its helpers from `bot.reference.currencies`; do not import private names.
- Log events, exactly: `default_spreads.absent` (warning, `path=`), `default_spreads.malformed` (warning, `path=`, `reason=`), `default_spreads.loaded` (info, `path=`, `brackets=n`, `ratings=m`).
- Every `ValueError` message starts with the path (`f"{path}: ..."`).
- Brackets: `lower` inclusive, `upper` exclusive, `null` = unbounded. Probabilities are decimals in the closed interval [0, 1].
- `Settings.default_spreads_path: Path = Field(default=Path("./config/default_spreads.yaml"), description="Curated interest coverage → synthetic rating → cumulative default probability tables for distressed stories (#213).")`, placed right after `currencies_path`. Env `BOT_DEFAULT_SPREADS_PATH`.
- `mypy --strict`, ruff and the full suite pass.
- Commit message for the feature: `feat(#213): default-spread tables (coverage → rating → default probability) with a pure loader`.

## Decisions

1. **Malformed vs. `ValueError`.** Malformed means the shape or a type is wrong: not YAML, top level not a mapping, an unknown or missing top-level key (`horizon_years`, `coverage_to_rating`, `rating_to_default_probability` are the only ones), a duplicate key, `coverage_to_rating` not a list, `rating_to_default_probability` not a mapping, a row not a mapping, a missing field, a non-number (a `bool` is not a number), a bad date, a rating (bracket `rating` or probability key) that is not a non-empty string, a `source` that is not a non-empty string. Everything else raises `ValueError`: probability outside [0, 1], `horizon_years` not a positive `int` (a `bool`, a float such as `10.0`, `0` or `-1` included), `lower >= upper` in a bracket, brackets that overlap or leave a gap once sorted by `lower`, a first `lower` or last `upper` that is not `null`, a `null` bound anywhere else, and a bracket rating with no probability row.
2. **`horizon_years` may be `null`.** The field `DefaultSpreadTable.horizon_years: int | None` exists for the empty table. In the file the key is required and must be a positive integer.
3. **Missing field vs. `null` bound.** A bracket must have all five keys `lower, upper, rating, source, as_of`. `lower` and `upper` may be `null`; the other three may not. A missing key is malformed.
4. **Sorting.** Brackets are sorted by `lower` (with `null` first) before the tiling check. The table stores them sorted. A `null` lower anywhere but first, or a `null` upper anywhere but last, is a `ValueError` ("unbounded bracket in the middle").
5. **`rating_for`.** It returns `None` when the table is empty or the coverage is NaN. Otherwise it returns the rating of the bracket with `lower <= coverage < upper`. `±inf` falls into the unbounded end brackets.
6. **Seed values** (read from the sources on 2026-11-05):
   - Coverage → rating, `source: https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/ratings.html`, `as_of: 2026-01-01`, left block (large non-financial firms):

     | lower | upper | rating |
     |---|---|---|
     | null | 0.2 | D |
     | 0.2 | 0.65 | C |
     | 0.65 | 0.8 | CC |
     | 0.8 | 1.25 | CCC |
     | 1.25 | 1.5 | B- |
     | 1.5 | 1.75 | B |
     | 1.75 | 2.0 | B+ |
     | 2.0 | 2.25 | BB |
     | 2.25 | 2.5 | BB+ |
     | 2.5 | 3.0 | BBB |
     | 3.0 | 4.25 | A- |
     | 4.25 | 5.5 | A |
     | 5.5 | 6.5 | A+ |
     | 6.5 | 8.5 | AA |
     | 8.5 | null | AAA |

   - Rating → 10-year probability, `source: https://pages.stern.nyu.edu/~adamodar/pdfiles/papers/NewDistress.pdf`, `as_of: 2009-06-01` (Table 5, pp. 41-42, Altman 2007):
     AAA 0.0007, AA 0.0051, A+ 0.0057, A 0.0066, A- 0.0500, BBB 0.0754, BB 0.1963, B+ 0.2825, B 0.3680, B- 0.4212, CCC 0.5902, CC 0.6660, C+ 0.7516, C 0.8103, C- 0.8716;
     plus BB+ 0.1963 (copies BB, the table's nearest class) and D 0.8716 (copies C-; a D rating means default already happened, the worst curated class is the nearest figure, and 1.0 is not a curated number that would zero every company with coverage under 0.2). Both decisions go in comments on their rows.
   - Table 5 is irregular: A- jumps to 5.00% from A's 0.66%, and A+ (0.57%) sits barely above AA (0.51%). That is the source. The loader does not check monotonicity, and the seed copies the source.

## Review Focus

- A value that YAML reads as a `bool` (`probability: yes`, `lower: true`) must be malformed, not `1.0`. Task 1 test case `bool-probability`.
- `horizon_years: 10.0` or `true` must be a `ValueError`, not accepted as 10 or 1. Task 1 parametrised case.
- Coverage exactly on a bound belongs to the upper bracket (`rating_for(2.5) == "BBB"`, `rating_for(8.5) == "AAA"`). Task 2 lookup tests.
- `rating_for(float("nan"))` returns `None`, and `rating_for(float("inf"))` / `float("-inf")` return the end ratings. Task 1 test `test_rating_for_nan_and_infinities`.
- Brackets written out of order in the file still load (they are sorted), and the probabilities mapping is read-only. Task 1 tests `test_brackets_out_of_order_are_sorted` and `test_probabilities_are_read_only`.

---

### Task 1: Loader `bot.reference.default_spreads`

**Files:**
- Create: `src/bot/reference/default_spreads.py`
- Test: `tests/unit/test_default_spreads.py` (all tests here use `tmp_path` files; Task 2 adds the repo-file tests)

**Interfaces:**
- Produces:
  ```python
  DEFAULT_SPREADS_PATH = Path("config/default_spreads.yaml")

  @dataclass(frozen=True)
  class CoverageBracket:
      lower: float | None
      upper: float | None
      rating: str
      source: str
      as_of: date

  @dataclass(frozen=True)
  class DefaultProbability:
      probability: float
      source: str
      as_of: date

  @dataclass(frozen=True)
  class DefaultSpreadTable:
      horizon_years: int | None
      brackets: tuple[CoverageBracket, ...]
      probabilities: Mapping[str, DefaultProbability]
      @property
      def is_empty(self) -> bool: ...                          # no brackets
      def rating_for(self, coverage: float) -> str | None: ...
      def probability_for(self, rating: str) -> float | None: ...

  EMPTY_DEFAULT_SPREADS = DefaultSpreadTable(None, (), MappingProxyType({}))

  def load_default_spreads(path: Path | None = None) -> DefaultSpreadTable: ...
  ```

- [ ] **Step 1: Write the failing tests.** A helper `_write(tmp_path, text) -> Path` and a minimal valid document `_VALID` with `horizon_years: 10`, three brackets (`null–1.0 → C`, `1.0–3.0 → BB`, `3.0–null → AAA`) and probabilities for `C 0.8`, `BB 0.2`, `AAA 0.001`, each with `source: https://example.org/x` and `as_of: 2026-01-01`. Tests:
  - `test_loads_a_valid_table`: `horizon_years == 10`; `brackets[0] == CoverageBracket(None, 1.0, "C", "https://example.org/x", date(2026, 1, 1))`; `probabilities["BB"] == DefaultProbability(0.2, ...)`; `not is_empty`.
  - `test_rating_for_bounds`: `rating_for(0.99) == "C"`, `rating_for(1.0) == "BB"`, `rating_for(3.0) == "AAA"`, `rating_for(-50.0) == "C"`.
  - `test_rating_for_nan_and_infinities`: NaN → `None`; `inf` → `"AAA"`; `-inf` → `"C"`.
  - `test_probability_for`: `probability_for("C") == 0.8`; `probability_for("ZZZ") is None`.
  - `test_brackets_out_of_order_are_sorted`: the same three brackets written AAA, C, BB load, and `[b.rating for b in brackets] == ["C", "BB", "AAA"]`.
  - `test_probabilities_are_read_only`: assigning `table.probabilities["X"] = ...` raises `TypeError`.
  - `test_absent_file_warns_and_is_empty`: `load_default_spreads(tmp_path / "absent.yaml") is EMPTY_DEFAULT_SPREADS`; `is_empty`; `rating_for(0.5) is None`; `probability_for("C") is None`; exactly one `default_spreads.absent` event.
  - `test_empty_table_constant`: `EMPTY_DEFAULT_SPREADS.horizon_years is None`, `brackets == ()`, `dict(probabilities) == {}`.
  - `test_malformed_file_warns_and_is_empty` (parametrised, each a mutation of `_VALID`): ids `unparsable`, `not-a-mapping`, `unknown-top-level-key`, `missing-top-level-key`, `duplicate-key`, `brackets-not-a-list`, `probabilities-not-a-mapping`, `bracket-not-a-mapping`, `probability-row-not-a-mapping`, `missing-field` (a bracket without `as_of`), `missing-probability-field`, `non-number-bound` (`lower: abc`), `bool-probability` (`probability: true`), `bad-date`, `empty-rating` (`rating: ""`), `non-string-rating` (`rating: 5`), `empty-source`. Each → result `is_empty` and `default_spreads.malformed` in the events.
  - `test_unreadable_path_warns_and_is_empty`: a directory as path → empty + `default_spreads.malformed`.
  - `test_invalid_value_fails_at_load` (parametrised): ids `probability-above-one` (1.2), `probability-negative` (-0.01), `horizon-zero`, `horizon-negative`, `horizon-float` (10.0), `horizon-bool` (true), `lower-not-below-upper` (a bracket 3.0–1.0), `gap` (1.0–3.0 changed to 1.5–3.0), `overlap` (1.0–3.0 changed to 0.5–3.0), `first-lower-bounded` (`lower: 0.0` on the first), `last-upper-bounded` (`upper: 100.0` on the last), `rating-without-probability` (drop the `BB` probability row). Each raises `ValueError` and `str(path) in str(excinfo.value)`.
  - `test_probability_bounds_are_closed`: probabilities 0.0 and 1.0 load.
  - `test_datetime_as_of_is_narrowed_to_date`: `as_of: 2026-01-01T00:00:00` gives `type(as_of) is date`.

- [ ] **Step 2: Run them to verify they fail.**
  Run: `uv run pytest tests/unit/test_default_spreads.py -q`
  Expected: collection error, `ModuleNotFoundError: bot.reference.default_spreads`.

- [ ] **Step 3: Implement `src/bot/reference/default_spreads.py`.** Module docstring in the style of `currencies.py`, naming #213, the two sources and the degrade/fail rule. Private helpers copied from `currencies.py` (`_MalformedError`, `_UniqueKeyLoader`, `_number`, `_text`, `_date`), adapted to a `where: str` label. `_parse(path, data) -> DefaultSpreadTable` checks shape first (raising `_MalformedError`), then values (raising `ValueError`). `load_default_spreads` catches `yaml.YAMLError, _MalformedError, OSError, UnicodeDecodeError` like `load_currency_table`. `rating_for` is a linear scan over the 15 sorted brackets (no `bisect` needed).

- [ ] **Step 4: Run the tests to verify they pass.**
  Run: `uv run pytest tests/unit/test_default_spreads.py -q && uv run mypy src && uv run ruff check .`
  Expected: all pass, clean.

- [ ] **Step 5: Commit.** `git add src/bot/reference/default_spreads.py tests/unit/test_default_spreads.py && git commit -m "feat(#213): default-spread table loader"`

### Task 2: The curated file and `Settings.default_spreads_path`

**Files:**
- Create: `config/default_spreads.yaml`
- Modify: `src/bot/config.py` (new field right after `currencies_path`, around line 86)
- Test: `tests/unit/test_default_spreads.py` (append)

**Interfaces:**
- Consumes: `load_default_spreads`, `DefaultSpreadTable` from Task 1.
- Produces: the repo file (schema in issue #243) and `Settings.default_spreads_path`.

- [ ] **Step 1: Write the failing tests.** `REPO_FILE = Path(__file__).resolve().parents[2] / "config" / "default_spreads.yaml"`.
  - `test_repo_file_shape`: `horizon_years == 10`; `len(brackets) == 15`; `brackets[0].lower is None`; `brackets[-1].upper is None`; `[b.rating for b in brackets] == ["D", "C", "CC", "CCC", "B-", "B", "B+", "BB", "BB+", "BBB", "A-", "A", "A+", "AA", "AAA"]`.
  - `test_every_repo_row_has_https_source_and_as_of`: for every bracket and every probability row, `source.startswith("https://")` and `isinstance(as_of, date)`.
  - `test_every_repo_bracket_rating_has_a_probability`.
  - `test_repo_lookups`: `rating_for(0.6) == "C"`, `rating_for(0.67) == "CC"`, `rating_for(-3.0) == "D"`, `rating_for(2.5) == "BBB"`, `rating_for(8.5) == "AAA"`, `rating_for(100.0) == "AAA"`; `probability_for("C") == pytest.approx(0.8103)`; `probability_for("BB+") == probability_for("BB")`; `probability_for("D") == probability_for("C-")`; `probability_for("ZZZ") is None`.
  - `test_repo_probabilities_match_table_5`: the 15 Table 5 ten-year values from Decision 6, exact (`pytest.approx`).
  - `test_settings_default_spreads_path_default_and_override`: copy of `test_settings_currencies_path_default_and_override` with `BOT_DEFAULT_SPREADS_PATH`.

- [ ] **Step 2: Run them to verify they fail.**
  Run: `uv run pytest tests/unit/test_default_spreads.py -q`
  Expected: the repo-file tests fail (file absent → empty table), the Settings test fails with `AttributeError`.

- [ ] **Step 3: Write `config/default_spreads.yaml`** with the values of Decision 6 and the schema of issue #243 (flow-style rows). The header says what each table is, gives both source URLs, says how to reproduce (the HTML page's left block; the PDF's pp. 41-42, 10-year column, with the `uv run --with pypdf python -I` recipe), and records the BB+ and D decisions. Add the `Settings` field verbatim from Global Constraints.

- [ ] **Step 4: Run the tests and the acceptance one-liner.**
  Run: `uv run pytest tests/unit/test_default_spreads.py -q && uv run python -c "from bot.reference.default_spreads import load_default_spreads as l; t = l(); r = t.rating_for(0.6); print(r, t.probability_for(r))"`
  Expected: pass; prints `C 0.8103`.

- [ ] **Step 5: Full gate and commit.**
  Run: `uv run ruff check . && uv run mypy src && uv run pytest -q`
  Then: `git add config/default_spreads.yaml src/bot/config.py tests/unit/test_default_spreads.py && git commit -m "feat(#213): default-spread tables (coverage → rating → default probability) with a pure loader"`
