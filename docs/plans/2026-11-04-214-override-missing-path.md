# `bot analyze --override` refuses a path that is not a file — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `.agents/skills/subagent-driven-development/SKILL.md` to implement this plan task-by-task; implementers write code with `.agents/skills/test-driven-development/SKILL.md`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `bot analyze TICKER --override PATH` stops with exit code 2 and names `PATH` on stderr when `PATH` is not an existing file, instead of silently valuing without overrides.

**Architecture:** One more argument check in `bot.cli.analyze` (`src/bot/cli.py:413-422`), after the existing three and before `_open_db()`: `override is not None and not override.is_file()` echoes `--override <path>: no such file.` to stderr and raises `typer.Exit(code=2)`. `load_override` (`src/bot/valuator/assumptions.py:718-728`) keeps returning `{}` for a missing path, because `conventional_override_path` and the screener and portfolio callers rely on it. The atlas then names the new refusal: the `override` decision and the errors note on `analyze.d2`, the `asked -> command_stops` exit-code-2 edge on `analyze-inputs.d2`, the `TheArgumentsAreRefused` step in `models/analyze.tla` (comment) and `models/analyze.view.js` (label), and a re-render with `docs/pipeline/build.sh`.

**Tech Stack:** Python 3, typer, pytest, mypy --strict, ruff; d2 v0.9.0 (TALA), TLA+/TLC through the statechart launcher.

**Spec:** GitHub issue #214 (nicolas-ricc/damodaran) and its Agent Brief comment.

## Global Constraints

- Message, verbatim from the brief: `--override <path>: no such file.` on stderr, where `<path>` is the path as given.
- Exit code 2, "same family as the other argument errors". The check runs "after the existing argument checks and before opening the DB".
- "Not an existing file" covers a missing path and a directory (acceptance criterion 4).
- The conventional path `config/assumptions/TICKER.yaml` keeps today's behaviour: absent means no overrides.
- `load_override` keeps tolerating a missing path. Out of scope: validating the file's contents, and the screener and portfolio override paths.
- Atlas labels: a model step's label in `analyze.view.js` and its edge's first line on the sub-board are the same string (`tests/unit/test_pipeline_models.py`, `_SUBBOARDED`).
- `uv run ruff check . && uv run mypy src && uv run pytest -q`, `python3 docs/pipeline/check.py` and TLC green.
- Commits: Conventional Commits, `(#214)` scope.

## Review Focus

1. `--override` pointing at a directory: `Path.exists()` is true, so an `exists()` check would let it through, and then `read_text()` raises `IsADirectoryError` outside the `ValueError` catch. Use `is_file()`. Test in Task 1.
2. A broken symlink, or a symlink to a directory: `is_file()` follows links, so both are refused and a symlink to a real file passes. No separate test; the directory test pins the rule `is_file()` implements.
3. `--override` with two tickers and a missing path: the "exactly one ticker" message must still win, since it is the earlier check (`test_analyze_explicit_override_with_many_tickers_is_rejected` already passes `x.yaml`, which does not exist). Test in Task 1 asserts the message.
4. The refusal happens before the DB is opened: no report directory gets created and no ticker gets valued. Test in Task 1 asserts no `*/analysis/*` file.
5. A relative path resolves against the current directory, the same way `read_text()` resolves it today. No change and no test.

## Assumptions

- A directory gets the same `no such file.` message as a missing path: the brief fixes one message and calls both "not an existing file". Rejected: a second message (`is a directory`).
- The path is echoed as typer received it (`str(override)`), not resolved, so the user sees their own typo.
- `docs/plano/estado.py:136` cites `cli.py:477`. The new check moves that line by about four. `estado.html` is hand-curated, and this issue does not re-audit it, so the citation is left alone. The leccion cites only `assumptions.py:706`, which does not move.

## File Structure

- Modify: `src/bot/cli.py` (`analyze`, the argument checks)
- Modify: `tests/unit/test_cli_analyze.py`
- Modify: `docs/pipeline/analyze.d2`, `docs/pipeline/analyze-inputs.d2`, `docs/pipeline/models/analyze.tla`, `docs/pipeline/models/analyze.view.js`; re-rendered `docs/pipeline/*.svg` and `docs/pipeline/rendered.sha256`
- Possibly modify: `tests/unit/test_pipeline_diagram.py:1605`, only if a phrase it pins on the `override` node changes (none should)

---

### Task 1: `bot analyze` refuses an `--override` that is not a file

**Files:**
- Modify: `src/bot/cli.py` (`analyze`, after the `len(tickers) != 1` check)
- Test: `tests/unit/test_cli_analyze.py`

**Interfaces:**
- Produces: no new symbol. `bot analyze` exits 2 with `--override <path>: no such file.` on stderr.

- [ ] **Step 1: Write the failing tests.** Seed AAPL with `_seed`, set `BOT_DB_PATH`, `BOT_REPORTS_DIR`, `BOT_SEC_USER_AGENT` as the neighbouring tests do. Use `CliRunner()`; read stderr through `result.output` like the existing tests.

```python
def test_analyze_explicit_override_that_does_not_exist_is_rejected(tmp_path, monkeypatch) -> None:
    missing = tmp_path / "does" / "not" / "exist.yaml"
    result = runner.invoke(app, ["analyze", "AAPL", "--override", str(missing)])
    assert result.exit_code == 2
    assert f"--override {missing}: no such file." in result.output
    assert list(reports_dir.glob("*/analysis/*")) == []


def test_analyze_explicit_override_that_is_a_directory_is_rejected(tmp_path, monkeypatch) -> None:
    directory = tmp_path / "assumptions"; directory.mkdir()
    result = runner.invoke(app, ["analyze", "AAPL", "--override", str(directory)])
    assert result.exit_code == 2
    assert f"--override {directory}: no such file." in result.output
    assert list(reports_dir.glob("*/analysis/*")) == []
```

Extend `test_analyze_explicit_override_with_many_tickers_is_rejected` with `assert "exactly one ticker" in result.output`.

- [ ] **Step 2: Run them, expect the two new tests to FAIL** (exit 0, a report written).

Run: `uv run pytest tests/unit/test_cli_analyze.py -q -k "override"`

- [ ] **Step 3: Implement** the check in `analyze`, written like the three checks above it (`typer.echo(..., err=True)`, `raise typer.Exit(code=2)`), using `override.is_file()`. Add a sentence to the `--override` help or docstring only if it stays accurate; not required.

- [ ] **Step 4: Run them, expect PASS**, then `uv run pytest tests/unit/test_cli_analyze.py -q`. `test_analyze_applies_override`, `test_analyze_picks_up_config_assumptions_by_convention` and `test_analyze_explicit_override_wins_over_convention` cover acceptance criteria 2 and 3 and must stay green unchanged.

- [ ] **Step 5: Commit** `fix(#214): refuse an --override path that is not a file`

### Task 2: The atlas names the missing `--override` file

**Files:**
- Modify: `docs/pipeline/analyze.d2` (the `cli.errors` note's "bad arguments" bullet; the `override` decision label)
- Modify: `docs/pipeline/analyze-inputs.d2` (the `asked -> command_stops` exit-code-two edge for arguments; the `override_picked` node's `--override path` line)
- Modify: `docs/pipeline/models/analyze.view.js` (`TheArgumentsAreRefused` label)
- Modify: `docs/pipeline/models/analyze.tla` (the comment above `TheArgumentsAreRefused`; the TLA+ logic does not change)
- Regenerate: `docs/pipeline/*.svg`, `docs/pipeline/rendered.sha256` via `docs/pipeline/build.sh`

**Interfaces:**
- Consumes: Task 1's behaviour and message.

- [ ] **Step 1: Change the labels.** The new `TheArgumentsAreRefused` label, identical in `analyze.view.js` and as the first line of the `analyze-inputs.d2` edge:
  `the command stops, exit code two [tickers with --from-screen, neither, --override without exactly one ticker, or an --override path that is not a file]`
  On `analyze.d2`: the errors bullet becomes `bad arguments (tickers with --from-screen, neither, --override without exactly one ticker, an --override path that is not a file): exit code 2`. The `override` decision's `--override path (only with exactly one ticker)` line gains `; not a file: exit code 2`. On `analyze-inputs.d2`, the `override_picked` node's line gets the same addition. The `.tla` comment gains `; an --override path that is not a file (override.is_file())`.

- [ ] **Step 2: Run the board and model tests, expect PASS.**

Run: `uv run pytest tests/unit/test_pipeline_models.py tests/unit/test_pipeline_subboards.py tests/unit/test_pipeline_diagram.py -q`

- [ ] **Step 3: Render** with d2 v0.9.0 on `PATH` (install it outside the repo with `curl -fsSL https://d2lang.com/install.sh | sh -s -- --version v0.9.0 --method standalone --prefix <dir>`): `docs/pipeline/build.sh`, then `python3 docs/pipeline/check.py`. Expect: check passes and only the analyze SVGs and `rendered.sha256` change.

- [ ] **Step 4: Check the models** with TLC as CI does (`.github/workflows/pipeline-diagram.yml`, job `models`) when Java and the launcher can be installed outside the repo. Otherwise CI's `models` job is the gate.

- [ ] **Step 5: Commit** `docs(#214): the atlas names an --override path that is not a file`
