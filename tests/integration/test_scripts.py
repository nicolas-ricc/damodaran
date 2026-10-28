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
SCRIPTS = ["bootstrap.sh", "install_cron.sh", "daily.sh", "weekly.sh", "publish_site.sh"]

# `uv run <cmd> ...` -> `<test venv>/bin/<cmd> ...`: real `bot`, no new venv.
_UV_SHIM = f"""#!/usr/bin/env bash
[ "$1" = run ] || exit 64
shift
exec "{VENV_BIN}/$1" "${{@:2}}"
"""

# Logs argv, prints a line, exits with FAKE_<SUBCOMMAND>_EXIT (default 0),
# where SUBCOMMAND is the bot subcommand: `uv run bot refresh ...` -> REFRESH.
# The first FAKE_DEFERRED_ROUNDS `refresh --prices` calls also print the bot's
# deferred NOTE, as a rate-limited price refresh does; FAKE_PRICES_EXIT, when
# set, is the exit code of `refresh --prices` alone.
_UV_RECORDER = """#!/usr/bin/env bash
echo "$*" >> "{calls}"
echo "fake uv: $*"
if [ "$3 $4" = "refresh --prices" ]; then
  n=$(( $(cat "{calls}.rounds" 2>/dev/null || echo 0) + 1 ))
  echo "$n" > "{calls}.rounds"
  if [ "$n" -le "${{FAKE_DEFERRED_ROUNDS:-0}}" ]; then
    echo "NOTE — 5 tickers deferred (provider rate limit); re-run to continue."
  fi
  [ -z "${{FAKE_PRICES_EXIT:-}}" ] || exit "$FAKE_PRICES_EXIT"
fi
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
    "daily.sh": ["run bot refresh --prices", "run bot refresh --fx", "run bot portfolio"],
    "weekly.sh": [
        "run bot refresh --all",
        "run bot screen --preset damodaran_value",
        "run bot analyze --from-screen",
    ],
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


# A failing refresh skips what follows it, except that daily.sh still refreshes
# FX after failing prices, as `bot refresh --prices --fx` did in one process.
_AFTER_FAILING_REFRESH = {
    "daily.sh": _WRAPPERS["daily.sh"][:2],
    "weekly.sh": _WRAPPERS["weekly.sh"][:1],
}


@pytest.mark.parametrize("name", list(_WRAPPERS))
def test_wrapper_failing_refresh_skips_the_second_command(
    name: str, repo: Path, recorder_bin: Path, calls: Path
) -> None:
    result = _run(repo / "scripts" / name, env=_env(recorder_bin, FAKE_REFRESH_EXIT="3"))

    assert result.returncode == 3
    assert _calls(calls) == _AFTER_FAILING_REFRESH[name]


def test_daily_exits_with_portfolio_failure_and_logs_it(
    repo: Path, recorder_bin: Path, calls: Path
) -> None:
    result = _run(repo / "scripts" / "daily.sh", env=_env(recorder_bin, FAKE_PORTFOLIO_EXIT="1"))

    assert result.returncode == 1
    assert _calls(calls) == _WRAPPERS["daily.sh"]
    assert "fake uv: run bot portfolio" in (repo / ".cache" / "daily.log").read_text()


_PRICES = "run bot refresh --prices"
_NO_PAUSE = {"BOT_PRICE_RETRY_PAUSE": "0"}


def test_daily_repeats_price_refresh_while_tickers_are_deferred(
    repo: Path, recorder_bin: Path, calls: Path
) -> None:
    env = _env(recorder_bin, FAKE_DEFERRED_ROUNDS="2", **_NO_PAUSE)
    result = _run(repo / "scripts" / "daily.sh", env=env)

    assert result.returncode == 0, result.stderr
    assert _calls(calls) == [_PRICES] * 3 + _WRAPPERS["daily.sh"][1:]
    assert "tickers deferred" in (repo / ".cache" / "daily.log").read_text()


def test_daily_stops_after_max_rounds_and_still_runs_fx_and_portfolio(
    repo: Path, recorder_bin: Path, calls: Path
) -> None:
    env = _env(recorder_bin, FAKE_DEFERRED_ROUNDS="99", BOT_PRICE_ROUNDS="3", **_NO_PAUSE)
    result = _run(repo / "scripts" / "daily.sh", env=env)

    assert result.returncode == 0, result.stderr
    assert _calls(calls) == [_PRICES] * 3 + _WRAPPERS["daily.sh"][1:]


@pytest.mark.parametrize("rounds", ["0", "abc"])
def test_daily_runs_one_round_when_max_rounds_is_invalid(
    repo: Path, recorder_bin: Path, calls: Path, rounds: str
) -> None:
    env = _env(recorder_bin, FAKE_DEFERRED_ROUNDS="99", BOT_PRICE_ROUNDS=rounds, **_NO_PAUSE)
    result = _run(repo / "scripts" / "daily.sh", env=env)

    assert result.returncode == 0, result.stderr
    assert _calls(calls) == [_PRICES, *_WRAPPERS["daily.sh"][1:]]


def test_daily_failing_price_round_stops_the_loop_still_refreshes_fx_skips_portfolio(
    repo: Path, recorder_bin: Path, calls: Path
) -> None:
    env = _env(recorder_bin, FAKE_DEFERRED_ROUNDS="1", FAKE_PRICES_EXIT="2", **_NO_PAUSE)
    result = _run(repo / "scripts" / "daily.sh", env=env)

    assert result.returncode == 2
    assert _calls(calls) == _WRAPPERS["daily.sh"][:2]


def test_daily_exits_with_the_worst_of_prices_and_fx(
    repo: Path, recorder_bin: Path, calls: Path
) -> None:
    env = _env(recorder_bin, FAKE_PRICES_EXIT="1", FAKE_REFRESH_EXIT="2", **_NO_PAUSE)
    result = _run(repo / "scripts" / "daily.sh", env=env)

    assert result.returncode == 2
    assert _calls(calls) == _WRAPPERS["daily.sh"][:2]


def _fake_sleep(bin_dir: Path, calls: Path) -> None:
    _write_exe(bin_dir / "sleep", f'#!/usr/bin/env bash\necho "sleep $*" >> "{calls}"\n')


def test_daily_pauses_between_rounds_but_not_after_the_last(
    repo: Path, recorder_bin: Path, calls: Path
) -> None:
    _fake_sleep(recorder_bin, calls)
    env = _env(recorder_bin, FAKE_DEFERRED_ROUNDS="99", BOT_PRICE_ROUNDS="3")
    result = _run(repo / "scripts" / "daily.sh", env=env)

    assert result.returncode == 0, result.stderr
    assert _calls(calls)[:5] == [_PRICES, "sleep 3600", _PRICES, "sleep 3600", _PRICES]
    assert _calls(calls)[5:] == _WRAPPERS["daily.sh"][1:]


@pytest.mark.parametrize(("pause", "expected"), [("5", "sleep 5"), ("soon", "sleep 3600")])
def test_daily_pause_is_configurable_and_falls_back_when_invalid(
    repo: Path, recorder_bin: Path, calls: Path, pause: str, expected: str
) -> None:
    _fake_sleep(recorder_bin, calls)
    env = _env(recorder_bin, FAKE_DEFERRED_ROUNDS="1", BOT_PRICE_RETRY_PAUSE=pause)
    result = _run(repo / "scripts" / "daily.sh", env=env)

    assert result.returncode == 0, result.stderr
    assert _calls(calls)[:3] == [_PRICES, expected, _PRICES]


def test_daily_log_marks_each_price_round(repo: Path, recorder_bin: Path) -> None:
    env = _env(recorder_bin, FAKE_DEFERRED_ROUNDS="1", **_NO_PAUSE)
    assert _run(repo / "scripts" / "daily.sh", env=env).returncode == 0

    log = (repo / ".cache" / "daily.log").read_text()
    assert "--- prices round 1/10 " in log
    assert "--- prices round 2/10 " in log


def test_weekly_exits_with_screen_failure(repo: Path, recorder_bin: Path, calls: Path) -> None:
    result = _run(repo / "scripts" / "weekly.sh", env=_env(recorder_bin, FAKE_SCREEN_EXIT="4"))

    assert result.returncode == 4
    assert _calls(calls) == _WRAPPERS["weekly.sh"][:2]


def test_weekly_publishes_the_site_after_analyze(
    repo: Path, recorder_bin: Path, calls: Path
) -> None:
    result = _run(repo / "scripts" / "weekly.sh", env=_env(recorder_bin))

    assert result.returncode == 0, result.stderr
    assert _calls(calls) == _WRAPPERS["weekly.sh"]
    assert "publish_site:" in (repo / ".cache" / "weekly.log").read_text()


def test_weekly_failing_analyze_skips_publish(repo: Path, recorder_bin: Path, calls: Path) -> None:
    result = _run(repo / "scripts" / "weekly.sh", env=_env(recorder_bin, FAKE_ANALYZE_EXIT="5"))

    assert result.returncode == 5
    assert _calls(calls) == _WRAPPERS["weekly.sh"]
    assert "publish_site:" not in (repo / ".cache" / "weekly.log").read_text()


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


# --- publish_site.sh: sidecars -> master, through a worktree under .cache --------------

_GIT_ENV = {
    "GIT_AUTHOR_NAME": "t",
    "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t",
    "GIT_COMMITTER_EMAIL": "t@example.com",
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_SYSTEM": os.devnull,
}


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env={**os.environ, **_GIT_ENV},
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.strip()


@pytest.fixture
def git_repo(tmp_path: Path, repo: Path) -> Path:
    """``repo`` as a clone of a bare ``origin`` whose ``master`` holds scripts/ and .gitignore."""
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", "-b", "master", str(origin))
    shutil.copy2(REPO_ROOT / ".gitignore", repo / ".gitignore")
    _git(repo, "init", "-q", "-b", "master")
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "init")
    _git(repo, "push", "-q", "-u", "origin", "master")
    return repo


def _origin_master(repo: Path) -> str:
    return _git(repo, "ls-remote", "origin", "refs/heads/master").split()[0]


def _origin_files(repo: Path) -> list[str]:
    _git(repo, "fetch", "-q", "origin")
    return _git(repo, "ls-tree", "-r", "--name-only", "origin/master").splitlines()


def _sidecar(repo: Path, day: str, ticker: str, body: str = "{}") -> Path:
    path = repo / "reports" / day / "analysis" / f"{ticker}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body)
    return path


def _publish(repo: Path, shim_bin: Path) -> subprocess.CompletedProcess[str]:
    return _run(repo / "scripts" / "publish_site.sh", env=_env(shim_bin, **_GIT_ENV))


def test_publish_pushes_the_sidecars_to_origin_master(git_repo: Path, shim_bin: Path) -> None:
    before = _origin_master(git_repo)
    _sidecar(git_repo, "2026-10-24", "AAPL")
    _sidecar(git_repo, "2026-10-24", "AAPL", body="x")  # the .md/.html next to it stay local
    (git_repo / "reports" / "2026-10-24" / "analysis" / "AAPL.md").write_text("# report")

    result = _publish(git_repo, shim_bin)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _origin_master(git_repo) != before
    assert "reports/2026-10-24/analysis/AAPL.json" in _origin_files(git_repo)
    assert "reports/2026-10-24/analysis/AAPL.md" not in _origin_files(git_repo)
    assert "publish_site: pushed" in result.stdout


def test_publish_leaves_the_checkout_branch_and_changes_alone(
    git_repo: Path, shim_bin: Path
) -> None:
    _git(git_repo, "checkout", "-q", "-b", "feature/wip")
    (git_repo / "scripts" / "daily.sh").write_text("# edited, not committed\n")
    (git_repo / "untracked.txt").write_text("scratch")
    _sidecar(git_repo, "2026-10-24", "MSFT")

    assert _publish(git_repo, shim_bin).returncode == 0

    assert _git(git_repo, "rev-parse", "--abbrev-ref", "HEAD") == "feature/wip"
    status = [line.strip() for line in _git(git_repo, "status", "--porcelain").splitlines()]
    assert "M scripts/daily.sh" in status
    assert "?? untracked.txt" in status
    assert "?? reports/" in status  # still untracked here: nothing was staged in this checkout
    assert "scripts/daily.sh" in _origin_files(git_repo)
    assert "untracked.txt" not in _origin_files(git_repo)
    assert "# edited" not in _git(git_repo, "show", "origin/master:scripts/daily.sh")


def test_publish_without_new_analyses_makes_no_commit(git_repo: Path, shim_bin: Path) -> None:
    _sidecar(git_repo, "2026-10-24", "AAPL")
    assert _publish(git_repo, shim_bin).returncode == 0
    after_first = _origin_master(git_repo)

    result = _publish(git_repo, shim_bin)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _origin_master(git_repo) == after_first
    assert "publish_site: no new analyses" in result.stdout


def test_publish_without_any_sidecar_exits_zero_and_touches_no_git(
    git_repo: Path, shim_bin: Path
) -> None:
    before = _origin_master(git_repo)

    result = _publish(git_repo, shim_bin)

    assert result.returncode == 0, result.stdout + result.stderr
    assert _origin_master(git_repo) == before
    assert not (git_repo / ".cache" / "site-publish").exists()
    assert "publish_site: no analyses to publish" in result.stdout


def test_publish_picks_up_commits_landed_on_origin_in_between(
    git_repo: Path, shim_bin: Path, tmp_path: Path
) -> None:
    _sidecar(git_repo, "2026-10-17", "AAPL")
    assert _publish(git_repo, shim_bin).returncode == 0
    other = tmp_path / "other"
    _git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(other))
    (other / "NEWS.md").write_text("landed elsewhere")
    _git(other, "add", "NEWS.md")
    _git(other, "commit", "-q", "-m", "elsewhere")
    _git(other, "push", "-q")
    _sidecar(git_repo, "2026-10-24", "AAPL")

    result = _publish(git_repo, shim_bin)

    assert result.returncode == 0, result.stdout + result.stderr
    files = _origin_files(git_repo)
    assert "NEWS.md" in files
    assert "reports/2026-10-17/analysis/AAPL.json" in files
    assert "reports/2026-10-24/analysis/AAPL.json" in files


def test_publish_fails_loudly_when_the_push_is_refused(git_repo: Path, shim_bin: Path) -> None:
    _sidecar(git_repo, "2026-10-24", "AAPL")
    _git(git_repo, "remote", "set-url", "--push", "origin", str(git_repo / "nowhere.git"))

    result = _publish(git_repo, shim_bin)

    assert result.returncode != 0
    assert "publish_site: push failed" in result.stdout + result.stderr
