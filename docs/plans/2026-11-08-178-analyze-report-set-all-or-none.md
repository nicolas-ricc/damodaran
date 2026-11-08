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
- Type hints everywhere. `uv run ruff check . && uv run mypy src && uv run pytest -q` must be green at the end of each task. The stage-3 eval commit (`test(#178): evals`) is red by design.
- Commits use Conventional Commits with the `(#178)` scope.

## Review Focus

1. **A rename fails after another rename succeeded.** The new `AAPL.md` is in place, but `AAPL.html` can't be renamed and the old one is still there, so the set is mixed. Expected: none of the three targets is left (the brief allows removing the old set). Test in Task 1: `test_a_failed_rename_removes_the_whole_set`.
2. **A temporary write fails while an old complete set exists.** Expected: the old set is untouched (the old three files, byte for byte), and no temporary file is left. Test in Task 1: `test_a_failed_write_keeps_the_previous_set`.
3. **File permissions on the success path.** The files used to be created by `Path.write_text`, so their mode came from the umask. `tempfile.mkstemp` would create them as `0600`, which changes the success path silently. Expected: the final files keep the mode a plain `write_text` gives them. Test in Task 1: `test_written_files_have_the_default_mode`.
4. **A leftover temporary from an earlier interrupted run** (`.AAPL.md.tmp`). Expected: it is overwritten, and the run succeeds and leaves no `.tmp` behind. Test in Task 1: `test_a_stale_temporary_is_overwritten`.
5. **A non-`OSError` exception during the writes** (for example `KeyboardInterrupt`). Expected: the temporaries are still removed and the exception propagates unchanged; only an `OSError` becomes `ReportWriteError`. Test in Task 1: `test_other_exceptions_clean_up_and_propagate`.

## Assumptions

- Only `ValueError` from the renderers is caught, which is the known case: `render_analysis_json` uses `allow_nan=False`. Any other exception from a renderer is a programming bug and keeps propagating. I rejected catching `Exception`, because it would hide bugs, and ruff's BLE rule flags it.
- Temporary names are deterministic, `.{name}.tmp` in the same directory, written with `Path.write_text` so the umask still decides the mode (Review Focus 3). Because the name starts with a dot and ends in `.tmp`, the web index's `*/analysis/*.json` glob never picks one up. That glob (`src/bot/web/index.py:68`) is the only code in `src/` that enumerates an analysis directory (checked with grep). Two `bot analyze` runs can't overlap: `_open_db` opens the DuckDB file read-write (`src/bot/cli.py:66-71`), which holds DuckDB's exclusive file lock, and ADR 0001 says "No concurrent writes (acceptable — single user, CLI invocations are serial)". I rejected `mkstemp`, because of the mode change.
- Content is written with `Path.write_text(content)` and no explicit encoding, as today, so the bytes on disk don't change.
- Cleanup errors are suppressed (`unlink(missing_ok=True)` inside `contextlib.suppress(OSError)`): the original error is what gets reported.
- The messages are `"{TICKER}: cannot render report — {exc}"` and `"{TICKER}: cannot write report — {exc}"`, both on stderr. They follow the existing `"{TICKER}: cannot value — {exc}"` (`src/bot/cli.py:503`). `str(ReportWriteError)` is `"{path}: {reason}"`, where reason is `cause.strerror` or, failing that, `str(cause)`. `path` is the user-facing path: the report target (`AAPL.html`) when the write or rename for that file fails, or the directory when creating it fails. It is never the temporary, which is an implementation detail and is gone by the time the message is printed.
- A failure to create the directory is a `ReportWriteError` on the directory path, caught the same way (acceptance criterion 3).
- Rendering stays in the same order as today (md, html, json). Every `Wrote` line is printed only after all the writes, as today (`src/bot/cli.py:517-527`: the `mkdir` and the three writes are in `_analyze_one`, and the three `Wrote` lines come after the last write).
- Cleanup is best effort. If unlinking an already renamed target fails during cleanup (for example, the directory just turned read-only), the set may stay mixed, and nothing can undo a rename on a file system that refuses changes. The same holds for a process killed (SIGKILL, power loss) between two renames: three files can't be swapped in one atomic file-system operation. Both cases are left unguarded and untested. The brief's rule covers failures the process sees ("after any write failure").
- `write_report_set(out_dir, {})` creates the directory and returns `[]`. The CLI never calls it that way, so there is no test.
- Task 1's tests come before the implementation as a red step that fails rather than errors (`.agents/skills/test-driven-development/SKILL.md`: "Test fails (not errors)"). So stage 3 commits a skeleton `src/bot/reporting/report_set.py`: `ReportWriteError` fully defined, and `write_report_set` with its final signature and a body of `raise NotImplementedError`. The tests then fail on behaviour, not on an import.
- `docs/leccion/index.html:352` cites `src/bot/cli.py:516` for `bot.cli.screen`, and `docs/leccion/check.py` warns when a cited line moves. Task 2 updates that line number.
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
- Modify: `src/bot/reporting/report_set.py` (skeleton committed in stage 3)
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
  - `test_a_failed_write_writes_nothing`: writing `.A.html.tmp` fails. `ReportWriteError` is raised, `exc.path == out_dir / "A.html"`, `"No space left on device" in str(exc)`, and `list(out_dir.iterdir()) == []`.
  - `test_a_failed_write_keeps_the_previous_set`: the old `A.md`, `A.html` and `A.json` are written first with content `"old"`, then the write of `.A.json.tmp` fails. All three still read `"old"`, and no `.tmp` is left.
  - `test_a_failed_rename_removes_the_whole_set`: an old set exists, and `os.replace` fails for the target `A.html`. Afterwards `list(out_dir.iterdir()) == []`, and `exc.path == out_dir / "A.html"`.
  - `test_a_failed_mkdir_is_a_report_write_error`: `Path.mkdir` raises `OSError(errno.EACCES, "Permission denied")`. `exc.path == out_dir`.
  - `test_written_files_have_the_default_mode`: the mode of each target equals the mode of a sibling written with a plain `write_text`.
  - `test_a_stale_temporary_is_overwritten`: `.A.md.tmp` exists beforehand with `"stale"`. After the call, `A.md` reads `"m"` and no `.tmp` remains.
  - `test_other_exceptions_clean_up_and_propagate`: the write of `.A.html.tmp` raises `KeyboardInterrupt`. `pytest.raises(KeyboardInterrupt)` catches it and `out_dir` is empty.
- [ ] **Step 2: Run the tests and check they fail.** Run `uv run pytest tests/unit/test_report_set.py -q`. Expected: every test FAILS with `NotImplementedError` from the stage-3 skeleton.
- [ ] **Step 3: Implement `ReportWriteError` and `write_report_set`** in `src/bot/reporting/report_set.py`, following the Interfaces block. Give the module a docstring that says why the writes go through temporaries (#178).
- [ ] **Step 4: Run the tests and check they pass.** Run `uv run pytest tests/unit/test_report_set.py -q && uv run mypy src && uv run ruff check src tests`. Expected: everything passes.
- [ ] **Step 5: Commit** with the message `feat(#178): write_report_set writes a report set all-or-none`.

### Task 2: `_analyze_one` renders first, writes all-or-none, and fails per ticker

**Files:**
- Modify: `src/bot/cli.py` (`_analyze_one`, plus the docstrings of `analyze` and `_analyze_one`)
- Modify: `docs/pipeline/models/analyze.tla` (the wording of the citation comments at lines 720 and 874)
- Test: `tests/unit/test_cli_analyze.py` (the stage-3 evals, already committed and failing)

**Acceptance criteria → evals** (brief order):
1. AAPL's HTML write raises `OSError`: `test_batch_html_write_error_fails_the_ticker_alone`.
2. `render_analysis_json` raises `ValueError` for AAPL: `test_batch_json_render_error_fails_the_ticker_alone`.
3. Creating the output directory fails: `test_batch_mkdir_error_fails_each_ticker`.
4. The success path is unchanged: `test_batch_success_output_is_unchanged`, which compares the `Wrote` lines, their order and the file names.
5. All three or none: `test_batch_reports_are_all_or_none`, for every ticker in a batch where one fails.

The evals inject faults by monkeypatching `pathlib.Path.write_text` and `pathlib.Path.mkdir` globally, matching on the path's name. For the write, they match any name containing `AAPL.html`, so both the temporary and a direct write are caught whatever module performs it. The render fault is injected by patching `bot.cli.render_analysis_json`, the name `_analyze_one` calls. Assertions on stderr: it contains `AAPL`, `cannot write report` (or `cannot render report`), and, for writes, `AAPL.html`.

**Interfaces:**
- Consumes: `write_report_set` and `ReportWriteError` from Task 1.
- Produces: `_analyze_one` keeps its signature. It returns 1 when rendering raises `ValueError` or writing raises `ReportWriteError`, and in both cases it prints a single stderr line that starts with `"{TICKER}: "`.

- [ ] **Step 1: Check that the stage-3 evals fail on the current code.** They are in `tests/unit/test_cli_analyze.py`, and their names start with `test_batch_` (they cover the html `OSError`, the json render `ValueError`, the mkdir failure, all-or-none, and the unchanged success output). Run `uv run pytest tests/unit/test_cli_analyze.py -q -k batch_`. Expected: they FAIL. The failures should be the exception escaping the batch or the AAPL files being left behind.
- [ ] **Step 2: Implement.**
  1. Render the md, html and json into a dict `{f"{ticker}.md": …, f"{ticker}.html": …, f"{ticker}.json": …}` inside a `try`. On `except ValueError`, print `"{ticker}: cannot render report — {exc}"` and return 1.
  2. Call `write_report_set(out_dir, reports)`. On `except ReportWriteError`, print `"{ticker}: cannot write report — {exc}"` and return 1.
  3. Print `Wrote {path}` for each returned path, in order, and then the summary, exactly as today.
  4. Extend the `_analyze_one` docstring to cover the new code-1 cases. In the `analyze` docstring, add "a report that can't be rendered or written" to the per-ticker failures.
  5. Update the `src/bot/cli.py:<line>` citation for `bot.cli.screen` in `docs/leccion/index.html` to its new line.
  6. In `analyze.tla`, change the two comments so they cite `write_report_set` instead of "three write_text calls".
- [ ] **Step 3: Run the tests and check they pass.** Run `uv run pytest tests/unit/test_cli_analyze.py tests/unit/test_pipeline_models.py tests/unit/test_analyze_model_replay.py -q`. Expected: everything passes.
- [ ] **Step 4: Run the full gate.** Run `uv run ruff check . && uv run mypy src && uv run pytest -q`, plus `python3 docs/leccion/check.py`, `python3 docs/pipeline/check.py` and `python3 docs/plano/build.py`. Expected: everything is green.
- [ ] **Step 5: Commit** with the message `fix(#178): a report that can't be rendered or written fails its ticker alone`.

## Grilling

The grilling ran for one round. The revision kept the same seam and the same two tasks: it pinned the eval names, the path semantics and the red-step skeleton, so a second round was not needed. The griller (model: fable) asked 14 questions.

**Answers by source:**

| Source | Count | Questions | What backs the answer |
|---|---|---|---|
| ISSUE | 3 | Q1, Q2, Q9 | Agent Brief: acceptance criteria; "a message naming the ticker and the path"; "after any write failure" |
| CODE | 6 | Q3, Q6, Q7, Q8, Q11, Q13 | `src/bot/cli.py:66-71` and `:517-527`; `src/bot/web/index.py:68`; `tests/unit/test_pipeline_models.py:859-878` (it checks that the citations are present, not what they say); `docs/leccion/index.html:352`; `pyproject.toml` `[tool.ruff.lint] select`, which has no BLE or TRY |
| DOC | 2 | Q5, Q14 | ADR 0001 ("No concurrent writes … CLI invocations are serial"); the test-driven-development skill ("Test fails (not errors)") |
| NO SOURCE, technical assumption | 3 | Q4, Q10, Q12 | Decided below |

**Assumptions** (all are recorded under Assumptions above):
- Cleanup is best effort. A process kill between renames and a failed unlink during cleanup are left unguarded.
- `write_report_set` with an empty mapping creates the directory and returns `[]`.
- `ReportWriteError.path` is the report target or the directory, never the temporary.
- Stage 3 commits a skeleton that raises `NotImplementedError`, so the red step fails rather than errors.
- The leccion line citation for `bot.cli.screen` gets updated.

**Issues opened:** none, and no question was out of scope.

**Spec ambiguities:** none.
