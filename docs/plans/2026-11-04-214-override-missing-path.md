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
4. The refusal happens before the DB is opened: `_open_db()` → `connect()` creates the DuckDB file (`src/bot/storage/db.py:29-31`), so the missing-path test runs without a DB and asserts that none was created. A report check alone would not tell the difference, because an empty DB exits 2 as an unknown ticker. Test in Task 1.
5. A relative path resolves against the current directory, the same way `read_text()` resolves it today. No change and no test.

## Assumptions

- A directory gets the same `no such file.` message as a missing path: the brief fixes one message and calls both "not an existing file". Rejected: a second message (`is a directory`).
- The path is echoed as typer received it (`str(override)`), not resolved, so the user sees their own typo.
- `--override` is a plain `typer.Option(None, "--override")` (`src/bot/cli.py:388-393`). The check is hand-written, not `typer.Option(exists=True, dir_okay=False)`, because the brief fixes the message `--override <path>: no such file.` and its placement "after the existing argument checks": typer's own validation would run before the many-tickers check and print click's wording.
- Symlinks follow `Path.is_file()`: the brief does not mention them, and `is_file()` answers "is an existing file" the way `read_text()` will see it.
- An existing file that cannot be read (`PermissionError`), and a conventional `TICKER.yaml` that is a directory, crash outside the `ValueError` catch today. Both are out of scope (the conventional path keeps its behaviour, and the brief only asks about a path that does not exist or is a directory). They are follow-up #227.
- The `--override` help text does not change: the brief names only stderr and the atlas.
- `docs/plano/estado.py:136` cites `cli.py:477`. The new check moves that line by about four. `estado.html` is hand-curated, and this issue does not re-audit it, so the citation is left alone. No test checks `docs/plano` line numbers. `build_estado.py` only warns when `src/` moved after the audit commit (`docs/plano/build_estado.py:205-229`), and the same is true of every merge touching `src/`. The leccion cites only `assumptions.py:706`, which does not move.

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

- [ ] **Step 1: Write the failing tests.** Set `BOT_DB_PATH`, `BOT_REPORTS_DIR`, `BOT_SEC_USER_AGENT` as `test_analyze_explicit_override_with_many_tickers_is_rejected` does. Use `CliRunner()` and read stderr through `result.output`. Under click 8.4.1 (`uv.lock`) `output` interleaves stderr, and `test_analyze_from_screen_without_runs_fails_clearly` already asserts an `err=True` message that way.

```python
def test_analyze_explicit_override_that_does_not_exist_is_rejected(tmp_path, monkeypatch) -> None:
    # No DB is created: the refusal must come before _open_db(), which creates the file.
    missing = tmp_path / "does" / "not" / "exist.yaml"
    result = runner.invoke(app, ["analyze", "AAPL", "--override", str(missing)])
    assert result.exit_code == 2
    assert f"--override {missing}: no such file." in result.output
    assert not db_path.exists()
    assert list(reports_dir.glob("*/analysis/*")) == []


def test_analyze_explicit_override_that_is_a_directory_is_rejected(tmp_path, monkeypatch) -> None:
    # DB seeded with _seed(conn, "AAPL"), so without the check AAPL would be valued.
    directory = tmp_path / "assumptions"; directory.mkdir()
    result = runner.invoke(app, ["analyze", "AAPL", "--override", str(directory)])
    assert result.exit_code == 2
    assert f"--override {directory}: no such file." in result.output
    assert list(reports_dir.glob("*/analysis/*")) == []
```

Extend `test_analyze_explicit_override_with_many_tickers_is_rejected` with `assert "exactly one ticker" in result.output`.

- [ ] **Step 2: Run them, expect the two new tests to FAIL.** Missing path: exit 2 from the unknown-ticker path (the DB is empty), but no `no such file.` message and the DB file is created. Directory: `load_override` passes `exists()` and `read_text()` raises `IsADirectoryError`, so the exit is 1 with an exception, not 2.

Run: `uv run pytest tests/unit/test_cli_analyze.py -q -k "override"`

- [ ] **Step 3: Implement** the check in `analyze`, written like the three checks above it (`typer.echo(..., err=True)`, `raise typer.Exit(code=2)`), using `override.is_file()`. Leave the `--override` help text and the docstring as they are.

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
  Labels in `analyze.view.js` carry no underscore and no camelCase word (`test_labels_name_no_code`).
  On `analyze.d2`: the errors bullet becomes `bad arguments (tickers with --from-screen, neither, --override without exactly one ticker, an --override path that is not a file): exit code 2`. The `override` decision's `--override path (only with exactly one ticker)` line gains `; not a file: exit code 2`. On `analyze-inputs.d2`, the `override_picked` node's line gets the same addition. The `.tla` comment gains `; an --override path that is not a file (override.is_file())`.

- [ ] **Step 2: Run the board and model tests, expect PASS.**

Run: `uv run pytest tests/unit/test_pipeline_models.py tests/unit/test_pipeline_subboards.py tests/unit/test_pipeline_diagram.py -q`

- [ ] **Step 3: Render** with d2 v0.9.0 on `PATH` (install it outside the repo with `curl -fsSL https://d2lang.com/install.sh | sh -s -- --version v0.9.0 --method standalone --prefix <dir>`): `docs/pipeline/build.sh`, then `python3 docs/pipeline/check.py`. Expect: check passes. `rendered.sha256` is the hash of the `.d2` sources only (`check.py: source_hash`). Commit the SVGs of the two edited boards and `rendered.sha256`. If `build.sh` re-renders any other SVG differently, `git checkout` it: its source did not change. If d2 v0.9.0 cannot be installed, the edited sources would fail `check.py` and CI, so the stage stops blocked instead of committing.

- [ ] **Step 4: Check the models** with TLC as CI does (`.github/workflows/pipeline-diagram.yml`, job `models`) when Java and the launcher can be installed outside the repo. Otherwise CI's `models` job is the gate.

- [ ] **Step 5: Commit** `docs(#214): the atlas names an --override path that is not a file`

## Grilling

- Rounds: 1 (the revisions are clarifications, not new steps or a different seam). Questions: 16.
- Sources: CODE 11 (Q1 `src/bot/cli.py:470-481`, the conventional path is substituted inside `_analyze_one`, so `analyze`'s `override` is still the raw option; Q2; Q3 `uv.lock` click 8.4.1 + `tests/unit/test_cli_analyze.py:258-271`; Q5 `src/bot/cli.py:388-393`; Q8 `src/bot/storage/db.py:29-31`; Q9; Q10 `tests/unit/test_pipeline_diagram.py:1603-1607`, phrases kept; Q11; Q12 `docs/pipeline/check.py:191`; Q13 `.github/workflows/pipeline-diagram.yml`; Q14 `tests/unit/test_pipeline_models.py:547-571`), ISSUE 2 (Q4 criteria; Q5 the verbatim message), technical assumption 3 (Q6 path echoed as `str(Path)`, the same as the absolute test path; Q15 help text unchanged; Q16 symlinks follow `is_file()`), out of scope 1 (Q7 unreadable file → #227).
- Q4: the criteria are (1) missing path exits 2, writes no report and names the path → Task 1 tests; (2) existing file as today → `test_analyze_applies_override`; (3) no conventional file as today → `test_analyze_writes_report`; (4) directory exits 2 → Task 1; (5) pipeline check, TLC and the full suite → Task 2 Steps 2-4 and the stage-end suite.
- Q9: `CliRunner` runs in pytest's working directory, but the many-tickers check fires before any path check, so a stray `x.yaml` cannot change which check fires. The added message assertion pins that.
- Spec ambiguities: none. Issues opened: #227.
