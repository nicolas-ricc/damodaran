"""docs/pipeline/<stage>-<sub>.d2: the sub-board conventions (#164).

Generic over every sub-board in the folder, so each stage that gains sub-boards inherits them.
A sub-board is the stage's checked statechart drawn in d2: see docs/pipeline/README.md.
"""

from __future__ import annotations

import re
from collections import Counter
from pathlib import Path

import pytest

from bot.screener.rules import registered_rules
from tests.unit.test_pipeline_diagram import (
    _SCREEN_LAYER_BOARDS,
    _STAGES,
    _block,
    _check,
    _cited_values,
    _nodes,
    _preset_rule_layers,
    _uncited_numbers,
)

_PIPELINE = Path(__file__).resolve().parents[2] / "docs" / "pipeline"
_MODELS = _PIPELINE / "models"
_MAX_EDGES = 24
_STORES = {"store", "file", "external"}
_MD_RE = re.compile(r":\s*\|+[^\w\s|]*md\s(.*?)\s*\|")
_QUOTED_RE = re.compile(r':\s*"((?:[^"\\]|\\.)*)"')
_EDGE_RE = re.compile(r'^\s*([\w.]+)\s*->\s*([\w.]+)\s*:\s*"((?:[^"\\]|\\.)*)"')


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
    from tests.unit.test_pipeline_models import _map

    if not (_MODELS / f"{stage}.view.js").exists():
        return []
    return [g for g in dict.fromkeys(_map(stage, "groups").values()) if g]


def node_labels(text: str) -> dict[str, tuple[int, str | None, str]]:
    """Dotted path -> (0-based declaration line, class, label text)."""
    lines = _check()._scan(text)
    out = {}
    for path, (i, cls) in _nodes(text).items():
        visible = lines[i].visible
        found = [m for m in (_QUOTED_RE.search(visible), _MD_RE.search(visible)) if m]
        m = min(found, key=lambda m: m.start(), default=None)
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


def _anchors(stem: str) -> Counter[str]:
    """Target -> number of `<a href>` in the rendered SVG: d2 writes one per `link:`."""
    svg = _PIPELINE / f"{stem}.svg"
    text = svg.read_text(encoding="utf-8") if svg.exists() else ""
    return Counter(re.findall(r'<a href="([^"]+)"', text))


def _hrefs(stem: str) -> set[str]:
    return set(_anchors(stem))


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


@pytest.mark.parametrize("stem", _SUBBOARDS + _SUBBOARDED_STAGES)
def test_svg_keeps_every_link(stem: str) -> None:
    """A link dropped by d2 cannot hide behind another node linking the same target."""
    assert _anchors(stem) == Counter(target for target, _ in _check().links(_text(stem)))


# Refresh sub-boards (#166).
_REFRESH_SUBBOARDS = {
    "refresh-damodaran", "refresh-fundamentals", "refresh-facts", "refresh-prices", "refresh-fx",
}
# Scheduled entry points appear only on the sub-board they enter.
_REFRESH_CRONS: dict[str, set[str]] = {
    "refresh-damodaran": {"scripts/weekly.sh"},
    "refresh-fundamentals": set(),
    "refresh-facts": set(),
    "refresh-prices": {"scripts/daily.sh", "scripts/price_fill.sh"},
    "refresh-fx": {"scripts/daily.sh"},
}
# What a reader must find on each board (issue #166 acceptance criteria).
_REFRESH_TEXT: dict[str, list[str]] = {
    "refresh-damodaran": [
        "the earlier file wins a shared column",
        "D/E = w ÷ (1 - w)",  # normalize() reads the minus sign as a hyphen
        "beta_unlevered = beta_levered ÷ (1 + (1 - tax) \u00d7 D/E)",
    ],
    "refresh-fundamentals": ["5%", "25%", "deferred, not failed"],
    "refresh-facts": [
        "350 to 380 days",
        "80 to 100 days",
        "the first concept in the list",
        "calendar year of its end",
        "91.3",
        "1,000,000",
        "financials_annual",
        "financials_quarterly",
    ],
    "refresh-prices": ["5%", "25%", "deferred, not failed", "stalest first"],
    "refresh-fx": ["5%", "25%", "deferred"],
}


def test_refresh_has_five_subboards() -> None:
    assert {s for s, (stage, _) in subboards().items() if stage == "refresh"} == _REFRESH_SUBBOARDS


@pytest.mark.parametrize("stem", sorted(_REFRESH_CRONS))
def test_refresh_subboard_crons(stem: str) -> None:
    text = _text(stem)
    cron_lines = {i + 1 for i, cls, _ in node_labels(text).values() if cls == "cron"}
    cited = {
        d.argument
        for d in _check().directives(text)
        if d.kind == "file" and d.line in cron_lines
    }
    assert cited == _REFRESH_CRONS[stem]


@pytest.mark.parametrize("stem", sorted(_REFRESH_TEXT))
def test_refresh_subboard_text(stem: str) -> None:
    text = _text(stem)
    visible = _check().normalize(_check().visible(text).replace("\\n", " "))
    missing = [p for p in _REFRESH_TEXT[stem] if _check().normalize(p) not in visible]
    assert missing == []


def test_refresh_damodaran_objective_names_the_eight_files() -> None:
    _, _, label = node_labels(_text("refresh-damodaran"))["objective"]
    assert "eight files" in label


# Screen sub-boards (#168).
_SCREEN_SUBBOARDS = {
    "screen-snapshot", "screen-coverage", "screen-quality", "screen-value", "screen-traps",
    "screen-ranking",
}
# What a reader must find on each board (issue #168 acceptance criteria).
_SCREEN_TEXT: dict[str, list[str]] = {
    "screen-snapshot": [
        "ROE = net income \u00f7 total equity",
        "EV \u00f7 EBITDA = (market cap + net debt) \u00f7 EBITDA",
        "ROIC = EBIT \u00d7 (1 \u2212 tax) \u00f7 (total debt + total equity)",
        "free cash flow yield = free cash flow \u00f7 market cap",
        "21%",
    ],
    "screen-coverage": ["ADR 0006 (Implemented)", "config/currencies.yaml"],
    "screen-quality": ["100M", "\u2264 4", "\u2265 2", "\u2264 0.5"],
    "screen-value": [
        "0.7 \u00d7 sector median",
        "8%",
        "value metric = highest score among passing indicators",
    ],
    "screen-traps": ["\u22125%", "\u2212200 basis points", "< 0.1", "\u2264 5%"],
    "screen-ranking": [
        "0.40 \u00d7 value",
        "0.30 \u00d7 quality",
        "0.20 \u00d7 growth",
        "0.10 \u00d7 margin of safety",
        "ties share a percentile",
        "--top",
        "0.5",
    ],
}
_COVERAGE_ORDER = ("industry_unmapped", "benchmark_missing", "currency_uncovered")
# A skipped value indicator neither passes nor fails; a skipped trap detector fails.
_SKIP_TARGETS = {
    "screen-value": "every value indicator was skipped",
    "screen-traps": "a trap detector failed",
}


def _visible(stem: str) -> str:
    return _check().normalize(_check().visible(_text(stem)).replace("\\n", " "))


def test_screen_has_six_subboards() -> None:
    assert {s for s, (stage, _) in subboards().items() if stage == "screen"} == _SCREEN_SUBBOARDS


def _rule_boards(rule: str) -> set[str]:
    """Screen sub-boards with a decision node citing `@rule <rule>` on its line or the one before."""
    found = set()
    for stem in sorted(_SCREEN_SUBBOARDS & set(subboards())):
        text = _text(stem)
        cited = {d.line for d in _check().directives(text) if d.kind == "rule" and d.argument == rule}
        decisions = [i for i, cls, _ in node_labels(text).values() if cls == "decision"]
        if any(i + 1 in cited or i in cited for i in decisions):
            found.add(stem)
    return found


def test_screen_preset_holds_every_registered_rule() -> None:
    assert set(_preset_rule_layers()) == set(registered_rules())


@pytest.mark.parametrize("rule", sorted(_preset_rule_layers()))
def test_screen_rules_sit_on_their_layer_subboard(rule: str) -> None:
    assert _rule_boards(rule) == {_SCREEN_LAYER_BOARDS[_preset_rule_layers()[rule]]}


@pytest.mark.parametrize("stem", sorted(_SKIP_TARGETS))
def test_screen_skip_branches(stem: str) -> None:
    text = _text(stem)
    nodes = node_labels(text)
    targets = {first_line(nodes[dst][2]) for _, _, dst, label in edges(text) if "[skipped]" in label}
    assert targets == {_SKIP_TARGETS[stem]}


def test_screen_coverage_reasons_in_order() -> None:
    _, _, label = node_labels(_text("screen-coverage"))["rejected_coverage"]
    positions = [label.find(reason) for reason in _COVERAGE_ORDER]
    assert -1 not in positions and positions == sorted(positions)


@pytest.mark.parametrize("stem", sorted(_SCREEN_TEXT))
def test_screen_subboard_text(stem: str) -> None:
    visible = _visible(stem)
    missing = [p for p in _SCREEN_TEXT[stem] if _check().normalize(p) not in visible]
    assert missing == []


# Analyze sub-boards (#170).
_ANALYZE_SUBBOARDS = {
    "analyze-inputs", "analyze-story", "analyze-assumptions", "analyze-dcf",
    "analyze-sensitivity", "analyze-flags", "analyze-verdict",
}
# What a reader must find on each board (issue #170 acceptance criteria); the DCF lines are
# the arithmetic of src/bot/valuator/dcf.py.
_ANALYZE_TEXT: dict[str, list[str]] = {
    "analyze-inputs": [
        "--from-screen",
        "config/assumptions/TICKER.yaml",
        "China, India, Japan",
        "net debt = total debt \u2212 cash",
        "interest coverage = EBIT \u00f7 interest expense",
    ],
    "analyze-story": [
        "first match wins",
        "Altman Z < 1.81",
        "coefficient of variation = standard deviation \u00f7 |mean| of net income",
        "CAGR = (last \u00f7 first)^(1 \u00f7 (years \u2212 1)) \u2212 1",
    ],
    "analyze-assumptions": [
        "story_pattern",
        "historical_average",
        "sector_default_damodaran_cross_region",
        "min(risk-free rate, nominal GDP growth)",
        "debt weight = D/E \u00f7 (1 + D/E)",
        "config/currencies.yaml",
    ],
    "analyze-dcf": [
        "WACC = equity weight \u00d7 cost of equity + debt weight \u00d7 pre-tax cost of debt"
        " \u00d7 (1 \u2212 tax)",
        "revenue_t = revenue_t\u22121 \u00d7 (1 + g_t)",
        "EBIT_t = revenue_t \u00d7 margin_t",
        "NOPAT_t = EBIT_t \u00d7 (1 \u2212 tax)",
        "reinvestment_t = (revenue_t \u2212 revenue_t\u22121) \u00f7 sales-to-capital",
        "FCFF_t = NOPAT_t \u2212 reinvestment_t",
        "present value_t = FCFF_t \u00f7 (1 + WACC)^t",
        "terminal value = FCFF_N+1 \u00f7 (WACC \u2212 g_terminal)",
        "present value of terminal value = terminal value \u00f7 (1 + WACC)^N",
        "EV = \u03a3 present value_t + present value of terminal value",
        "equity = EV \u2212 net debt + adjustments",
        "going-concern value per share = equity \u00f7 diluted shares",
        "intrinsic value per share = (1 \u2212 p) \u00d7 going-concern value per share"
        " + p \u00d7 distress value per share",
    ],
    "analyze-sensitivity": [
        "swing = |intrinsic value at \u00d7 1.2 \u2212 intrinsic value at \u00d7 0.8|",
        "two widest",
        "cell = intrinsic value \u00f7 price",
    ],
    "analyze-flags": ["always unknown", "300 bps", "operating leverage = %\u0394EBIT \u00f7 %\u0394Revenue"],
    "analyze-verdict": [
        "potentially undervalued",
        "around fair value",
        "potentially overvalued",
        "n/a",
        "decides nothing",
        "reports/YYYY-MM-DD/analysis/TICKER.json",
    ],
}
# The gap notes a sub-board repeats because they change what the reader sees in the flow.
_ANALYZE_GAPS = {"analyze-story": "Altman Z", "analyze-flags": "always unknown"}


def test_analyze_has_seven_subboards() -> None:
    assert {s for s, (stage, _) in subboards().items() if stage == "analyze"} == _ANALYZE_SUBBOARDS


@pytest.mark.parametrize("stem", sorted(_ANALYZE_TEXT))
def test_analyze_subboard_text(stem: str) -> None:
    visible = _visible(stem)
    missing = [p for p in _ANALYZE_TEXT[stem] if _check().normalize(p) not in visible]
    assert missing == []


def test_analyze_verdict_outputs() -> None:
    from tests.unit.test_pipeline_models import _map

    text = _text("analyze-verdict")
    nodes = node_labels(text)
    reported = _map("analyze", "states")["reported"]
    outputs = {p for p, (_, cls, _) in nodes.items() if cls == "output" and p != "out"}
    assert len(outputs) == 3
    fed = {dst for _, src, dst, _ in edges(text) if first_line(nodes.get(src, (0, None, ""))[2]) == reported}
    assert outputs <= fed
    json_outputs = [p for p in outputs if ".json" in nodes[p][2]]
    assert len(json_outputs) == 1
    assert _link(_block(text, json_outputs[0]) or "") == "./site.svg"


@pytest.mark.parametrize("stem", sorted(_ANALYZE_SUBBOARDS))
def test_analyze_gap_notes(stem: str) -> None:
    gaps = [label for _, cls, label in node_labels(_text(stem)).values() if cls == "gap"]
    if stem in _ANALYZE_GAPS:
        assert any(g.startswith("Gap:") and _ANALYZE_GAPS[stem] in g for g in gaps), gaps
    else:
        assert gaps == []
