"""The d2 boards in docs/pipeline/ (issue #144) stay true to src/bot/ and config/.

Shared machinery for every board: each stage issue (#146 to #150) appends its own
entries to the `_REQUIRED_*` dicts and to `_ACRONYMS`. Nothing here runs d2.
"""

from __future__ import annotations

import importlib
import importlib.util
import re
import subprocess
import sys
from enum import Enum
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

from bot.reporting.analysis_report import margin_verdict
from bot.screener.rules import registered_rules
from bot.web.views import MOS_FAIR, MOS_UNDERVALUED

_ROOT = Path(__file__).resolve().parents[2]
_PIPELINE = _ROOT / "docs" / "pipeline"
_SCHEMA = _ROOT / "src" / "bot" / "storage" / "schema.sql"
_PRESET = _ROOT / "config" / "presets" / "damodaran_value.yaml"


def _load_check() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pipeline_check", _PIPELINE / "check.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@cache
def _check() -> ModuleType:
    return _load_check()


@cache
def _boards() -> dict[str, str]:
    return {p.stem: p.read_text(encoding="utf-8") for p in _check().boards(_PIPELINE)}


def _schema_tables() -> set[str]:
    sql = _SCHEMA.read_text(encoding="utf-8")
    return set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", sql))


# --------------------------------------------------------------------------- #
# Required citations, per board stem. Stage issues append their own entries.
# --------------------------------------------------------------------------- #

_REQUIRED_SYMBOLS: dict[str, set[str]] = {
    "pipeline": {
        "bot.cli.refresh",
        "bot.cli.screen",
        "bot.cli.analyze",
        "bot.cli.portfolio",
        "bot.cli.site",
        "bot.web.site.build",
        "bot.notifier.notify_alerts",
    },
}
# Derived from schema.sql, so a new table cannot go undrawn on the overview.
_REQUIRED_TABLES: dict[str, set[str]] = {"pipeline": _schema_tables()}
_REQUIRED_FILES: dict[str, set[str]] = {
    "pipeline": {
        "src/bot/ingest/universe_default.csv",
        "src/bot/ingest/industry_mapping.csv",
        "config/presets/damodaran_value.yaml",
        "scripts/daily.sh",
        "scripts/weekly.sh",
        "scripts/publish_site.sh",
        ".github/workflows/site.yml",
    },
}
_REQUIRED_RULES: dict[str, set[str]] = {}
_REQUIRED_PARAMS: dict[str, set[str]] = {}
_REQUIRED_CONSTS: dict[str, set[str]] = {
    "pipeline": {"bot.web.views.MOS_UNDERVALUED", "bot.web.views.MOS_FAIR"},
}
_REQUIRED_ENUMS: dict[str, set[str]] = {"pipeline": {"bot.web.views.Verdict"}}

_REQUIRED: dict[str, dict[str, set[str]]] = {
    "symbol": _REQUIRED_SYMBOLS,
    "table": _REQUIRED_TABLES,
    "file": _REQUIRED_FILES,
    "rule": _REQUIRED_RULES,
    "param": _REQUIRED_PARAMS,
    "const": _REQUIRED_CONSTS,
    "enum": _REQUIRED_ENUMS,
}

# Acronym -> expansion. Its first use in a board must be preceded by, or share
# its line with, the expansion. Any all-caps token not listed here or in
# _ACRONYMS_EXEMPT fails the suite, so a new acronym cannot slip in unexplained.
_ACRONYMS: dict[str, str] = {
    "SEC": "Securities and Exchange Commission",
    "EDGAR": "Electronic Data Gathering, Analysis, and Retrieval",
    "EOD": "end of day",
    "FX": "foreign exchange",
    "IBKR": "Interactive Brokers",
    "TWS": "Trader Workstation",
    "DCF": "discounted cash flow",
    "WACC": "weighted average cost of capital",
    "MoS": "margin of safety",
    "CI": "continuous integration",
    "FMP": "Financial Modeling Prep",
}
# File formats and words written in capitals that need no expansion.
_ACRONYMS_EXEMPT: set[str] = {
    "JSON", "CSV", "YAML", "SVG", "URL", "HTML", "PNG",
    "US", "USD", "YYYY", "MM", "DD", "TICKER",
}
_ACRONYM_RE = re.compile(r"\b[A-Z][A-Z0-9]+\b|\bMoS\b")


# --------------------------------------------------------------------------- #
# A minimal reading of d2 node blocks, enough to find a node's class and text.
# Convention (docs/pipeline/README.md): `class:` is a node's first attribute.
# --------------------------------------------------------------------------- #


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip())


def _block(text: str, dotted: str) -> str | None:
    """The source of node `a.b.c`: its declaration line and every deeper line after it.

    The first part is a top-level key; each next part is searched inside the block found so far.
    """
    lines = text.splitlines()
    lo, hi, found = 0, len(lines), -1
    for n, part in enumerate(dotted.split(".")):
        key = re.compile(rf"^{'' if n == 0 else r'\s*'}{re.escape(part)}\s*:")
        hit = next((i for i in range(lo, hi) if key.match(lines[i])), None)
        if hit is None:
            return None
        found, depth, stop = hit, _indent(lines[hit]), hit + 1
        while stop < hi and (not lines[stop].strip() or _indent(lines[stop]) > depth):
            stop += 1
        lo, hi = found + 1, stop
    return "\n".join(lines[found:hi])


def _node_class(text: str, dotted: str) -> str | None:
    block = _block(text, dotted)
    if block is None:
        return None
    m = re.search(r"\bclass:\s*(\w+)", block)
    return m.group(1) if m else None


def _shown_in_board(value: str, board: str) -> bool:
    return _check().normalize(value) in _check().normalize(_check().visible(board))


# --------------------------------------------------------------------------- #
# Machinery shared by every board
# --------------------------------------------------------------------------- #


def test_there_are_boards() -> None:
    assert "pipeline" in _boards()
    assert "classes" not in _boards()


def test_check_py_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, str(_PIPELINE / "check.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert re.search(r"check \| \d+ boards, \d+ citations, 0 errors", result.stdout)


def _preset_params() -> dict[str, Any]:
    preset = yaml.safe_load(_PRESET.read_text(encoding="utf-8"))
    params: dict[str, Any] = {
        f"ranking.{k}": v for k, v in preset["ranking"]["weights"].items()
    }
    for section in ("quality_gates", "value_indicators", "trap_detection"):
        for rule in preset[section]["rules"]:
            for name, value in (rule.get("params") or {}).items():
                params[f"{rule['name']}.{name}"] = value
    return params


def _resolve(dotted: str) -> Any:
    module, _, name = dotted.rpartition(".")
    return getattr(importlib.import_module(module), name)


def _directive_problem(d: Any, board: str) -> str | None:
    if d.kind == "rule":
        return None if d.argument in registered_rules() else "no such rule"
    if d.kind == "param":
        params = _preset_params()
        if d.argument not in params:
            return f"not in {_PRESET.name}"
        value = params[d.argument]
        return None if _check().shown(value, d.text) else f"value {value!r} not shown"
    if d.kind == "const":
        try:
            value = _resolve(d.argument)
        except (ImportError, AttributeError):
            return "no such constant"
        return None if _check().shown(value, d.text) else f"value {value!r} not shown"
    if d.kind == "enum":
        try:
            enum = _resolve(d.argument)
        except (ImportError, AttributeError):
            return "no such enum"
        if not (isinstance(enum, type) and issubclass(enum, Enum)):
            return "not an Enum"
        missing = [m.value for m in enum if not _shown_in_board(str(m.value), board)]
        return f"members not shown: {missing}" if missing else None
    return None  # symbol / table / file: _check().py owns them (test_check_py_exits_zero)


def test_every_directive_is_valid() -> None:
    problems = [
        f"{stem}.d2:{d.line} @{d.kind} {d.argument}: {problem}"
        for stem, board in _boards().items()
        for d in _check().directives(board)
        if (problem := _directive_problem(d, board))
    ]
    assert problems == []


@pytest.mark.parametrize("kind", list(_REQUIRED))
def test_required_citations_present(kind: str) -> None:
    missing = {
        stem: sorted(
            required
            - {d.argument for d in _check().directives(_boards().get(stem, "")) if d.kind == kind}
        )
        for stem, required in _REQUIRED[kind].items()
    }
    assert {stem: m for stem, m in missing.items() if m} == {}


def test_acronyms_are_expanded() -> None:
    problems = []
    for stem, board in _boards().items():
        vis = _check().visible(board)
        for token in sorted(set(_ACRONYM_RE.findall(vis)) - _ACRONYMS_EXEMPT):
            if token not in _ACRONYMS:
                problems.append(f"{stem}.d2: {token} is not in _ACRONYMS")
                continue
            first = re.search(rf"\b{re.escape(token)}\b", vis)
            assert first is not None
            end = vis.find("\n", first.start())
            upto = vis[: end if end != -1 else len(vis)]

            def norm(s: str) -> str:
                return " ".join(s.lower().replace("-", " ").split())

            if norm(_ACRONYMS[token]) not in norm(upto):
                problems.append(f"{stem}.d2: {token} used before '{_ACRONYMS[token]}'")
    assert problems == []


def test_each_board_has_a_rendered_svg() -> None:
    for stem in _boards():
        svg = _PIPELINE / f"{stem}.svg"
        assert svg.exists(), f"{svg.name} missing: run docs/pipeline/build.sh"
        assert "<svg" in svg.read_text(encoding="utf-8")[:2000]


def test_classes_define_the_nine_shapes() -> None:
    classes = (_PIPELINE / "classes.d2").read_text(encoding="utf-8")
    shapes = {
        "step": "rectangle",
        "decision": "diamond",
        "store": "cylinder",
        "external": "cloud",
        "file": "page",
        "output": "document",
        "cron": "hexagon",
        "note": "text",
        "gap": "text",
    }
    body = _block(classes, "classes")
    assert body is not None
    depth = min(_indent(line) for line in body.splitlines()[1:] if line.strip() not in ("", "}"))
    declared = {
        m.group(1)
        for line in body.splitlines()[1:]
        if _indent(line) == depth and (m := re.match(r"\s*(\w+)\s*:", line))
    }
    assert declared == set(shapes)
    for name, shape in shapes.items():
        block = _block(classes, f"classes.{name}")
        assert block is not None and re.search(rf"\bshape:\s*{shape}\b", block), name


def test_every_board_imports_the_classes_and_no_other_board() -> None:
    for stem, board in _boards().items():
        assert re.search(r"(?m)^\.\.\.@classes\s*$", board), stem
        imports = set(re.findall(r"@(\w+)", _check().visible(board)))
        assert imports <= {"classes"}, f"{stem}.d2 imports {imports - {'classes'}}"


# --------------------------------------------------------------------------- #
# pipeline.d2 — the whole pipeline on one page (#145)
# --------------------------------------------------------------------------- #

_STAGES = ("refresh", "screen", "analyze", "portfolio", "site")
_EXTERNALS = {
    "damodaran_data": "Damodaran",
    "edgar": "EDGAR",
    "tiingo": "Tiingo",
    "stooq": "Stooq",
    "fmp": "Financial Modeling Prep",
    "tws": "Trader Workstation",
    "flex": "Flex",
    "pages": "GitHub Pages",
}
_FILES = ("universe_csv", "industry_mapping_csv", "presets", "assumptions", "sidecars")
_OUTPUTS = ("screen_report", "analysis_reports", "portfolio_md", "notifier_message", "published_site")


def _overview() -> str:
    return _boards()["pipeline"]


@pytest.mark.parametrize(
    ("key", "cls"),
    [(s, "step") for s in _STAGES]
    + [("daily", "cron"), ("weekly", "cron")]
    + [(e, "external") for e in _EXTERNALS]
    + [(f, "file") for f in _FILES]
    + [(o, "output") for o in _OUTPUTS]
    + [("site.verdicts", "note")],
)
def test_overview_nodes(key: str, cls: str) -> None:
    assert _node_class(_overview(), key) == cls


def test_external_services_are_named() -> None:
    for key, name in _EXTERNALS.items():
        block = _block(_overview(), key)
        assert block is not None and name in block, key


def test_every_table_is_a_store_in_the_duckdb_container() -> None:
    for table in sorted(_schema_tables()):
        assert _node_class(_overview(), f"duckdb.{table}") == "store", table
    lines = {d.line for d in _check().directives(_overview()) if d.kind == "table"}
    assert len(lines) == len(_schema_tables())  # each table on its own node


def test_stage_labels_carry_a_purpose() -> None:
    for stage in _STAGES:
        block = _block(_overview(), stage)
        assert block is not None
        label = block.splitlines()[0].split(":", 1)[1]
        assert stage in label and len(label.split()) >= 4, stage


def _cron_edges(cron: str) -> list[tuple[int, str]]:
    edges = re.findall(rf'(?m)^\s*{cron}\s*->\s*(\w+)\s*:\s*"?(\d+)\.', _overview())
    return sorted((int(n), target) for target, n in edges)


def test_cron_edges_run_the_commands_in_order() -> None:
    assert _cron_edges("weekly") == [(1, "refresh"), (2, "screen"), (3, "analyze"), (4, "site")]
    assert _cron_edges("daily") == [(1, "refresh"), (2, "refresh"), (3, "portfolio")]


def test_every_edge_is_labelled() -> None:
    unlabelled = [
        line.strip()
        for line in _check().visible(_overview()).splitlines()
        if re.search(r"->|<-", line) and not re.search(r"(->|<-)[^:]*:\s*\S", line)
    ]
    assert unlabelled == []


def test_verdict_note_states_the_thresholds() -> None:
    block = _block(_overview(), "site.verdicts")
    assert block is not None
    for words in ("1.3", "potentially undervalued", "1.0", "around fair value",
                  "potentially overvalued", "n/a"):
        assert words in block, words


def test_verdict_thresholds_match_margin_verdict() -> None:
    assert margin_verdict(MOS_UNDERVALUED) == "potentially undervalued"
    assert margin_verdict(MOS_UNDERVALUED - 1e-9) == "around fair value"
    assert margin_verdict(MOS_FAIR) == "around fair value"
    assert margin_verdict(MOS_FAIR - 1e-9) == "potentially overvalued"
    assert margin_verdict(None) == "n/a"


# --------------------------------------------------------------------------- #
# README and CONTEXT.md
# --------------------------------------------------------------------------- #


def test_readme_has_build_and_check_commands() -> None:
    readme = (_PIPELINE / "README.md").read_text(encoding="utf-8")
    assert len(readme.splitlines()) <= 40
    assert "docs/pipeline/build.sh" in readme
    assert "python3 docs/pipeline/check.py" in readme
    for kind in _check().KINDS:
        assert f"`@{kind}" in readme, kind
    assert "D2_VERSION" in readme
    assert "pipeline-diagram" in readme and "pipeline-render" in readme


def test_context_source_of_truth_links_the_pipeline_docs() -> None:
    context = (_ROOT / "CONTEXT.md").read_text(encoding="utf-8")
    section = context[
        context.index("## Source of truth") : context.index("## Working with the plans")
    ]
    assert "docs/pipeline/" in section
