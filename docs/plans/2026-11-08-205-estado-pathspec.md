# build_estado.py counts commits on the top-level `src` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `desfasaje()` in `docs/plano/build_estado.py` counts the commits since `estado.AUDITADO_EN` that touch the repository's top-level `src/`, wherever the script is run from. When the count is above 0, the console `AVISO` is printed and the `viejo` banner is rendered.

**Architecture:** A one-token fix: the pathspec `'src'` becomes the top-level pathspec `':/src'`. Git still runs with `cwd=AQUI`. The tests drive the real `desfasaje()`, `aviso_desfasaje()` and `main()` against a throwaway git repository. The seam is the module global `AQUI`: a test points it at `<tmp repo>/docs/plano`, which reproduces the real layout. `main()` already writes `AQUI / 'estado.html'`, so the test's output lands in the temp repo and never touches the checkout.

**Tech Stack:** Python stdlib (`subprocess`, `pathlib`), pytest, git.

**Spec:** GitHub issue #205 (`gh api repos/nicolas-ricc/damodaran/issues/205/comments`). The triage comment's **Agent Brief** is the binding spec.

## Global Constraints

- The count covers "commits since `AUDITADO_EN` that touch the repository's top-level `src`". The pathspec is `':/src'`, which the brief offers as "a top-level pathspec". Verified on master: from `docs/plano/`, `-- src` gives 0 and `-- :/src` gives 29.
- "When git is unavailable, the current graceful fallback is kept": `desfasaje()` returns `None` on a non-zero exit, `OSError`, `ValueError` or `SubprocessError`, and `aviso_desfasaje()` returns `""` for `None` or `0`.
- Out of scope (brief): re-auditing or bumping `AUDITADO_EN`, and changing estado content (#277, #280). `estado.py` is not touched.
- `estado.html` is gitignored generated output (`docs/plano/README.md`, "Construir"; `.gitignore:32`). It is not regenerated into the commit.
- `uv run ruff check . && uv run mypy src && uv run pytest -q` green. The ruff config covers `docs/plano/*.py` and `tests/`.

## Assumptions (declared)

- **Seam.** The test loads `build_estado.py` with `importlib`, like `tests/unit/test_dilution_ma_docs.py:33-42`, under a unique module name. It monkeypatches `mod.AQUI` and `mod.estado.AUDITADO_EN`. `desfasaje()` reads both at call time. No new parameter is added to production code.
- **Temp repo.** `git init` in `tmp_path / "repo"`. Commits use `git -c user.name=t -c user.email=t@example.com -c commit.gpgsign=false commit`. The repo has a `docs/plano/` directory containing a tracked file, so `AQUI` exists. The audited commit's SHA comes from `git rev-parse HEAD` after the first commit.
- **"From any cwd".** Git always runs with `cwd=AQUI`, so the process cwd never reaches git. The test still pins the criterion: it `monkeypatch.chdir`s to the repo root, to `docs/plano`, and to a directory outside any repository, and asserts the same count each time.
- **Git unavailable.** The test sets `PATH` to an empty temp dir. `subprocess.run(['git', ...])` then raises `FileNotFoundError` (an `OSError`), so `desfasaje()` returns `None` and no banner is rendered. That behaviour already exists; the test pins it.
- **Docs.** The `desfasaje()` docstring and `docs/plano/README.md` ("El aviso de foto vieja") gain one sentence: the count uses the repository's `src/`, whatever the cwd. CONTEXT.md already says "touched `src/`" and does not change.
- **Plan location `docs/plans/`** follows the recent issue plans.

## Acceptance criteria → tests

All of these are in `tests/unit/test_estado_desfasaje.py`.

- "count above 0 and that the warning and banner appear": `test_src_commit_after_audit_is_counted` (`desfasaje() == 1`), `test_banner_rendered_when_src_moved` (`'class="viejo"'` in `aviso_desfasaje()` and in the generated `estado.html`), and `test_console_warning_printed_when_src_moved` (`"AVISO"` in the `main()` stdout).
- "count is 0, with no banner, when no `src` commit follows": `test_docs_only_commit_after_audit_is_not_counted` (`desfasaje() == 0`, `aviso_desfasaje() == ""`, and no `class="viejo"` and no `AVISO` from `main()`).
- "same count from any cwd": `test_count_is_the_same_from_any_cwd`.
- "existing docs tests pass": the full suite. Graceful fallback: `test_git_unavailable_gives_no_banner` and `test_unknown_audit_commit_gives_no_banner`.

## Review Focus

1. **A `src` file nested deeper, `src/bot/x.py`.** It must count. The temp repo's src commit writes `src/bot/x.py`, not `src/x.py`, so the test covers the real layout.
2. **A directory named `src` under `docs/plano/`.** It must NOT count: the old relative pathspec would match it. The docs-only commit also adds `docs/plano/src/nota.md`, so the 0 case fails under the old relative pathspec.
3. **Several `src` commits.** The count must be exact (2 commits → 2), not just above 0. `test_src_commit_after_audit_is_counted` makes two src commits and asserts `2`.
4. **Audit SHA not in history (shallow CI clone).** `rev-list` exits non-zero, so `None` and no banner: `test_unknown_audit_commit_gives_no_banner`.
5. **The test must not write into the checkout.** `main()` writes `AQUI / 'estado.html'`, and with `AQUI` patched that is inside `tmp_path`. The test asserts that the file exists there.

---

### Task 1: Top-level pathspec in `desfasaje()`, with tests

**Files:**
- Modify: `docs/plano/build_estado.py:204-218` (`desfasaje`)
- Modify: `docs/plano/README.md` ("El aviso de foto vieja")
- Create: `tests/unit/test_estado_desfasaje.py`

**Interfaces:**
- Consumes: `build_estado.desfasaje() -> int | None`, `build_estado.aviso_desfasaje() -> str` and `build_estado.main() -> None`, all existing and unchanged in signature. Module globals: `AQUI: pathlib.Path` and `estado.AUDITADO_EN: str`.
- Produces: nothing new.

- [ ] **Step 1: Write the failing tests.** Fixture `repo(tmp_path) -> tuple[Path, str]`: it builds the temp repo with a first commit (`docs/plano/README.md` and `src/bot/__init__.py`) and returns `(root, audited_sha)`. Helper `_commit(root, path, text)` writes the file, then runs `git add -A` and `git commit`. Fixture `build_estado(monkeypatch, repo)` loads the module, sets `AQUI = root / "docs" / "plano"` and `estado.AUDITADO_EN = audited_sha`, and returns the module. Tests:
  - `test_src_commit_after_audit_is_counted`: two commits under `src/bot/`. Assert `desfasaje() == 2`.
  - `test_banner_rendered_when_src_moved`: one src commit. Assert `'class="viejo"' in aviso_desfasaje()`, then run `main()` and assert that `(AQUI / "estado.html")` contains `class="viejo"`.
  - `test_console_warning_printed_when_src_moved`: one src commit, then `main()`. Assert `"AVISO"` in `capsys` stdout.
  - `test_docs_only_commit_after_audit_is_not_counted`: commit `docs/plano/src/nota.md` and `docs/x.md`. Assert `desfasaje() == 0` and `aviso_desfasaje() == ""`. Run `main()` and assert no `class="viejo"` in the html and no `"AVISO"` in stdout.
  - `test_count_is_the_same_from_any_cwd`: one src commit. For each cwd in `[root, root/"docs"/"plano", tmp_path/"elsewhere"]`, `monkeypatch.chdir`. Assert that every result equals `1`.
  - `test_git_unavailable_gives_no_banner`: `monkeypatch.setenv("PATH", str(empty_dir))`. Assert `desfasaje() is None` and `aviso_desfasaje() == ""`.
  - `test_unknown_audit_commit_gives_no_banner`: `estado.AUDITADO_EN = "0" * 40`. Assert `desfasaje() is None` and `aviso_desfasaje() == ""`.

- [ ] **Step 2: Run them and confirm they fail.** Run: `uv run pytest tests/unit/test_estado_desfasaje.py -q`. Expected: the counted, banner, warning and any-cwd tests FAIL, because the count is 0. The docs-only test also FAILS: the relative pathspec counts `docs/plano/src/nota.md` as 1. The git-unavailable and unknown-commit tests PASS, because they pin existing behaviour.

- [ ] **Step 3: Fix the pathspec.** In `desfasaje()`, `'src'` becomes `':/src'`. Add one docstring sentence saying the pathspec is top-level (`:/`) because git resolves a bare `src` against `cwd=AQUI`, that is `docs/plano/src`. In `docs/plano/README.md` "El aviso de foto vieja", add one sentence: the count uses the repository's `src/` (pathspec `:/src`), wherever you run the build from.

- [ ] **Step 4: Run them and confirm they pass.** Run: `uv run pytest tests/unit/test_estado_desfasaje.py -q`. Expected: 7 passed. Then run `uv run ruff check . && uv run mypy src && uv run pytest -q`, which must be green.

- [ ] **Step 5: Commit.** `git add docs/plano/build_estado.py docs/plano/README.md tests/unit/test_estado_desfasaje.py && git commit -m "fix(#205): build_estado counts commits on the top-level src"`
