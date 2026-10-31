"""docs/pipeline/models: the TLA+ models of the pipeline stages and their check (#163).

No test here runs Java or Node: a fake statechart launcher writes the report the test gives it.
"""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_MODELS = _ROOT / "docs" / "pipeline" / "models"
_CHECK = _MODELS / "check.sh"
_STEMS = sorted(p.stem for p in _MODELS.glob("*.tla"))
_EXPORTS = {"state", "step", "group", "colors", "title"}
_COLORS = {"blue", "orange", "purple", "yellow", "teal", "tan", "pink"}
_SITE_GROUPS = {"site-publish", "site-ci", "site-scan", "site-views"}
_FIXED = {"check.sh", "README.md", "TLA_VERSION", "TLA_SHA256", "STATECHART_COMMIT"}

_HOLDS = "# site\n\n## Rules that hold\nA, B, NoDeadlock\n"


# --- pins and check.sh -------------------------------------------------------


def test_pins() -> None:
    assert (_MODELS / "TLA_VERSION").read_text() == "1.7.4\n"
    assert (_MODELS / "TLA_SHA256").read_text() == (
        "936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88\n"
    )
    assert (_MODELS / "STATECHART_COMMIT").read_text() == (
        "4dd1d05818d19792e7cd6e818f1667f95f7e1dbe\n"
    )


def test_check_script_is_executable_and_strict() -> None:
    assert os.access(_CHECK, os.X_OK)
    text = _CHECK.read_text()
    assert text.startswith("#!/usr/bin/env bash\n")
    assert "set -euo pipefail" in text


def test_check_script_is_shellcheck_clean() -> None:
    shellcheck = shutil.which("shellcheck")
    assert shellcheck, "shellcheck-py is a dev dependency: run under `uv run`"
    result = subprocess.run([shellcheck, str(_CHECK)], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout


def _folder(tmp_path: Path, *stems: str, cfg: bool = True, view: bool = True) -> Path:
    """A copy of check.sh beside fake model files."""
    work = tmp_path / "models"
    work.mkdir()
    shutil.copy2(_CHECK, work / "check.sh")
    for stem in stems:
        (work / f"{stem}.tla").write_text(f"---- MODULE {stem} ----\n====\n")
        if cfg:
            (work / f"{stem}.cfg").write_text("SPECIFICATION Spec\n")
        if view:
            (work / f"{stem}.view.js").write_text('export const title = "x";\n')
    return work


def _launcher(tmp_path: Path) -> Path:
    """A fake statechart: logs its arguments, copies $FAKE_REPORT_<stem> into --out."""
    fake = tmp_path / "statechart"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        'echo "$*" >> "$FAKE_LOG"\n'
        'stem=$(basename "$1" .tla)\n'
        'while [ $# -gt 0 ]; do if [ "$1" = --out ]; then out=$2; fi; shift; done\n'
        'mkdir -p "$out"\n'
        'report="$FAKE_DIR/$stem.md"\n'
        'if [ -f "$report" ]; then cp "$report" "$out/report.md"; fi\n'
        'code="$FAKE_DIR/$stem.exit"\n'
        'if [ -f "$code" ]; then exit "$(cat "$code")"; fi\n'
        "exit 0\n"
    )
    fake.chmod(fake.stat().st_mode | stat.S_IXUSR)
    return fake


def _run(
    tmp_path: Path,
    work: Path,
    reports: dict[str, str],
    exits: dict[str, int] | None = None,
    **env: str,
) -> subprocess.CompletedProcess[str]:
    fakes = tmp_path / "fakes"
    fakes.mkdir(exist_ok=True)
    for stem, text in reports.items():
        (fakes / f"{stem}.md").write_text(text)
    for stem, code in (exits or {}).items():
        (fakes / f"{stem}.exit").write_text(str(code))
    full = {
        "PATH": os.environ["PATH"],
        "FAKE_LOG": str(tmp_path / "launcher.log"),
        "FAKE_DIR": str(fakes),
        "STATECHART": str(_launcher(tmp_path)),
        "TLA2TOOLS": str(tmp_path / "tla2tools.jar"),
        **env,
    }
    full = {k: v for k, v in full.items() if v}
    return subprocess.run(
        ["bash", str(work / "check.sh"), str(tmp_path / "out")],
        cwd=_ROOT,
        env=full,
        capture_output=True,
        text=True,
        check=False,
    )


def _calls(tmp_path: Path) -> list[str]:
    log = tmp_path / "launcher.log"
    return log.read_text().splitlines() if log.exists() else []


def test_check_passes_on_rules_that_hold(tmp_path: Path) -> None:
    work = _folder(tmp_path, "site")
    result = _run(tmp_path, work, {"site": _HOLDS})
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == "models | 1 models, 3 rules, 0 errors"
    out = tmp_path / "out"
    assert _calls(tmp_path) == [
        f"{work}/site.tla --config {work}/site.cfg --view {work}/site.view.js --out {out}/site"
    ]


@pytest.mark.parametrize(
    ("report", "code"),
    [
        pytest.param("# site\n\n## A breaks\n0. x\n\n## Rules that hold\nB\n", 1, id="breaks"),
        pytest.param(
            "# site\n\n## Rules that hold\nB\n\n## Rules not checked\nA\n", 0, id="not-checked"
        ),
        pytest.param(
            "# site\n\n## Rules that hold\nB\n\n## TLC stopped\nboom\n", 0, id="tlc-stopped"
        ),
        pytest.param("# site\n\nTLC reached 3 states.\n", 0, id="no-holds"),
        pytest.param(None, 2, id="launcher-exit"),
    ],
)
def test_check_fails(tmp_path: Path, report: str | None, code: int) -> None:
    work = _folder(tmp_path, "site")
    result = _run(tmp_path, work, {"site": report} if report else {}, {"site": code})
    assert result.returncode == 1, result.stdout + result.stderr
    assert "error  site: " in result.stdout
    assert result.stdout.splitlines()[-1].endswith(", 1 errors")


@pytest.mark.parametrize(
    ("missing", "kwargs"), [("site.cfg", {"cfg": False}), ("site.view.js", {"view": False})]
)
def test_check_fails_without_a_companion_file(
    tmp_path: Path, missing: str, kwargs: dict[str, bool]
) -> None:
    work = _folder(tmp_path, "site", **kwargs)
    result = _run(tmp_path, work, {"site": _HOLDS})
    assert result.returncode == 1
    error = next(ln for ln in result.stdout.splitlines() if ln.startswith("error  site: "))
    assert missing in error
    assert _calls(tmp_path) == []


def test_check_runs_every_model_and_counts(tmp_path: Path) -> None:
    work = _folder(tmp_path, "a", "b")
    result = _run(tmp_path, work, {"a": "# a\n\n## X breaks\n", "b": _HOLDS})
    assert result.returncode == 1
    assert len(_calls(tmp_path)) == 2
    assert [ln for ln in result.stdout.splitlines() if ln.startswith("error  ")] == [
        next(ln for ln in result.stdout.splitlines() if ln.startswith("error  a: "))
    ]
    assert result.stdout.splitlines()[-1] == "models | 2 models, 3 rules, 1 errors"


@pytest.mark.parametrize("var", ["STATECHART", "TLA2TOOLS"])
def test_check_requires_env(tmp_path: Path, var: str) -> None:
    work = _folder(tmp_path, "site")
    result = _run(tmp_path, work, {"site": _HOLDS}, **{var: ""})
    assert result.returncode != 0
    assert var in result.stderr
    assert _calls(tmp_path) == []


# --- model conventions -------------------------------------------------------


def _text(stem: str, ext: str) -> str:
    return (_MODELS / f"{stem}{ext}").read_text(encoding="utf-8")


def _map(stem: str, name: str) -> dict[str, str | None]:
    """A `const <name> = { ... };` literal of the view: one `key: "value",` per line."""
    lines = _text(stem, ".view.js").splitlines()
    start = lines.index(f"const {name} = {{")
    found: dict[str, str | None] = {}
    for line in lines[start + 1 :]:
        if line.strip() == "};":
            return found
        m = re.fullmatch(r'\s+(\w+): (?:"([^"]*)"|(null)),?', line)
        assert m, f'{stem}.view.js {name}: not one `key: "value",` entry: {line!r}'
        found[m.group(1)] = None if m.group(3) else m.group(2)
    raise AssertionError(f"{stem}.view.js: {name} is not closed by `}};`")


def _colors(stem: str) -> dict[str, str]:
    m = re.search(r"^export const colors = \{(.*?)\};", _text(stem, ".view.js"), re.M | re.S)
    assert m, f"{stem}.view.js has no colors"
    return dict(re.findall(r'"([^"]+)":\s*"([^"]+)"', m.group(1)))


def _definitions(stem: str) -> list[tuple[str, list[str], str]]:
    """(name, `\\*` comment lines directly above, body up to the next blank line) per definition."""
    lines = _text(stem, ".tla").splitlines()
    out = []
    for i, line in enumerate(lines):
        m = re.match(r"^(\w+)(\(.*?\))? ==", line)
        if not m:
            continue
        comments = []
        j = i - 1
        while j >= 0 and lines[j].lstrip().startswith("\\*"):
            comments.insert(0, lines[j].strip())
            j -= 1
        body = [line]
        for nxt in lines[i + 1 :]:
            if not nxt.strip():
                break
            body.append(nxt)
        out.append((m.group(1) + (m.group(2) or ""), comments, "\n".join(body)))
    return out


def _invariants(stem: str) -> list[str]:
    names = []
    for line in _text(stem, ".cfg").splitlines():
        if line.startswith("INVARIANT"):
            names += line.split()[1:]
    return names


def test_site_model_exists() -> None:
    assert "site" in _STEMS


@pytest.mark.parametrize("stem", _STEMS)
def test_model_files_sit_together(stem: str) -> None:
    assert (_MODELS / f"{stem}.cfg").is_file()
    assert (_MODELS / f"{stem}.view.js").is_file()
    assert re.fullmatch(rf"-{{4,}} MODULE {stem} -{{4,}}", _text(stem, ".tla").splitlines()[0])


@pytest.mark.parametrize("stem", _STEMS)
def test_cfg_has_spec_and_invariants(stem: str) -> None:
    lines = _text(stem, ".cfg").splitlines()
    assert "SPECIFICATION Spec" in lines
    assert _invariants(stem)


@pytest.mark.parametrize("stem", _STEMS)
def test_tla_has_next_and_done(stem: str) -> None:
    bodies = {name: body for name, _, body in _definitions(stem)}
    assert {"Next", "Done", "Spec"} <= set(bodies)
    assert "phase \\in EndPhases" in bodies["Done"]
    assert "UNCHANGED vars" in bodies["Done"]
    assert "Init /\\ [][Next]_vars" in bodies["Spec"]


@pytest.mark.parametrize("stem", _STEMS)
def test_next_names_every_step(stem: str) -> None:
    body = {name: body for name, _, body in _definitions(stem)}["Next"]
    actions = [a.strip() for a in body.split("==", 1)[1].split("\\/") if a.strip()]
    assert all(re.fullmatch(r"\w+", a) for a in actions), actions
    assert sorted(actions) == sorted(_map(stem, "steps"))


@pytest.mark.parametrize("stem", _STEMS)
def test_view_maps_and_exports(stem: str) -> None:
    text = _text(stem, ".view.js")
    for name in ("states", "steps", "groups"):
        assert f"\nconst {name} = {{\n" in f"\n{text}"
    assert set(re.findall(r"^export const (\w+)", text, re.M)) == _EXPORTS
    assert len(re.findall(r"^export ", text, re.M)) == len(_EXPORTS)
    assert "export const state = (v) => states[v.phase];" in text
    assert "export const step = (action) => steps[action] ?? null;" in text
    assert "export const group = (v) => groups[v.phase];" in text
    assert re.search(rf'^export const title = "{stem}: one \w+ through bot {stem}";$', text, re.M)
    assert "import" not in text


@pytest.mark.parametrize("stem", _STEMS)
def test_groups_are_stage_subboards(stem: str) -> None:
    groups = set(_map(stem, "groups").values())
    assert all(g and re.fullmatch(rf"{stem}-[a-z][a-z-]*", g) for g in groups), groups
    colors = _colors(stem)
    assert set(colors) == groups
    assert set(colors.values()) <= _COLORS


@pytest.mark.parametrize("stem", _STEMS)
def test_states_and_groups_keys_match(stem: str) -> None:
    assert set(_map(stem, "states")) == set(_map(stem, "groups"))
    assert all(_map(stem, "states").values())


@pytest.mark.parametrize("stem", _STEMS)
def test_labels_name_no_code(stem: str) -> None:
    """No label shows an action name, a camelCase identifier or an underscore."""
    actions = set(_map(stem, "steps"))
    labels = [v for v in _map(stem, "states").values() if v]
    labels += [v for v in _map(stem, "steps").values() if v]
    for label in labels:
        assert "_" not in label, label
        words = set(re.findall(r"\w+", label))
        assert not words & actions, label
        assert not [w for w in words if re.fullmatch(r"[a-z]+[A-Z]\w*", w)], label


@pytest.mark.parametrize("stem", _STEMS)
def test_every_cfg_invariant_has_a_sentence(stem: str) -> None:
    defs = {name: comments for name, comments, _ in _definitions(stem)}
    for rule in _invariants(stem):
        assert rule in defs, f"{stem}.cfg names {rule}, which {stem}.tla does not define"
        sentences = [c for c in defs[rule] if not c.startswith("\\* broken:")]
        assert sentences, f"{rule} has no reader's sentence above it"


@pytest.mark.parametrize("stem", _STEMS)
def test_rules_are_checked_or_marked_broken(stem: str) -> None:
    checked = set(_invariants(stem))
    for name, comments, body in _definitions(stem):
        shaped = comments and "(" not in name and "'" not in body and "UNCHANGED" not in body
        if not shaped or name in checked:
            continue
        assert any(re.fullmatch(r"\\\* broken: #\d+", c) for c in comments), (
            f"{stem}.tla {name} looks like a rule but is neither in {stem}.cfg nor marked broken"
        )


def test_site_groups() -> None:
    assert set(_map("site", "groups").values()) == _SITE_GROUPS
    assert len(_invariants("site")) >= 6


# --- docs and layout ---------------------------------------------------------


def test_models_readme() -> None:
    text = (_MODELS / "README.md").read_text(encoding="utf-8")
    assert "docs/pipeline/models/check.sh" in text
    assert "pipeline-models" in text
    assert "## Known broken rules" in text
    assert "| Stage | Rule | Reader's sentence | Issue |" in text


def test_models_folder_holds_only_ours() -> None:
    tracked = subprocess.run(
        ["git", "ls-files", "--", "docs/pipeline/models"],
        cwd=_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    names = {Path(p).name for p in tracked} | {p.name for p in _MODELS.iterdir() if p.is_file()}
    models = {f"{s}{ext}" for s in _STEMS for ext in (".tla", ".cfg", ".view.js")}
    assert names <= _FIXED | models, names - _FIXED - models
    assert _FIXED | {"site.tla", "site.cfg", "site.view.js"} <= names


def test_pipeline_readme_points_at_models() -> None:
    text = (_ROOT / "docs" / "pipeline" / "README.md").read_text(encoding="utf-8")
    assert "## Models" in text
    assert "models/README.md" in text


def test_context_lists_the_models() -> None:
    text = (_ROOT / "CONTEXT.md").read_text(encoding="utf-8")
    boards = text.index("**The pipeline boards**")
    models = text.index("docs/pipeline/models/")
    assert boards < models < text.index("## Working with the plans")
