"""docs/pipeline/<stage>-<sub>.d2: the sub-board conventions (#164).

Generic over every sub-board in the folder, so each stage that gains sub-boards inherits them.
A sub-board is the stage's checked statechart drawn in d2: see docs/pipeline/README.md.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests.unit.test_pipeline_diagram import (
    _STAGES,
    _block,
    _check,
    _cited_values,
    _nodes,
    _uncited_numbers,
)

_PIPELINE = Path(__file__).resolve().parents[2] / "docs" / "pipeline"
_MODELS = _PIPELINE / "models"
_MAX_EDGES = 24
_STORES = {"store", "file", "external"}
_MD_RE = re.compile(r":\s*\|+[^\w\s|]*md\s(.*?)\s*\|")
_QUOTED_RE = re.compile(r':\s*"((?:[^"\\]|\\.)*)"')
_EDGE_RE = re.compile(r'^\s*([\w.]+)\s*->\s*([\w.]+)\s*:\s*"((?:[^"\\]|\\.)*)"')
_GROUP_RE = re.compile(r'^\s+\w+: "([^"]+)",?$')


def subboards() -> dict[str, tuple[str, str]]:
    """Stem -> (stage, sub) for every docs/pipeline/<stage>-<sub>.d2."""
    out = {}
    for path in sorted(_PIPELINE.glob("*-*.d2")):
        stage, _, sub = path.stem.partition("-")
        if stage in _STAGES:
            out[path.stem] = (stage, sub)
    return out


def group_order(stage: str) -> list[str]:
    """The groups of models/<stage>.view.js, in order of first appearance."""
    path = _MODELS / f"{stage}.view.js"
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()
    start = lines.index("const groups = {")
    order: list[str] = []
    for line in lines[start + 1 :]:
        if line.strip() == "};":
            break
        m = _GROUP_RE.match(line)
        if m and m.group(1) not in order:
            order.append(m.group(1))
    return order


def node_labels(text: str) -> dict[str, tuple[int, str | None, str]]:
    """Dotted path -> (0-based declaration line, class, label text)."""
    lines = _check()._scan(text)
    out = {}
    for path, (i, cls) in _nodes(text).items():
        visible = lines[i].visible
        m = _QUOTED_RE.search(visible) or _MD_RE.search(visible)
        out[path] = (i, cls, m.group(1).strip() if m else "")
    return out


def edges(text: str) -> list[tuple[int, str, str, str]]:
    """(0-based line, src, dst, quoted label) per `a -> b: "..."` line."""
    return [
        (i, m.group(1), m.group(2), m.group(3))
        for i, ln in enumerate(_check()._scan(text))
        if (m := _EDGE_RE.match(ln.visible))
    ]


def first_line(label: str) -> str:
    return label.split("\\n")[0].replace('\\"', '"').strip()


def _text(stem: str) -> str:
    return (_PIPELINE / f"{stem}.d2").read_text(encoding="utf-8")


def _link(block: str) -> str | None:
    m = re.search(r'(?:^|[\s{;])link:\s*"([^"]+)"', block)
    return m.group(1) if m else None


def _next_link(stem: str) -> str:
    stage, _ = subboards()[stem]
    order = group_order(stage)
    i = order.index(stem)
    return f"./{order[i + 1]}.svg" if i + 1 < len(order) else f"./{stage}.svg"


def _hrefs(stem: str) -> set[str]:
    svg = _PIPELINE / f"{stem}.svg"
    return set(re.findall(r'href="([^"]+)"', svg.read_text(encoding="utf-8"))) if svg.exists() else set()


_SUBBOARDS = sorted(subboards())
_SUBBOARDED_STAGES = sorted({stage for stage, _ in subboards().values()})


def test_site_has_four_subboards() -> None:
    assert {s for s, (stage, _) in subboards().items() if stage == "site"} == {
        "site-publish", "site-ci", "site-scan", "site-views",
    }


@pytest.mark.parametrize("stem", _SUBBOARDS)
def test_subboard_names(stem: str) -> None:
    stage, _ = subboards()[stem]
    assert stem in group_order(stage), f"{stem} is not a group of models/{stage}.view.js"
    lines = [ln for ln in _text(stem).splitlines() if ln.strip()]
    assert lines[:2] == ["...@classes", "direction: down"]


@pytest.mark.parametrize("stem", _SUBBOARDS)
def test_objective_note(stem: str) -> None:
    _, cls, label = node_labels(_text(stem)).get("objective", (0, None, ""))
    assert cls == "note"
    assert label.startswith("Objective:") and "\\n" not in label and "\n" not in label


@pytest.mark.parametrize("stem", _SUBBOARDS)
def test_back_note(stem: str) -> None:
    stage, _ = subboards()[stem]
    _, cls, label = node_labels(_text(stem)).get("back", (0, None, ""))
    assert cls == "note"
    assert label == f"back to the {stage} board"
    assert _link(_block(_text(stem), "back") or "") == f"./{stage}.svg"


@pytest.mark.parametrize("stem", _SUBBOARDS)
def test_out_node(stem: str) -> None:
    text = _text(stem)
    _, cls, label = node_labels(text).get("out", (0, None, ""))
    assert cls == "output"
    assert label.startswith("Comes out:")
    assert any(dst == "out" for _, _, dst, _ in edges(text)), "no edge into out"
    assert _link(_block(text, "out") or "") == _next_link(stem)


@pytest.mark.parametrize("stem", _SUBBOARDS)
def test_every_edge_line_is_parsed(stem: str) -> None:
    parsed = {i for i, *_ in edges(_text(stem))}
    loose = [
        ln.visible.strip()
        for i, ln in enumerate(_check()._scan(_text(stem)))
        if "->" in ln.code and i not in parsed
    ]
    assert loose == [], "write every edge as one `a -> b: \"label\"` line"


@pytest.mark.parametrize("stem", _SUBBOARDS)
def test_edge_cap(stem: str) -> None:
    assert len(edges(_text(stem))) <= _MAX_EDGES


@pytest.mark.parametrize("stem", _SUBBOARDS)
def test_decision_edges_carry_a_condition(stem: str) -> None:
    text = _text(stem)
    classes = {path: cls for path, (_, cls, _) in node_labels(text).items()}
    bare = [
        f"{src} -> {dst}"
        for _, src, dst, label in edges(text)
        if classes.get(src) == "decision" and not re.search(r"\[[^\]]+\]", label)
    ]
    assert bare == []


@pytest.mark.parametrize("stem", _SUBBOARDS)
def test_step_and_decision_nodes_carry_a_directive(stem: str) -> None:
    text = _text(stem)
    cited_lines = {d.line for d in _check().directives(text)}
    bare = [
        path
        for path, (i, cls, _) in node_labels(text).items()
        if cls in ("step", "decision") and i + 1 not in cited_lines
    ]
    assert bare == []


@pytest.mark.parametrize("stem", _SUBBOARDS)
def test_subboard_digits_are_cited(stem: str) -> None:
    text = _text(stem)
    cited = _cited_values(text)
    labels = [(i, path, label) for path, (i, _, label) in node_labels(text).items()]
    labels += [(i, f"{src} -> {dst}", label) for i, src, dst, label in edges(text)]
    problems = [
        f"{where}: {bad}"
        for i, where, label in labels
        if (bad := _uncited_numbers(label, cited.get(i + 1, [])))
    ]
    assert problems == []


@pytest.mark.parametrize("stem", _SUBBOARDS)
def test_no_store_only_container(stem: str) -> None:
    nodes = node_labels(_text(stem))
    for path in nodes:
        children = [cls for p, (_, cls, _) in nodes.items() if p.rpartition(".")[0] == path]
        assert not children or not set(children) <= _STORES, f"{path} holds only stores"


@pytest.mark.parametrize("stage", _SUBBOARDED_STAGES)
def test_stage_board_links_its_subboards(stage: str) -> None:
    links = {target for target, _ in _check().links(_text(stage))}
    stems = [s for s, (st, _) in subboards().items() if st == stage]
    assert [s for s in stems if f"./{s}.svg" not in links] == []


@pytest.mark.parametrize("stage", _SUBBOARDED_STAGES)
def test_stage_svg_links_its_subboards(stage: str) -> None:
    stems = [s for s, (st, _) in subboards().items() if st == stage]
    assert [s for s in stems if f"./{s}.svg" not in _hrefs(stage)] == []


@pytest.mark.parametrize("stem", _SUBBOARDS)
def test_subboard_svg_hrefs(stem: str) -> None:
    stage, _ = subboards()[stem]
    hrefs = _hrefs(stem)
    assert f"./{stage}.svg" in hrefs
    assert _next_link(stem) in hrefs
