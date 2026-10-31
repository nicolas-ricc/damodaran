# A malformed override fails its ticker, not the batch — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `.agents/skills/subagent-driven-development/SKILL.md` to implement this plan task-by-task; implementers write code with `.agents/skills/test-driven-development/SKILL.md`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every malformed `config/assumptions/<TICKER>.yaml` makes that ticker exit "cannot value" (code 1) and lets `bot analyze` go on with the rest of the batch, instead of crashing the whole command.

**Architecture:** `_load_override` in `src/bot/valuator/assumptions.py` becomes the one gate of the override surface. It turns `yaml.YAMLError` into `ValueError`, sorts unknown keys by their `str` so a non-string key is reported instead of crashing `sorted`, and checks every numeric key's value up front with a new `_check_override_values`. Every refusal is a `ValueError` naming the file and the key. `_analyze_one` (`src/bot/cli.py:453`) already maps `ValueError` to "cannot value", exit 1, and continues. The screener's second pass (`src/bot/screener/engine.py:142-147`) and holding marks (`src/bot/portfolio/marks.py:146`) already catch `ValueError` too, so the same fix covers them with no change there.

**Tech Stack:** Python 3, PyYAML (`yaml.safe_load`), typer, pytest, mypy --strict, ruff.

**Spec:** GitHub issue #180 (nicolas-ricc/damodaran), "Only refused arguments or an empty screen stop the whole command; a failing ticker never does (broken: malformed override YAML)", plus its owner comment widening it to `TypeError` from `_override_scalar` / `_override_path_field`.

## Global Constraints

- Rule (issue + owner comment): "Only refused arguments, an empty screen or a refused currency table stop the whole command; a failing ticker never does."
- A malformed override maps to "cannot value, exit code 1" (issue: "as is already done for a non-mapping file or an unknown key"). So it raises `ValueError`, never `LookupError` (exit 2 is reserved for an unknown ticker).
- The override surface covered (owner comment): malformed YAML, and "any value that isn't a number (or a list of numbers for the path keys)".
- Path keys: `revenue_growth`, `operating_margin` (`_override_path_field`). Scalar numeric keys: every other key in `_OVERRIDE_KEYS` except `story_type` and `notes`.
- The error message names the override file path and, for a value error, the key, so the user can fix the file.
- No change to the precedence of sources, to `story_type` handling (an invalid label already logs a warning and falls back), or to `notes`.
- Type hints everywhere; `uv run ruff check . && uv run mypy src && uv run pytest -q` green.
- Commits: Conventional Commits with `(#180)` scope.

## Review Focus

1. `tax_rate: true` (or `yes`): YAML reads a bool, `float(True)` is `1.0`, and today the override silently applies a 100 % tax rate. A bool is not a number: refuse it. Test in Task 2.
2. `terminal_growth: .nan` / `.inf`: `float()` accepts it, and the report's JSON sidecar later raises `ValueError` *outside* `_analyze_one`'s `try`, so the batch still dies (probed on master). Refuse non-finite numbers. Test in Task 2.
3. `operating_margin: []`: today the empty tuple raises `IndexError`, a `LookupError`, so the ticker exits 2 as if it were unknown. An empty path is not a list of numbers: refuse it with `ValueError`. Test in Task 2.
4. A YAML mapping with a non-string key (`1: 2` beside `foo: 3`): `sorted(set(loaded) - _OVERRIDE_KEYS)` compares `int` with `str` and raises `TypeError`, which escapes the batch (probed on master). Test in Task 1.
5. A numeric string (`terminal_growth: '3e-2'`; PyYAML reads an unquoted `3e-2` as a string too) works today through `float()`. Keep accepting a string `float()` parses to a finite number, so existing files keep working. Test in Task 2.

## Assumptions

- Values are checked eagerly in `_load_override`, not lazily in `_override_scalar` / `_override_path_field`: one gate, and a bad value is refused even for a key a given resolution path happens not to read (for example `probability_of_bankruptcy` on a non-distressed company), so the file is either valid or not.
- `tests/unit/test_analyze_model_replay.py` and `docs/pipeline/models/analyze.cfg` exist only on `feature/161-pipeline-subboards` (#169 merged there). This branch targets `master` (#180 has no parent issue), so it cannot delete `test_a_malformed_override_raises_out_of_the_batch`, remove the strict `xfail`, or restore the rule in `analyze.cfg`. Instead, Task 3 adds the replay's three cases (plus the Review Focus ones) as CLI batch tests on master. When `master` is merged into the feature branch, the pinned-behaviour test will fail and the strict xfail will XPASS, which is the signal to do the cleanup the issue describes there.
- A list of the wrong length for a path key (`revenue_growth: [0.1]`) is not refused: today it runs, and the issue doesn't ask for a length rule.

## File Structure

- Modify: `src/bot/valuator/assumptions.py`: `_load_override` (YAML error, key sort), new `_check_override_values` beside it.
- Modify: `tests/unit/test_valuator_assumptions.py`: unit tests for the gate.
- Modify: `tests/unit/test_cli_analyze.py`: batch-continues tests.
- Modify: `docs/leccion/index.html`: the `resolve_assumptions` line citation, if the line moves (`docs/leccion/check.py` warns).

---

### Task 1: Malformed YAML and non-string keys refuse the ticker

**Files:**
- Modify: `src/bot/valuator/assumptions.py` (`_load_override`)
- Test: `tests/unit/test_valuator_assumptions.py`

**Interfaces:**
- Produces: `_load_override(override_path: Path | None) -> dict[str, Any]` (unchanged signature) raises `ValueError` for invalid YAML and for unknown keys of any type.

- [ ] **Step 1: Write the failing tests** (in the "Manual override wins" section, using the existing `_write_override` and `conn` fixtures)

```python
def test_override_that_is_not_yaml_is_refused(conn, tmp_path) -> None:
    _seed_full_sector(conn)
    override = _write_override(tmp_path, "revenue_growth: [0.1\n")
    with pytest.raises(ValueError, match=r"ACME\.yaml.*not valid YAML"):
        resolve_assumptions("ACME", conn, override_path=override)


def test_override_with_a_non_string_key_is_refused(conn, tmp_path) -> None:
    _seed_full_sector(conn)
    override = _write_override(tmp_path, "1: 2\nfoo: 3\n")
    with pytest.raises(ValueError, match=r"unknown override key\(s\): 1, foo"):
        resolve_assumptions("ACME", conn, override_path=override)
```

- [ ] **Step 2: Run them, expect FAIL** (`yaml.YAMLError` / `TypeError`)

Run: `uv run pytest tests/unit/test_valuator_assumptions.py -q -k "not_yaml or non_string_key"`

- [ ] **Step 3: Implement.** Wrap `yaml.safe_load` in `try/except yaml.YAMLError as exc` and raise `ValueError(f"override file {override_path} is not valid YAML: {exc}") from exc`. Build `unknown` with `sorted(..., key=str)` and join with `str(k)`.

- [ ] **Step 4: Run them, expect PASS**, then the whole file.

- [ ] **Step 5: Commit** `fix(#180): refuse an override that is not YAML`

### Task 2: Every numeric override value is a finite number

**Files:**
- Modify: `src/bot/valuator/assumptions.py` (new `_check_override_values`, called from `_load_override` after the unknown-key check)
- Test: `tests/unit/test_valuator_assumptions.py`

**Interfaces:**
- Consumes: `_load_override` from Task 1.
- Produces: `_check_override_values(override_path: Path, override: dict[str, Any]) -> None`, which raises `ValueError(f"{override_path}: {key} must be a number ...")`. Path keys accept a number or a non-empty list of numbers. A number is an `int`/`float` that is not a `bool`, or a `str` that `float()` parses, and in every case finite. Define the path-key set once (for example `_OVERRIDE_PATH_KEYS = frozenset({"revenue_growth", "operating_margin"})`) and treat `_OVERRIDE_KEYS - _OVERRIDE_PATH_KEYS - {"story_type", "notes"}` as scalar keys.

- [ ] **Step 1: Write the failing tests**

```python
@pytest.mark.parametrize(
    ("body", "key"),
    [
        pytest.param("terminal_growth:\n", "terminal_growth", id="empty-value"),
        pytest.param("tax_rate: [0.2]\n", "tax_rate", id="list-for-a-number"),
        pytest.param("tax_rate: true\n", "tax_rate", id="bool"),
        pytest.param("sales_to_capital: {a: 1}\n", "sales_to_capital", id="mapping"),
        pytest.param("cost_of_equity: high\n", "cost_of_equity", id="word"),
        pytest.param("terminal_growth: .nan\n", "terminal_growth", id="nan"),
        pytest.param("terminal_growth: .inf\n", "terminal_growth", id="inf"),
        pytest.param("operating_margin: []\n", "operating_margin", id="empty-path"),
        pytest.param("revenue_growth: [0.1, null]\n", "revenue_growth", id="null-in-path"),
        pytest.param("revenue_growth: [0.1, [0.2]]\n", "revenue_growth", id="list-in-path"),
    ],
)
def test_override_value_that_is_not_a_number_is_refused(conn, tmp_path, body, key) -> None:
    _seed_full_sector(conn)
    override = _write_override(tmp_path, body)
    with pytest.raises(ValueError, match=rf"ACME\.yaml: {key} must be"):
        resolve_assumptions("ACME", conn, override_path=override)


def test_override_numeric_string_still_applies(conn, tmp_path) -> None:
    _seed_full_sector(conn)
    override = _write_override(tmp_path, "terminal_growth: 3e-2\n")
    result = resolve_assumptions("ACME", conn, override_path=override)
    assert result.terminal_growth.value == pytest.approx(0.03)
    assert result.terminal_growth.source is AssumptionSource.MANUAL
```

- [ ] **Step 2: Run them, expect FAIL** (`TypeError` for empty-value, list, mapping, list-in-path, null-in-path; no raise for bool, nan, inf; `ValueError` without the key in its message for word; `IndexError` or no raise for empty-path)

Run: `uv run pytest tests/unit/test_valuator_assumptions.py -q -k "not_a_number or numeric_string"`

- [ ] **Step 3: Implement `_check_override_values`** and call it from `_load_override`. `_override_scalar` / `_override_path_field` stay as they are: after the gate their `float()` calls cannot fail.

- [ ] **Step 4: Run them, expect PASS**, then `uv run pytest tests/unit/test_valuator_assumptions.py -q`.

- [ ] **Step 5: Commit** `fix(#180): refuse an override value that is not a number`

### Task 3: `bot analyze` carries on past a malformed override

**Files:**
- Test: `tests/unit/test_cli_analyze.py`
- Modify: `docs/leccion/index.html` (citation of `resolve_assumptions`, only if `uv run python docs/leccion/check.py` reports it moved)

**Interfaces:**
- Consumes: Tasks 1 and 2 (no new code; `_analyze_one` already maps `ValueError` to exit 1).

- [ ] **Step 1: Write the test** (seed AAPL and MSFT with `_seed`, write `AAPL.yaml` in a `BOT_ASSUMPTIONS_DIR`, run `analyze AAPL MSFT`)

```python
@pytest.mark.parametrize(
    "body",
    [
        pytest.param("revenue_growth: [0.1\n", id="not-yaml"),
        pytest.param("terminal_growth:\n", id="empty-value"),
        pytest.param("tax_rate: [0.2]\n", id="list-for-a-number"),
        pytest.param("terminal_growth: .nan\n", id="nan"),
        pytest.param("1: 2\nfoo: 3\n", id="non-string-key"),
    ],
)
def test_analyze_malformed_override_fails_its_ticker_and_continues_batch(
    tmp_path, monkeypatch, body
) -> None:
    ...
    result = CliRunner().invoke(app, ["analyze", "AAPL", "MSFT"])
    assert isinstance(result.exception, SystemExit), result.exception
    assert result.exit_code == 1, result.output
    assert "AAPL: cannot value" in result.output
    out_dir = next(reports_dir.glob("*/analysis"))
    assert (out_dir / "MSFT.md").exists()
    assert not (out_dir / "AAPL.md").exists()
```

- [ ] **Step 2: Run it.** Expect FAIL before Tasks 1–2, PASS after.

Run: `uv run pytest tests/unit/test_cli_analyze.py -q -k malformed_override`

- [ ] **Step 3: Run `uv run python docs/leccion/check.py`.** If it reports `resolve_assumptions` moved, update its `src/bot/valuator/assumptions.py:<line>` citation in `docs/leccion/index.html`. Leave the warnings that were already there before this branch alone.

- [ ] **Step 4: Full suite and lint:** `uv run pytest -q && uv run ruff check . && uv run mypy src`, all green.

- [ ] **Step 5: Commit** `test(#180): analyze batch survives a malformed override`
