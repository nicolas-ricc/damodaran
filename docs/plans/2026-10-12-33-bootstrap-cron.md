# Bootstrap script and cron install — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `scripts/bootstrap.sh` (first-run setup), `scripts/install_cron.sh` (idempotent crontab install/remove), and the `scripts/daily.sh` / `scripts/weekly.sh` cron wrappers, with pytest coverage and README docs.

**Architecture:** Four bash scripts under `scripts/`, each resolving the repo root from its own symlink-resolved location the way `scripts/price_fill.sh` does. No `src/` change. Tests in `tests/integration/test_scripts.py` copy `scripts/` and `.env.example` into `tmp_path` and drive the scripts with `subprocess`, putting fake `uv` / `crontab` executables first on `PATH` (or in `CRONTAB`). `shellcheck` comes from the `shellcheck-py` dev dependency so the lint check runs in CI without a system package.

**Tech Stack:** bash, pytest, `uv`, `shellcheck-py`, `python-dotenv` (already a dependency; used in tests to parse the written `.env`).

**Spec:** GitHub issue #33 (nicolas-ricc/damodaran), "[M6.4] Bootstrap script + cron install". Context: `scripts/price_fill.sh`, `src/bot/config.py`, `src/bot/cli.py` (`doctor`, `refresh`), `.env.example`, README "Portfolio sync → Prerequisites", ADR 0004, ADR 0007. The issue supersedes spec §9.3 and §13.1 where they differ.

## Global Constraints

- Required keys are exactly `BOT_SEC_USER_AGENT` and `BOT_TIINGO_API_KEY`. Nothing else is prompted for (no FMP, no Stooq, no IBKR).
- Prompts use plain bash `read`; no TUI libraries.
- Cron lines, verbatim (`<repo>` = absolute, symlink-resolved checkout root):
  `0 9  * * 1-5  <repo>/scripts/daily.sh   # bot-daily`
  `0 10 * * 6    <repo>/scripts/weekly.sh  # bot-weekly`
- `daily.sh`: `uv run bot refresh --prices --fx && uv run bot portfolio`, log `.cache/daily.log`.
- `weekly.sh`: `uv run bot refresh --all && uv run bot screen --preset damodaran_value`, log `.cache/weekly.log`.
- Log header per run: `=== <date -Is> run ===` (as `price_fill.sh`).
- The crontab command is `${CRONTAB:-crontab}`.
- Bootstrap's exit code is `bot doctor`'s exit code. Bootstrap does not run `refresh --fundamentals` or `--prices`.
- All four scripts executable (git mode 100755) and `shellcheck` clean.
- Tests: `tests/integration/test_scripts.py`, `subprocess`, temporary copy of the repo, no network.
- Out of scope: Python CLI file logging, backups, new `bot` subcommands, extending `bot doctor`, provider-aware bootstrap, adding `price_fill.sh` to `install_cron.sh`, `bootstrap --uninstall`.
- `uv run pytest -q`, `uv run ruff check .`, `uv run mypy src` pass.

## Decisions (technical assumptions, declared)

1. **Fake `uv` in tests.** Running the real `uv run` inside a temp copy would build a fresh virtualenv (slow, may touch the network). Tests put a fake `uv` first on `PATH`. Two flavours: a *shim* that runs `uv run <cmd> ...` as `<test venv>/bin/<cmd> ...` (real `bot doctor`, used for the acceptance test that the DB is created and doctor passes), and a *recorder* that logs its argv to a file and exits with `FAKE_<SUBCOMMAND>_EXIT` (default 0), used everywhere else. The installed `bot` reads `.env` from its cwd (`env_file=".env"` in `config.py`), which is the temp copy because every script `cd`s into its repo root.
2. **Wrappers append to `PATH` instead of prepending.** `price_fill.sh` prepends `$HOME/.local/bin:/usr/local/bin:/usr/bin`, which would shadow a test's fake `uv`. Appending still finds `uv` under cron's minimal `PATH=/usr/bin:/bin`, and lets tests override. `daily.sh`/`weekly.sh` call `uv` by name.
3. **`.env.example`'s placeholder user agent becomes empty.** It currently seeds `BOT_SEC_USER_AGENT="Nombre Apellido email@example.com"`, which is non-empty, so a fresh `.env` would never be prompted for it and acceptance criterion 1 ("creates `.env` with both values") would fail. The line becomes `BOT_SEC_USER_AGENT=""` with the expected format in its comment. Nothing in `src/` or `tests/` reads `.env.example` (`grep -rn env.example src tests` is empty).
4. **What "empty" means.** A key is set when a non-commented `KEY=` line exists whose value, after stripping one pair of surrounding `"` or `'` quotes (or, if unquoted, an inline `# comment`) and whitespace, is non-empty. The last such line wins, as in python-dotenv.
5. **How a value is written.** Always double-quoted, with `\` and `"` backslash-escaped (python-dotenv decodes both inside double quotes). An existing `KEY=` line is replaced in place, keeping its trailing inline comment; an absent key is appended on its own line at the end. `.env` is only rewritten when at least one key changes, so a no-op run leaves it byte-identical.
6. **Interactive edge cases.** An empty answer re-prompts. EOF on stdin exits 1 naming the variable. Prompt text goes to stderr via `printf` (bash's `read -p` prints nothing when stdin is not a terminal, which would hide the prompt from tests and pipes).
7. **Failure ordering.** `--yes` checks every missing key before writing, so a failure leaves `.env` as it was after seeding. A failing `bot refresh --damodaran` stops bootstrap with that exit code (`set -e`); doctor does not run.
8. **Quickstart numbering.** Collapsing README steps 2–4 into one bootstrap step renumbers the later steps: `refresh --fundamentals`/`--prices` becomes 3, `screen` 4, `analyze` 5. Bootstrap's next-steps block names the commands and points at "README → Quickstart, steps 3–5"; the issue's "steps 5–7" refers to today's numbering of the same commands.
9. **Unknown arguments** exit 2 with a usage line, in both `bootstrap.sh` and `install_cron.sh`.

## Review Focus

1. A `BOT_SEC_USER_AGENT` with spaces (the normal case: `Jane Doe jane@example.com`) or a `"` must round-trip: `dotenv_values(.env)` returns exactly what was typed. Task 3 tests both.
2. A `.env` whose last line has no trailing newline, with a key absent: the appended key must land on its own line, not glued to the last one. Task 3.
3. A user with no crontab at all (`crontab -l` exits 1 with "no crontab for ..."): install still works, and the result has no leading blank line. Task 1.
4. Invoking a script through a symlink from another directory (how a user might put it on `PATH`): the repo root, and the cron line's path, is still the real checkout. Task 1.
5. `bot portfolio` failing (TWS down) after a good refresh: the daily wrapper logs it and exits with that code; a failing refresh short-circuits portfolio. Task 2.

---

## File Structure

- Create `scripts/install_cron.sh` — crontab install/remove.
- Create `scripts/daily.sh`, `scripts/weekly.sh` — cron wrappers.
- Create `scripts/bootstrap.sh` — first-run setup.
- Create `tests/integration/test_scripts.py` — all tests for the above.
- Modify `pyproject.toml` / `uv.lock` — add `shellcheck-py` to the `dev` group.
- Modify `.env.example` — empty `BOT_SEC_USER_AGENT` (Decision 3).
- Modify `README.md` — Quickstart steps 2–4, new "Scheduling" subsection.
- Modify `docs/plano/estado.py` — `bootstrap` and `cron` inventory rows, cron brecha.

## Shared test helpers (written in Task 1, used by every task)

Top of `tests/integration/test_scripts.py`:

```python
"""The shell scripts under ``scripts/`` (#33), driven via ``subprocess``.

Each test runs the scripts from a temporary copy of the repo with fake ``uv``
and ``crontab`` executables, so nothing touches the network, the real crontab
or the developer's ``.env``.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from dotenv import dotenv_values

REPO_ROOT = Path(__file__).resolve().parents[2]
VENV_BIN = Path(sys.executable).parent
SCRIPTS = ["bootstrap.sh", "install_cron.sh", "daily.sh", "weekly.sh"]

# `uv run <cmd> ...` -> `<test venv>/bin/<cmd> ...`: real `bot`, no new venv.
_UV_SHIM = f"""#!/usr/bin/env bash
[ "$1" = run ] || exit 64
shift
exec "{VENV_BIN}/$1" "${{@:2}}"
"""

# Logs argv, prints a line, exits with FAKE_<SUBCOMMAND>_EXIT (default 0),
# where SUBCOMMAND is the bot subcommand: `uv run bot refresh ...` -> REFRESH.
_UV_RECORDER = """#!/usr/bin/env bash
echo "$*" >> "{calls}"
echo "fake uv: $*"
var="FAKE_${{3^^}}_EXIT"
exit "${{!var:-0}}"
"""

# `-l` prints the stored crontab (exit 1 when there is none), `-` stores stdin.
_FAKE_CRONTAB = """#!/usr/bin/env bash
case "$1" in
  -l) [ -f "{state}" ] || {{ echo "no crontab for $USER" >&2; exit 1; }}; cat "{state}" ;;
  -) cat > "{state}" ;;
  *) exit 64 ;;
esac
"""


def _write_exe(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    path.chmod(0o755)
    return path


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """A minimal copy of the checkout: the scripts and the .env template."""
    root = tmp_path / "repo"
    shutil.copytree(REPO_ROOT / "scripts", root / "scripts")
    shutil.copy2(REPO_ROOT / ".env.example", root / ".env.example")
    return root


@pytest.fixture
def calls(tmp_path: Path) -> Path:
    return tmp_path / "uv_calls.txt"


@pytest.fixture
def recorder_bin(tmp_path: Path, calls: Path) -> Path:
    bin_dir = tmp_path / "bin-recorder"
    _write_exe(bin_dir / "uv", _UV_RECORDER.format(calls=calls))
    return bin_dir


@pytest.fixture
def shim_bin(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin-shim"
    _write_exe(bin_dir / "uv", _UV_SHIM)
    return bin_dir


def _env(bin_dir: Path, **extra: str) -> dict[str, str]:
    """The test process's environment without any BOT_* key, fakes first on PATH."""
    env = {k: v for k, v in os.environ.items() if not k.startswith("BOT_")}
    env["PATH"] = f"{bin_dir}{os.pathsep}{env['PATH']}"
    env.update(extra)
    return env


def _run(
    script: Path, *args: str, env: dict[str, str], stdin: str | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(script), *args],
        env=env,
        input=stdin,
        stdin=None if stdin is not None else subprocess.DEVNULL,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _calls(path: Path) -> list[str]:
    return path.read_text().splitlines() if path.exists() else []
```

---

### Task 1: `install_cron.sh`, shellcheck in the dev group, lint test

**Files:**
- Create: `scripts/install_cron.sh` (mode 755)
- Create: `tests/integration/test_scripts.py` (helpers above + tests below)
- Modify: `pyproject.toml` (`[dependency-groups] dev`), `uv.lock`

**Interfaces:**
- Consumes: nothing.
- Produces: the helpers above; `install_cron.sh [--remove]` reading `CRONTAB`.

- [ ] **Step 1: Add the dev dependency.** `uv add --dev shellcheck-py`. Check `"$(dirname "$(uv run python -c 'import sys; print(sys.executable)')")/shellcheck" --version` prints a version.

- [ ] **Step 2: Write the failing tests** (after the helpers):

```python
@pytest.mark.parametrize("name", SCRIPTS)
def test_script_is_executable_and_shellcheck_clean(name: str) -> None:
    script = REPO_ROOT / "scripts" / name
    assert os.access(script, os.X_OK), f"{name} is not executable"
    result = subprocess.run(
        [str(VENV_BIN / "shellcheck"), str(script)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


def _cron_lines(root: Path) -> list[str]:
    return [
        f"0 9  * * 1-5  {root}/scripts/daily.sh   # bot-daily",
        f"0 10 * * 6    {root}/scripts/weekly.sh  # bot-weekly",
    ]


@pytest.fixture
def crontab_state(tmp_path: Path) -> Path:
    return tmp_path / "crontab.txt"


@pytest.fixture
def cron_env(tmp_path: Path, crontab_state: Path) -> dict[str, str]:
    fake = _write_exe(tmp_path / "fake-crontab", _FAKE_CRONTAB.format(state=crontab_state))
    return _env(tmp_path, CRONTAB=str(fake))


_UNRELATED = "# my own jobs\n7 * * * * /home/me/repo/scripts/price_fill.sh # bot-price-fill\n@reboot echo hi\n"


def test_install_cron_with_no_crontab_adds_exactly_the_two_lines(
    repo: Path, cron_env: dict[str, str], crontab_state: Path
) -> None:
    result = _run(repo / "scripts" / "install_cron.sh", env=cron_env)
    assert result.returncode == 0, result.stderr
    assert crontab_state.read_text().splitlines() == _cron_lines(repo.resolve())


def test_install_cron_is_idempotent_and_preserves_unrelated_lines(
    repo: Path, cron_env: dict[str, str], crontab_state: Path
) -> None:
    crontab_state.write_text(_UNRELATED)
    script = repo / "scripts" / "install_cron.sh"

    assert _run(script, env=cron_env).returncode == 0
    first = crontab_state.read_text()
    assert first.splitlines() == _UNRELATED.splitlines() + _cron_lines(repo.resolve())

    assert _run(script, env=cron_env).returncode == 0
    assert crontab_state.read_text() == first


def test_install_cron_remove_drops_only_the_tagged_lines(
    repo: Path, cron_env: dict[str, str], crontab_state: Path
) -> None:
    crontab_state.write_text(_UNRELATED)
    script = repo / "scripts" / "install_cron.sh"
    assert _run(script, env=cron_env).returncode == 0

    result = _run(script, "--remove", env=cron_env)

    assert result.returncode == 0, result.stderr
    assert crontab_state.read_text() == _UNRELATED


def test_install_cron_remove_without_tagged_lines_changes_nothing(
    repo: Path, cron_env: dict[str, str], crontab_state: Path
) -> None:
    crontab_state.write_text(_UNRELATED)
    assert _run(repo / "scripts" / "install_cron.sh", "--remove", env=cron_env).returncode == 0
    assert crontab_state.read_text() == _UNRELATED


def test_install_cron_through_a_symlink_uses_the_real_checkout(
    repo: Path, tmp_path: Path, cron_env: dict[str, str], crontab_state: Path
) -> None:
    link = tmp_path / "elsewhere" / "install-bot-cron"
    link.parent.mkdir()
    link.symlink_to(repo / "scripts" / "install_cron.sh")

    assert _run(link, env=cron_env).returncode == 0
    assert crontab_state.read_text().splitlines() == _cron_lines(repo.resolve())


def test_install_cron_rejects_unknown_arguments(
    repo: Path, cron_env: dict[str, str], crontab_state: Path
) -> None:
    result = _run(repo / "scripts" / "install_cron.sh", "--bogus", env=cron_env)
    assert result.returncode == 2
    assert not crontab_state.exists()
```

- [ ] **Step 3: Run, expect FAIL** (`install_cron.sh` missing): `uv run pytest tests/integration/test_scripts.py -q -k install_cron`.

- [ ] **Step 4: Implement `scripts/install_cron.sh`**, then `chmod +x`:

```bash
#!/usr/bin/env bash
# Install the bot's daily and weekly cron jobs, or remove them with --remove.
#
# Each line carries a marker comment (# bot-daily, # bot-weekly), so a second
# install adds nothing and --remove drops exactly those lines; every other
# crontab line is kept as is. Logs land in .cache/daily.log and .cache/weekly.log.
#
# Usage: scripts/install_cron.sh [--remove]
# CRONTAB overrides the crontab command (tests point it at a fake).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd -P)"
REPO="$(dirname "$SCRIPT_DIR")"
CRONTAB="${CRONTAB:-crontab}"

MARKERS=("# bot-daily" "# bot-weekly")
LINES=(
  "0 9  * * 1-5  $REPO/scripts/daily.sh   # bot-daily"
  "0 10 * * 6    $REPO/scripts/weekly.sh  # bot-weekly"
)

# No crontab yet is not an error: start from an empty one.
current="$("$CRONTAB" -l 2>/dev/null || true)"

case "${1:-}" in
  "")
    new="$current"
    for i in "${!MARKERS[@]}"; do
      if ! grep -qF -- "${MARKERS[$i]}" <<<"$current"; then
        new="${new:+$new$'\n'}${LINES[$i]}"
        echo "added: ${LINES[$i]}"
      else
        echo "already installed: ${MARKERS[$i]}"
      fi
    done
    ;;
  --remove)
    new="$(grep -vF -e "${MARKERS[0]}" -e "${MARKERS[1]}" <<<"$current" || true)"
    echo "removed: ${MARKERS[*]}"
    ;;
  *)
    echo "usage: $0 [--remove]" >&2
    exit 2
    ;;
esac

printf '%s\n' "$new" | "$CRONTAB" -
```

Note: when `new` is empty (`--remove` on a crontab holding only our lines), `printf '%s\n' ""` stores a single blank line; that is harmless to cron.

- [ ] **Step 5: Run, expect PASS** for the `install_cron` tests and `test_script_is_executable_and_shellcheck_clean[install_cron.sh]`; the other three parametrized cases still fail (their scripts come in Tasks 2–4).

- [ ] **Step 6: Commit.** `git add scripts/install_cron.sh tests/integration/test_scripts.py pyproject.toml uv.lock && git commit -m "feat(#33): install_cron.sh with marker-tagged daily and weekly lines"`

---

### Task 2: `daily.sh` and `weekly.sh` cron wrappers

**Files:**
- Create: `scripts/daily.sh`, `scripts/weekly.sh` (mode 755)
- Test: `tests/integration/test_scripts.py`

**Interfaces:**
- Consumes: helpers (`repo`, `recorder_bin`, `calls`, `_env`, `_run`, `_calls`).
- Produces: `scripts/daily.sh`, `scripts/weekly.sh` (no args), referenced by Task 1's cron lines.

- [ ] **Step 1: Write the failing tests**:

```python
_WRAPPERS = {
    "daily.sh": ["run bot refresh --prices --fx", "run bot portfolio"],
    "weekly.sh": ["run bot refresh --all", "run bot screen --preset damodaran_value"],
}


@pytest.mark.parametrize("name", list(_WRAPPERS))
def test_wrapper_runs_both_commands_and_logs_with_a_header(
    name: str, repo: Path, recorder_bin: Path, calls: Path
) -> None:
    result = _run(repo / "scripts" / name, env=_env(recorder_bin))

    assert result.returncode == 0, result.stderr
    assert _calls(calls) == _WRAPPERS[name]
    log = (repo / ".cache" / name.replace(".sh", ".log")).read_text()
    assert log.startswith("=== ") and " run ===\n" in log
    assert f"fake uv: {_WRAPPERS[name][1]}" in log


@pytest.mark.parametrize("name", list(_WRAPPERS))
def test_wrapper_failing_refresh_skips_the_second_command(
    name: str, repo: Path, recorder_bin: Path, calls: Path
) -> None:
    result = _run(repo / "scripts" / name, env=_env(recorder_bin, FAKE_REFRESH_EXIT="3"))

    assert result.returncode == 3
    assert _calls(calls) == _WRAPPERS[name][:1]


def test_daily_exits_with_portfolio_failure_and_logs_it(
    repo: Path, recorder_bin: Path, calls: Path
) -> None:
    result = _run(repo / "scripts" / "daily.sh", env=_env(recorder_bin, FAKE_PORTFOLIO_EXIT="1"))

    assert result.returncode == 1
    assert _calls(calls) == _WRAPPERS["daily.sh"]
    assert "fake uv: run bot portfolio" in (repo / ".cache" / "daily.log").read_text()


def test_wrapper_appends_to_the_log(repo: Path, recorder_bin: Path) -> None:
    script = repo / "scripts" / "weekly.sh"
    assert _run(script, env=_env(recorder_bin)).returncode == 0
    assert _run(script, env=_env(recorder_bin)).returncode == 0
    assert (repo / ".cache" / "weekly.log").read_text().count(" run ===") == 2


def test_wrapper_run_from_another_directory_logs_in_the_checkout(
    repo: Path, tmp_path: Path, recorder_bin: Path
) -> None:
    subprocess.run(
        [str(repo / "scripts" / "daily.sh")],
        cwd=tmp_path,
        env=_env(recorder_bin),
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=True,
    )
    assert (repo / ".cache" / "daily.log").exists()
    assert not (tmp_path / ".cache").exists()
```

- [ ] **Step 2: Run, expect FAIL**: `uv run pytest tests/integration/test_scripts.py -q -k 'wrapper or daily'`.

- [ ] **Step 3: Implement `scripts/daily.sh`** (then `chmod +x`):

```bash
#!/usr/bin/env bash
# Daily cron job (weekdays 09:00, installed by scripts/install_cron.sh):
# refresh prices and FX, then sync the IBKR portfolio. Fundamentals are
# quarterly, so they are refreshed weekly, not here.
#
# Output appends to .cache/daily.log; the exit code is the bot's. `bot
# portfolio` fails while TWS is not running and logged in — that is an
# expected, logged outcome.
set -uo pipefail

# Repo root = parent of this script's directory (resolve symlinks for cron).
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd -P)"
REPO="$(dirname "$SCRIPT_DIR")"
cd "$REPO" || exit 1

# cron's PATH is minimal — make sure uv is findable. Appended, so a uv
# already on PATH wins.
export PATH="$PATH:$HOME/.local/bin:/usr/local/bin:/usr/bin"

mkdir -p "$REPO/.cache"
LOG="$REPO/.cache/daily.log"

{
  echo "=== $(date -Is) run ==="
  uv run bot refresh --prices --fx && uv run bot portfolio
} >> "$LOG" 2>&1
```

The script's exit status is the brace group's, which is that of the `&&` list: the first failing command's code, or `bot portfolio`'s.

- [ ] **Step 4: Implement `scripts/weekly.sh`** the same way:

```bash
#!/usr/bin/env bash
# Weekly cron job (Saturdays 10:00, installed by scripts/install_cron.sh):
# refresh every source, then run the Damodaran value screen.
#
# Output appends to .cache/weekly.log; the exit code is the bot's.
set -uo pipefail

# Repo root = parent of this script's directory (resolve symlinks for cron).
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd -P)"
REPO="$(dirname "$SCRIPT_DIR")"
cd "$REPO" || exit 1

# cron's PATH is minimal — make sure uv is findable. Appended, so a uv
# already on PATH wins.
export PATH="$PATH:$HOME/.local/bin:/usr/local/bin:/usr/bin"

mkdir -p "$REPO/.cache"
LOG="$REPO/.cache/weekly.log"

{
  echo "=== $(date -Is) run ==="
  uv run bot refresh --all && uv run bot screen --preset damodaran_value
} >> "$LOG" 2>&1
```

- [ ] **Step 5: Run, expect PASS** for the wrapper tests and the `daily.sh`/`weekly.sh` shellcheck cases.

- [ ] **Step 6: Commit.** `git add scripts/daily.sh scripts/weekly.sh tests/integration/test_scripts.py && git commit -m "feat(#33): daily and weekly cron wrappers"`

---

### Task 3: `bootstrap.sh` — `.env` as a key-value store

**Files:**
- Create: `scripts/bootstrap.sh` (mode 755)
- Modify: `.env.example` (line 2)
- Test: `tests/integration/test_scripts.py`

**Interfaces:**
- Consumes: helpers.
- Produces: `scripts/bootstrap.sh [--yes] [--skip-damodaran]`, ending (in this task) with `exit 0` after the `.env` step; Task 4 appends the setup steps after the `.env` block.

- [ ] **Step 1: Change `.env.example` line 2** to:

```
BOT_SEC_USER_AGENT=""             # required by SEC fair use: "Your Name you@example.com"
```

- [ ] **Step 2: Write the failing tests** (they use the recorder `uv`, so they stay valid once Task 4 adds `bot doctor`):

```python
_UA = "Jane Doe jane@example.com"


def _bootstrap(repo: Path) -> Path:
    return repo / "scripts" / "bootstrap.sh"


def test_bootstrap_yes_creates_env_from_example_with_both_values(
    repo: Path, recorder_bin: Path
) -> None:
    env = _env(recorder_bin, BOT_SEC_USER_AGENT=_UA, BOT_TIINGO_API_KEY="tk-123")

    result = _run(_bootstrap(repo), "--yes", "--skip-damodaran", env=env)

    assert result.returncode == 0, result.stderr
    values = dotenv_values(repo / ".env")
    assert values["BOT_SEC_USER_AGENT"] == _UA
    assert values["BOT_TIINGO_API_KEY"] == "tk-123"
    # Every other line of the template survives, in order.
    example = (repo / ".env.example").read_text().splitlines()
    written = (repo / ".env").read_text().splitlines()
    assert len(written) == len(example)
    for before, after in zip(example, written, strict=True):
        if not before.startswith(("BOT_SEC_USER_AGENT=", "BOT_TIINGO_API_KEY=")):
            assert after == before


_PARTIAL = (
    "# my settings\n"
    'BOT_SEC_USER_AGENT="Already Here a@b.c"   # keep me\n'
    "\n"
    'BOT_TIINGO_API_KEY=""           # free key at tiingo.com\n'
    "# BOT_DB_PATH=./bot.duckdb\n"
)


def test_bootstrap_prompts_only_for_the_empty_key(repo: Path, recorder_bin: Path) -> None:
    (repo / ".env").write_text(_PARTIAL)

    result = _run(_bootstrap(repo), "--skip-damodaran", env=_env(recorder_bin), stdin="tk-999\n")

    assert result.returncode == 0, result.stderr
    assert "BOT_TIINGO_API_KEY" in result.stderr
    assert "BOT_SEC_USER_AGENT:" not in result.stderr
    assert "BOT_SEC_USER_AGENT already set" in result.stdout
    assert (repo / ".env").read_text() == _PARTIAL.replace(
        'BOT_TIINGO_API_KEY=""', 'BOT_TIINGO_API_KEY="tk-999"'
    )


def test_bootstrap_yes_fills_only_the_empty_key_from_the_environment(
    repo: Path, recorder_bin: Path
) -> None:
    (repo / ".env").write_text(_PARTIAL)
    env = _env(recorder_bin, BOT_SEC_USER_AGENT="Other Person o@p.q", BOT_TIINGO_API_KEY="tk-env")

    result = _run(_bootstrap(repo), "--yes", "--skip-damodaran", env=env)

    assert result.returncode == 0, result.stderr
    assert (repo / ".env").read_text() == _PARTIAL.replace(
        'BOT_TIINGO_API_KEY=""', 'BOT_TIINGO_API_KEY="tk-env"'
    )


def test_bootstrap_yes_with_a_key_missing_everywhere_exits_1_naming_it(
    repo: Path, recorder_bin: Path, calls: Path
) -> None:
    env = _env(recorder_bin, BOT_SEC_USER_AGENT=_UA)

    result = _run(_bootstrap(repo), "--yes", "--skip-damodaran", env=env)

    assert result.returncode == 1
    assert "BOT_TIINGO_API_KEY" in result.stderr
    assert _calls(calls) == []


def test_bootstrap_with_everything_set_never_prompts_or_rewrites(
    repo: Path, recorder_bin: Path
) -> None:
    text = 'BOT_SEC_USER_AGENT="A B a@b.c"\nBOT_TIINGO_API_KEY=tk  # no trailing newline'
    (repo / ".env").write_text(text)

    # stdin is /dev/null: any prompt would hit EOF and exit 1.
    result = _run(_bootstrap(repo), "--skip-damodaran", env=_env(recorder_bin))

    assert result.returncode == 0, result.stderr
    assert (repo / ".env").read_text() == text


def test_bootstrap_appends_an_absent_key_on_its_own_line(repo: Path, recorder_bin: Path) -> None:
    (repo / ".env").write_text('BOT_SEC_USER_AGENT="A B a@b.c"')  # no trailing newline
    env = _env(recorder_bin, BOT_TIINGO_API_KEY="tk-new")

    assert _run(_bootstrap(repo), "--yes", "--skip-damodaran", env=env).returncode == 0

    assert (repo / ".env").read_text() == (
        'BOT_SEC_USER_AGENT="A B a@b.c"\nBOT_TIINGO_API_KEY="tk-new"\n'
    )


def test_bootstrap_round_trips_quotes_and_backslashes(repo: Path, recorder_bin: Path) -> None:
    tricky = 'Jane "JD" Doe c:\\path jane@example.com'
    env = _env(recorder_bin, BOT_SEC_USER_AGENT=tricky, BOT_TIINGO_API_KEY="tk")

    assert _run(_bootstrap(repo), "--yes", "--skip-damodaran", env=env).returncode == 0

    assert dotenv_values(repo / ".env")["BOT_SEC_USER_AGENT"] == tricky


def test_bootstrap_reprompts_on_an_empty_answer(repo: Path, recorder_bin: Path) -> None:
    (repo / ".env").write_text('BOT_SEC_USER_AGENT="A B a@b.c"\nBOT_TIINGO_API_KEY=\n')

    result = _run(_bootstrap(repo), "--skip-damodaran", env=_env(recorder_bin), stdin="\n\ntk-3\n")

    assert result.returncode == 0, result.stderr
    assert result.stderr.count("BOT_TIINGO_API_KEY") >= 3
    assert dotenv_values(repo / ".env")["BOT_TIINGO_API_KEY"] == "tk-3"


def test_bootstrap_prompt_at_eof_exits_1_naming_the_key(repo: Path, recorder_bin: Path) -> None:
    (repo / ".env").write_text('BOT_SEC_USER_AGENT="A B a@b.c"\nBOT_TIINGO_API_KEY=\n')

    result = _run(_bootstrap(repo), "--skip-damodaran", env=_env(recorder_bin))

    assert result.returncode == 1
    assert "BOT_TIINGO_API_KEY" in result.stderr


def test_bootstrap_rejects_unknown_arguments(repo: Path, recorder_bin: Path) -> None:
    assert _run(_bootstrap(repo), "--bogus", env=_env(recorder_bin)).returncode == 2
    assert not (repo / ".env").exists()
```

- [ ] **Step 3: Run, expect FAIL**: `uv run pytest tests/integration/test_scripts.py -q -k bootstrap`.

- [ ] **Step 4: Implement `scripts/bootstrap.sh`** (then `chmod +x`):

```bash
#!/usr/bin/env bash
# First-run setup for a checkout: .env, Damodaran benchmarks, health check.
#
# Usage: scripts/bootstrap.sh [--yes] [--skip-damodaran]
#   --yes             never prompt: take missing required keys from the
#                     environment, and exit 1 naming any that is not there.
#   --skip-damodaran  skip `bot refresh --damodaran` (bot doctor then creates the DB).
#
# Safe to re-run: keys already set in .env are never asked for again and the
# file is only rewritten when a value changes. Exit code is `bot doctor`'s.
set -euo pipefail

# Repo root = parent of this script's directory (resolve symlinks).
SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "$0")")" && pwd -P)"
REPO="$(dirname "$SCRIPT_DIR")"
cd "$REPO"

REQUIRED_KEYS=(BOT_SEC_USER_AGENT BOT_TIINGO_API_KEY)
YES=0
SKIP_DAMODARAN=0
for arg in "$@"; do
  case "$arg" in
    --yes) YES=1 ;;
    --skip-damodaran) SKIP_DAMODARAN=1 ;;
    *)
      echo "usage: $0 [--yes] [--skip-damodaran]" >&2
      exit 2
      ;;
  esac
done

ENV_FILE="$REPO/.env"
if [ ! -f "$ENV_FILE" ]; then
  cp "$REPO/.env.example" "$ENV_FILE"
  echo "Created .env from .env.example"
fi

# True when KEY has a non-blank value in .env (last assignment wins, as in
# python-dotenv). Quotes and an unquoted inline comment are not part of it.
is_set() {
  local line value
  line="$(grep -E "^$1=" "$ENV_FILE" | tail -n 1)" || return 1
  value="${line#*=}"
  if [[ $value =~ ^\"([^\"]*)\" || $value =~ ^\'([^\']*)\' ]]; then
    value="${BASH_REMATCH[1]}"
  else
    value="${value%%#*}"
  fi
  [[ -n "${value//[[:space:]]/}" ]]
}

# Sets ANSWER to a non-empty line read from stdin; exits 1 at EOF.
ask() {
  ANSWER=""
  while [ -z "$ANSWER" ]; do
    printf '%s: ' "$1" >&2
    if ! IFS= read -r ANSWER; then
      echo >&2
      echo "bootstrap: no value given for $1" >&2
      exit 1
    fi
  done
}

declare -A NEW=()
for key in "${REQUIRED_KEYS[@]}"; do
  if is_set "$key"; then
    echo "$key already set in .env — skipping"
  elif [ "$YES" = 1 ]; then
    if [ -z "${!key:-}" ]; then
      echo "bootstrap: $key is empty in .env and not set in the environment" >&2
      exit 1
    fi
    NEW[$key]="${!key}"
  else
    ask "$key"
    NEW[$key]="$ANSWER"
  fi
done

# Rewrite .env with the new values: a KEY= line is replaced in place (its
# inline comment kept), an absent key is appended; every other line is copied.
if [ "${#NEW[@]}" -gt 0 ]; then
  tmp="$(mktemp "$ENV_FILE.XXXXXX")"
  declare -A written=()
  while IFS= read -r line || [ -n "$line" ]; do
    for key in "${!NEW[@]}"; do
      if [[ $line =~ ^$key=(\"[^\"]*\"|\'[^\']*\'|[^#]*)(.*)$ ]]; then
        rest="${BASH_REMATCH[2]}"
        # An unquoted value's [^#]* ate the spaces before '#'; dotenv needs one.
        [[ $rest == \#* ]] && rest=" $rest"
        value="${NEW[$key]//\\/\\\\}"
        line="$key=\"${value//\"/\\\"}\"$rest"
        written[$key]=1
      fi
    done
    printf '%s\n' "$line"
  done < "$ENV_FILE" > "$tmp"
  for key in "${!NEW[@]}"; do
    if [ -z "${written[$key]:-}" ]; then
      value="${NEW[$key]//\\/\\\\}"
      printf '%s="%s"\n' "$key" "${value//\"/\\\"}" >> "$tmp"
    fi
  done
  mv "$tmp" "$ENV_FILE"
  echo "Wrote ${!NEW[*]} to .env"
fi

exit 0
```

Implementation notes:
- `${!NEW[@]}` iteration order is unspecified in bash; appended keys may come out in either order. The tests that append only append one key.
- An unquoted `KEY=value  # c` line: `[^#]*` consumes the spaces before `#`, so `rest` is re-prefixed with one space (python-dotenv only treats `#` as a comment after whitespace). Quoted values keep their spacing because the quoted group ends at the closing quote.
- `mktemp` next to `.env` keeps the `mv` atomic on the same filesystem.

- [ ] **Step 5: Run, expect PASS** for the `bootstrap` tests of this task; `test_script_is_executable_and_shellcheck_clean[bootstrap.sh]` passes.

- [ ] **Step 6: Commit.** `git add .env.example scripts/bootstrap.sh tests/integration/test_scripts.py && git commit -m "feat(#33): bootstrap.sh fills the required .env keys"`

---

### Task 4: `bootstrap.sh` — Damodaran, IBKR checklist, doctor, next steps

**Files:**
- Modify: `scripts/bootstrap.sh` (replace the final `exit 0`)
- Test: `tests/integration/test_scripts.py`

**Interfaces:**
- Consumes: Task 3's `bootstrap.sh`; helpers incl. `shim_bin`.
- Produces: nothing new.

- [ ] **Step 1: Write the failing tests**:

```python
def test_bootstrap_fresh_copy_creates_env_and_db_and_doctor_passes(
    repo: Path, shim_bin: Path
) -> None:
    env = _env(shim_bin, BOT_SEC_USER_AGENT=_UA, BOT_TIINGO_API_KEY="tk-123")

    result = _run(_bootstrap(repo), "--yes", "--skip-damodaran", env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "All checks OK." in result.stdout
    assert (repo / "bot.duckdb").is_file()
    values = dotenv_values(repo / ".env")
    assert values["BOT_SEC_USER_AGENT"] == _UA
    assert values["BOT_TIINGO_API_KEY"] == "tk-123"


def test_bootstrap_second_run_is_a_no_op(repo: Path, shim_bin: Path) -> None:
    env = _env(shim_bin, BOT_SEC_USER_AGENT=_UA, BOT_TIINGO_API_KEY="tk-123")
    assert _run(_bootstrap(repo), "--yes", "--skip-damodaran", env=env).returncode == 0
    before = (repo / ".env").read_bytes()

    result = _run(_bootstrap(repo), "--yes", "--skip-damodaran", env=env)

    assert result.returncode == 0, result.stdout + result.stderr
    assert (repo / ".env").read_bytes() == before
    assert "BOT_SEC_USER_AGENT already set" in result.stdout
    assert "BOT_TIINGO_API_KEY already set" in result.stdout


def _filled_env(repo: Path) -> None:
    (repo / ".env").write_text('BOT_SEC_USER_AGENT="A B a@b.c"\nBOT_TIINGO_API_KEY="tk"\n')


def test_bootstrap_refreshes_damodaran_then_runs_doctor(
    repo: Path, recorder_bin: Path, calls: Path
) -> None:
    _filled_env(repo)

    result = _run(_bootstrap(repo), env=_env(recorder_bin))

    assert result.returncode == 0, result.stderr
    assert _calls(calls) == ["run bot refresh --damodaran", "run bot doctor"]


def test_bootstrap_skip_damodaran_runs_only_doctor(
    repo: Path, recorder_bin: Path, calls: Path
) -> None:
    _filled_env(repo)
    assert _run(_bootstrap(repo), "--skip-damodaran", env=_env(recorder_bin)).returncode == 0
    assert _calls(calls) == ["run bot doctor"]


def test_bootstrap_exit_code_is_doctors(repo: Path, recorder_bin: Path) -> None:
    _filled_env(repo)
    env = _env(recorder_bin, FAKE_DOCTOR_EXIT="1")
    assert _run(_bootstrap(repo), "--skip-damodaran", env=env).returncode == 1


def test_bootstrap_stops_when_damodaran_fails(
    repo: Path, recorder_bin: Path, calls: Path
) -> None:
    _filled_env(repo)
    result = _run(_bootstrap(repo), env=_env(recorder_bin, FAKE_REFRESH_EXIT="2"))
    assert result.returncode == 2
    assert _calls(calls) == ["run bot refresh --damodaran"]


def test_bootstrap_prints_the_tws_checklist_and_next_steps(
    repo: Path, recorder_bin: Path
) -> None:
    _filled_env(repo)

    out = _run(_bootstrap(repo), "--skip-damodaran", env=_env(recorder_bin)).stdout

    for needle in (
        "Enable ActiveX and Socket Clients",
        "127.0.0.1",
        "Read-Only API",
        "BOT_IBKR_HOST=127.0.0.1",
        "BOT_IBKR_PORT=7496",
        "BOT_IBKR_CLIENT_ID=1",
        "IbkrClient.from_settings(load_settings()).accounts()",
        "bot portfolio",
        "uv run bot refresh --fundamentals",
        "uv run bot refresh --prices --only-missing",
        "scripts/price_fill.sh",
        "uv run bot screen",
        "uv run bot analyze",
    ):
        assert needle in out, needle
```

- [ ] **Step 2: Run, expect FAIL**: `uv run pytest tests/integration/test_scripts.py -q -k bootstrap`.

- [ ] **Step 3: Replace the trailing `exit 0` of `scripts/bootstrap.sh`** with:

```bash
# No explicit DB step: refresh --damodaran and doctor both open BOT_DB_PATH and
# apply the schema, so whichever runs first creates the file.
if [ "$SKIP_DAMODARAN" = 0 ]; then
  echo
  echo "Loading Damodaran sector benchmarks (bot refresh --damodaran)..."
  uv run bot refresh --damodaran
fi

cat <<'EOF'

IBKR portfolio sync (bot portfolio) talks to a running TWS or IB Gateway over
its local socket. Bootstrap does not connect to it; set it up once in TWS:
  1. File -> Global Configuration -> API -> Settings: tick
     "Enable ActiveX and Socket Clients".
  2. Add 127.0.0.1 to Trusted IPs.
  3. Recommended: also tick "Read-Only API".
Connection defaults (override in .env):
  BOT_IBKR_HOST=127.0.0.1
  BOT_IBKR_PORT=7496        # live TWS; 7497 paper TWS, 4001/4002 IB Gateway live/paper
  BOT_IBKR_CLIENT_ID=1
Smoke test, with TWS running and logged in:
  uv run python -c "from bot.config import load_settings; from bot.ingest.ibkr import IbkrClient; print(IbkrClient.from_settings(load_settings()).accounts())"
Until TWS is running and logged in, `bot portfolio` fails.

EOF

status=0
uv run bot doctor || status=$?

cat <<'EOF'

Next steps (README -> Quickstart, steps 3-5):
  uv run bot refresh --fundamentals              # the universe, from SEC EDGAR
  uv run bot refresh --prices --only-missing     # Tiingo prices; re-run per hourly window,
                                                 # or arm the scripts/price_fill.sh drip
  uv run bot screen --preset damodaran_value --top 10
  uv run bot analyze --from-screen
Scheduled daily/weekly runs: scripts/install_cron.sh
EOF

exit "$status"
```

- [ ] **Step 4: Run, expect PASS**: whole `tests/integration/test_scripts.py`.

- [ ] **Step 5: Commit.** `git add scripts/bootstrap.sh tests/integration/test_scripts.py && git commit -m "feat(#33): bootstrap.sh loads Damodaran, prints the TWS checklist and runs doctor"`

---

### Task 5: README and the status plan

**Files:**
- Modify: `README.md` (Quickstart steps 2–4; new "Scheduling" section after Quickstart, before "Portfolio sync")
- Modify: `docs/plano/estado.py` (rows `bootstrap`, `cron`; brecha "Cree que es operable por cron.")

**Interfaces:** none.

- [ ] **Step 1: Replace README Quickstart steps 2–4** (from `2. \`cp .env.example .env\`` through `4. \`uv run bot refresh --damodaran\`...`) with:

```markdown
2. `scripts/bootstrap.sh` — first-run setup. Creates `.env` from `.env.example` and asks for
   the two required keys, `BOT_SEC_USER_AGENT` (your name + email) and `BOT_TIINGO_API_KEY` (a
   free token from [tiingo.com](https://www.tiingo.com/)); keys already set are never asked
   again. Then loads Damodaran's US sector benchmarks (`bot refresh --damodaran`), prints the
   TWS checklist for `bot portfolio`, and runs `bot doctor` — its exit code is bootstrap's. Safe
   to re-run. `--yes` never prompts and takes the keys from the environment (exit 1 naming any
   that is missing); `--skip-damodaran` skips the download. The default provider is
   `edgar-tiingo` — SEC EDGAR for fundamentals (no key) + Tiingo for EOD prices. See
   [ADR 0007](docs/adr/0007-free-data-stack-edgar-stooq.md).

   <details>
   <summary>By hand</summary>

   1. `cp .env.example .env` and fill in `BOT_SEC_USER_AGENT` and `BOT_TIINGO_API_KEY`.
   2. `uv run bot doctor` — verify setup.
   3. `uv run bot refresh --damodaran` — US sector benchmarks from Damodaran (once yearly).

   </details>
```

and renumber the following items: `5.` → `3.`, `6.` → `4.`, `7.` → `5.`, `8.` → `6.`.

- [ ] **Step 2: Add the "Scheduling" section** right before `## Portfolio sync — Interactive Brokers (M5)`:

````markdown
## Scheduling

`scripts/install_cron.sh` adds two jobs to your crontab:

```
0 9  * * 1-5  <repo>/scripts/daily.sh   # bot-daily
0 10 * * 6    <repo>/scripts/weekly.sh  # bot-weekly
```

- **Daily** (weekdays 09:00): `bot refresh --prices --fx && bot portfolio`. Fundamentals are
  quarterly and are not refreshed daily. `bot portfolio` fails while TWS is not running and
  logged in; that is logged, not a bug.
- **Weekly** (Saturday 10:00): `bot refresh --all && bot screen --preset damodaran_value`.

Each run appends to `.cache/daily.log` / `.cache/weekly.log` under a `=== <timestamp> run ===`
header; the job's exit code is the bot's. Running the installer again adds nothing; lines are
found by their `# bot-daily` / `# bot-weekly` markers, and every other crontab line is kept.
`scripts/install_cron.sh --remove` drops just those two lines. The hourly `price_fill.sh` drip is
separate (Quickstart step 3).
````

- [ ] **Step 3: Update `docs/plano/estado.py`.** Replace the two rows:

```python
 ("bootstrap", "scripts/bootstrap.sh", "hecho", "scripts/bootstrap.sh",
  "Crea .env desde .env.example y pide solo las dos claves obligatorias que falten (BOT_SEC_USER_AGENT, BOT_TIINGO_API_KEY); --yes las toma del entorno. Carga Damodaran, imprime el checklist de TWS y corre bot doctor, cuyo exit code es el suyo. Re-ejecutable sin cambios. Tests en tests/integration/test_scripts.py (#33)."),
 ("cron", "scripts/install_cron.sh", "hecho", "scripts/install_cron.sh; scripts/daily.sh; scripts/weekly.sh",
  "Instala dos líneas marcadas (# bot-daily, # bot-weekly), idempotente; --remove borra solo esas. daily.sh (precios + FX, luego portfolio) y weekly.sh (refresh --all, luego screen) loguean a .cache/*.log con el exit code del bot (#33)."),
```

and the brecha text for `"Cree que es operable por cron."` with:

```python
  "Ya hay bootstrap, instalador de cron y wrappers que loguean a .cache/*.log (#33), pero el log es la salida de consola tal cual: sin log estructurado del CLI ni respaldo. La ADR 0004 eligió TWS justamente por la compatibilidad con cron."),
```

Leave `AUDITADO_EN` / `AUDITADO_EL` alone: this is a targeted update of two rows, not a full re-audit.

- [ ] **Step 4: Rebuild the plans.** `python3 docs/plano/build.py && python3 docs/plano/build_estado.py` — both exit 0 (outputs are git-ignored).

- [ ] **Step 5: Full gate.** `uv run pytest -q && uv run ruff check . && uv run mypy src`.

- [ ] **Step 6: Commit.** `git add README.md docs/plano/estado.py && git commit -m "docs(#33): README bootstrap and scheduling, estado rows"`
