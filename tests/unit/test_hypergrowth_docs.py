"""The written record of the hypergrowth story type (issue #198, story #192).

ADR 0009, the spec, the glossary and the two plans say what the code does.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from dataclasses import fields
from pathlib import Path
from types import ModuleType

from bot.valuator.hypergrowth import StoryInputs

_ROOT = Path(__file__).resolve().parents[2]
_ADR = _ROOT / "docs" / "adr" / "0009-hypergrowth-story-driven-gated-on-story-file.md"
_SPEC = _ROOT / "docs" / "superpowers" / "specs" / "2026-05-25-investment-bot-design.md"
_PLANO = _ROOT / "docs" / "plano"
_STORY_KEYS = {f.name for f in fields(StoryInputs)}


def _section(text: str, start: str, end: str | None) -> str:
    begin = text.index(start)
    if end is None:
        return text[begin:]
    return text[begin : text.index(end, begin)]


def _adr_section(heading: str) -> str:
    text = _ADR.read_text(encoding="utf-8")
    body = text[text.index(f"## {heading}") + len(heading) + 3 :]
    return body.split("\n## ", 1)[0]


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"plano_{name}", _PLANO / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(_PLANO))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(_PLANO))
    return module


def _js_card(text: str, card: str) -> str:
    begin = text.index(f'"{card}":{{')
    match = re.compile(r'\n"?[\w-]+"?:\{').search(text, begin + 1)
    return text[begin : match.start() if match else len(text)]


def test_adr_0009_exists_and_is_implemented() -> None:
    assert list((_ROOT / "docs" / "adr").glob("0009-*.md")) == [_ADR]
    text = _ADR.read_text(encoding="utf-8")
    headings = re.findall(r"^## (\w+)", text, re.M)
    assert headings == ["Status", "Context", "Decision", "Consequences"]
    status = _adr_section("Status")
    assert "Accepted (2026-11-02)" in status
    assert "Implemented (2026-11-02, issue #192)" in status


def test_adr_0009_decision_covers_the_design() -> None:
    decision = _adr_section("Decision")
    for words in (
        "story",
        "high-growth",
        "red",
        "year1_margin",
        "target_revenue_y10",
        "wacc_path",
        "tax_rate_path",
        "terminal_roic",
        "distress_proceeds_pct",
        "fixed_commitments",
        "extra_cash",
        "governance_discount",
        "scenarios",
        "hypergrowth_story",
        "hypergrowth_revenue_scale",
        "hypergrowth_terminal_roic",
        "screener",
        "raw reporting currency",
    ):
        assert words in decision, words


def test_adr_0009_consequences() -> None:
    consequences = _adr_section("Consequences")
    for words in ("never applied automatically", "schema_version", "447.34", "same-year"):
        assert words in consequences, words
    assert "10-point" in consequences or "0.10" in consequences


def test_context_links_adr_0009_and_defines_the_terms() -> None:
    context = (_ROOT / "CONTEXT.md").read_text(encoding="utf-8")
    assert "docs/adr/0009-hypergrowth-story-driven-gated-on-story-file.md" in context
    story_type = next(ln for ln in context.splitlines() if ln.startswith("- **Story type**"))
    assert "`hypergrowth`" in story_type
    for term in ("Hypergrowth", "Story file", "Governance discount"):
        assert f"\n- **{term}**" in context, term
    mos = next(ln for ln in context.splitlines() if ln.startswith("- **Margin of safety"))
    assert "intrinsic_value_after_governance" in mos


def _spec(start: str, end: str) -> str:
    return _section(_SPEC.read_text(encoding="utf-8"), start, end)


def test_spec_7_1_has_the_hypergrowth_row() -> None:
    section = _spec("### 7.1", "### 7.2")
    row = next(ln for ln in section.splitlines() if ln.startswith("| `hypergrowth` |"))
    for words in ("año 10", "rampa", "WACC", "quiebra", "compromisos", "deuda"):
        assert words in row, words
    assert "sección `story`" in section


def test_spec_7_3_lists_story_source() -> None:
    section = _spec("### 7.3", "### 7.4")
    sources = re.search(r"source ∈ \{([^}]*)\}", section)
    assert sources is not None
    assert "story" in [s.strip() for s in sources.group(1).split(",")]


def test_spec_7_5_lists_hypergrowth_flags() -> None:
    section = _spec("### 7.5", "### 7.6")
    for flag in ("hypergrowth_story", "hypergrowth_revenue_scale", "hypergrowth_terminal_roic"):
        assert flag in section, flag


def test_spec_7_6_documents_every_story_key() -> None:
    section = _spec("### 7.6", "### 7.7")
    for key in sorted(_STORY_KEYS | {"founded_year", "scenarios", "worst", "best"}):
        assert key in section, key


_HY_FLAGS = {
    "f-hy-story": "hypergrowth_story_flag",
    "f-hy-scale": "hypergrowth_revenue_scale_flag",
    "f-hy-roic": "hypergrowth_terminal_roic_flag",
}


def test_plano_story_has_hypergrowth() -> None:
    stories = _load("views").STORIES
    assert ("s-hy", "hypergrowth", "la historia manda, no el balance") in [s[:3] for s in stories]


def test_plano_flags_have_the_hypergrowth_three() -> None:
    ids = [f[0] for f in _load("views").FLAGS]
    assert ids[:5] == ["f-story", "f-growth", "f-beta", "f-tv", "f-country"]
    assert [i for i in ids if i in _HY_FLAGS] == list(_HY_FLAGS)
    assert ids.index("f-hy-story") > ids.index("f-country")


def test_plano_cards_and_meta() -> None:
    data = (_PLANO / "part-data.js").read_text(encoding="utf-8")
    meta = (_PLANO / "part-meta.js").read_text(encoding="utf-8")
    order = (_PLANO / "part-js.js").read_text(encoding="utf-8")
    order = order[order.index("const ORDEN") : order.index("].filter")]
    assert '"s-hy":{role:"valua"' in data
    assert '"s-hy":{sym:"src/bot/valuator/story_types.py:StoryType"' in meta
    for card, function in _HY_FLAGS.items():
        assert f'"{card}":{{role:"valua"' in data, card
        assert f'"{card}":{{sym:"src/bot/valuator/narrative_flags.py:{function}"' in meta, card
    for card in ("s-hy", *_HY_FLAGS):
        assert f'"{card}"' in order, card


def test_plano_a_default_mentions_the_story() -> None:
    card = _js_card((_PLANO / "part-data.js").read_text(encoding="utf-8"), "a-default")
    for key in ("failure_probability", "failure_proceeds_pct_of_value"):
        assert key in _STORY_KEYS, key
        assert key in card, key


def test_plano_build_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(_PLANO / "build.py")], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_estado_audit_stamp() -> None:
    estado = _load("estado")
    assert estado.AUDITADO_EN == "90f717c"
    assert estado.AUDITADO_EL == "2 de noviembre de 2026"


def test_estado_rows_carry_hypergrowth_evidence() -> None:
    estado = _load("estado")
    rows = {row[0]: row for layer in ("capa-c", "proyecto") for row in estado.INVENTARIO[layer][2]}
    for cid in ("classify", "story-uso", "a-quiebra", "dcf-quiebra", "flags-4", "m4"):
        _, _, _, evidence, note = rows[cid]
        assert "hypergrowth" in f"{evidence} {note or ''}", cid
    assert "valuator/story_types.py:" in rows["classify"][3]
    assert "valuator/hypergrowth.py:" in rows["story-uso"][3]


def test_estado_still_79_rows() -> None:
    estado = _load("estado")
    assert sum(len(items) for _, _, items in estado.INVENTARIO.values()) == 79
    assert "79 componentes" in (_PLANO / "README.md").read_text(encoding="utf-8")


def test_estado_build_passes() -> None:
    result = subprocess.run(
        [sys.executable, str(_PLANO / "build_estado.py")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
