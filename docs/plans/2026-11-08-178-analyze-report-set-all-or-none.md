# bot analyze writes a ticker's report set all-or-none — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: `.agents/skills/subagent-driven-development/SKILL.md` to implement this plan task-by-task; implementers write code with `.agents/skills/test-driven-development/SKILL.md`. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** In `bot analyze`, a ticker whose reports can't be rendered or written fails alone (exit 1, a message naming the ticker), leaves no partial or mixed report set behind, and the rest of the batch is still analysed.

**Architecture:** `_analyze_one` (`src/bot/cli.py:474-532`) renders the three reports in memory inside a `try` that maps `ValueError` to exit 1. It then hands them to a new `write_report_set` in a new module `src/bot/reporting/report_set.py`. That function creates the directory, writes every file to a temporary sibling, and renames the temporaries into place only once all of them have been written. On any failure it removes what it created, then raises `ReportWriteError`, which names the path. `_analyze_one` maps `ReportWriteError` to exit 1, and `analyze` keeps taking the worst code (`src/bot/cli.py:465-471`).

**Tech Stack:** Python 3, `pathlib`, `os.replace`, typer, pytest, mypy --strict, ruff.

**Spec:** GitHub issue #178 (nicolas-ricc/damodaran), specifically its triage "Agent Brief" comment (desired behaviour, key interfaces, acceptance criteria, out of scope).

## Global Constraints

- Per-ticker exit-code contract (brief): "0 ok, 1 cannot value / cannot write, 2 unknown ticker". No new exit code.
- "All three reports (Markdown, HTML, JSON) are rendered in memory before any file is touched."
- "A rendering error marks that ticker as failed with exit 1 and a message naming the ticker, and nothing is written for it."
- "Writes are all-or-none per ticker … none of that ticker's three report files for that run is left half-written or orphaned."
- "An `OSError` gives exit 1 with a message naming the ticker and the path, and the next ticker is analysed."
- "The command still exits with the worst per-ticker code."
- "If a previous complete report set for that ticker and date exists, a failed rewrite must not leave it mixed with new files. It may keep the old complete set or remove it."
- Success path unchanged: "same file names and locations, same 'Wrote …' lines and summary output".
- Out of scope: unreadable override files (#227), upstream sources of non-finite numbers, the TLA+ analyze model's file-system abstraction, and atomic writes for `bot screen`.
- Type hints everywhere. `uv run ruff check . && uv run mypy src && uv run pytest -q` must be green.
- Commits use Conventional Commits with the `(#178)` scope.

## Review Focus

1. **A rename fails after another rename succeeded.** The new `AAPL.md` is in place, but `AAPL.html` can't be renamed and the old one is still there, so the set is mixed. Expected: none of the three targets is left (the brief allows removing the old set). Test in Task 1: `test_a_failed_rename_removes_the_whole_set`.
2. **A temporary write fails while an old complete set exists.** Expected: the old set is untouched (the old three files, byte for byte), and no temporary file is left. Test in Task 1: `test_a_failed_write_keeps_the_previous_set`.
3. **File permissions on the success path.** The files used to be created by `Path.write_text`, so their mode came from the umask. `tempfile.mkstemp` would create them as `0600`, which changes the success path silently. Expected: the final files keep the mode a plain `write_text` gives them. Test in Task 1: `test_written_files_have_the_default_mode`.
4. **A leftover temporary from an earlier interrupted run** (`.AAPL.md.tmp`). Expected: it is overwritten, and the run succeeds and leaves no `.tmp` behind. Test in Task 1: `test_a_stale_temporary_is_overwritten`.
5. **A non-`OSError` exception during the writes** (for example `KeyboardInterrupt`). Expected: the temporaries are still removed and the exception propagates unchanged; only an `OSError` becomes `ReportWriteError`. Test in Task 1: `test_other_exceptions_clean_up_and_propagate`.

## Assumptions

- Only `ValueError` from the renderers is caught, which is the known case: `render_analysis_json` uses `allow_nan=False`. Any other exception from a renderer is a programming bug and keeps propagating. I rejected catching `Exception`, because it would hide bugs, and ruff's BLE rule flags it.
- Temporary names are deterministic, `.{name}.tmp` in the same directory, written with `Path.write_text` so the umask still decides the mode (Review Focus 3). Because the name starts with a dot and ends in `.tmp`, the web index's `*/analysis/*.json` glob (`src/bot/web/index.py:68`) never picks one up. Two concurrent `bot analyze` runs on the same ticker on the same day are not a case this single-user CLI meets. I rejected `mkstemp`, because of the mode change.
- Content is written with `Path.write_text(content)` and no explicit encoding, as today, so the bytes on disk don't change.
- Cleanup errors are suppressed (`unlink(missing_ok=True)` inside `contextlib.suppress(OSError)`): the original error is what gets reported.
- The messages are `"{TICKER}: cannot render report — {exc}"` and `"{TICKER}: cannot write report — {exc}"`, both on stderr. They follow the existing `"{TICKER}: cannot value — {exc}"` (`src/bot/cli.py:503`). `str(ReportWriteError)` is `"{path}: {reason}"`, where reason is `cause.strerror` or, failing that, `str(cause)`.
- A failure to create the directory is a `ReportWriteError` on the directory path, caught the same way (acceptance criterion 3).
- The `(* … *)` comments in `docs/pipeline/models/analyze.tla` (lines 720 and 874) that cite "three write_text calls" get their wording refreshed so they still describe the code. The model's actions and rules don't change (that is out of scope).

## File Structure

- Create `src/bot/reporting/report_set.py`, holding `ReportWriteError` and `write_report_set`.
- Create `tests/unit/test_report_set.py` for the unit tests of the writer.
- Modify `src/bot/cli.py` `_analyze_one` (render in a `try`, then write through `write_report_set`) and the docstrings of `analyze` and `_analyze_one`.
- Modify `tests/unit/test_cli_analyze.py` for the batch-level acceptance tests (stage-3 evals).
- Modify `docs/pipeline/models/analyze.tla`: the wording of the two citation comments only.

---

### Task 1: `write_report_set` writes a set of files all-or-none

**Files:**
- Create: `src/bot/reporting/report_set.py`
- Test: `tests/unit/test_report_set.py`

**Interfaces:**
- Produces:
  - `class ReportWriteError(Exception)` with `path: Path` and `__init__(self, path: Path, cause: OSError)`. `str()` gives `f"{path}: {cause.strerror or cause}"`, and it is raised `from cause`.
  - `write_report_set(out_dir: Path, files: Mapping[str, str]) -> list[Path]` returns `[out_dir / name for name in files]` in insertion order. Its steps:
    1. `out_dir.mkdir(parents=True, exist_ok=True)`.
    2. Write every `out_dir / f".{name}.tmp"`.
    3. `os.replace` each temporary onto `out_dir / name`.
  - Failure rules:
    - If step 1 or 2 fails, remove every temporary created so far and leave the targets alone.
    - If step 3 fails, remove every temporary and every target in `files`.
    - The cleanup runs for any exception (`except BaseException`). Only `OSError` is wrapped in `ReportWriteError`, carrying the path being created, written or renamed. Any other exception is re-raised as it is.

- [ ] **Step 1: Write the failing tests.** Inject failures by monkeypatching `Path.write_text`, `Path.mkdir` or `os.replace` (as imported in `bot.reporting.report_set`) so they raise `OSError(errno.ENOSPC, "No space left on device")` for one specific path.
  - `test_writes_every_file_and_no_temporary`: the files are `{"A.md": "m", "A.html": "h", "A.json": "j"}`. The return value equals the three paths in order, each file's content matches, and `sorted(p.name for p in out_dir.iterdir()) == ["A.html", "A.json", "A.md"]`.
  - `test_creates_missing_parent_directories`: `out_dir = tmp_path / "x" / "y"`.
  - `test_a_failed_write_writes_nothing`: writing `.A.html.tmp` fails. `ReportWriteError` is raised, `exc.path == out_dir / ".A.html.tmp"`, `"No space left on device" in str(exc)`, and `list(out_dir.iterdir()) == []`.
  - `test_a_failed_write_keeps_the_previous_set`: the old `A.md`, `A.html` and `A.json` are written first with content `"old"`, then the write of `.A.json.tmp` fails. All three still read `"old"`, and no `.tmp` is left.
  - `test_a_failed_rename_removes_the_whole_set`: an old set exists, and `os.replace` fails for the target `A.html`. Afterwards `list(out_dir.iterdir()) == []`, and `exc.path` is the path that was being renamed.
  - `test_a_failed_mkdir_is_a_report_write_error`: `Path.mkdir` raises `OSError(errno.EACCES, "Permission denied")`. `exc.path == out_dir`.
  - `test_written_files_have_the_default_mode`: the mode of each target equals the mode of a sibling written with a plain `write_text`.
  - `test_a_stale_temporary_is_overwritten`: `.A.md.tmp` exists beforehand with `"stale"`. After the call, `A.md` reads `"m"` and no `.tmp` remains.
  - `test_other_exceptions_clean_up_and_propagate`: the write of `.A.html.tmp` raises `KeyboardInterrupt`. `pytest.raises(KeyboardInterrupt)` catches it and `out_dir` is empty.
- [ ] **Step 2: Run the tests and check they fail.** Run `uv run pytest tests/unit/test_report_set.py -q`. Expected: collection fails with `ModuleNotFoundError: bot.reporting.report_set`.
- [ ] **Step 3: Implement `ReportWriteError` and `write_report_set`** in `src/bot/reporting/report_set.py`, following the Interfaces block. Give the module a docstring that says why the writes go through temporaries (#178).
- [ ] **Step 4: Run the tests and check they pass.** Run `uv run pytest tests/unit/test_report_set.py -q && uv run mypy src && uv run ruff check src tests`. Expected: everything passes.
- [ ] **Step 5: Commit** with the message `feat(#178): write_report_set writes a report set all-or-none`.

### Task 2: `_analyze_one` renders first, writes all-or-none, and fails per ticker

**Files:**
- Modify: `src/bot/cli.py` (`_analyze_one`, plus the docstrings of `analyze` and `_analyze_one`)
- Modify: `docs/pipeline/models/analyze.tla` (the wording of the citation comments at lines 720 and 874)
- Test: `tests/unit/test_cli_analyze.py` (the stage-3 evals, already committed and failing)

**Interfaces:**
- Consumes: `write_report_set` and `ReportWriteError` from Task 1.
- Produces: `_analyze_one` keeps its signature. It returns 1 when rendering raises `ValueError` or writing raises `ReportWriteError`, and in both cases it prints a single stderr line that starts with `"{TICKER}: "`.

- [ ] **Step 1: Check that the stage-3 evals fail on the current code.** They are in `tests/unit/test_cli_analyze.py`, and their names start with `test_batch_` (they cover the html `OSError`, the json render `ValueError`, the mkdir failure, all-or-none, and the unchanged success output). Run `uv run pytest tests/unit/test_cli_analyze.py -q -k batch_`. Expected: they FAIL. The failures should be the exception escaping the batch or the AAPL files being left behind.
- [ ] **Step 2: Implement.**
  1. Render the md, html and json into a dict `{f"{ticker}.md": …, f"{ticker}.html": …, f"{ticker}.json": …}` inside a `try`. On `except ValueError`, print `"{ticker}: cannot render report — {exc}"` and return 1.
  2. Call `write_report_set(out_dir, reports)`. On `except ReportWriteError`, print `"{ticker}: cannot write report — {exc}"` and return 1.
  3. Print `Wrote {path}` for each returned path, in order, and then the summary, exactly as today.
  4. Extend the `_analyze_one` docstring to cover the new code-1 cases. In the `analyze` docstring, add "a report that can't be rendered or written" to the per-ticker failures.
  5. In `analyze.tla`, change the two comments so they cite `write_report_set` instead of "three write_text calls".
- [ ] **Step 3: Run the tests and check they pass.** Run `uv run pytest tests/unit/test_cli_analyze.py tests/unit/test_pipeline_models.py tests/unit/test_analyze_model_replay.py -q`. Expected: everything passes.
- [ ] **Step 4: Run the full gate.** Run `uv run ruff check . && uv run mypy src && uv run pytest -q`, plus `python3 docs/leccion/check.py`, `python3 docs/pipeline/check.py` and `python3 docs/plano/build.py`. Expected: everything is green.
- [ ] **Step 5: Commit** with the message `fix(#178): a report that can't be rendered or written fails its ticker alone`.
