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
_SCREEN_GROUPS = {
    "screen-snapshot",
    "screen-coverage",
    "screen-quality",
    "screen-value",
    "screen-traps",
    "screen-ranking",
}
_SCREEN_RULES = {
    "UnmappedLeavesAsUnmapped",
    "NoWaccNoRule",
    "UncoveredCurrencyNoRule",
    "OneCoverageReason",
    "EveryLayerRecorded",
    "FailedLayerRejects",
    "OnlySurvivorsInPercentiles",
    "CutNeitherValuedNorSaved",
    "UnvaluedKeepsPlaceholder",
    "RejectedSavedAsFailed",
    "OneEndOnly",
    "NoUsdCapFailsQuality",
    "SkippedValueRecordsNothing",
}
_FIXED = {"check.sh", "README.md", "TLA_VERSION", "TLA_SHA256", "STATECHART_COMMIT"}

_HOLDS = "# site\n\n## Rules that hold\nA, B, NoDeadlock\n"


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
        'if [ -f "$report" ]; then cp "$report" "$out/report.md"; cat "$report"; fi\n'
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


def _only_summary_lines(result: subprocess.CompletedProcess[str]) -> None:
    """The launcher prints its report to stdout; check.sh must not pass that on."""
    for line in result.stdout.splitlines():
        assert line.startswith(("error  ", "models | ")), line


def _calls(tmp_path: Path) -> list[str]:
    log = tmp_path / "launcher.log"
    return log.read_text().splitlines() if log.exists() else []


def test_check_passes_on_rules_that_hold(tmp_path: Path) -> None:
    work = _folder(tmp_path, "site")
    result = _run(tmp_path, work, {"site": _HOLDS})
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.splitlines()[-1] == "models | 1 models, 3 rules, 0 errors"
    _only_summary_lines(result)
    out = tmp_path / "out"
    assert _calls(tmp_path) == [
        f"{work}/site.tla --config {work}/site.cfg --view {work}/site.view.js --out {out}/site"
    ]


@pytest.mark.parametrize(
    ("report", "code"),
    [
        pytest.param("# site\n\n## A breaks\n0. x\n\n## Rules that hold\nB\n", 1, id="breaks"),
        pytest.param("# site\n\n## A breaks\n0. x\n", 1, id="breaks-exit-1"),
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
    _only_summary_lines(result)


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


def test_check_refuses_a_used_out_dir(tmp_path: Path) -> None:
    work = _folder(tmp_path, "site")
    (tmp_path / "out" / "site").mkdir(parents=True)
    (tmp_path / "out" / "site" / "report.md").write_text("# site\n\n## A breaks\n")
    result = _run(tmp_path, work, {"site": _HOLDS})
    assert result.returncode == 1
    error = next(ln for ln in result.stdout.splitlines() if ln.startswith("error  site: "))
    assert "not empty" in error
    assert _calls(tmp_path) == []


def test_check_fails_without_models(tmp_path: Path) -> None:
    work = _folder(tmp_path)
    result = _run(tmp_path, work, {})
    assert result.returncode == 1
    assert result.stdout.splitlines()[-1] == "models | 0 models, 0 rules, 1 errors"


def test_check_needs_an_out_dir(tmp_path: Path) -> None:
    work = _folder(tmp_path, "site")
    result = subprocess.run(
        ["bash", str(work / "check.sh")],
        env={"PATH": os.environ["PATH"], "STATECHART": "x", "TLA2TOOLS": "y"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "usage: check.sh OUT_DIR" in result.stderr


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


def _is_broken(comments: list[str]) -> bool:
    return any(re.fullmatch(r"\\\* broken: #\d+", c) for c in comments)


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
        assert _is_broken(comments), (
            f"{stem}.tla {name} looks like a rule but is neither in {stem}.cfg nor marked broken"
        )


def test_site_groups() -> None:
    assert set(_map("site", "groups").values()) == _SITE_GROUPS
    assert len(_invariants("site")) >= 6


def test_screen_groups() -> None:
    assert "screen" in _STEMS
    assert set(_map("screen", "groups").values()) == _SCREEN_GROUPS


def test_screen_rules() -> None:
    """Every rule is checked in the .cfg, or marked broken in the .tla (broken-rule protocol)."""
    broken = {
        name
        for name, comments, _ in _definitions("screen")
        if any(re.fullmatch(r"\\\* broken: #\d+", c) for c in comments)
    }
    assert set(_invariants("screen")) | broken == _SCREEN_RULES
    assert not set(_invariants("screen")) & broken


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


# Sub-boards drawn from the models (#164): the stages whose groups are drawn as sub-boards.
_SUBBOARDED = ("site", "refresh", "screen")
_PHASES_RE = re.compile(r"phase = \"(\w+)\".*?phase' = \"(\w+)\"", re.S)


def _transitions(stem: str) -> dict[str, tuple[str, str]]:
    """Action -> (state it leaves, state it enters), from `phase = "a"` and `phase' = "b"`."""
    out = {}
    for action in _map(stem, "steps"):
        if action == "Done":
            continue
        body = {name: body for name, _, body in _definitions(stem)}[action]
        m = _PHASES_RE.search(body)
        assert m, f'{stem}.tla {action}: no `phase = "a"` ... `phase\' = "b"`'
        out[action] = (m.group(1), m.group(2))
    return out


_SOURCES_RE = re.compile(r"phase (?:= \"(\w+)\"|\\in \{([^}]*)\}).*?phase' = \"(\w+)\"", re.S)


def _moves(stem: str) -> list[tuple[str, str, str]]:
    """(action, state it leaves, state it enters), one per source of `phase \\in {"a", "b"}` (#168)."""
    bodies = {name: body for name, _, body in _definitions(stem)}
    out = []
    for action in _map(stem, "steps"):
        if action == "Done":
            continue
        m = _SOURCES_RE.search(bodies[action])
        assert m, f'{stem}.tla {action}: no `phase = "a"` or `phase \\in {{...}}` ... `phase\' = "b"`'
        sources = [m.group(1)] if m.group(1) else re.findall(r'"(\w+)"', m.group(2))
        out += [(action, a, m.group(3)) for a in sources]
    return out


def _stage_boards(stage: str) -> dict[str, str]:
    from tests.unit.test_pipeline_subboards import subboards

    root = _ROOT / "docs" / "pipeline"
    return {
        stem: (root / f"{stem}.d2").read_text(encoding="utf-8")
        for stem, (st, _) in subboards().items()
        if st == stage
    }


def _drawn_nodes(text: str) -> dict[str, tuple[str | None, str]]:
    """Node path -> (class, first line of its label)."""
    from tests.unit.test_pipeline_subboards import first_line, node_labels

    return {p: (cls, first_line(label)) for p, (_, cls, label) in node_labels(text).items()}


@pytest.mark.parametrize("stage", _SUBBOARDED)
def test_subboards_are_the_groups(stage: str) -> None:
    assert set(_stage_boards(stage)) == set(_map(stage, "groups").values())


@pytest.mark.parametrize("stage", _SUBBOARDED)
def test_state_labels_are_drawn(stage: str) -> None:
    boards = _stage_boards(stage)
    groups = _map(stage, "groups")
    missing = []
    for key, label in _map(stage, "states").items():
        group = groups[key]
        drawn = {first for _, first in _drawn_nodes(boards.get(group or "", "")).values()}
        if label not in drawn:
            missing.append(f"{group}: {label}")
    assert missing == []


@pytest.mark.parametrize("stage", _SUBBOARDED)
def test_step_labels_are_drawn(stage: str) -> None:
    from tests.unit.test_pipeline_subboards import edges, first_line

    drawn = {
        first_line(label) for text in _stage_boards(stage).values() for *_, label in edges(text)
    }
    missing = [label for label in _map(stage, "steps").values() if label and label not in drawn]
    assert missing == []


@pytest.mark.parametrize("stage", _SUBBOARDED)
def test_subboard_edges_join_the_model_states(stage: str) -> None:
    from tests.unit.test_pipeline_subboards import edges, first_line

    states, steps = _map(stage, "states"), _map(stage, "steps")
    drawn = set()
    for text in _stage_boards(stage).values():
        nodes = _drawn_nodes(text)
        for _, src, dst, label in edges(text):
            ends = (nodes.get(src, (None, ""))[1], nodes.get(dst, (None, ""))[1])
            drawn.add((first_line(label), *ends))
    missing = [
        f"{action}: {states[a]} -> {states[b]}"
        for action, a, b in _moves(stage)
        if (steps[action], states[a], states[b]) not in drawn
    ]
    assert missing == []


@pytest.mark.parametrize("stage", _SUBBOARDED)
def test_subboard_state_classes(stage: str) -> None:
    """A state is a decision when at least two steps leave it under a [condition]."""
    states, steps = _map(stage, "states"), _map(stage, "steps")
    conditioned = {key: 0 for key in states}
    for action, a, _ in _moves(stage):
        if "[" in (steps[action] or ""):
            conditioned[a] += 1
    expected = {
        label: "decision" if conditioned[key] >= 2 else "step" for key, label in states.items()
    }
    wrong = [
        f"{stem} {path}: {cls}, expected {expected[first]}"
        for stem, text in _stage_boards(stage).items()
        for path, (cls, first) in _drawn_nodes(text).items()
        if first in expected and cls != expected[first]
    ]
    assert wrong == []


@pytest.mark.parametrize("stage", _SUBBOARDED)
def test_neighbour_nodes_link_their_subboard(stage: str) -> None:
    """A state drawn on another group's sub-board links the sub-board it belongs to."""
    from tests.unit.test_pipeline_diagram import _block
    from tests.unit.test_pipeline_subboards import _link

    groups = _map(stage, "groups")
    group_of = {label: groups[key] for key, label in _map(stage, "states").items()}
    wrong = []
    for stem, text in _stage_boards(stage).items():
        for path, (_, first) in _drawn_nodes(text).items():
            group = group_of.get(first)
            if group and group != stem:
                link = _link(_block(text, path) or "")
                if link != f"./{group}.svg":
                    wrong.append(f"{stem} {path}: link {link}, expected ./{group}.svg")
    assert wrong == []


_REFRESH_GROUPS = {
    "refresh-damodaran",
    "refresh-fundamentals",
    "refresh-facts",
    "refresh-prices",
    "refresh-fx",
}
# Issue #165 rules (a)-(m) plus the prices rate limit: checked, or marked broken.
_REFRESH_RULES = {
    "CoreFileFailureWritesNothing",
    "EmptySideKeepsItsRows",
    "StoredFilingIsSkipped",
    "UnmappedIndustryStillImported",
    "InvalidMappingImportsNothing",
    "RateLimitDefersTheRest",
    "FactOutsideAPeriodIsDropped",
    "AnnualRowHasAFiscalYear",
    "RescaleNeedsThreeOtherCounts",
    "CurrentTickerIsNotRequested",
    "MarketCapNeedsAFreshBarAndShares",
    "UsdOnlyFxCallsNoProvider",
    "StagesRunInOrder",
    "PriceRateLimitDefersTheRest",
}


def test_refresh_groups() -> None:
    assert set(_map("refresh", "groups").values()) == _REFRESH_GROUPS


def test_refresh_title() -> None:
    assert 'export const title = "refresh: one ticker through bot refresh";' in _text(
        "refresh", ".view.js"
    )


def test_refresh_rules_are_all_present() -> None:
    defs = {name: comments for name, comments, _ in _definitions("refresh")}
    checked = set(_invariants("refresh"))
    for rule in _REFRESH_RULES:
        assert rule in defs, f"refresh.tla does not define {rule}"
        assert rule in checked or _is_broken(defs[rule]), (
            f"{rule} is neither checked nor marked broken"
        )
    assert len(checked) >= 10


def test_refresh_ends_and_handovers() -> None:
    bodies = {name: body for name, _, body in _definitions("refresh")}
    assert bodies["EndPhases"] == 'EndPhases == {"mapping_refused", "fx_done"}'
    assert 'phase = "started"' in bodies["Init"]
    assert "stagesDone = {}" in bodies["Init"]
    for handover, stage in [
        ("FundamentalsStartAfterTheWrite", "damodaran"),
        ("FundamentalsStartAfterTheFailure", "damodaran"),
        ("PricesStart", "fundamentals"),
        ("FxStarts", "prices"),
    ]:
        assert f'stagesDone\' = stagesDone \\cup {{"{stage}"}}' in bodies[handover], handover


_PORTFOLIO_GROUPS = {
    "portfolio-sync",
    "portfolio-marks",
    "portfolio-events",
    "portfolio-mark-events",
    "portfolio-alerts",
}
# Issue #171 rules (a)-(k): checked, or marked broken.
_PORTFOLIO_RULES = {
    "MisconfiguredChannelStoresNothing",
    "UnreachableTwsWritesNoMarkOrEvent",
    "MarkedAfterTheSnapshot",
    "UnknownValueFiresNoMarkEvent",
    "FirstRunOpensEveryPosition",
    "NoPreviousMarkOnlyRedFlags",
    "ReportedFilingNeverFiresAgain",
    "ConcentrationOnEveryRun",
    "EventsLoggedBeforeAlerts",
    "AlertsWrittenSentOnlyWithText",
    "CorporateActionsFailureNeverStops",
}


def test_portfolio_groups() -> None:
    assert "portfolio" in _STEMS
    assert set(_map("portfolio", "groups").values()) == _PORTFOLIO_GROUPS


def test_portfolio_title() -> None:
    assert 'export const title = "portfolio: one holding through bot portfolio";' in _text(
        "portfolio", ".view.js"
    )


def test_portfolio_rules_are_all_present() -> None:
    defs = {name: comments for name, comments, _ in _definitions("portfolio")}
    checked = set(_invariants("portfolio"))
    for rule in _PORTFOLIO_RULES:
        assert rule in defs, f"portfolio.tla does not define {rule}"
        assert rule in checked or _is_broken(defs[rule]), (
            f"{rule} is neither checked nor marked broken"
        )
    assert not checked & {n for n, c in defs.items() if _is_broken(c)}
    assert len(checked) >= 9


@pytest.mark.parametrize("stem", _STEMS)
def test_rules_cite_the_code(stem: str) -> None:
    """A `(* Cites: ... *)` line sits directly above each rule's `\\*` sentence."""
    lines = _text(stem, ".tla").splitlines()
    for rule in _invariants(stem):
        i = next(n for n, ln in enumerate(lines) if re.match(rf"^{rule} ==", ln))
        j = i - 1
        while lines[j].lstrip().startswith("\\*"):
            j -= 1
        assert lines[j].lstrip().startswith("(* Cites:"), f"{stem}.tla {rule} cites no code"

# The analyze model (#169): one ticker through `bot analyze`.
_ANALYZE_GROUPS = {
    "analyze-inputs",
    "analyze-story",
    "analyze-assumptions",
    "analyze-dcf",
    "analyze-sensitivity",
    "analyze-flags",
    "analyze-verdict",
}
_ANALYZE_RULES = {
    "VerdictOnlyIfValued",
    "UnresolvedNeverValued",
    "TerminalGrowthAtTheWaccStops",
    "ImplausibleSharesStop",
    "OneStoryType",
    "UncoveredCurrencyLeavesTerminalGrowthUnresolved",
    "VerdictFromTheMargin",
    "FlagsAfterTheDcfNotInTheVerdict",
    "ReportsTogetherOnlyWhenValued",
    "UnknownTickerSkippedBatchGoesOn",
    "OnlyTheCommandStopsTheBatch",
    "CannotValueMeansNoReport",
}
_ANALYZE_END = {"command_stops", "not_found", "cannot_value", "crashed", "reported"}


def _analyze_defined() -> dict[str, list[str]]:
    """Rule name -> its `\\*` comments, for every definition of analyze.tla."""
    return {name: comments for name, comments, _ in _definitions("analyze")}


def test_analyze_model_exists() -> None:
    assert "analyze" in _STEMS


def test_analyze_groups() -> None:
    assert set(_map("analyze", "groups").values()) == _ANALYZE_GROUPS
    assert len(_invariants("analyze")) >= 8


def test_analyze_rules() -> None:
    """Every rule is checked, or kept in the .tla and marked broken."""
    checked = set(_invariants("analyze"))
    defined = _analyze_defined()
    for rule in _ANALYZE_RULES:
        assert rule in defined, rule
        broken = any(re.fullmatch(r"\\\* broken: #\d+", c) for c in defined[rule])
        assert (rule in checked) != broken, rule


def test_analyze_end_phases() -> None:
    line = next(ln for ln in _text("analyze", ".tla").splitlines() if ln.startswith("EndPhases =="))
    assert set(re.findall(r'"(\w+)"', line)) == _ANALYZE_END


def test_analyze_every_phase_is_reachable() -> None:
    edges = _transitions("analyze")
    seen, todo = {"asked"}, ["asked"]
    while todo:
        here = todo.pop()
        for src, dst in edges.values():
            if src == here and dst not in seen:
                seen.add(dst)
                todo.append(dst)
    assert seen == set(_map("analyze", "states"))


def test_analyze_end_phases_have_no_step_out() -> None:
    assert not [a for a, (src, _) in _transitions("analyze").items() if src in _ANALYZE_END]


@pytest.mark.parametrize(
    "assignment",
    [
        "gVsWacc' = \"at or above\"",
        "shares' = \"implausible\"",
        "unresolved' = TRUE",
        "currency' = \"uncovered\"",
        "batch' = \"stopped\"",
        "overrideStory' = \"given\"",
        "tgSource' = \"manual\"",
        "valued' = TRUE",
        "margin' = \"no price\"",
        "margin' = \"below 1.0\"",
        "margin' = \"1.0 to under 1.3\"",
        "margin' = \"1.3 or more\"",
    ],
)
def test_analyze_rule_antecedents_are_set(assignment: str) -> None:
    assert assignment in _text("analyze", ".tla")


def test_analyze_groups_fit_a_subboard() -> None:
    groups = _map("analyze", "groups")
    edges = _transitions("analyze").values()
    for group in _ANALYZE_GROUPS:
        steps = sum(1 for s, t in edges if groups[s] == group or groups[t] == group)
        assert steps <= 20, f"{group}: {steps} steps"


def test_analyze_avoids_what_sany_export_rejects() -> None:
    text = _text("analyze", ".tla")
    assert "EXTENDS" not in text
    assert "Cardinality" not in text
    assert "<=>" not in text


def test_analyze_actions_are_cited() -> None:
    lines = _text("analyze", ".tla").splitlines()
    missing = []
    for action in _map("analyze", "steps"):
        if action == "Done":
            continue
        i = lines.index(f"{action} ==")
        if not lines[i - 1].rstrip().endswith("*)"):
            missing.append(action)
    assert missing == []


def test_analyze_rules_are_cited() -> None:
    lines = _text("analyze", ".tla").splitlines()
    for rule in _ANALYZE_RULES:
        i = lines.index(f"{rule} ==")
        j = i - 1
        while lines[j].lstrip().startswith("\\*"):
            j -= 1
        assert lines[j].rstrip().endswith("*)") and "Cites:" in "\n".join(lines[j - 3 : j + 1]), rule
