"""docs/pipeline/build.sh and the pipeline-diagram workflow render the boards (#145).

No test here runs the real d2: a fake `d2` script on PATH records its arguments.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import stat
import subprocess
from pathlib import Path
from types import ModuleType

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[2]
_PIPELINE = _ROOT / "docs" / "pipeline"
_BUILD = _PIPELINE / "build.sh"
_WORKFLOW = _ROOT / ".github" / "workflows" / "pipeline-diagram.yml"
_SETUP = _ROOT / ".factory" / "setup.sh"
_INSTALL = "curl -fsSL https://d2lang.com/install.sh | sh -s -- --version"
_TOOLS = ("bash", "env", "cat", "dirname", "cut", "sha256sum", "sort", "ls", "mkdir", "grep", "sed", "head", "tr")


@pytest.fixture(scope="module")
def check() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pipeline_check", _PIPELINE / "check.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _workspace(tmp_path: Path) -> Path:
    """A copy of build.sh and D2_VERSION with two boards and classes.d2."""
    work = tmp_path / "pipeline"
    work.mkdir()
    shutil.copy2(_BUILD, work / "build.sh")
    shutil.copy2(_PIPELINE / "D2_VERSION", work / "D2_VERSION")
    (work / "classes.d2").write_text("classes: {}\n")
    (work / "pipeline.d2").write_text("...@classes\na -> b\n")
    (work / "refresh.d2").write_text("...@classes\nc -> d\n")
    return work


def _bin(tmp_path: Path, d2_version: str | None) -> Path:
    """A PATH directory with the coreutils build.sh needs and, optionally, a fake d2."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool in _TOOLS:
        found = shutil.which(tool)
        if found:
            (bindir / tool).symlink_to(found)
    if d2_version is not None:
        fake = bindir / "d2"
        fake.write_text(
            "#!/usr/bin/env bash\n"
            f'if [ "$1" = version ]; then echo "{d2_version}"; exit 0; fi\n'
            'echo "$*" >> "$D2_LOG"\n'
            'for last; do :; done\n'
            'echo fake > "$last"\n'
        )
        fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    return bindir


def _run(work: Path, bindir: Path, **env: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(bindir / "bash"), str(work / "build.sh")],
        cwd=_ROOT,  # build.sh must work from any directory
        env={"PATH": str(bindir), "D2_LOG": str(work.parent / "d2.log"), **env},
        capture_output=True,
        text=True,
        check=False,
    )


def test_d2_version_is_pinned() -> None:
    assert (_PIPELINE / "D2_VERSION").read_text() == "v0.9.0\n"


def test_build_script_is_executable_and_strict() -> None:
    assert os.access(_BUILD, os.X_OK)
    text = _BUILD.read_text()
    assert text.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in text


def test_build_refuses_without_d2(tmp_path: Path) -> None:
    work = _workspace(tmp_path)
    result = _run(work, _bin(tmp_path, None))
    assert result.returncode != 0
    assert "d2" in result.stderr and "pipeline-diagram" in result.stderr
    assert not list(work.glob("*.svg")) and not (work / "rendered.sha256").exists()


def test_build_refuses_wrong_version(tmp_path: Path) -> None:
    work = _workspace(tmp_path)
    result = _run(work, _bin(tmp_path, "v0.8.1"))
    assert result.returncode != 0
    assert "0.8.1" in result.stderr and "0.9.0" in result.stderr
    assert not list(work.glob("*.svg")) and not (work / "rendered.sha256").exists()


@pytest.mark.parametrize("reported", ["v0.9.0", "0.9.0"])
def test_build_renders_every_board_and_writes_the_hash(
    check: ModuleType, tmp_path: Path, reported: str
) -> None:
    work = _workspace(tmp_path)
    result = _run(work, _bin(tmp_path, reported), TALA_SEEDS="3")
    assert result.returncode == 0, result.stderr
    calls = (tmp_path / "d2.log").read_text().splitlines()
    assert calls == [
        "--layout tala --tala-seeds 3 pipeline.d2 pipeline.svg",
        "--layout tala --tala-seeds 3 pipeline.d2 pipeline.png",
        "--layout tala --tala-seeds 3 refresh.d2 refresh.svg",
        "--layout tala --tala-seeds 3 refresh.d2 refresh.png",
    ]
    assert (work / "rendered.sha256").read_text() == check.source_hash(work) + "\n"
    assert not (work / "classes.svg").exists()


def test_build_defaults_to_one_tala_seed(tmp_path: Path) -> None:
    work = _workspace(tmp_path)
    assert _run(work, _bin(tmp_path, "v0.9.0")).returncode == 0
    assert (tmp_path / "d2.log").read_text().splitlines()[0].startswith(
        "--layout tala --tala-seeds 1 "
    )


def test_shellcheck_is_clean() -> None:
    shellcheck = shutil.which("shellcheck")
    assert shellcheck, "shellcheck-py is a dev dependency: run under `uv run`"
    result = subprocess.run(
        [shellcheck, str(_BUILD), str(_SETUP)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout


def test_setup_installs_d2_best_effort() -> None:
    text = _SETUP.read_text()
    assert subprocess.run(["bash", "-n", str(_SETUP)], check=False).returncode == 0
    assert text.index("uv sync --frozen") < text.index(_INSTALL)
    assert '--version "$(cat docs/pipeline/D2_VERSION)"' in text
    assert "--method standalone --prefix /usr/local" in text
    assert "d2 not installed; the pipeline-diagram workflow renders instead" in text


def test_png_renders_are_ignored() -> None:
    assert "docs/pipeline/*.png" in (_ROOT / ".gitignore").read_text().splitlines()


def test_workflow_renders_uploads_checks_and_gates_staleness() -> None:
    wf = yaml.safe_load(_WORKFLOW.read_text())
    triggers = wf.get("on", wf.get(True))  # PyYAML reads the bare key `on` as True
    assert sorted(triggers) == ["push", "workflow_dispatch"]
    assert wf["permissions"] == {"contents": "read"}
    assert wf["concurrency"]["cancel-in-progress"] is True
    assert "github.ref" in wf["concurrency"]["group"]
    assert list(wf["jobs"]) == ["render", "models"]
    job = wf["jobs"]["render"]
    assert job["runs-on"] == "ubuntu-latest"
    steps = job["steps"]
    runs = [s.get("run", "") for s in steps]
    uses = [s.get("uses", "") for s in steps]

    def at(pred: object) -> int:
        return next(i for i, s in enumerate(steps) if pred(s))  # type: ignore[operator]

    checkout = at(lambda s: s.get("uses") == "actions/checkout@v4")
    install = at(lambda s: _INSTALL in s.get("run", ""))
    assert '--version "$(cat docs/pipeline/D2_VERSION)"' in runs[install]
    assert '--method standalone --prefix "$HOME/.local"' in runs[install]
    assert 'echo "$HOME/.local/bin" >> "$GITHUB_PATH"' in "\n".join(runs)
    tala = at(lambda s: "d2 layout" in s.get("run", "") and "tala" in s.get("run", ""))
    assert "d2 version" in "\n".join(runs[: tala + 1])
    build = at(lambda s: "docs/pipeline/build.sh" in s.get("run", ""))
    upload = at(lambda s: s.get("uses") == "actions/upload-artifact@v4")
    assert steps[upload]["if"] == "always()"
    assert steps[upload]["with"]["name"] == "pipeline-render"
    paths = steps[upload]["with"]["path"].split()
    assert paths == [
        "docs/pipeline/*.svg",
        "docs/pipeline/*.png",
        "docs/pipeline/rendered.sha256",
    ]
    checker = at(lambda s: "python3 docs/pipeline/check.py" in s.get("run", ""))
    current = at(lambda s: s.get("name") == "committed render is current")
    assert "git diff --exit-code -- docs/pipeline/rendered.sha256" in runs[current]
    assert "git ls-files --others --exclude-standard docs/pipeline/*.svg" in runs[current]
    ls_files = next(ln for ln in runs[current].splitlines() if "git ls-files" in ln)
    assert "docs/pipeline/rendered.sha256" in ls_files
    assert checkout < install < tala < build < upload < checker < current == len(steps) - 1
    assert not any("uv" in u for u in uses)


def test_workflow_checks_models() -> None:
    wf = yaml.safe_load(_WORKFLOW.read_text())
    job = wf["jobs"]["models"]
    assert job["runs-on"] == "ubuntu-latest"
    steps = job["steps"]
    runs = [s.get("run", "") for s in steps]

    def at(pred: object) -> int:
        return next(i for i, s in enumerate(steps) if pred(s))  # type: ignore[operator]

    checkout = at(lambda s: s.get("uses") == "actions/checkout@v4")
    java = at(lambda s: s.get("uses") == "actions/setup-java@v4")
    assert steps[java]["with"] == {"distribution": "temurin", "java-version": "21"}
    node = at(lambda s: s.get("uses") == "actions/setup-node@v4")
    assert steps[node]["with"] == {"node-version": "24"}
    download = at(lambda s: "tla2tools.jar" in s.get("run", "") and "curl -fsSL" in s.get("run", ""))
    assert (
        "https://github.com/tlaplus/tlaplus/releases/download/"
        "v$(cat docs/pipeline/models/TLA_VERSION)/tla2tools.jar"
    ) in runs[download]
    assert "-o /tmp/tla2tools.jar" in runs[download]
    checksum = at(lambda s: "sha256sum -c" in s.get("run", ""))
    assert "$(cat docs/pipeline/models/TLA_SHA256)  /tmp/tla2tools.jar" in runs[checksum]
    skill = at(lambda s: "cursor/plugins" in s.get("run", ""))
    assert (
        "git clone --filter=blob:none --no-checkout https://github.com/cursor/plugins /tmp/plugins"
    ) in runs[skill]
    assert "sparse-checkout set pstack/skills/statechart" in runs[skill]
    assert 'checkout "$(cat docs/pipeline/models/STATECHART_COMMIT)"' in runs[skill]
    check = at(lambda s: "docs/pipeline/models/check.sh /tmp/models" in s.get("run", ""))
    assert "TLA2TOOLS=/tmp/tla2tools.jar" in runs[check]
    assert "STATECHART=/tmp/plugins/pstack/skills/statechart/scripts/statechart" in runs[check]
    upload = at(lambda s: s.get("uses") == "actions/upload-artifact@v4")
    assert steps[upload]["if"] == "always()"
    assert steps[upload]["with"] == {"name": "pipeline-models", "path": "/tmp/models"}
    assert checkout < java < check and checkout < node < check
    assert download <= checksum < check and skill < check
    assert upload == len(steps) - 1
