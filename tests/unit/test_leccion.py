"""The lesson in docs/leccion/ (issue #120) stays true to src/bot/."""

from __future__ import annotations

import importlib
import math
import re
import subprocess
import sys
from dataclasses import dataclass, field
from functools import cache
from html.parser import HTMLParser
from pathlib import Path

import yaml

from bot.reporting.analysis_report import margin_verdict
from bot.screener.ranking import RankingWeights, ScoredCandidate, rescore_with_margins
from bot.valuator.assumptions import AssumptionSource
from bot.valuator.dcf import Assumptions, Financials, dcf
from bot.valuator.sensitivity import tornado
from bot.valuator.story_types import StoryType

_ROOT = Path(__file__).resolve().parents[2]
_LECCION = _ROOT / "docs" / "leccion"
_INDEX = _LECCION / "index.html"

_CHAPTERS = [
    ("cap-0", "El mapa"),
    ("cap-1", "La vara: Damodaran (Capa A)"),
    ("cap-2", "Los números de cada empresa"),
    ("cap-3", "Quality gates"),
    ("cap-4", "Barato vs. trampa"),
    ("cap-5", "El ranking"),
    ("cap-6", "Story types (Capa C)"),
    ("cap-7", "El DCF sin matemática"),
    ("cap-8", "Dudar del resultado"),
]


_PARTS = ("concepto", "ejemplo", "en-codigo", "caveat")


@dataclass
class _Chapter:
    id: str
    title: str = ""
    text: list[str] = field(default_factory=list)
    classes: set[str] = field(default_factory=set)
    symbols: list[str] = field(default_factory=list)
    codes: list[str] = field(default_factory=list)
    params: dict[str, str] = field(default_factory=dict)
    consts: dict[str, str] = field(default_factory=dict)
    dcf_in: dict[str, str] = field(default_factory=dict)
    dcf_out: dict[str, str] = field(default_factory=dict)
    tornado_low: dict[str, str] = field(default_factory=dict)
    tornado_high: dict[str, str] = field(default_factory=dict)
    tornado_order: list[str] = field(default_factory=list)
    parts: list[str] = field(default_factory=list)
    svg_etapas: set[str] = field(default_factory=set)
    tables: int = 0


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.chapters: list[_Chapter] = []
        self.nav_hrefs: list[str] = []
        self.links: list[str] = []
        self.script_srcs: list[str] = []
        self.styles: list[str] = []
        self._in_nav = 0
        self._in_h2 = False
        self._code_depth = 0
        self._code_buf: list[str] = []
        self._in_style = False
        self._section_depth = 0

    @property
    def _cur(self) -> _Chapter | None:
        return self.chapters[-1] if self._section_depth else None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        a = {k: v or "" for k, v in attrs}
        if tag == "section" and a.get("id", "").startswith("cap-") and not self._section_depth:
            self.chapters.append(_Chapter(a["id"]))
            self._section_depth = 1
        elif tag == "section" and self._section_depth:
            self._section_depth += 1
        if tag == "nav":
            self._in_nav += 1
        if tag == "a" and self._in_nav and a.get("href", "").startswith("#cap-"):
            self.nav_hrefs.append(a["href"])
        if tag == "link":
            self.links.append(a.get("href", ""))
        if tag == "script" and "src" in a:
            self.script_srcs.append(a["src"])
        if tag == "style":
            self._in_style = True
        cur = self._cur
        if cur is None:
            return
        cur.classes.update(a.get("class", "").split())
        cur.parts.extend(c for c in a.get("class", "").split() if c in _PARTS)
        if tag == "tr" and "data-tornado" in a:
            cur.tornado_order.append(a["data-tornado"])
        if tag == "h2":
            self._in_h2 = True
        if tag == "table":
            cur.tables += 1
        if tag == "code":
            self._code_depth += 1
            self._code_buf = []
            if "data-symbol" in a:
                cur.symbols.append(a["data-symbol"])
        if "data-etapa" in a:
            cur.svg_etapas.add(a["data-etapa"])
        if tag == "data":
            for key, target in (
                ("data-param", cur.params),
                ("data-const", cur.consts),
                ("data-dcf", cur.dcf_in),
                ("data-dcf-out", cur.dcf_out),
                ("data-tornado-low", cur.tornado_low),
                ("data-tornado-high", cur.tornado_high),
            ):
                if key in a:
                    target[a[key]] = a.get("value", "")

    def handle_endtag(self, tag: str) -> None:
        if tag == "nav":
            self._in_nav -= 1
        if tag == "style":
            self._in_style = False
        if tag == "h2":
            self._in_h2 = False
        if tag == "code" and self._code_depth:
            self._code_depth -= 1
            if self._cur is not None:
                self._cur.codes.append("".join(self._code_buf).strip())
        if tag == "section" and self._section_depth:
            self._section_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_style:
            self.styles.append(data)
        cur = self._cur
        if cur is None:
            return
        cur.text.append(data)
        if self._in_h2:
            cur.title += data
        if self._code_depth:
            self._code_buf.append(data)


@cache
def _html() -> str:
    return _INDEX.read_text(encoding="utf-8")


@cache
def _parsed() -> _Parser:
    p = _Parser()
    p.feed(_html())
    return p


def _chapter(cid: str) -> _Chapter:
    return next(c for c in _parsed().chapters if c.id == cid)


def _css() -> str:
    return "\n".join(_parsed().styles)


def test_index_is_self_contained() -> None:
    p = _parsed()
    assert p.script_srcs == []
    for href in p.links:
        assert re.match(r"https://fonts\.(googleapis|gstatic)\.com(/|$)", href), href
    html = _html()
    assert "base64," not in html
    assert "feTurbulence" not in html
    assert "@import" not in _css()
    assert re.findall(r"url\(\s*['\"]?https?://", _css()) == []


def test_document_basics() -> None:
    html = _html()
    assert html.lstrip().lower().startswith("<!doctype html>")
    assert '<html lang="es">' in html
    assert re.search(r'<meta name="viewport" content="width=device-width, initial-scale=1"', html)
    for family in ("Shantell+Sans", "Literata", "Sometype+Mono"):
        assert family in html


def test_chapters_in_order_with_titles() -> None:
    chapters = _parsed().chapters
    assert [c.id for c in chapters] == [cid for cid, _ in _CHAPTERS]
    for chapter, (_, title) in zip(chapters, _CHAPTERS, strict=True):
        assert title in " ".join(chapter.title.split()), (chapter.id, chapter.title)


def test_nav_links_every_chapter_in_order() -> None:
    assert _parsed().nav_hrefs == [f"#{cid}" for cid, _ in _CHAPTERS]
    assert 'href="#contenido"' in _html()
    assert ":focus-visible" in _css()


_DESIGN_TOKENS = {
    "--desk": "oklch(0.665 0.048 66)",
    "--sheet": "oklch(0.845 0.035 82)",
    "--sheet-deep": "oklch(0.795 0.038 80)",
    "--ink": "oklch(0.315 0.045 55)",
    "--ink-soft": "oklch(0.385 0.040 56)",
    "--p-datos": "oklch(0.620 0.115 78)",
    "--p-datos-t": "oklch(0.400 0.085 72)",
    "--p-elimina": "oklch(0.505 0.145 30)",
    "--p-elimina-t": "oklch(0.385 0.120 30)",
    "--p-selecciona": "oklch(0.545 0.095 135)",
    "--p-selecciona-t": "oklch(0.395 0.075 135)",
    "--p-valua": "oklch(0.470 0.115 265)",
    "--p-valua-t": "oklch(0.375 0.105 265)",
    "--p-vigila": "oklch(0.505 0.115 350)",
    "--p-vigila-t": "oklch(0.385 0.105 350)",
}


def _block(css: str, opener: str) -> str:
    start = css.index(opener)
    depth, i = 0, css.index("{", start)
    for j in range(i, len(css)):
        depth += {"{": 1, "}": -1}.get(css[j], 0)
        if depth == 0:
            return css[i : j + 1]
    raise AssertionError(f"unbalanced block after {opener!r}")


def _light_root() -> str:
    return _block(_css(), ":root")


def _dark_root() -> str:
    return _block(_css(), "prefers-color-scheme: dark")


def _token(block: str, name: str) -> str:
    m = re.search(rf"{re.escape(name)}\s*:\s*(oklch\([^)]*\))", block)
    assert m, f"{name} missing"
    return " ".join(m[1].split())


def test_tokens_come_from_design_md() -> None:
    design = (_ROOT / "docs" / "plano" / "DESIGN.md").read_text(encoding="utf-8")
    root = _light_root()
    for name, value in _DESIGN_TOKENS.items():
        assert value in design, (name, "no longer in DESIGN.md")
        assert _token(root, name) == value, name


def _luminance(oklch: str) -> float:
    lightness, chroma, hue = (float(x) for x in re.findall(r"[\d.]+", oklch)[:3])
    a = chroma * math.cos(math.radians(hue))
    b = chroma * math.sin(math.radians(hue))
    l_ = (lightness + 0.3963377774 * a + 0.2158037573 * b) ** 3
    m_ = (lightness - 0.1055613458 * a - 0.0638541728 * b) ** 3
    s_ = (lightness - 0.0894841775 * a - 1.2914855480 * b) ** 3
    rgb = (
        4.0767416621 * l_ - 3.3077115913 * m_ + 0.2309699292 * s_,
        -1.2684380046 * l_ + 2.6097574011 * m_ - 0.3413193965 * s_,
        -0.0041960863 * l_ - 0.7034186147 * m_ + 1.7076147010 * s_,
    )
    r, g, bl = (min(max(c, 0.0), 1.0) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * bl


def _contrast(fg: str, bg: str) -> float:
    hi, lo = sorted((_luminance(fg), _luminance(bg)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_body_text_contrast_is_aa_in_light_and_dark() -> None:
    for block in (_light_root(), _dark_root()):
        sheet = _token(block, "--sheet")
        for ink in ("--ink", "--ink-soft"):
            assert _contrast(_token(block, ink), sheet) >= 4.5, (ink, block[:40])


def test_layout_hooks_for_phone_width() -> None:
    css = _css()
    measures = [float(x) for x in re.findall(r"max-(?:width|inline-size)\s*:\s*([\d.]+)ch", css)]
    assert any(65 <= m <= 75 for m in measures), measures
    assert re.search(r"\.tabla\s*\{[^}]*overflow-x\s*:\s*auto", css)
    assert re.search(r"overflow-wrap\s*:\s*anywhere", css)
    assert "overflow-x: clip" not in css and "overflow-x:clip" not in css
    assert "prefers-reduced-motion" in css


def test_check_py_exits_zero() -> None:
    result = subprocess.run(
        [sys.executable, str(_LECCION / "check.py")], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr


_REQUIRED_SYMBOLS: dict[str, list[str]] = {
    "cap-0": ["bot.cli.refresh", "bot.cli.screen", "bot.cli.analyze"],
    "cap-1": [
        "bot.ingest.damodaran.import_damodaran",
        "bot.ingest.damodaran.parse_industry_xls",
        "bot.ingest.damodaran.parse_country_xls",
        "bot.screener.benchmarks.load_industry_benchmarks",
        "bot.screener.types.IndustryBenchmarks",
    ],
    "cap-2": [
        "bot.ingest.universe.refresh_universe",
        "bot.ingest.universe.refresh_prices",
        "bot.ingest.sec_edgar",
        "bot.storage.db",
        "bot.screener.types.CompanyData",
        "bot.screener.engine.build_company_data",
    ],
    "cap-3": [
        "bot.screener.rules.MinMarketCap",
        "bot.screener.rules.MinYearsHistory",
        "bot.screener.rules.ExcludeSectors",
        "bot.screener.rules.MaxNetDebtToEBITDA",
        "bot.screener.rules.MinInterestCoverage",
        "bot.screener.rules.PositiveOperatingCashflow",
        "bot.screener.rules.MaxGoodwillToAssets",
        "bot.screener.rules.register",
        "bot.screener.rules.get_rule",
    ],
    "cap-4": [
        "bot.screener.rules.PEBelowIndustryMultiple",
        "bot.screener.rules.EVEBITDABelowIndustryMultiple",
        "bot.screener.rules.PBVBelowIndustryMultipleWithROEAboveMedian",
        "bot.screener.rules.FCFYieldAbove",
        "bot.screener.rules.RevenueNotDeclining",
        "bot.screener.rules.OperatingMarginNotContracting",
        "bot.screener.rules.ROICAboveSectorWACC",
        "bot.screener.rules.SloanAccrualsBelow",
        "bot.screener.rules.ShareCountNotDiluting",
        "bot.screener.engine.evaluate_company",
        "bot.screener.engine.run_screen",
        "bot.screener.engine.ScreenResult",
        "bot.screener.engine.RejectedCompany",
    ],
    "cap-5": [
        "bot.screener.ranking.RankingWeights",
        "bot.screener.ranking.rank",
        "bot.screener.ranking.rescore_with_margins",
        "bot.screener.persist",
    ],
    "cap-6": [
        "bot.valuator.story_types.StoryType",
        "bot.valuator.story_types.classify",
        "bot.valuator.story_types.SectorContext",
        "bot.valuator.assumptions.conventional_override_path",
    ],
    "cap-7": [
        "bot.valuator.dcf.Financials",
        "bot.valuator.dcf.Assumptions",
        "bot.valuator.dcf.dcf",
        "bot.valuator.dcf.DCFResult",
        "bot.valuator.dcf.YearProjection",
        "bot.valuator.assumptions.AssumptionSource",
        "bot.valuator.assumptions.Sourced",
        "bot.valuator.assumptions.resolve_assumptions",
    ],
    "cap-8": [
        "bot.valuator.sensitivity.tornado",
        "bot.valuator.sensitivity.grid_2d",
        "bot.valuator.narrative_flags.story_margin_flag",
        "bot.valuator.narrative_flags.growth_reinvestment_flag",
        "bot.valuator.narrative_flags.beta_business_risk_flag",
        "bot.valuator.narrative_flags.terminal_value_share_flag",
        "bot.valuator.narrative_flags.country_exposure_flag",
        "bot.valuator.analysis.analyze",
        "bot.reporting.analysis_report.margin_verdict",
    ],
}

_REQUIRED_CONSTS: dict[str, list[str]] = {
    "cap-1": ["bot.screener.engine.DEFAULT_REGION"],
    "cap-5": ["bot.screener.ranking.PLACEHOLDER_MARGIN_OF_SAFETY"],
    "cap-6": [
        "bot.valuator.story_types._DISTRESS_ALTMAN_Z",
        "bot.valuator.story_types._DISTRESS_INTEREST_COVERAGE",
        "bot.valuator.story_types._CYCLICAL_EARNINGS_CV",
        "bot.valuator.story_types._HIGH_GROWTH_CAGR",
        "bot.valuator.story_types._MATURE_AGE_YEARS",
        "bot.valuator.story_types._DECLINE_CAGR",
    ],
    "cap-7": ["bot.valuator.assumptions._HORIZON"],
    "cap-8": [
        "bot.valuator.sensitivity._TORNADO_HIGH",
        "bot.valuator.narrative_flags._TERMINAL_VALUE_SHARE_CEILING",
    ],
}

_CAVEATS = {"cap-1", "cap-2", "cap-4", "cap-7"}


def test_each_chapter_has_its_parts() -> None:
    for chapter in _parsed().chapters:
        for part in ("concepto", "ejemplo", "en-codigo"):
            assert part in chapter.classes, (chapter.id, part)
        if chapter.id in _CAVEATS:
            assert "caveat" in chapter.classes, chapter.id


def test_each_chapter_parts_come_in_order() -> None:
    for chapter in _parsed().chapters:
        expected = [p for p in _PARTS if p in chapter.parts]
        assert chapter.parts == expected, (chapter.id, chapter.parts)


def test_required_symbols_are_cited() -> None:
    for cid, symbols in _REQUIRED_SYMBOLS.items():
        missing = set(symbols) - set(_chapter(cid).symbols)
        assert not missing, (cid, sorted(missing))


def test_every_cited_symbol_is_a_bot_path() -> None:
    for chapter in _parsed().chapters:
        for symbol in chapter.symbols:
            assert symbol.startswith("bot."), symbol


def test_named_constants_match_code() -> None:
    for cid, names in _REQUIRED_CONSTS.items():
        missing = set(names) - set(_chapter(cid).consts)
        assert not missing, (cid, sorted(missing))
    for chapter in _parsed().chapters:
        for dotted, shown in chapter.consts.items():
            module, name = dotted.rsplit(".", 1)
            actual = getattr(importlib.import_module(module), name)
            if isinstance(actual, str):
                assert shown == actual, dotted
            else:
                assert math.isclose(float(shown), float(actual)), (dotted, shown, actual)


_MATH = ("∑", "Σ", "\\sum", "sum_{", "<math", "\\frac", "∫", ")^", "^t", "^N")


def test_no_math_notation() -> None:
    text = "".join(t for c in _parsed().chapters for t in c.text)
    for token in _MATH:
        assert token not in text, token


def test_funnel_svg_in_chapter_0() -> None:
    assert {"calidad", "valor", "trampa", "ranking", "capa-c"} <= _chapter("cap-0").svg_etapas
    section = _html()[_html().index('id="cap-0"') : _html().index('id="cap-1"')]
    assert re.search(r'<svg\b[^>]*role="img"', section)
    assert "<title" in section


_PRESET = _ROOT / "config" / "presets" / "damodaran_value.yaml"
_LAYER_CHAPTER = {"quality_gates": "cap-3", "value_indicators": "cap-4", "trap_detection": "cap-4"}


def test_preset_thresholds_appear_in_chapters_3_and_4() -> None:
    preset = yaml.safe_load(_PRESET.read_text(encoding="utf-8"))
    for layer, cid in _LAYER_CHAPTER.items():
        params = _chapter(cid).params
        for rule in preset[layer]["rules"]:
            for key, value in (rule.get("params") or {}).items():
                shown = params.get(f"{rule['name']}.{key}")
                assert shown is not None, (cid, rule["name"], key)
                if isinstance(value, list):
                    assert shown.split(",") == value, (rule["name"], key)
                else:
                    assert math.isclose(float(shown), float(value)), (rule["name"], key)


def test_ranking_weights_match_code_and_preset() -> None:
    preset = yaml.safe_load(_PRESET.read_text(encoding="utf-8"))["ranking"]["weights"]
    code = RankingWeights()
    params = _chapter("cap-5").params
    for name in ("value", "quality", "growth", "margin_of_safety"):
        shown = float(params[f"ranking.{name}"])
        assert math.isclose(shown, getattr(code, name)), name
        assert math.isclose(shown, preset[name]), name


def test_ranking_example_matches_code() -> None:
    ex = _chapter("cap-5").params
    base = ScoredCandidate(
        ticker="EJ",
        value_score=float(ex["ejemplo.value_pct"]),
        quality_score=float(ex["ejemplo.quality_pct"]),
        growth_score=float(ex["ejemplo.growth_pct"]),
        margin_of_safety=0.0,
        score=0.0,
    )
    for mos_key, score_key in (
        ("ejemplo.mos", "ejemplo.score"),
        ("ejemplo.mos_placeholder", "ejemplo.score_placeholder"),
    ):
        (scored,) = rescore_with_margins([base], {"EJ": float(ex[mos_key])})
        assert math.isclose(float(ex[score_key]), scored.score, abs_tol=0.051), score_key


def test_story_types_listed_in_chapter_6() -> None:
    codes = set(_chapter("cap-6").codes)
    assert {s.value for s in StoryType} <= codes


def test_every_assumption_source_listed_in_chapter_7() -> None:
    codes = set(_chapter("cap-7").codes)
    missing = {s.value for s in AssumptionSource} - codes
    assert not missing, sorted(missing)


def _close(shown: str, actual: float) -> bool:
    return math.isclose(float(shown), actual, rel_tol=0.01, abs_tol=0.051)


def _dcf_example() -> tuple[Financials, Assumptions]:
    i = _chapter("cap-7").dcf_in
    growth = tuple(float(x) for x in i["revenue_growth"].split(","))
    financials = Financials(
        revenue=float(i["revenue"]),
        net_debt=float(i["net_debt"]),
        shares_diluted=float(i["shares_diluted"]),
    )
    assumptions = Assumptions(
        revenue_growth=growth,
        operating_margin=(float(i["operating_margin"]),) * len(growth),
        tax_rate=float(i["tax_rate"]),
        sales_to_capital=float(i["sales_to_capital"]),
        terminal_growth=float(i["terminal_growth"]),
        cost_of_equity=float(i["cost_of_equity"]),
        pretax_cost_of_debt=float(i["pretax_cost_of_debt"]),
        equity_weight=float(i["equity_weight"]),
        debt_weight=float(i["debt_weight"]),
    )
    return financials, assumptions


def test_dcf_example_matches_code() -> None:
    chapter = _chapter("cap-7")
    financials, assumptions = _dcf_example()
    result = dcf(financials, assumptions)
    out = chapter.dcf_out
    assert len(assumptions.revenue_growth) >= 2
    assert chapter.tables >= 1
    assert _close(out["wacc"], result.wacc)
    for p in result.projections:
        assert _close(out[f"fcff.{p.year}"], p.fcff), p.year
        assert _close(out[f"pv.{p.year}"], p.present_value), p.year
    for name in ("terminal_value", "enterprise_value", "intrinsic_value"):
        assert _close(out[name], getattr(result, name)), name


def test_tornado_example_matches_code() -> None:
    chapter = _chapter("cap-8")
    entries = tornado(*_dcf_example())
    assert chapter.tornado_order == [e.axis.value for e in entries]
    for entry in entries:
        axis = entry.axis.value
        assert entry.intrinsic_low is not None and entry.intrinsic_high is not None
        assert _close(chapter.tornado_low[axis], entry.intrinsic_low), axis
        assert _close(chapter.tornado_high[axis], entry.intrinsic_high), axis


def test_margin_verdict_thresholds_match_code() -> None:
    params = _chapter("cap-8").params
    under = float(params["margin_verdict.undervalued"])
    fair = float(params["margin_verdict.fair"])
    assert margin_verdict(under) == "potentially undervalued"
    assert margin_verdict(under - 1e-9) == "around fair value"
    assert margin_verdict(fair) == "around fair value"
    assert margin_verdict(fair - 1e-9) == "potentially overvalued"
    codes = set(_chapter("cap-8").codes)
    assert {"potentially undervalued", "around fair value", "potentially overvalued"} <= codes


def test_readme_is_short_and_says_how_to_use_it() -> None:
    readme = (_LECCION / "README.md").read_text(encoding="utf-8")
    assert len(readme.strip().splitlines()) <= 12
    for needle in ("index.html", "python3 docs/leccion/check.py", "Artifact"):
        assert needle in readme, needle


def test_context_source_of_truth_links_the_lesson() -> None:
    context = (_ROOT / "CONTEXT.md").read_text(encoding="utf-8")
    section = context[
        context.index("## Source of truth") : context.index("## Working with the plans")
    ]
    assert "docs/leccion/" in section
