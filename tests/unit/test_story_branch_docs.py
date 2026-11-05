"""#247: the atlas, model labels, lesson and plano describe the distressed and
mature-decline branches of `resolve_assumptions` (story #213)."""

from __future__ import annotations

import html
import re

from tests.unit.test_hypergrowth_docs import _js_card, _load
from tests.unit.test_pipeline_diagram import _ROOT, _analyze_block, _check, _label
from tests.unit.test_pipeline_models import _MODELS, _map
from tests.unit.test_pipeline_subboards import _text, edges, first_line

_MARGIN_STEPS = (
    "operating margin, a 10-year path",
    "1. manual → manual",
    "2. high-growth with a latest EBIT ÷ revenue: straight line from it to the sector op_margin"
    " → story_pattern",
    "3. cyclical with ≥ 4 years: mean of the yearly EBIT ÷ revenue → historical_average",
    "4. mature-decline with a latest EBIT ÷ revenue: that margin each year → historical_average",
    "5. sector op_margin each year → sector label",
    "no sector op_margin: unresolved",
)
_BANKRUPTCY_STEPS = (
    "probability of bankruptcy p and distress value per share",
    "1. manual → manual",
    "2. distressed: interest coverage → synthetic rating → ten-year cumulative default"
    " probability,",
    "both tables in config/default_spreads.yaml → rule_based",
    "coverage unknown, or the file absent or malformed: 0 → rule_based, and the report says why",
    "3. else 0 → rule_based",
    "distress value per share: manual, else 0 → rule_based",
)
_ALTMAN_GAP = (
    "Gap: spec §7.3 derives a distressed company's p from its rating or Altman Z; Altman Z is"
    " computed nowhere, so the rating is synthetic, from interest coverage alone; the distress"
    " value per share is still manual or 0."
)
_MARGIN_FIRST = (
    "operating margin gets a source [manual, story pattern, cycle average, own margin, or sector]"
)
_BANKRUPTCY_FIRST = (
    "tax rate and bankruptcy odds are set [no story; tax manual, sector, country, or 25%;"
    " bankruptcy manual, from the coverage rating of a distressed company, or 0]"
)
_TABLE_CITATION = (
    "@file config/default_spreads.yaml @symbol bot.reference.default_spreads.load_default_spreads"
)
_LECCION = _ROOT / "docs" / "leccion" / "index.html"
_PLANO = _ROOT / "docs" / "plano"


def _flat(text: str) -> str:
    return _check().normalize(text.replace("\\n", " "))


def _in_order(text: str, parts: tuple[str, ...]) -> list[str]:
    """The parts missing from `text`, or found out of order."""
    flat, at, bad = _flat(text), 0, []
    for part in parts:
        i = flat.find(_flat(part), at)
        if i < 0:
            bad.append(part)
        else:
            at = i + len(_flat(part))
    return bad


def _edge(src: str, dst: str, first: str) -> tuple[int, str]:
    text = _text("analyze-assumptions")
    found = [(i, label) for i, s, d, label in edges(text)
             if (s, d) == (src, dst) and first_line(label) == first]
    assert len(found) == 1, f"{src} -> {dst}: no edge whose first line is {first!r}"
    return found[0]


def _directive(i: int) -> str:
    return _text("analyze-assumptions").splitlines()[i]


# analyze.d2


def test_analyze_board_margin_node_carries_the_pinned_text() -> None:
    block = _analyze_block("assumptions.margin")
    assert _in_order(_label(block), _MARGIN_STEPS) == []
    for cite in ("_resolve_operating_margin", "_HORIZON", "_MIN_CYCLE_YEARS"):
        assert cite in block.splitlines()[0], cite


def test_analyze_board_bankruptcy_node_carries_the_pinned_text() -> None:
    block = _analyze_block("assumptions.bankruptcy")
    assert _in_order(_label(block), _BANKRUPTCY_STEPS) == []
    assert (
        "# @symbol bot.valuator.assumptions._resolve_probability_of_bankruptcy " + _TABLE_CITATION
        in block.splitlines()[0]
    )


def test_analyze_board_altman_gap_replaces_manual_only() -> None:
    block = _analyze_block("assumptions.bankruptcy")
    assert "manual_only" not in block
    gap = _analyze_block("assumptions.bankruptcy.altman")
    assert "class: gap" in gap
    assert _flat(_ALTMAN_GAP) in _flat(gap)
    assert "class: gap" in _analyze_block("story_type.distressed.altman")


# analyze-assumptions.d2, analyze.view.js, analyze.tla


def test_assumptions_board_keeps_24_edges() -> None:
    assert len(edges(_text("analyze-assumptions"))) == 24


def test_assumptions_board_first_lines_equal_the_view_labels() -> None:
    steps = _map("analyze", "steps")
    assert steps["MarginIsResolved"] == _MARGIN_FIRST
    assert steps["TaxAndBankruptcyAreSet"] == _BANKRUPTCY_FIRST
    _edge("growth_set", "margin_set", _MARGIN_FIRST)
    _edge("tg_set", "ready", _BANKRUPTCY_FIRST)


def test_assumptions_board_margin_edge_lists_mature_decline() -> None:
    _, label = _edge("growth_set", "margin_set", _MARGIN_FIRST)
    assert _in_order(label, (
        "1. manual → manual",
        "2. high-growth",
        "3. cyclical",
        "4. mature-decline with a latest EBIT ÷ revenue: that margin each year → historical_average",
        "5. sector margin each year → sector label",
    )) == []


def test_assumptions_board_bankruptcy_edge_cites_the_table() -> None:
    i, label = _edge("tg_set", "ready", _BANKRUPTCY_FIRST)
    assert _in_order(label, (
        "1. manual → manual",
        "2. distressed: interest coverage → synthetic rating → ten-year cumulative default"
        " probability",
        "config/default_spreads.yaml → rule_based",
        "coverage unknown, or the file absent or malformed: 0 → rule_based, and the report says why",
        "3. else 0 → rule_based",
        "distress value per share: manual, else 0 → rule_based",
    )) == []
    assert "bankruptcy odds and distress value per share: manual, else 0" not in label
    assert _TABLE_CITATION in _directive(i)
    assert "_resolve_tax_rate" in _directive(i)


def _tla_comment(action: str) -> str:
    lines = (_MODELS / "analyze.tla").read_text(encoding="utf-8").splitlines()
    at = lines.index(f"{action} ==")
    return lines[at - 1]


def test_tla_comments_cite_the_new_branches() -> None:
    margin = _tla_comment("MarginIsResolved")
    assert margin.startswith("(*") and "_resolve_operating_margin" in margin
    assert "mature-decline" in margin
    tax = _tla_comment("TaxAndBankruptcyAreSet")
    assert tax.startswith("(*")
    for cite in ("_resolve_tax_rate", "_resolve_probability_of_bankruptcy",
                 "src/bot/reference/default_spreads.py"):
        assert cite in tax, cite


# docs/leccion/index.html


def _cap(n: int) -> str:
    text = _LECCION.read_text(encoding="utf-8")
    start = text.index(f'<section id="cap-{n}"')
    return text[start : text.index("</section>", start)]


def _row(section: str, label: str) -> str:
    m = re.search(
        rf'<tr><th scope="row"><code>{re.escape(label)}</code></th>(.*?)</tr>', section, re.S
    )
    assert m, f"no row for {label}"
    return html.unescape(m.group(1))


def test_leccion_cap6_splits_the_three_rows() -> None:
    cap6 = _cap(6)
    assert "<code>mature-stable</code>, <code>mature-decline</code>" not in cap6
    assert "Sin tratamiento propio" in _row(cap6, "mature-stable")
    decline = _row(cap6, "mature-decline")
    assert "propio margen" in decline and "plano" in decline
    assert "sin converger al sector" in decline
    distressed = _row(cap6, "distressed")
    assert "probabilidad de quiebra" in distressed and "capítulo 7" in distressed


def test_leccion_caveat_describes_the_coverage_chain() -> None:
    caveat = html.unescape(_cap(6).split('<aside class="caveat">')[1])
    for phrase in ("config/default_spreads.yaml", "rating sintético", "diez años", "Altman",
                   "a mano", "valor de liquidación por acción"):
        assert phrase in caveat, phrase
    assert "queda en 0 salvo" not in caveat
    assert "Nada de eso se calcula solo" not in caveat


def test_leccion_cap7_rule_based_mentions_the_chain() -> None:
    row = _row(_cap(7), "rule_based")
    assert "distressed" in row and "cobertura" in row and "rating sintético" in row


def test_leccion_cites_load_default_spreads_at_its_line() -> None:
    src = (_ROOT / "src" / "bot" / "reference" / "default_spreads.py").read_text(encoding="utf-8")
    found = re.search(r"^def load_default_spreads\(", src, re.M)
    assert found, "src/bot/reference/default_spreads.py has no load_default_spreads"
    line = src.count("\n", 0, found.start()) + 1
    cited = re.search(
        r'data-symbol="bot\.reference\.default_spreads\.load_default_spreads">[^<]*</code>'
        r' · <code class="at">src/bot/reference/default_spreads\.py:(\d+)</code>',
        _cap(7),
    )
    assert cited, "cap-7 does not list load_default_spreads in «En el código»"
    assert int(cited.group(1)) == line


# docs/plano


def _estado_rows() -> dict[str, tuple[str, str, str, str, str]]:
    estado = _load("estado")
    return {row[0]: row for row in estado.INVENTARIO["capa-c"][2]}


def test_plano_estado_rows_describe_the_derivation() -> None:
    rows = _estado_rows()
    assert rows["story-altman"][2] == "falta"
    for cid in ("story-uso", "story-altman", "a-quiebra", "dcf-quiebra"):
        text = f"{rows[cid][3]} {rows[cid][4]}"
        assert "cobertura" in text, cid
        assert "solo de un override manual" not in text, cid
    assert "mature-decline" in rows["story-uso"][4]
    assert "Siguen faltando los otros cinco arquetipos" not in rows["story-uso"][4]
    assert "reference/default_spreads.py:" in rows["a-quiebra"][3]
    assert "Altman" in rows["a-quiebra"][4]
    for cid in ("a-quiebra", "dcf-quiebra"):
        assert "liquidación" in rows[cid][4], cid


def test_plano_cards_describe_the_branches() -> None:
    data = (_PLANO / "part-data.js").read_text(encoding="utf-8")
    s_md, s_ds, a_default = (_js_card(data, c) for c in ("s-md", "s-ds", "a-default"))
    assert "margen" in s_md and "propio" in s_md and "sin converger" in s_md
    assert "El Altman Z decide la clasificación" in s_ds
    for card in (s_ds, a_default):
        assert "cobertura" in card
        assert "config/default_spreads.yaml" in card
        assert "se quedan en cero hasta" not in card
        assert "sigue en cero hasta que se la pone a mano" not in card
    assert "Esa derivación no está hecha" not in a_default
