"""The d2 boards in docs/pipeline/ (issue #144) stay true to src/bot/ and config/.

Shared machinery for every board: each stage issue (#146 to #150) appends its own
entries to the `_REQUIRED_*` dicts and to `_ACRONYMS`. Nothing here runs d2.
"""

from __future__ import annotations

import importlib
import importlib.util
import math
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
from bot.screener.ranking import RankingWeights
from bot.screener.rules import registered_rules
from bot.screener.types import CompanyData, IndustryBenchmarks
from bot.web.views import MOS_FAIR, MOS_UNDERVALUED

_ROOT = Path(__file__).resolve().parents[2]
_PIPELINE = _ROOT / "docs" / "pipeline"
_SCHEMA = _ROOT / "src" / "bot" / "storage" / "schema.sql"
_PRESET = _ROOT / "config" / "presets" / "damodaran_value.yaml"


@cache
def _check() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pipeline_check", _PIPELINE / "check.py")
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@cache
def _boards() -> dict[str, str]:
    return {p.stem: p.read_text(encoding="utf-8") for p in _check().boards(_PIPELINE)}


def _schema_tables() -> set[str]:
    sql = _SCHEMA.read_text(encoding="utf-8")
    return set(re.findall(r"CREATE TABLE IF NOT EXISTS (\w+)", sql))


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


# Required citations, per board stem. Stage issues append their own entries.
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
    "refresh": {
        "bot.cli.refresh",
        "bot.ingest.damodaran.import_damodaran",
        "bot.ingest.damodaran.merge_industry_datasets",
        "bot.ingest.damodaran.derive_industry_columns",
        "bot.ingest.damodaran.parse_country_tax_rates",
        "bot.ingest.damodaran.parse_preheader_scalar",
        "bot.ingest.universe.refresh_universe",
        "bot.ingest.universe.refresh_prices",
        "bot.ingest.universe.refresh_fx",
        "bot.ingest.universe.import_company",
        "bot.ingest.universe._should_skip",
        "bot.ingest.universe._stale_first",
        "bot.ingest.sec_edgar.parse_company_facts",
        "bot.ingest.sec_edgar._collect_period_rows",
        "bot.ingest.sec_edgar._fiscal_quarter_key",
        "bot.ingest.sec_edgar._derive_financial_fields",
        "bot.ingest.sec_edgar._rescale_shares_diluted",
        "bot.ingest.sec_edgar.SecEdgarClient.shares_outstanding",
        "bot.ingest.edgar_base.EdgarPricedProvider",
        "bot.ingest.edgar_tiingo",
        "bot.ingest.stooq",
        "bot.ingest.fmp",
        "bot.ingest.industry_mapping.load_industry_mapping",
        "bot.reference.industries",
        "bot.utils.fx.import_fx_rates",
    },
    "screen": {
        "bot.cli.screen",
        "bot.screener.engine.run_screen",
        "bot.screener.engine.build_company_data",
        "bot.screener.engine.evaluate_company",
        "bot.screener.engine._quality_metric",
        "bot.screener.engine._growth_metric",
        "bot.screener.engine._resolve_tax_rate",
        "bot.screener.engine._resolve_region",
        "bot.screener.engine._batch_dcf_margins",
        "bot.screener.benchmarks.load_industry_benchmarks",
        "bot.screener.rules._value_score",
        "bot.screener.rules._avg_growth_rate",
        "bot.screener.ranking.rank",
        "bot.screener.ranking._percentiles",
        "bot.screener.ranking.rescore_with_margins",
        "bot.screener.ranking.RankingWeights",
        "bot.screener.persist.persist_candidates",
        "bot.screener.config.load_screener_config",
        "bot.reporting.screen_report.render_markdown",
        "bot.reporting.screen_report.render_csv",
        "bot.reference.sectors.is_financial_services",
        "bot.reference.regions.dataset_region",
        "bot.utils.finance.cagr",
    },
}
# Derived from schema.sql, so a new table cannot go undrawn on the overview.
_REQUIRED_TABLES: dict[str, set[str]] = {
    "pipeline": _schema_tables(),
    "refresh": {
        "damodaran_industry",
        "damodaran_country",
        "companies",
        "financials_annual",
        "financials_quarterly",
        "filings_log",
        "prices_daily",
        "currencies",
        "refresh_log",
    },
    "screen": {
        "companies",
        "financials_annual",
        "prices_daily",
        "currencies",
        "damodaran_industry",
        "damodaran_country",
        "screener_candidates",
    },
}
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
    "refresh": {
        "src/bot/ingest/universe_default.csv",
        "src/bot/ingest/industry_mapping.csv",
        "scripts/daily.sh",
        "scripts/weekly.sh",
        "scripts/price_fill.sh",
    },
    "screen": {
        "config/presets/damodaran_value.yaml",
        "config/presets/deep_value.yaml",
        "config/presets/qarp.yaml",
    },
}
# Derived from the rule registry and the preset, so a new rule or parameter
# cannot go undrawn on the screen board.
_REQUIRED_RULES: dict[str, set[str]] = {"screen": set(registered_rules())}
_REQUIRED_PARAMS: dict[str, set[str]] = {"screen": set(_preset_params())}
_REQUIRED_CONSTS: dict[str, set[str]] = {
    "pipeline": {"bot.web.views.MOS_UNDERVALUED", "bot.web.views.MOS_FAIR"},
    "refresh": {
        "bot.ingest.sec_edgar.ANNUAL_SPAN_DAYS",
        "bot.ingest.sec_edgar.QUARTERLY_SPAN_DAYS",
        "bot.ingest.sec_edgar._SHARE_SCALE_FACTORS",
        "bot.ingest.sec_edgar._MIN_SHARE_COMPARATORS",
        "bot.ingest.sec_edgar._SHARE_SCALE_TOLERANCE",
        "bot.ingest.edgar_base._FRESH_DAYS",
        "bot.ingest.universe.SUCCESS_MAX_FAILURE_RATE",
        "bot.ingest.universe.PARTIAL_MAX_FAILURE_RATE",
    },
    "screen": {
        "bot.screener.engine.DEFAULT_REGION",
        "bot.screener.engine.DEFAULT_TAX_RATE",
        "bot.screener.ranking.PLACEHOLDER_MARGIN_OF_SAFETY",
        "bot.screener.rules.DEFAULT_EXCLUDED_SECTORS",
    },
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
    "EBIT": "earnings before interest and taxes",
    "EBITDA": "earnings before interest, taxes, depreciation and amortization",
    "SIC": "Standard Industrial Classification",
    "ADR": "architecture decision record",
    "ROE": "return on equity",
    "ROIC": "return on invested capital",
    "EPS": "earnings per share",
    "EV": "enterprise value",
    "BV": "book value",
    "CAGR": "compound annual growth rate",
}
# File formats and words written in capitals that need no expansion.
_ACRONYMS_EXEMPT: set[str] = {
    "JSON", "CSV", "YAML", "SVG", "URL", "HTML", "PNG",
    "US", "USD", "YYYY", "MM", "DD", "TICKER",
}
_ACRONYM_RE = re.compile(r"\b[A-Z][A-Z0-9]+\b|\bMoS\b")


# A minimal reading of d2 node blocks, enough to find a node's class and text.
# Convention (docs/pipeline/README.md): `class:` is a node's first attribute.
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
    return None  # symbol / table / file: check.py owns them (test_check_py_exits_zero)


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
        f"{stem}: {line.strip()}"
        for stem, board in _boards().items()
        for line in _check().visible(board).splitlines()
        if re.search(r"->|<-", line) and not re.search(r"(->|<-)[^:]*:\s*\S", line)
    ]
    assert unlabelled == []


def test_gap_notes_start_with_gap() -> None:
    bad = [
        f"{stem}: {line.strip()}"
        for stem, board in _boards().items()
        for line in _check().visible(board).splitlines()
        if re.search(r"\bclass:\s*gap\b", line) and not re.search(r"\|md\s+Gap:", line)
    ]
    assert bad == []


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


_SUBFLOWS = ("damodaran", "fundamentals", "prices", "fx")
_REFRESH_TABLES = sorted(_REQUIRED_TABLES["refresh"])

_REFRESH_NODES: list[tuple[str, str]] = (
    [("weekly", "cron"), ("daily", "cron"), ("price_fill", "cron")]
    + [("cli", "step"), ("region", "decision")]
    + [(e, "external") for e in ("damodaran_data", "edgar", "tiingo", "stooq", "fmp")]
    + [("universe_csv", "file"), ("industry_mapping_csv", "file")]
    + [(f"duckdb.{t}", "store") for t in _REFRESH_TABLES]
    + [
        ("damodaran.download", "step"),
        ("damodaran.files_ok", "decision"),
        ("damodaran.merge", "step"),
        ("damodaran.derive", "step"),
        ("damodaran.country", "step"),
        ("damodaran.country.risk_free", "gap"),
        ("damodaran.empty_rows", "decision"),
        ("damodaran.write", "step"),
        ("damodaran.write.us_only", "gap"),
        ("fundamentals.mapping", "step"),
        ("fundamentals.mapping_valid", "decision"),
        ("fundamentals.skip", "decision"),
        ("fundamentals.import", "step"),
        ("fundamentals.periods", "decision"),
        ("fundamentals.fiscal", "step"),
        ("fundamentals.precedence", "decision"),
        ("fundamentals.derive", "step"),
        ("fundamentals.shares", "decision"),
        ("fundamentals.status", "decision"),
        ("fundamentals.rate_limit", "decision"),
        ("prices.only_missing", "decision"),
        ("prices.up_to_date", "decision"),
        ("prices.order", "step"),
        ("prices.fetch", "step"),
        ("prices.fetch.default_provider", "gap"),
        ("prices.market_cap", "decision"),
        ("prices.rate_limit", "decision"),
        ("prices.status", "decision"),
        ("fx.currencies", "step"),
        ("fx.fetch", "step"),
        ("fx.fetch.no_op", "gap"),
    ]
)

# Node -> phrases its block must show (compared after check.normalize, so U+2212
# minus signs in the board match the ASCII hyphens here).
_TIMES = "\u00d7"  # the board's multiplication sign
_REFRESH_TEXT: dict[str, list[str]] = {
    "region": ["US", "exit code 2"],
    "damodaran.files_ok": ["wacc.xls", "ctryprem.xls", "partial", "error"],
    "damodaran.merge": ["outer join", "earlier file wins"],
    "damodaran.derive": [
        "D/E = w ÷ (1 - w)",
        "w = D/(D+E)",
        f"beta_unlevered = beta_levered ÷ (1 + (1 - tax) {_TIMES} D/E)",
    ],
    "fundamentals.derive": [
        "EBITDA = EBIT + depreciation",
        "free cash flow = operating cash flow - capex",
        "working capital = current assets - current liabilities",
    ],
    "fundamentals.shares": ["median", "factor ÷ 2", f"factor {_TIMES} 2"],
    "fundamentals.periods": ["10-K", "10-Q"],
    "fundamentals.fiscal": ["calendar year of the period end"],
    "fundamentals.skip": ["--force"],
    "fundamentals.status": ["failed ÷ attempted"],
    "fundamentals.rate_limit": ["deferred"],
    "prices.only_missing": ["--only-missing"],
    "prices.up_to_date": ["last weekday before today"],
    "prices.order": ["never priced first"],
    "prices.market_cap": [f"market cap = close {_TIMES} shares outstanding"],
    "fx.fetch": [f"usd = amount {_TIMES} rate_to_usd", "nearest prior"],
}


def _refresh() -> str:
    return _boards().get("refresh", "")


def _refresh_block(key: str) -> str:
    block = _block(_refresh(), key)
    assert block is not None, f"refresh.d2 has no node {key}"
    return block


@pytest.mark.parametrize(("key", "cls"), _REFRESH_NODES)
def test_refresh_nodes(key: str, cls: str) -> None:
    assert _node_class(_refresh(), key) == cls


@pytest.mark.parametrize("sub", _SUBFLOWS)
def test_refresh_containers_hold_steps_and_decisions(sub: str) -> None:
    block = _refresh_block(sub)
    assert re.search(r"\bclass:\s*step\b", block), sub
    if sub != "fx":
        assert re.search(r"\bclass:\s*decision\b", block), sub


@pytest.mark.parametrize("key", list(_REFRESH_TEXT))
def test_refresh_text(key: str) -> None:
    block = _check().normalize(_refresh_block(key))
    missing = [w for w in _REFRESH_TEXT[key] if _check().normalize(w) not in block]
    assert missing == []


def test_refresh_gap_notes() -> None:
    assert "ADR 0005" in _refresh_block("damodaran.write.us_only")
    assert "risk-free" in _refresh_block("damodaran.country.risk_free")
    assert "Financial Modeling Prep" in _refresh_block("fx.fetch.no_op")


def _edge_line(board: str, src: str, dst: str) -> str | None:
    pattern = re.compile(rf"^\s*{re.escape(src)}\s*->\s*{re.escape(dst)}\s*:")
    return next((ln for ln in _check().visible(board).splitlines() if pattern.match(ln)), None)


def test_refresh_cron_edges() -> None:
    for cron in ("weekly", "daily", "price_fill"):
        assert _edge_line(_refresh(), cron, "cli") is not None, cron
    daily = _edge_line(_refresh(), "daily", "cli")
    assert daily is not None and "tickers deferred" in daily


def test_refresh_daily_defaults_match_script() -> None:
    script = (_ROOT / "scripts" / "daily.sh").read_text(encoding="utf-8")
    assert "BOT_PRICE_ROUNDS:-10}" in script
    assert "BOT_PRICE_RETRY_PAUSE:-3600}" in script
    daily = _edge_line(_refresh(), "daily", "cli")
    assert daily is not None
    assert re.search(r"\b10\b", daily) and re.search(r"\b3600\b", daily)


def test_estado_default_provider_gap_is_current() -> None:
    from bot.config import Settings

    estado = (_ROOT / "docs" / "plano" / "estado.py").read_text(encoding="utf-8")
    disagree = (
        "BOT_DATA_PROVIDER=edgar-stooq)" in estado
        and Settings.model_fields["data_provider"].default == "edgar-tiingo"
    )
    has_gap = _node_class(_refresh(), "prices.fetch.default_provider") == "gap"
    assert has_gap == disagree, (
        "estado.py and the code now agree on the default provider: remove the gap"
        if has_gap
        else "estado.py disagrees with the code default provider: draw the gap"
    )


def test_pipeline_links_the_refresh_board() -> None:
    block = _block(_overview(), "refresh")
    # The ./ prefix is load-bearing: d2 v0.9.0 drops `link: refresh.svg` on a board
    # that also has a node keyed `refresh`.
    assert block is not None and re.search(r'(?m)^\s*link:\s*"\./refresh\.svg"\s*$', block)


# --------------------------------------------------------------------------- #
# screen board (#147)
# --------------------------------------------------------------------------- #

_LAYERS = ("quality_gates", "value_indicators", "trap_detection")


def _screen() -> str:
    return _boards().get("screen", "")


def _screen_block(key: str) -> str:
    block = _block(_screen(), key)
    assert block is not None, f"screen.d2 has no node {key}"
    return block


def _preset_rule_layers() -> dict[str, str]:
    preset = yaml.safe_load(_PRESET.read_text(encoding="utf-8"))
    return {rule["name"]: layer for layer in _LAYERS for rule in preset[layer]["rules"]}


def _class_at_line(text: str, line: int) -> str | None:
    """Class of the node opened on 1-based `line`: inline `{class: X}`, else the next line's."""
    lines = text.splitlines()
    m = re.search(r"\{\s*class:\s*(\w+)", lines[line - 1])
    if m:
        return m.group(1)
    nxt = next((ln for ln in lines[line:] if ln.strip()), "")
    m = re.match(r"\s*class:\s*(\w+)", nxt)
    return m.group(1) if m else None


_SCREEN_NODES: list[tuple[str, str]] = (
    [("cli", "step"), ("cli.options", "note"), ("analyze_stage", "step")]
    + [(f, "file") for f in ("damodaran_value", "deep_value", "qarp", "assumptions")]
    + [("report_md", "output"), ("report_csv", "output")]
    + [(f"duckdb.{t}", "store") for t in sorted(_REQUIRED_TABLES["screen"])]
    + [
        ("snapshot.load", "step"),
        ("snapshot.region", "decision"),
        ("snapshot.tax", "decision"),
        ("snapshot.tax.fallback", "gap"),
        ("snapshot.ratios", "step"),
        ("snapshot.ratios.formulas", "note"),
        ("snapshot.usd", "decision"),
        ("snapshot.benchmark", "step"),
        ("coverage_gate.gate", "decision"),
        ("quality_gates.all_pass", "decision"),
        ("quality_gates.all_pass.all_layers", "note"),
        ("value_indicators.score", "step"),
        ("value_indicators.at_least_one", "decision"),
        ("trap_detection.growth_rate", "step"),
        ("trap_detection.share_count_not_diluting.mergers", "gap"),
        ("trap_detection.all_pass", "decision"),
        ("trap_detection.auditor", "gap"),
        ("ranking.metrics", "step"),
        ("ranking.metrics.spec_scores", "gap"),
        ("ranking.percentiles", "step"),
        ("ranking.weights", "step"),
        ("ranking.weights.bounds", "note"),
        ("ranking.first_pass", "step"),
        ("ranking.top_n", "decision"),
        ("ranking.second_pass", "step"),
        ("ranking.valued", "decision"),
        ("ranking.rescore", "step"),
        ("persist_and_report.persist", "step"),
        ("persist_and_report.persist.cut", "note"),
        ("persist_and_report.report", "step"),
    ]
    + [(f"{layer}.{rule}", "decision") for rule, layer in sorted(_preset_rule_layers().items())]
)

# Node -> phrases its block must show (compared after check.normalize, so the
# board's U+2212 minus signs match the ASCII hyphens here).
_SCREEN_TEXT: dict[str, list[str]] = {
    "snapshot.ratios.formulas": [
        "net debt = total debt - cash",
        "ROE = net income ÷ total equity",
        "EPS = net income ÷ diluted shares",
        "P/E = close ÷ EPS, only when EPS > 0",
        "BV per share = total equity ÷ diluted shares",
        "P/BV = close ÷ BV per share",
        "EV ÷ EBITDA = (market cap + net debt) ÷ EBITDA",
        f"ROIC = EBIT {_TIMES} (1 - tax) ÷ (total debt + total equity)",
        "free cash flow yield = free cash flow ÷ market cap",
        "operating margin = EBIT ÷ revenue",
    ],
    "snapshot.tax": ["21%", "[0, 1)"],
    "snapshot.region": ["China, India, Japan", "grouping", "US"],
    "snapshot.usd": ["rate_to_usd", "on or before"],
    "snapshot.benchmark": ["newest", "(industry, region)"],
    "coverage_gate.gate": ["coverage_gate", "leaves the universe", "before any rule runs"],
    "quality_gates.exclude_sectors": ["financial services", "exact match", "bank", "insurance"],
    "quality_gates.max_net_debt_to_ebitda": ["net debt ≤ 0: passes"],
    "quality_gates.min_interest_coverage": ["interest expense ≤ 0: passes"],
    "value_indicators.score": [
        "score = (threshold - value) ÷ threshold, clipped to [0, 1]",
        "min(1, yield ÷ minimum)",
        "highest score",
    ],
    "value_indicators.at_least_one": [
        "neither passes nor fails",
        "all four skipped: rejected",
        "a skip records no failed rule",
    ],
    "trap_detection.growth_rate": ["mean of (current - previous) ÷ previous", "≤ 0"],
    "trap_detection.sloan_accruals_below": [
        "(net income - operating cash flow) ÷ total assets",
    ],
    "trap_detection.operating_margin_not_contracting": [f"(last - first) {_TIMES} 10,000"],
    "trap_detection.roic_above_sector_wacc": ["skipped"],
    "trap_detection.share_count_not_diluting": ["whole share history"],
    "trap_detection.all_pass": ["skipped detector is eliminatory"],
    "ranking.metrics": ["(ROIC - sector WACC) + ROE", "CAGR", "(last ÷ first)"],
    "ranking.percentiles": ["0-based rank", "÷ (distinct values - 1)", "1.0", "ties share"],
    "ranking.weights": [
        f"100 {_TIMES} (0.40 {_TIMES} value + 0.30 {_TIMES} quality + 0.20 {_TIMES} growth"
        f" + 0.10 {_TIMES} margin of safety)",
    ],
    "ranking.weights.bounds": ["sum", "no ceiling"],
    "ranking.first_pass": ["0.5"],
    "ranking.top_n": ["--top"],
    "ranking.second_pass": ["intrinsic value ÷ price", "config/assumptions/TICKER.yaml"],
    "ranking.valued": ["0.5"],
    "ranking.rescore": ["percentiles kept"],
    "persist_and_report.persist": ["passed = true", "passed = false"],
    "persist_and_report.persist.cut": ["--top", "not written"],
}


@pytest.mark.parametrize(("key", "cls"), _SCREEN_NODES)
def test_screen_nodes(key: str, cls: str) -> None:
    assert _node_class(_screen(), key) == cls


@pytest.mark.parametrize("key", list(_SCREEN_TEXT))
def test_screen_text(key: str) -> None:
    block = _check().normalize(_screen_block(key))
    missing = [w for w in _SCREEN_TEXT[key] if _check().normalize(w) not in block]
    assert missing == []


def test_screen_rules_are_decisions() -> None:
    board = _screen()
    rules = [d for d in _check().directives(board) if d.kind == "rule"]
    assert {d.argument for d in rules} >= set(registered_rules())
    misplaced = [d.argument for d in rules if _class_at_line(board, d.line) != "decision"]
    assert misplaced == []


def test_screen_rule_nodes_follow_the_preset() -> None:
    preset = yaml.safe_load(_PRESET.read_text(encoding="utf-8"))
    problems = []
    for layer in _LAYERS:
        for rule in preset[layer]["rules"]:
            name = rule["name"]
            block = _block(_screen(), f"{layer}.{name}")
            if block is None:
                problems.append(f"no node {layer}.{name}")
                continue
            cited = {(d.kind, d.argument) for d in _check().directives(block)}
            wanted = {("rule", name)} | {
                ("param", f"{name}.{p}") for p in (rule.get("params") or {})
            }
            problems += [f"{layer}.{name} lacks @{k} {a}" for k, a in sorted(wanted - cited)]
    assert problems == []


def test_screen_ranking_weights_match_code() -> None:
    preset = yaml.safe_load(_PRESET.read_text(encoding="utf-8"))["ranking"]["weights"]
    code = RankingWeights()
    for name in ("value", "quality", "growth", "margin_of_safety"):
        assert math.isclose(preset[name], getattr(code, name)), name


def _company(**fields: Any) -> CompanyData:
    return CompanyData(ticker="T", name="T", **fields)


def _bench(**fields: Any) -> IndustryBenchmarks:
    return IndustryBenchmarks(industry="I", region="US", year=2026, **fields)


# Each rule evaluated exactly at its threshold: an inclusive operator on the board
# (≤, ≥) must mean the code passes at equality, a strict one (<, >) that it fails.
# Constructor kwargs pick thresholds that are exact in binary floating point.
_DIRECTIONS: list[tuple[str, str, str, dict[str, Any], CompanyData, IndustryBenchmarks]] = [
    ("min_market_cap", "market cap in USD ≥ 100M", "≥", {},
     _company(market_cap=100_000_000.0), _bench()),
    ("min_years_history", "annual rows ≥ 5", "≥", {}, _company(years_of_financials=5), _bench()),
    ("max_net_debt_to_ebitda", "net debt ÷ EBITDA ≤ 4", "≤", {},
     _company(net_debt=4.0, ebitda=1.0), _bench()),
    ("min_interest_coverage", "EBIT ÷ interest expense ≥ 2", "≥", {},
     _company(ebit=2.0, interest_expense=1.0), _bench()),
    ("positive_operating_cashflow", "operating cash flow > 0 in ≥ 4 of the last 5 years", "≥",
     {}, _company(operating_cashflow_history=(1.0, 1.0, 1.0, 1.0, -1.0)), _bench()),
    # a zero year is not positive: three positives out of five fail
    ("positive_operating_cashflow", "operating cash flow > 0", ">", {},
     _company(operating_cashflow_history=(1.0, 1.0, 1.0, 0.0, 0.0)), _bench()),
    ("max_goodwill_to_assets", "goodwill ÷ total assets ≤ 0.5", "≤", {},
     _company(goodwill=0.5, total_assets=1.0), _bench()),
    ("pe_below_industry_multiple", f"P/E < 0.7 {_TIMES} sector median P/E", "<", {"multiple": 0.5},
     _company(pe=1.0), _bench(pe=2.0)),
    ("ev_ebitda_below_industry_multiple", f"EV/EBITDA < 0.7 {_TIMES} sector median EV/EBITDA", "<",
     {"multiple": 0.5}, _company(ev_ebitda=1.0), _bench(ev_ebitda=2.0)),
    ("pbv_below_industry_multiple_with_roe_above_median",
     f"P/BV < 0.7 {_TIMES} sector median P/BV and ROE > sector median ROE", "<", {"multiple": 0.5},
     _company(pbv=1.0, roe=0.5), _bench(pbv=2.0, roe=0.1)),
    # the ROE leg at equality: P/BV clearly below, ROE equal to the median
    ("pbv_below_industry_multiple_with_roe_above_median", "ROE > sector median ROE", ">",
     {"multiple": 0.5}, _company(pbv=0.5, roe=0.25), _bench(pbv=2.0, roe=0.25)),
    ("fcf_yield_above", "free cash flow yield > 8%", ">", {}, _company(fcf_yield=0.08), _bench()),
    ("revenue_not_declining", "average revenue growth over the last 3 years > -5%", ">",
     {"max_decline": -0.5}, _company(revenue_history=(8.0, 4.0, 2.0, 1.0)), _bench()),
    ("operating_margin_not_contracting", "≥ -200 bps", "≥", {"max_contraction_bps": -2500.0},
     _company(operating_margin_history=(0.5, 0.25)), _bench()),
    ("roic_above_sector_wacc", "ROIC > sector WACC", ">", {}, _company(roic=0.25),
     _bench(wacc=0.25)),
    ("sloan_accruals_below", "÷ total assets < 0.1", "<", {"maximum": 0.25},
     _company(net_income=0.25, operating_cashflow=0.0, total_assets=1.0), _bench()),
    ("share_count_not_diluting", "average diluted share count growth ≤ 5% a year", "≤",
     {"max_annual_growth": 0.5}, _company(share_count_history=(2.0, 3.0)), _bench()),
]


@pytest.mark.parametrize(
    ("rule", "phrase", "op", "kwargs", "company", "bench"),
    _DIRECTIONS,
    ids=[f"{d[0]}[{d[2]}]" for d in _DIRECTIONS],
)
def test_screen_rule_directions_match_code(
    rule: str,
    phrase: str,
    op: str,
    kwargs: dict[str, Any],
    company: CompanyData,
    bench: IndustryBenchmarks,
) -> None:
    assert op in phrase
    block = _screen_block(f"{_preset_rule_layers()[rule]}.{rule}")
    assert _check().normalize(phrase) in _check().normalize(block)
    result = registered_rules()[rule](**kwargs).evaluate(company, bench)
    assert not result.skipped
    assert result.passed == (op in "≤≥")


def test_screen_gap_notes() -> None:
    assert "21%" in _screen_block("snapshot.tax.fallback")
    assert "auditor" in _screen_block("trap_detection.auditor")
    assert "mergers and acquisitions" in _screen_block(
        "trap_detection.share_count_not_diluting.mergers"
    )
    spec_scores = _screen_block("ranking.metrics.spec_scores")
    assert "margin stability" in spec_scores and "free cash flow growth" in spec_scores


def test_screen_dcf_seam_and_rejections() -> None:
    board = _screen()
    assert _edge_line(board, "ranking.second_pass", "analyze_stage") is not None
    assert _edge_line(board, "analyze_stage", "ranking.valued") is not None
    assert _edge_line(board, "coverage_gate.gate", "persist_and_report.persist") is not None
    assert _edge_line(board, "persist_and_report.persist", "duckdb.screener_candidates")


def test_pipeline_links_the_screen_board() -> None:
    block = _block(_overview(), "screen")
    assert block is not None and re.search(r'(?m)^\s*link:\s*"\./screen\.svg"\s*$', block)
