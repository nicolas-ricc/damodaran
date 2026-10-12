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

# `-l` prints the stored crontab (exit 1 when there is none, or when
# FAKE_CRONTAB_BROKEN is set, with a different error), `-` stores stdin.
_FAKE_CRONTAB = """#!/usr/bin/env bash
case "$1" in
  -l)
    [ -z "${{FAKE_CRONTAB_BROKEN:-}}" ] || {{ echo "crontab: permission denied" >&2; exit 1; }}
    [ -f "{state}" ] || {{ echo "no crontab for $USER" >&2; exit 1; }}
    cat "{state}" ;;
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


def test_install_cron_aborts_when_the_crontab_cannot_be_read(
    repo: Path, cron_env: dict[str, str], crontab_state: Path
) -> None:
    crontab_state.write_text(_UNRELATED)

    result = _run(
        repo / "scripts" / "install_cron.sh", env={**cron_env, "FAKE_CRONTAB_BROKEN": "1"}
    )

    assert result.returncode == 1
    assert "permission denied" in result.stderr
    assert crontab_state.read_text() == _UNRELATED


def test_install_cron_rejects_unknown_arguments(
    repo: Path, cron_env: dict[str, str], crontab_state: Path
) -> None:
    result = _run(repo / "scripts" / "install_cron.sh", "--bogus", env=cron_env)
    assert result.returncode == 2
    assert not crontab_state.exists()


def test_install_cron_remove_with_no_crontab_writes_nothing(
    repo: Path, cron_env: dict[str, str], crontab_state: Path
) -> None:
    result = _run(repo / "scripts" / "install_cron.sh", "--remove", env=cron_env)

    assert result.returncode == 0, result.stderr
    assert not crontab_state.exists()


def test_install_cron_ignores_commented_and_lookalike_markers(
    repo: Path, cron_env: dict[str, str], crontab_state: Path
) -> None:
    disabled = "#0 9  * * 1-5  /old/scripts/daily.sh   # bot-daily\n"
    lookalike = "0 8 * * * /home/me/other.sh # bot-weekly-old\n"
    crontab_state.write_text(disabled + lookalike)
    script = repo / "scripts" / "install_cron.sh"

    assert _run(script, env=cron_env).returncode == 0
    assert crontab_state.read_text().splitlines() == [
        disabled.rstrip("\n"),
        lookalike.rstrip("\n"),
        *_cron_lines(repo.resolve()),
    ]

    assert _run(script, "--remove", env=cron_env).returncode == 0
    assert crontab_state.read_text() == lookalike


@pytest.mark.parametrize("args", [["--remove", "extra"], ["--bogus"]])
def test_install_cron_rejects_bad_arguments_before_reading_the_crontab(
    args: list[str], repo: Path, cron_env: dict[str, str], crontab_state: Path
) -> None:
    env = {**cron_env, "FAKE_CRONTAB_BROKEN": "1"}
    result = _run(repo / "scripts" / "install_cron.sh", *args, env=env)
    assert result.returncode == 2
    assert not crontab_state.exists()


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


def test_weekly_exits_with_screen_failure(repo: Path, recorder_bin: Path, calls: Path) -> None:
    result = _run(repo / "scripts" / "weekly.sh", env=_env(recorder_bin, FAKE_SCREEN_EXIT="4"))

    assert result.returncode == 4
    assert _calls(calls) == _WRAPPERS["weekly.sh"]


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
    assert "BOT_SEC_USER_AGENT (" not in result.stderr
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


def test_bootstrap_second_run_keeps_an_escaped_quote_value_byte_identical(
    repo: Path, recorder_bin: Path
) -> None:
    env = _env(recorder_bin, BOT_SEC_USER_AGENT='Jane "JD" Doe j@d.e', BOT_TIINGO_API_KEY="tk")
    assert _run(_bootstrap(repo), "--yes", "--skip-damodaran", env=env).returncode == 0
    before = (repo / ".env").read_bytes()

    assert _run(_bootstrap(repo), "--yes", "--skip-damodaran", env=env).returncode == 0

    assert (repo / ".env").read_bytes() == before


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


def test_bootstrap_yes_rejects_a_whitespace_only_value(repo: Path, recorder_bin: Path) -> None:
    env = _env(recorder_bin, BOT_SEC_USER_AGENT="   ", BOT_TIINGO_API_KEY="tk")

    result = _run(_bootstrap(repo), "--yes", "--skip-damodaran", env=env)

    assert result.returncode == 1
    assert "BOT_SEC_USER_AGENT" in result.stderr


def test_bootstrap_reprompts_on_a_whitespace_only_answer(repo: Path, recorder_bin: Path) -> None:
    (repo / ".env").write_text('BOT_SEC_USER_AGENT="A B a@b.c"\nBOT_TIINGO_API_KEY=\n')

    result = _run(_bootstrap(repo), "--skip-damodaran", env=_env(recorder_bin), stdin="   \ntk-4\n")

    assert result.returncode == 0, result.stderr
    assert dotenv_values(repo / ".env")["BOT_TIINGO_API_KEY"] == "tk-4"


def test_bootstrap_prompts_say_what_each_key_is(repo: Path, recorder_bin: Path) -> None:
    result = _run(
        _bootstrap(repo), "--skip-damodaran", env=_env(recorder_bin), stdin="A B a@b.c\ntk\n"
    )

    assert result.returncode == 0, result.stderr
    assert "Your Name you@example.com" in result.stderr
    assert "tiingo.com" in result.stderr


def test_bootstrap_keeps_the_padding_of_an_unquoted_empty_value(
    repo: Path, recorder_bin: Path
) -> None:
    (repo / ".env").write_text('BOT_SEC_USER_AGENT="A B a@b.c"\nBOT_TIINGO_API_KEY=     # key\n')
    env = _env(recorder_bin, BOT_TIINGO_API_KEY="tk")

    assert _run(_bootstrap(repo), "--yes", "--skip-damodaran", env=env).returncode == 0

    assert (repo / ".env").read_text().splitlines()[1] == 'BOT_TIINGO_API_KEY="tk"     # key'


def test_bootstrap_rejects_unknown_arguments(repo: Path, recorder_bin: Path) -> None:
    assert _run(_bootstrap(repo), "--bogus", env=_env(recorder_bin)).returncode == 2
    assert not (repo / ".env").exists()


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


def test_bootstrap_skip_damodaran_reminds_to_load_it_later(repo: Path, recorder_bin: Path) -> None:
    _filled_env(repo)
    out = _run(_bootstrap(repo), "--skip-damodaran", env=_env(recorder_bin)).stdout
    assert "uv run bot refresh --damodaran" in out


def test_bootstrap_exit_code_is_doctors(repo: Path, recorder_bin: Path) -> None:
    _filled_env(repo)
    env = _env(recorder_bin, FAKE_DOCTOR_EXIT="1")
    assert _run(_bootstrap(repo), "--skip-damodaran", env=env).returncode == 1


def test_bootstrap_stops_when_damodaran_fails(repo: Path, recorder_bin: Path, calls: Path) -> None:
    _filled_env(repo)
    result = _run(_bootstrap(repo), env=_env(recorder_bin, FAKE_REFRESH_EXIT="2"))
    assert result.returncode == 2
    assert _calls(calls) == ["run bot refresh --damodaran"]


def test_bootstrap_prints_the_tws_checklist_and_next_steps(repo: Path, recorder_bin: Path) -> None:
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
