"""The d2 boards in docs/pipeline/ (issue #144) stay true to src/bot/ and config/.

Shared machinery for every board: each stage issue (#146 to #150) appends its own
entries to the `_REQUIRED_*` dicts and to `_ACRONYMS`. Nothing here runs d2.
"""

from __future__ import annotations

import html
import importlib
import importlib.util
import inspect
import itertools
import math
import re
import subprocess
import sys
from datetime import date
from enum import Enum
from functools import cache
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
import yaml

from bot.portfolio import events as events_mod
from bot.portfolio.events import EventType, Position
from bot.portfolio.marks import HoldingMark
from bot.reference.currencies import CurrencyRates
from bot.reporting.analysis_report import margin_verdict
from bot.screener.engine import CoverageReason
from bot.screener.ranking import RankingWeights
from bot.screener.rules import registered_rules
from bot.screener.types import CompanyData, IndustryBenchmarks
from bot.valuator import narrative_flags as flags_mod
from bot.valuator import story_types as story_mod
from bot.valuator.assumptions import AssumptionSource
from bot.valuator.dcf import Assumptions, DCFResult, Financials, YearProjection, dcf
from bot.valuator.narrative_flags import NarrativeContext
from bot.valuator.story_types import ClassificationFinancials, SectorContext, StoryType, classify
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


# Rule layer of the preset -> the screen sub-board that draws its rules (#168).
_SCREEN_LAYER_BOARDS = {
    "quality_gates": "screen-quality",
    "value_indicators": "screen-value",
    "trap_detection": "screen-traps",
}


def _preset_layer_rules(section: str) -> set[str]:
    preset = yaml.safe_load(_PRESET.read_text(encoding="utf-8"))
    return {rule["name"] for rule in preset[section]["rules"]}


def _preset_layer_params(section: str) -> set[str]:
    """The `<rule>.<param>` keys of one preset section; `ranking` gives the weights."""
    if section == "ranking":
        return {k for k in _preset_params() if k.startswith("ranking.")}
    rules = _preset_layer_rules(section)
    return {k for k in _preset_params() if k.partition(".")[0] in rules}


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
        "bot.reference.currencies.load_currency_table",
        "bot.utils.fx.import_fx_rates",
    },
    "screen": {
        "bot.cli.screen",
        "bot.screener.engine.run_screen",
        "bot.screener.engine.CoverageReason",
        "bot.screener.engine.format_coverage_counts",
        "bot.reference.currencies.load_currency_table",
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
    "analyze": {
        "bot.cli.analyze",
        "bot.valuator.analysis.analyze",
        "bot.valuator.analysis.load_valuation_input",
        "bot.valuator.analysis._sanity_check",
        "bot.valuator.analysis._operating_leverage",
        "bot.valuator.story_types.classify",
        "bot.valuator.story_types._cagr",
        "bot.valuator.story_types._earnings_cv",
        "bot.valuator.assumptions.resolve_assumptions",
        "bot.valuator.assumptions.load_assumption_inputs",
        "bot.reference.currencies.load_currency_table",
        "bot.valuator.assumptions._resolve_revenue_growth",
        "bot.valuator.assumptions._resolve_operating_margin",
        "bot.valuator.assumptions._resolve_weights",
        "bot.valuator.assumptions._resolve_terminal_growth",
        "bot.valuator.assumptions._resolve_tax_rate",
        "bot.valuator.assumptions._load_sector_with_fallback",
        "bot.valuator.assumptions.conventional_override_path",
        "bot.valuator.dcf.dcf",
        "bot.valuator.dcf._wacc",
        "bot.valuator.sensitivity.tornado",
        "bot.valuator.sensitivity.grid_2d",
        "bot.valuator.narrative_flags.narrative_flags",
        "bot.valuator.narrative_flags.story_margin_flag",
        "bot.valuator.narrative_flags.growth_reinvestment_flag",
        "bot.valuator.narrative_flags.beta_business_risk_flag",
        "bot.valuator.narrative_flags.terminal_value_share_flag",
        "bot.valuator.narrative_flags.country_exposure_flag",
        "bot.reporting.analysis_report.margin_verdict",
        "bot.reporting.analysis_report.render_analysis",
        "bot.reporting.html.render_analysis_html",
        "bot.reporting.analysis_json.render_analysis_json",
        "bot.reference.sectors.is_cyclical",
        "bot.reference.regions.dataset_region",
    },
    "portfolio": {
        "bot.cli.portfolio",
        "bot.portfolio.command.run_portfolio",
        "bot.portfolio.sync.sync_portfolio",
        "bot.portfolio.sync.value_positions",
        "bot.portfolio.trades.sync_trades",
        "bot.portfolio.marks.mark_holdings",
        "bot.portfolio.events.compute_events",
        "bot.portfolio.events.persist_events",
        "bot.portfolio.events.detect_position_changes",
        "bot.portfolio.events.detect_currency_changes",
        "bot.portfolio.events.detect_corporate_action_events",
        "bot.portfolio.events.detect_new_filings",
        "bot.portfolio.events.detect_intrinsic_value_cross",
        "bot.portfolio.events.detect_new_red_flags",
        "bot.portfolio.events.detect_concentration",
        "bot.portfolio.events.detect_sector_recalibration",
        "bot.portfolio.events.detect_below_quality_gate",
        "bot.portfolio.report.build_report",
        "bot.portfolio.report.render_portfolio",
        "bot.portfolio.report.render_alerts",
        "bot.ingest.ibkr.IbkrClient",
        "bot.ingest.ibkr_flex.import_corporate_actions",
        "bot.notifier.build_notifier",
        "bot.notifier.notify_alerts",
        "bot.screener.engine.load_holding_inputs",
    },
    "site": {
        "bot.cli.site",
        "bot.web.site.build",
        "bot.web.site._renderable",
        "bot.web.index.scan",
        "bot.web.index.read_sidecar",
        "bot.web.views.row_view",
        "bot.web.views.detail_view",
        "bot.web.views.filter_sort",
        "bot.web.views.verdict_of",
        "bot.reporting.analysis_json.render_analysis_json",
    },
    "site-publish": {"bot.reporting.analysis_json.render_analysis_json"},
    "site-ci": {"bot.cli.site"},
    "site-scan": {
        "bot.web.site.build",
        "bot.web.index.scan",
        "bot.web.index.read_sidecar",
        "bot.web.site._prepare_out_dir",
        "bot.web.site._renderable",
    },
    "site-views": {"bot.web.views.verdict_of", "bot.web.views.row_view", "bot.web.views.filter_sort"},
    "refresh-damodaran": {
        "bot.ingest.damodaran.import_damodaran",
        "bot.ingest.damodaran.merge_industry_datasets",
        "bot.ingest.damodaran.derive_industry_columns",
    },
    "refresh-fundamentals": {
        "bot.ingest.universe.import_company",
        "bot.ingest.universe._should_skip",
        "bot.ingest.industry_mapping.load_industry_mapping",
        "bot.ingest.universe._run_bulk_refresh",
    },
    "refresh-facts": {
        "bot.ingest.sec_edgar._collect_period_rows",
        "bot.ingest.sec_edgar._rescale_shares_diluted",
        "bot.ingest.sec_edgar._fiscal_quarter_key",
        "bot.ingest.sec_edgar._derive_financial_fields",
    },
    "refresh-prices": {
        "bot.ingest.universe.refresh_prices",
        "bot.ingest.universe._stale_first",
        "bot.ingest.universe._last_weekday_before",
    },
    "refresh-fx": {"bot.ingest.universe.refresh_fx"},
    "screen-snapshot": {
        "bot.screener.engine.build_company_data",
        "bot.screener.engine._resolve_region",
        "bot.screener.engine._resolve_tax_rate",
        "bot.screener.engine._market_cap_usd",
    },
    "screen-coverage": {
        "bot.screener.engine.CoverageReason",
        "bot.screener.benchmarks.load_industry_benchmarks",
    },
    "screen-quality": {"bot.screener.engine.evaluate_company"},
    "screen-value": {"bot.screener.engine.evaluate_company", "bot.screener.rules._value_score"},
    "screen-traps": {"bot.screener.engine.evaluate_company"},
    "screen-ranking": {
        "bot.screener.ranking.rank",
        "bot.screener.ranking.rescore_with_margins",
        "bot.screener.ranking._percentiles",
        "bot.screener.persist.persist_candidates",
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
    "analyze": {
        "screener_candidates",
        "companies",
        "financials_annual",
        "prices_daily",
        "damodaran_industry",
        "damodaran_country",
    },
    "portfolio": {
        "portfolio_snapshots",
        "cash_balances",
        "trades",
        "corporate_actions",
        "holding_marks",
        "events_log",
        "filings_log",
        "prices_daily",
        "currencies",
    },
    "refresh-damodaran": {"damodaran_industry", "damodaran_country", "refresh_log"},
    "refresh-fundamentals": {"companies", "filings_log", "refresh_log"},
    "refresh-facts": {"financials_annual", "financials_quarterly"},
    "refresh-prices": {"prices_daily", "refresh_log"},
    "refresh-fx": {"companies", "currencies", "refresh_log"},
    "screen-snapshot": {
        "companies", "financials_annual", "prices_daily", "damodaran_country", "currencies",
    },
    "screen-coverage": {"damodaran_industry"},
    "screen-ranking": {"screener_candidates"},
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
        "config/currencies.yaml",
    },
    "screen": {
        "config/presets/damodaran_value.yaml",
        "config/presets/deep_value.yaml",
        "config/presets/qarp.yaml",
        "config/currencies.yaml",
    },
    # config/assumptions/<TICKER>.yaml is a pattern: its directory is cited.
    "analyze": {
        "config/assumptions",
        "config/assumptions/_EXAMPLE.yaml.example",
        "src/bot/reporting/templates/analysis.md.j2",
        "config/currencies.yaml",
    },
    "portfolio": {
        "scripts/daily.sh",
        "config/presets/damodaran_value.yaml",
        "config/currencies.yaml",
    },
    "site": {
        "scripts/publish_site.sh",
        ".github/workflows/site.yml",
        ".gitignore",
        "scripts/weekly.sh",
    },
    "site-publish": {"scripts/publish_site.sh", "scripts/weekly.sh"},
    "site-ci": {".github/workflows/site.yml"},
    "site-views": {".github/workflows/site.yml"},
    "refresh-damodaran": {"scripts/weekly.sh"},
    "refresh-fundamentals": {
        "src/bot/ingest/industry_mapping.csv",
        "src/bot/ingest/universe_default.csv",
    },
    "refresh-prices": {"scripts/daily.sh", "scripts/price_fill.sh"},
    "refresh-fx": {"scripts/daily.sh"},
    "screen-coverage": {
        "config/currencies.yaml",
        "docs/adr/0006-unmeasurable-companies-leave-the-universe.md",
    },
}
# Derived from the rule registry and the preset, so a new rule or parameter
# cannot go undrawn on the screen board.
_REQUIRED_RULES: dict[str, set[str]] = {
    "screen": set(registered_rules()),
    **{board: _preset_layer_rules(layer) for layer, board in _SCREEN_LAYER_BOARDS.items()},
}
_REQUIRED_PARAMS: dict[str, set[str]] = {
    "screen": set(_preset_params()),
    **{board: _preset_layer_params(layer) for layer, board in _SCREEN_LAYER_BOARDS.items()},
    "screen-ranking": _preset_layer_params("ranking"),
}
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
    "analyze": {
        "bot.valuator.story_types._DISTRESS_ALTMAN_Z",
        "bot.valuator.story_types._DISTRESS_INTEREST_COVERAGE",
        "bot.valuator.story_types._CYCLICAL_EARNINGS_CV",
        "bot.valuator.story_types._HIGH_GROWTH_CAGR",
        "bot.valuator.story_types._MATURE_AGE_YEARS",
        "bot.valuator.story_types._DECLINE_CAGR",
        "bot.valuator.assumptions._HORIZON",
        "bot.valuator.assumptions._MIN_CYCLE_YEARS",
        "bot.valuator.assumptions._DEFAULT_TAX_RATE",
        "bot.valuator.analysis.MIN_PLAUSIBLE_SHARES",
        "bot.valuator.analysis.MAX_PLAUSIBLE_SHARES",
        "bot.valuator.sensitivity._TORNADO_LOW",
        "bot.valuator.sensitivity._TORNADO_HIGH",
        "bot.valuator.sensitivity._GRID_MULTIPLIERS",
        "bot.valuator.narrative_flags._TERMINAL_VALUE_SHARE_CEILING",
        "bot.valuator.narrative_flags._FOREIGN_REVENUE_MAJORITY",
        "bot.valuator.narrative_flags._ERP_GAP_THRESHOLD",
        "bot.valuator.narrative_flags._DEFENSIVE_BETA",
        "bot.valuator.narrative_flags._HIGH_OPERATING_LEVERAGE",
        "bot.valuator.narrative_flags._HIGH_FINANCIAL_LEVERAGE",
        "bot.valuator.narrative_flags._STRETCHED_REINVESTMENT_RATE",
        "bot.web.views.MOS_UNDERVALUED",
        "bot.web.views.MOS_FAIR",
        "bot.reporting.analysis_json.SCHEMA_VERSION",
    },
    "portfolio": {
        "bot.portfolio.events.DEFAULT_SIZE_CHANGE_THRESHOLD",
        "bot.portfolio.events.DEFAULT_CONCENTRATION_THRESHOLD",
        "bot.portfolio.events.DEFAULT_WACC_RECALIBRATION_BPS",
    },
    "site": {
        "bot.web.views.MOS_UNDERVALUED",
        "bot.web.views.MOS_FAIR",
        "bot.web.views.FILTERS",
        "bot.web.views.SORTS",
        "bot.web.views.DIRECTIONS",
        "bot.web.site.MARKER",
        "bot.reporting.analysis_json.SCHEMA_VERSION",
    },
    "site-scan": {
        "bot.reporting.analysis_json.SCHEMA_VERSION",
        "bot.web.site.MARKER",
        "bot.web.views.MOS_UNDERVALUED",
        "bot.web.views.MOS_FAIR",
    },
    "site-views": {
        "bot.web.views.MOS_UNDERVALUED",
        "bot.web.views.MOS_FAIR",
        "bot.web.views.FILTERS",
        "bot.web.views.SORTS",
        "bot.web.views.DIRECTIONS",
    },
    "refresh-fundamentals": {
        "bot.ingest.universe.SUCCESS_MAX_FAILURE_RATE",
        "bot.ingest.universe.PARTIAL_MAX_FAILURE_RATE",
    },
    "refresh-facts": {
        "bot.ingest.sec_edgar.ANNUAL_SPAN_DAYS",
        "bot.ingest.sec_edgar.QUARTERLY_SPAN_DAYS",
        "bot.ingest.sec_edgar._QUARTER_DAYS",
        "bot.ingest.sec_edgar._SHARE_SCALE_FACTORS",
        "bot.ingest.sec_edgar._MIN_SHARE_COMPARATORS",
        "bot.ingest.sec_edgar._SHARE_SCALE_TOLERANCE",
    },
    "refresh-prices": {
        "bot.ingest.universe.SUCCESS_MAX_FAILURE_RATE",
        "bot.ingest.universe.PARTIAL_MAX_FAILURE_RATE",
        "bot.ingest.edgar_base._FRESH_DAYS",
    },
    "refresh-fx": {
        "bot.ingest.universe.SUCCESS_MAX_FAILURE_RATE",
        "bot.ingest.universe.PARTIAL_MAX_FAILURE_RATE",
    },
    "screen-snapshot": {"bot.screener.engine.DEFAULT_REGION", "bot.screener.engine.DEFAULT_TAX_RATE"},
    "screen-quality": {"bot.screener.rules.DEFAULT_EXCLUDED_SECTORS"},
    "screen-ranking": {"bot.screener.ranking.PLACEHOLDER_MARGIN_OF_SAFETY"},
}
_REQUIRED_ENUMS: dict[str, set[str]] = {
    "pipeline": {"bot.web.views.Verdict"},
    "analyze": {
        "bot.valuator.story_types.StoryType",
        "bot.valuator.assumptions.AssumptionSource",
        "bot.valuator.narrative_flags.FlagColor",
        "bot.valuator.sensitivity.SensitivityAxis",
    },
    "screen": {"bot.screener.engine.CoverageReason"},
    "portfolio": {"bot.portfolio.events.EventType"},
    "site": {"bot.web.views.Verdict"},
    "site-views": {"bot.web.views.Verdict"},
    "screen-coverage": {"bot.screener.engine.CoverageReason"},
}

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
    "NOPAT": "net operating profit after tax",
    "FCFF": "free cash flow to the firm",
    "ERP": "equity risk premium",
    "GDP": "gross domestic product",
    "P/E": "price to earnings",
    "P/BV": "price to book value",
    "D/E": "debt to equity",
    "P&L": "profit and loss",
    "UTC": "Coordinated Universal Time",
}
# File formats and words written in capitals that need no expansion.
_ACRONYMS_EXEMPT: set[str] = {
    "JSON", "CSV", "YAML", "SVG", "URL", "HTML", "PNG", "DESIGN",
    "US", "USD", "YYYY", "MM", "DD", "TICKER",
}
# Acronyms with a slash or an ampersand (P/E, P&L) are whole tokens, matched before their parts.
_SYMBOLIC = sorted((k for k in _ACRONYMS if re.search(r"[/&]", k)), key=len, reverse=True)


def _token_re(token: str) -> str:
    if re.search(r"[/&]", token):
        return rf"(?<![\w/&]){re.escape(token)}(?![\w/&])"
    return rf"\b{re.escape(token)}\b"


_ACRONYM_RE = re.compile("|".join([*map(_token_re, _SYMBOLIC), r"\b[A-Z][A-Z0-9]+\b", r"\bMoS\b"]))


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
            first = re.search(_token_re(token), vis)
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
    assert len(readme.splitlines()) <= 90
    assert "docs/pipeline/build.sh" in readme
    assert "python3 docs/pipeline/check.py" in readme
    for kind in _check().KINDS:
        assert f"`@{kind}" in readme, kind
    assert "D2_VERSION" in readme
    assert "pipeline-diagram" in readme and "pipeline-render" in readme
    for stem in ("pipeline", *_STAGES):
        assert f"{stem}.svg" in readme, stem
    for words in ("reading order", "TALA", "rendered.sha256", "add a step"):
        assert words.lower() in readme.lower(), words


def test_readme_documents_subboards() -> None:
    readme = (_PIPELINE / "README.md").read_text(encoding="utf-8")
    assert "## Sub-boards" in readme
    section = readme[readme.index("## Sub-boards") :]
    for words in ("<stage>-<sub>.d2", "`objective`", "`back`", "`out`", "Comes out:", "24",
                  "statechart", "models/"):
        assert words in section, words


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
        ("damodaran.country.risk_free", "note"),
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
    assert "risk-free" in _refresh_block("damodaran.country.risk_free")
    assert "Financial Modeling Prep" in _refresh_block("fx.fetch.no_op")
    assert "ADR 0005 (Implemented)" in _refresh_block("damodaran.write.us_only")
    assert "config/currencies.yaml" in _refresh_block("damodaran.country.risk_free")


def test_refresh_country_rows_carry_no_risk_free_rate() -> None:
    assert "wacc.xls" not in _refresh_block("damodaran.country")
    edge = _edge_line(_refresh(), "damodaran.write", "duckdb.damodaran_country")
    assert edge is not None and "risk-free" not in edge


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
    + [(f, "file") for f in ("damodaran_value", "deep_value", "qarp", "assumptions", "currencies_yaml")]
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
    "coverage_gate.gate": [
        "industry_unmapped",
        "benchmark_missing",
        "currency_uncovered",
        "leaves the universe",
        "before any rule runs",
        "one reason",
        "missing, or not in config/currencies.yaml",
    ],
    "currencies_yaml": ["absent or malformed", "every currency uncovered"],
    "persist_and_report.report": ["coverage gate exclusions per reason"],
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
    "ranking.percentiles": ["0-based rank", "÷ (distinct values - 1)", "all values equal: 1", "ties share"],
    "ranking.weights": [
        f"100 {_TIMES} (0.40 {_TIMES} value + 0.30 {_TIMES} quality + 0.20 {_TIMES} growth"
        f" + 0.10 {_TIMES} margin of safety)",
    ],
    "ranking.weights.bounds": ["sum", "no ceiling"],
    "ranking.first_pass": ["0.5"],
    "ranking.top_n": ["--top"],
    "ranking.second_pass": [
        "intrinsic value ÷ price", "config/assumptions/TICKER.yaml", "config/currencies.yaml",
    ],
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
    assert _edge_line(board, "currencies_yaml", "coverage_gate.gate") is not None
    assert _edge_line(board, "currencies_yaml", "ranking.second_pass") is not None
    assert _edge_line(board, "persist_and_report.persist", "duckdb.screener_candidates")


def test_screen_coverage_reasons_in_precedence_order() -> None:
    gate = _screen_block("coverage_gate.gate")
    order = ["industry_unmapped", "benchmark_missing", "currency_uncovered"]
    assert [gate.index(r) for r in order] == sorted(gate.index(r) for r in order)
    assert [r.value for r in CoverageReason] == order


def test_pipeline_links_the_screen_board() -> None:
    block = _block(_overview(), "screen")
    assert block is not None and re.search(r'(?m)^\s*link:\s*"\./screen\.svg"\s*$', block)


def _analyze() -> str:
    return _boards().get("analyze", "")


def _analyze_block(key: str) -> str:
    block = _block(_analyze(), key)
    assert block is not None, f"analyze.d2 has no node {key}"
    return block


_STORY_ORDER = ("distressed", "cyclical", "high_growth", "mature_decline", "mature_stable")
_FLAGS = (
    "story_margin",
    "growth_reinvestment",
    "beta_business_risk",
    "terminal_value_share",
    "country_exposure",
)

_ANALYZE_NODES: list[tuple[str, str]] = (
    [("cli", "step"), ("cli.errors", "note"), ("tickers", "decision"), ("override", "decision")]
    + [(f, "file") for f in ("override_yaml", "example_yaml", "template", "currencies_yaml")]
    + [(f"duckdb.{t}", "store") for t in sorted(_REQUIRED_TABLES["analyze"])]
    + [(o, "output") for o in ("report_md", "report_html", "report_json")]
    + [
        ("inputs.load", "step"),
        ("inputs.load.exact_region", "note"),
        ("inputs.region", "decision"),
        ("inputs.derived", "step"),
        ("inputs.derived.age", "gap"),
    ]
    + [(f"story_type.{k}", "decision") for k in (*_STORY_ORDER, "manual")]
    + [("story_type.distressed.altman", "gap"), ("story_type.manual.reasons", "note")]
    + [
        (f"assumptions.{k}", "step")
        for k in (
            "sector_row",
            "growth",
            "margin",
            "sales_to_capital",
            "discount_rates",
            "weights",
            "terminal_growth",
            "tax",
            "bankruptcy",
        )
    ]
    + [
        ("assumptions.growth.consensus", "gap"),
        ("assumptions.sales_to_capital.story", "gap"),
        ("assumptions.weights.company", "gap"),
        ("assumptions.bankruptcy.manual_only", "gap"),
        ("assumptions.sources", "note"),
        ("dcf.guard", "decision"),
        ("dcf.wacc", "step"),
        ("dcf.converges", "decision"),
        ("dcf.years", "step"),
        ("dcf.terminal", "step"),
        ("dcf.ev", "step"),
        ("dcf.equity", "step"),
        ("dcf.equity.adjustments", "gap"),
        ("dcf.blend", "step"),
        ("sensitivity.tornado", "step"),
        ("sensitivity.grid", "step"),
    ]
    + [(f"narrative_flags.{f}", "decision") for f in _FLAGS]
    + [
        ("narrative_flags.country_exposure.always_unknown", "gap"),
        ("verdict.mos", "step"),
        ("verdict.words", "decision"),
        ("sanity_check.multiples", "step"),
        ("reports.markdown", "step"),
        ("reports.html", "step"),
        ("reports.json", "step"),
    ]
)

# Node -> phrases its block must show (compared after check.normalize, so the
# board's U+2212 minus signs match the ASCII hyphens here).
_ANALYZE_TEXT: dict[str, list[str]] = {
    "tickers": ["--from-screen", "latest", "by rank", "exit code 2"],
    "override": ["--override", "exactly one ticker", "config/assumptions/TICKER.yaml"],
    "cli.errors": ["exit code 2", "exit code 1", "worst"],
    "inputs.load": [
        "non-restated", "oldest-first", "pe, ev_sales, op_margin, beta_levered", "valuation currency",
    ],
    "inputs.derived": [
        "net debt = total debt - cash",
        "EBIT ÷ interest expense",
        "ipo_date",
        "cyclical",
    ],
    "story_type.distressed": ["Altman Z < 1.81", "interest coverage ≤ 1.0"],
    "story_type.cyclical": [
        "coefficient of variation ≥ 0.50",
        "standard deviation ÷ |mean|",
        "net income",
    ],
    "story_type.high_growth": [
        "CAGR) ≥ 15%",
        "age ≤ 25",
        "(last ÷ first)^(1 ÷ (years - 1)) - 1",
        "unknown age counts as young",
    ],
    "story_type.mature_decline": ["CAGR ≤ -1%"],
    "story_type.manual": ["story_type", "unknown label"],
    "assumptions.sector_row": ["any region", "sector_default_damodaran_cross_region"],
    "assumptions.growth": [
        "manual",
        "story_pattern",
        "historical_average",
        "rule_based",
        "nominal GDP growth of the valuation currency",
        "unresolved",
        "(revenue_t - revenue_t-1) ÷ revenue_t-1",
    ],
    "assumptions.margin": [
        "story_pattern",
        "historical_average",
        "≥ 4 years",
        "sector label",
        "unresolved",
    ],
    "assumptions.sales_to_capital": ["manual", "sector label", "unresolved"],
    "assumptions.discount_rates": ["cost of equity", "pre-tax cost of debt", "unresolved"],
    "assumptions.weights": ["D/E ÷ (1 + D/E)", "1 - it", "sum to 1", "1 - debt weight"],
    "assumptions.terminal_growth": [
        "min(risk-free rate, nominal GDP growth)",
        "valuation currency",
        "config/currencies.yaml",
        "rule_based",
        "unresolved",
    ],
    "assumptions.tax": ["sector label", "country tax_rate", "sector_default_damodaran", "25%"],
    "assumptions.bankruptcy": ["manual", "else 0 → rule_based"],
    "dcf.guard": ["1,000,000 ≤ diluted shares ≤ 100,000,000,000", "exit code 1"],
    "dcf.wacc": [
        f"equity weight {_TIMES} cost of equity + debt weight {_TIMES} pre-tax cost of debt"
        f" {_TIMES} (1 - tax)",
    ],
    "dcf.converges": ["g_terminal < WACC"],
    "dcf.years": [
        f"revenue_t = revenue_t-1 {_TIMES} (1 + g_t)",
        f"EBIT_t = revenue_t {_TIMES} margin_t",
        f"EBIT_t {_TIMES} (1 - tax)",
        "(revenue_t - revenue_t-1) ÷ sales-to-capital",
        "NOPAT_t - reinvestment_t",
        "FCFF_t ÷ (1 + WACC)^t",
    ],
    "dcf.terminal": [
        f"revenue_N {_TIMES} (1 + g_terminal)",
        "FCFF_N+1 ÷ (WACC - g_terminal)",
        "terminal value ÷ (1 + WACC)^N",
    ],
    "dcf.ev": [
        "Σ present value_t + present value of terminal value",
        "present value of terminal value ÷ EV",
    ],
    "dcf.equity": ["EV - net debt + adjustments", "equity ÷ diluted shares"],
    "dcf.blend": [
        f"(1 - p) {_TIMES} going-concern value per share",
        f"p {_TIMES} distress value per share",
    ],
    "sensitivity.tornado": [f"{_TIMES} 0.8", f"{_TIMES} 1.2", "one at a time", "widest first"],
    "sensitivity.grid": [
        "five by five", "two widest", "0.8, 0.9, 1.0, 1.1, 1.2", "intrinsic value ÷ price",
    ],
    "narrative_flags.story_margin": ["high-growth", "> sector op_margin", "yellow", "unknown"],
    "narrative_flags.growth_reinvestment": ["FCFF < 0", "NOPAT ≤ 0", "red", "> 0.90", "yellow"],
    "narrative_flags.beta_business_risk": [
        "beta_levered < 1.0",
        "operating leverage > 1.5",
        "debt weight > 40%",
        "%ΔEBIT ÷ %ΔRevenue",
        "total debt ÷ (total debt + total equity)",
    ],
    "narrative_flags.terminal_value_share": ["terminal value share > 80%", "yellow"],
    "narrative_flags.country_exposure": ["> 50%", "> 300 bps", "red", "unknown"],
    "verdict.mos": ["intrinsic value per share ÷ latest close", "none"],
    "verdict.words": [
        "MoS ≥ 1.3: potentially undervalued",
        "MoS ≥ 1.0: around fair value",
        "MoS < 1.0: potentially overvalued",
        "n/a",
    ],
    "sanity_check.multiples": [
        "price ÷ earnings per share (EPS)",
        "net income ÷ diluted shares",
        "EV ÷ revenue",
        "decides nothing",
    ],
    "reports.json": ["schema_version 1", "verdict"],
}


@pytest.mark.parametrize(("key", "cls"), _ANALYZE_NODES)
def test_analyze_nodes(key: str, cls: str) -> None:
    assert _node_class(_analyze(), key) == cls


@pytest.mark.parametrize("key", list(_ANALYZE_TEXT))
def test_analyze_text(key: str) -> None:
    block = _check().normalize(_analyze_block(key))
    missing = [w for w in _ANALYZE_TEXT[key] if _check().normalize(w) not in block]
    assert missing == []


def _story(**fields: Any) -> StoryType:
    signals: dict[str, Any] = {"revenue_history": (1.0, 1.0), "earnings_history": (1.0, 1.0)}
    cyclical = fields.pop("cyclical", False)
    return classify(ClassificationFinancials(**(signals | fields)), SectorContext(cyclical))


_YEAR = YearProjection(1, 1.0, 1.0, 1.0, 0.0, 1.0, 1.0, 1.0)


def _flag(name: str, *, share: float = 0.5, year: YearProjection = _YEAR, **ctx: Any) -> str:
    fn = getattr(flags_mod, f"{name}_flag")
    fin = Financials(revenue=1.0, net_debt=0.0, shares_diluted=1.0)
    ass = Assumptions((0.0,), (0.1,), 0.2, 1.0, 0.02, 0.1, 0.05, 1.0, 0.0)
    res = DCFResult(1.0, 1.0, 1.0, (year,), 1.0, share, 0.1, 1.0)
    return str(fn(fin, ass, res, NarrativeContext(**ctx)).color)


_RISKY = {"sector_beta": 0.5, "operating_leverage": 2.0, "company_debt_weight": 0.5}

# Each comparison evaluated in the code exactly at its threshold: an inclusive
# operator on the board (≤, ≥) must mean the code fires at equality, a strict
# one (<, >) that it does not. Thresholds not exact in binary are patched to exact ones.
_ANALYZE_DIRECTIONS: list[tuple[str, str, str, dict[str, float], Any]] = [
    ("story_type.distressed", "Altman Z < 1.81", "<", {},
     lambda: _story(altman_z=1.81) is StoryType.DISTRESSED),
    ("story_type.distressed", "interest coverage ≤ 1.0", "≤", {},
     lambda: _story(interest_coverage=1.0) is StoryType.DISTRESSED),
    ("story_type.cyclical", "coefficient of variation ≥", "≥", {},
     lambda: _story(earnings_history=(1.0, 3.0), cyclical=True) is StoryType.CYCLICAL),
    ("story_type.high_growth", "CAGR) ≥", "≥", {"_HIGH_GROWTH_CAGR": 0.5},
     lambda: _story(revenue_history=(1.0, 1.5)) is StoryType.HIGH_GROWTH),
    ("story_type.high_growth", "age ≤ 25", "≤", {},
     lambda: _story(revenue_history=(1.0, 2.0), age_years=25) is StoryType.HIGH_GROWTH),
    ("story_type.mature_decline", "CAGR ≤", "≤", {"_DECLINE_CAGR": -0.5},
     lambda: _story(revenue_history=(2.0, 1.0)) is StoryType.MATURE_DECLINE),
    ("narrative_flags.terminal_value_share", "terminal value share > 80%", ">", {},
     lambda: _flag("terminal_value_share", share=0.8) == "yellow"),
    ("narrative_flags.growth_reinvestment", "> 0.90", ">", {},
     lambda: _flag("growth_reinvestment", year=YearProjection(1, 1, 1, 1.0, 0.9, 0.1, 1, 1))
     == "yellow"),
    ("narrative_flags.beta_business_risk", "beta_levered < 1.0", "<", {},
     lambda: _flag("beta_business_risk", **(_RISKY | {"sector_beta": 1.0})) == "yellow"),
    ("narrative_flags.beta_business_risk", "operating leverage > 1.5", ">", {},
     lambda: _flag("beta_business_risk", **(_RISKY | {"operating_leverage": 1.5})) == "yellow"),
    ("narrative_flags.beta_business_risk", "debt weight > 40%", ">", {},
     lambda: _flag("beta_business_risk", **(_RISKY | {"company_debt_weight": 0.4})) == "yellow"),
    ("narrative_flags.story_margin", "> sector op_margin", ">", {},
     lambda: _flag("story_margin", story_type="high-growth", company_operating_margin=0.25,
                   sector_operating_margin=0.25) == "yellow"),
    ("narrative_flags.country_exposure", "> 50%", ">", {},
     lambda: _flag("country_exposure", foreign_revenue_share=0.5, erp_weighted=1.0,
                   erp_listing=0.0) == "red"),
    ("narrative_flags.country_exposure", "> 300 bps", ">", {"_ERP_GAP_THRESHOLD": 0.25},
     lambda: _flag("country_exposure", foreign_revenue_share=1.0, erp_weighted=0.5,
                   erp_listing=0.25) == "red"),
]


@pytest.mark.parametrize(
    ("node", "phrase", "op", "patches", "fires"),
    _ANALYZE_DIRECTIONS,
    ids=[f"{d[0]}[{d[1]}]" for d in _ANALYZE_DIRECTIONS],
)
def test_analyze_directions_match_code(
    monkeypatch: pytest.MonkeyPatch,
    node: str,
    phrase: str,
    op: str,
    patches: dict[str, float],
    fires: Any,
) -> None:
    assert op in phrase
    assert _check().normalize(phrase) in _check().normalize(_analyze_block(node))
    for name, value in patches.items():
        monkeypatch.setattr(story_mod if hasattr(story_mod, name) else flags_mod, name, value)
    assert fires() == (op in "≤≥")


def test_analyze_story_type_order() -> None:
    board = _analyze()
    lines = [_analyze_block(f"story_type.{k}").splitlines()[0] for k in _STORY_ORDER]
    positions = [board.index(line) for line in lines]
    assert positions == sorted(positions)
    for a, b in itertools.pairwise(_STORY_ORDER):
        edge = _edge_line(board, f"story_type.{a}", f"story_type.{b}")
        assert edge is not None and '"no"' in edge, (a, b)


def test_analyze_story_priority_matches_classify() -> None:
    both = {"revenue_history": (1.0, 2.0), "earnings_history": (1.0, 3.0), "cyclical": True}
    assert _story(interest_coverage=0.5, **both) is StoryType.DISTRESSED
    assert _story(**both) is StoryType.CYCLICAL
    assert _story(**(both | {"cyclical": False})) is StoryType.HIGH_GROWTH
    assert _story(revenue_history=(2.0, 1.0)) is StoryType.MATURE_DECLINE
    assert _story(revenue_history=(1.0,)) is StoryType.MATURE_STABLE


def _valuation_input(shares: float) -> Any:
    from bot.valuator import analysis
    from bot.valuator import assumptions as resolve

    return analysis.ValuationInput(
        ticker="T",
        company=analysis._CompanyRow("T", "US", "USD", None, None),
        latest=analysis._LatestFinancials(100.0, 10.0, 8.0, 1.0, 0.0, shares, 0.0, 50.0),
        revenue_history=(90.0, 100.0),
        income_history=(7.0, 8.0),
        ebit_history=(9.0, 10.0),
        sector=analysis._SectorMultiples("US", None, None, None, None, None),
        current_price=10.0,
        assumption_inputs=resolve.AssumptionInputs(
            company=resolve._Company("US", None),
            country=None,
            sector=resolve._SectorRow(0.08, 0.09, 0.05, 0.1, 2.0, 0.25, 0.5),
            historical_growth_path=None,
            valuation_currency="USD",
            currency_rates=CurrencyRates(0.0395, 0.04, "s", "g", date(2026, 1, 1)),
        ),
    )


@pytest.mark.parametrize(
    ("shares", "valued"),
    [(1_000_000.0, True), (999_999.0, False), (100_000_000_000.0, True), (100_000_000_001.0, False)],
)
def test_analyze_share_bounds_are_inclusive(shares: float, valued: bool) -> None:
    from bot.valuator.analysis import analyze

    # The board's `1,000,000 ≤ diluted shares ≤ 100,000,000,000`: both ends are valued.
    conn: Any = None  # every row comes pre-loaded, so analyze issues no query
    if valued:
        assert analyze("T", conn, company=_valuation_input(shares)).dcf_result is not None
    else:
        with pytest.raises(ValueError, match="implausible diluted share count"):
            analyze("T", conn, company=_valuation_input(shares))


def test_analyze_has_no_gdp_constant() -> None:
    assert re.search(r"(?<![\d.])4%", _check().visible(_analyze())) is None


def test_analyze_terminal_growth_reads_the_currency_table() -> None:
    board = _analyze()
    assert _edge_line(board, "currencies_yaml", "assumptions.terminal_growth") is not None
    assert _edge_line(board, "duckdb.damodaran_country", "assumptions.terminal_growth") is None
    assert _edge_line(board, "inputs.load", "assumptions") is not None


def test_analyze_terminal_growth_must_stay_below_wacc() -> None:
    # terminal growth equal to WACC does not converge: the board's `<` is strict
    at_wacc = Assumptions((0.0,), (0.1,), 0.0, 1.0, 0.5, 0.5, 0.0, 1.0, 0.0)
    with pytest.raises(ValueError, match="terminal_growth"):
        dcf(Financials(revenue=1.0, net_debt=0.0, shares_diluted=1.0), at_wacc)


def test_analyze_assumption_sources() -> None:
    block = _analyze_block("assumptions")
    missing = [s.value for s in AssumptionSource if s.value not in block]
    assert missing == []


def test_analyze_report_sections_match_template() -> None:
    template = (_ROOT / "src" / "bot" / "reporting" / "templates" / "analysis.md.j2").read_text()
    titles = re.findall(r"(?m)^## (\d+\. .+)$", template)
    assert len(titles) == 8
    block = _check().normalize(_analyze_block("reports.markdown")).lower()
    missing = [t for t in titles if _check().normalize(t).lower() not in block]
    assert missing == []


_ANALYZE_GAPS: dict[str, list[str]] = {
    "story_type.distressed.altman": ["Altman Z", "computed nowhere"],
    "assumptions.bankruptcy.manual_only": ["manual override"],
    "narrative_flags.country_exposure.always_unknown": ["always unknown"],
    "assumptions.growth.consensus": ["analyst consensus", "analyst_consensus"],
    "assumptions.sales_to_capital.story": ["sales-to-capital and terminal growth"],
    "dcf.equity.adjustments": ["minority interests", "cross-holdings", "no input path"],
    "inputs.derived.age": ["ipo_date", "Verified", "parse_submissions_info"],
    "assumptions.weights.company": ["capital structure"],
}


@pytest.mark.parametrize("key", list(_ANALYZE_GAPS))
def test_analyze_gap_notes(key: str) -> None:
    block = _analyze_block(key)
    assert "Gap:" in block
    missing = [w for w in _ANALYZE_GAPS[key] if w not in block]
    assert missing == []


def test_analyze_ipo_date_gap_is_current() -> None:
    from bot.ingest.sec_edgar import parse_submissions_info

    edgar_fills_it = parse_submissions_info("T", {}).ipo_date is not None
    has_gap = _node_class(_analyze(), "inputs.derived.age") == "gap"
    assert has_gap != edgar_fills_it, (
        "EDGAR now fills ipo_date: remove the gap" if has_gap else "draw the ipo_date gap"
    )


@pytest.mark.parametrize(
    ("src", "dst"),
    [
        ("duckdb.screener_candidates", "tickers"),
        ("override", "inputs.load"),
        ("inputs.derived", "story_type.distressed"),
        ("story_type.manual", "assumptions"),
        ("assumptions", "dcf.guard"),
        ("dcf.blend", "verdict.mos"),
        ("verdict.mos", "verdict.words"),
        ("reports.markdown", "report_md"),
        ("reports.html", "report_html"),
        ("reports.json", "report_json"),
    ],
)
def test_analyze_flow_edges(src: str, dst: str) -> None:
    assert _edge_line(_analyze(), src, dst) is not None


def test_pipeline_links_the_analyze_board() -> None:
    block = _block(_overview(), "analyze")
    assert block is not None and re.search(r'(?m)^\s*link:\s*"\./analyze\.svg"\s*$', block)


def _portfolio() -> str:
    return _boards().get("portfolio", "")


def _portfolio_block(key: str) -> str:
    block = _block(_portfolio(), key)
    assert block is not None, f"portfolio.d2 has no node {key}"
    return block


_PORTFOLIO_TABLES = sorted(_REQUIRED_TABLES["portfolio"])

_PORTFOLIO_NODES: list[tuple[str, str]] = (
    [("daily", "cron")]
    + [(e, "external") for e in ("tws", "flex", "channels")]
    + [(f, "file") for f in ("preset", "override_yaml", "portfolio_template", "alerts_template")]
    + [(f"duckdb.{t}", "store") for t in _PORTFOLIO_TABLES]
    + [(o, "output") for o in ("portfolio_md", "alerts_md", "message")]
    + [
        ("cli", "step"),
        ("cli.exits", "note"),
        ("cli.gates", "note"),
        ("sync.snapshot", "step"),
        ("sync.value", "step"),
        ("sync.value.adr_0005", "gap"),
        ("sync.corporate_actions", "step"),
        ("sync.corporate_actions.unverified", "gap"),
        ("sync.trades", "step"),
        ("marks.held", "step"),
        ("marks.valuation", "step"),
        ("marks.gates", "step"),
        ("marks.persist", "step"),
        ("marks.persist.unknowns", "note"),
        ("events.window", "step"),
    ]
    + [(f"events.{t.value}", "decision") for t in EventType]
    + [
        ("events.split.other_actions", "gap"),
        ("events.new_filing.no_auto_analyze", "gap"),
        ("events.not_events", "note"),
        ("events.persist", "step"),
        ("events.persist.reruns", "note"),
        ("reports.portfolio", "step"),
        ("reports.alerts", "step"),
        ("notify.channel", "decision"),
        ("notify.send", "decision"),
    ]
)

# Node -> phrases its block must show (compared after check.normalize, so the
# board's U+2212 minus signs match the ASCII hyphens here).
_PORTFOLIO_TEXT: dict[str, list[str]] = {
    "daily": ["09:00", "only when both succeeded"],
    "cli.exits": ["exit code 2", "exit code 1"],
    "sync.snapshot": ["(snapshot_date, account)", "delete", "then insert"],
    "sync.value": [
        f"market value = quantity {_TIMES} latest close",
        "on or before the snapshot date",
        f"close {_TIMES} rate_to_usd of the listing currency ÷ rate_to_usd of the position's currency",
        "close ≤ 0",
        "unpriced",
    ],
    "sync.corporate_actions": [
        "BOT_IBKR_FLEX_TOKEN",
        "BOT_IBKR_FLEX_QUERY_ID",
        "ct:<id>",
        "ca:<id>",
        "de-duplicated on action_id",
        "warning",
    ],
    "sync.trades": [
        "newest executed_at",
        "de-duplicated on exec_id",
        "naive Coordinated Universal Time (UTC)",
    ],
    "marks.held": ["≠ 0"],
    "marks.valuation": [
        "config/assumptions/TICKER.yaml", "red narrative flags", "unknown",
        "config/currencies.yaml", "once per run",
    ],
    "marks.gates": ["skipped rule does not count", "sector WACC"],
    "marks.persist.unknowns": ["never fires", "counts as empty"],
    "events.window": ["per ticker across accounts", "never a recomputation"],
    "events.position_opened": ["≠ 0", "first run"],
    "events.position_closed": ["absent or 0 now", "returns no positions"],
    "events.position_size_changed": ["> 10%", "exactly 10%: no event"],
    "events.currency_changed": ["listing currency", "not on the first run"],
    "events.dividend": ["after the previous snapshot, on or before this one"],
    "events.split": ["split"],
    "events.new_filing": ["absent from events_log", "ingested"],
    "events.intrinsic_value_crossed_price": ["equality is not a cross"],
    "events.new_red_flag": ["not red in the previous mark"],
    "events.below_quality_gate": ["failing now and not failing before"],
    "events.sector_recalibrated": ["> 100 bps", "exactly 100 bps: no event"],
    "events.concentration": ["> 15%", "exactly 15%: no event", "fires on every run while above"],
    "events.not_events": ["price moves", "news"],
    "events.persist.reruns": ["same events again"],
    "reports.portfolio": [
        f"P&L = market value - quantity {_TIMES} average cost",
        "suggested review",
        "--history",
        "--concentration",
    ],
    "reports.alerts": ["always written", "empty"],
    "notify.channel": ["BOT_NOTIFIER", "exit code 2"],
    "notify.send": ["blank", "exit code 1"],
}


@pytest.mark.parametrize(("key", "cls"), _PORTFOLIO_NODES)
def test_portfolio_nodes(key: str, cls: str) -> None:
    assert _node_class(_portfolio(), key) == cls


@pytest.mark.parametrize("key", list(_PORTFOLIO_TEXT))
def test_portfolio_text(key: str) -> None:
    block = _check().normalize(_portfolio_block(key))
    missing = [w for w in _PORTFOLIO_TEXT[key] if _check().normalize(w) not in block]
    assert missing == []


def test_portfolio_every_event_type_is_a_decision() -> None:
    for event in EventType:
        block = _portfolio_block(f"events.{event.value}")
        assert _node_class(_portfolio(), f"events.{event.value}") == "decision", event
        assert event.value in block.splitlines()[0], event
    events = _portfolio_block("events")
    decisions = re.findall(r"(?m)^  (\w+):.*\n\s*class:\s*decision\b", events)
    assert sorted(decisions) == sorted(e.value for e in EventType)


_DAY = date(2026, 1, 2)
_PREV = date(2026, 1, 1)


def _pos(ticker: str, qty: float, mv: float | None = None) -> Position:
    return Position(ticker=ticker, qty=qty, market_value=mv, currency="USD")


def _mark(iv: float, price: float) -> HoldingMark:
    return HoldingMark(ticker="T", intrinsic_value=iv, price=price)


# Each detector evaluated exactly at its threshold: a strict operator on the
# board means no event at equality. Thresholds are passed as exact binary
# fractions; test_portfolio_threshold_defaults pins the defaults to the constants.
_PORTFOLIO_DIRECTIONS: list[tuple[str, str, str, Any]] = [
    ("events.position_size_changed", "> 10%", ">",
     lambda: any(e.event_type is EventType.POSITION_SIZE_CHANGED
                 for e in events_mod.detect_position_changes(
                     [_pos("T", 2.0)], [_pos("T", 3.0)], snapshot_date=_DAY, prev_date=_PREV,
                     size_change_threshold=0.5))),
    ("events.concentration", "> 15%", ">",
     lambda: any(e.ticker == "A"
                 for e in events_mod.detect_concentration(
                     [_pos("A", 1.0, 1.0), _pos("B", 1.0, 3.0)], snapshot_date=_DAY,
                     prev_date=_PREV, threshold=0.25))),
    ("events.sector_recalibrated", "> 100 bps", ">",
     lambda: events_mod.detect_sector_recalibration(
         0.5, 0.75, "T", snapshot_date=_DAY, prev_date=_PREV, threshold=0.25) is not None),
]


@pytest.mark.parametrize(
    ("node", "phrase", "op", "fires"),
    _PORTFOLIO_DIRECTIONS,
    ids=[f"{d[0]}[{d[1]}]" for d in _PORTFOLIO_DIRECTIONS],
)
def test_portfolio_directions_match_code(node: str, phrase: str, op: str, fires: Any) -> None:
    assert op in phrase
    assert _check().normalize(phrase) in _check().normalize(_portfolio_block(node))
    assert fires() == (op in "≤≥")


def test_portfolio_threshold_defaults() -> None:
    def default(fn: Any, name: str) -> Any:
        return inspect.signature(fn).parameters[name].default

    assert (default(events_mod.detect_position_changes, "size_change_threshold")
            == events_mod.DEFAULT_SIZE_CHANGE_THRESHOLD)
    assert (default(events_mod.detect_concentration, "threshold")
            == events_mod.DEFAULT_CONCENTRATION_THRESHOLD)
    assert (default(events_mod.detect_sector_recalibration, "threshold")
            == events_mod.DEFAULT_WACC_RECALIBRATION_BPS)
    # just above each threshold fires, so the explicit-threshold cases above are not vacuous
    assert events_mod.detect_sector_recalibration(
        0.5, 0.76, "T", snapshot_date=_DAY, prev_date=_PREV, threshold=0.25) is not None
    assert events_mod.detect_position_changes(
        [_pos("T", 2.0)], [_pos("T", 3.5)], snapshot_date=_DAY, prev_date=_PREV,
        size_change_threshold=0.5)
    assert any(e.ticker == "A" for e in events_mod.detect_concentration(
        [_pos("A", 1.0, 1.5), _pos("B", 1.0, 3.0)], snapshot_date=_DAY, prev_date=_PREV,
        threshold=0.25))


def test_portfolio_equality_is_not_a_cross() -> None:
    assert "equality is not a cross" in _portfolio_block("events.intrinsic_value_crossed_price")

    def cross(before: HoldingMark, now: HoldingMark) -> bool:
        return events_mod.detect_intrinsic_value_cross(
            before, now, snapshot_date=_DAY, prev_date=_PREV) is not None

    assert not cross(_mark(9.0, 10.0), _mark(10.0, 10.0))  # below, then equal
    assert not cross(_mark(10.0, 10.0), _mark(11.0, 10.0))  # equal, then above
    assert cross(_mark(9.0, 10.0), _mark(11.0, 10.0))
    assert cross(_mark(11.0, 10.0), _mark(9.0, 10.0))


def test_portfolio_run_steps_match_code() -> None:
    from bot.portfolio.command import run_portfolio

    source = inspect.getsource(run_portfolio)
    calls = ["sync_portfolio(", "corporate_actions_fn(conn)", "sync_trades(", "mark_holdings(",
             "compute_events(", "persist_events(", "build_report("]
    positions = [source.index(c) for c in calls]
    assert positions == sorted(positions)
    for key, number in (("sync.snapshot", "1."), ("sync.corporate_actions", "2."),
                        ("sync.trades", "3.")):
        label = _portfolio_block(key).splitlines()[0].split(":", 1)[1].strip().strip('"')
        assert label.startswith(number), key
    for key, number in (("marks", "4a."), ("events", "4b."), ("reports", "5."), ("notify", "6.")):
        label = _portfolio_block(key).splitlines()[0].split(":", 1)[1].strip().strip('"')
        assert label.startswith(number), key


def test_portfolio_cli_order_matches_code() -> None:
    from bot.cli import portfolio

    source = inspect.getsource(portfolio)
    calls = ["build_notifier(", "preset_path.exists()", "run_portfolio(", "notify_alerts("]
    positions = [source.index(c) for c in calls]
    assert positions == sorted(positions)
    assert "typer.Exit(code=2)" in source and "typer.Exit(code=1)" in source


_PORTFOLIO_GAPS: dict[str, list[str]] = {
    "sync.value.adr_0005": ["ADR 0005 (Implemented)", "§1\u2013§3", "US-only"],
    "sync.corporate_actions.unverified": ["not yet verified against a real pull", "issue 110"],
    "events.split.other_actions": ["mergers", "fire no event"],
    "events.new_filing.no_auto_analyze": [
        "Verified", "run_portfolio", "mark_holdings", "no analysis report",
    ],
}


@pytest.mark.parametrize("key", list(_PORTFOLIO_GAPS))
def test_portfolio_gap_notes(key: str) -> None:
    block = _portfolio_block(key)
    assert "Gap:" in block
    missing = [w for w in _PORTFOLIO_GAPS[key] if w not in block]
    assert missing == []


def _has_gap(key: str) -> bool:
    return _node_class(_portfolio(), key) == "gap"


def _collapsed(text: str) -> str:
    return " ".join(text.split())


def test_portfolio_adr_0005_gap_is_current() -> None:
    adr = next((_ROOT / "docs" / "adr").glob("0005-*.md")).read_text(encoding="utf-8")
    status = adr[adr.index("## Status") :].split("\n## ", 1)[0]
    # §4 is implemented (#109); the gap stays while §1-§3 are not.
    unimplemented = "still not implemented" in _collapsed(status)
    assert _has_gap("sync.value.adr_0005") == unimplemented


def test_portfolio_flex_gap_is_current() -> None:
    from bot.ingest import ibkr_flex

    unverified = "not yet verified against a real pull" in _collapsed(ibkr_flex.__doc__ or "")
    assert _has_gap("sync.corporate_actions.unverified") == unverified


def test_portfolio_other_actions_gap_is_current() -> None:
    def fired(action: str) -> list[Any]:
        return events_mod.detect_corporate_action_events(
            [("T", action, {})], snapshot_date=_DAY, prev_date=None)

    assert [e.event_type for e in fired("dividend")] == [EventType.DIVIDEND]  # positive control
    assert _has_gap("events.split.other_actions") == (fired("merger") == [])


def test_portfolio_filing_auto_analyze_gap_is_current() -> None:
    from bot.cli import portfolio
    from bot.portfolio.command import run_portfolio

    # A substring check: a mere mention in a docstring also counts as reacting.
    sources = inspect.getsource(portfolio) + inspect.getsource(run_portfolio)
    reacts = "NEW_FILING" in sources or "new_filing" in sources
    assert _has_gap("events.new_filing.no_auto_analyze") != reacts


@pytest.mark.parametrize(
    ("src", "dst"),
    [
        ("daily", "cli"),
        ("tws", "sync.snapshot"),
        ("flex", "sync.corporate_actions"),
        ("sync.value", "duckdb.portfolio_snapshots"),
        ("marks.persist", "duckdb.holding_marks"),
        ("duckdb.holding_marks", "events.intrinsic_value_crossed_price"),
        ("events.persist", "duckdb.events_log"),
        ("reports.portfolio", "portfolio_md"),
        ("reports.alerts", "alerts_md"),
        ("notify.send", "channels"),
    ],
)
def test_portfolio_flow_edges(src: str, dst: str) -> None:
    assert _edge_line(_portfolio(), src, dst) is not None


def test_portfolio_daily_runs_after_prices_and_fx() -> None:
    script = (_ROOT / "scripts" / "daily.sh").read_text(encoding="utf-8")
    assert script.index('((worst == 0)) || exit "$worst"') < script.index("uv run bot portfolio")


def test_pipeline_links_the_portfolio_board() -> None:
    block = _block(_overview(), "portfolio")
    assert block is not None and re.search(r'(?m)^\s*link:\s*"\./portfolio\.svg"\s*$', block)


def _site() -> str:
    return _boards().get("site", "")


def _site_block(key: str) -> str:
    block = _block(_site(), key)
    assert block is not None, f"site.d2 has no node {key}"
    return block


_SITE_CI = ("checkout", "sync", "ruff", "mypy", "pytest", "site", "upload", "deploy")
_SITE_PAGES = (
    "index_page", "not_found", "robots", "list_pages", "row_fragments",
    "company_pages", "detail_fragments", "static",
)

_SITE_NODES: list[tuple[str, str]] = (
    [(f, "file") for f in ("sidecars", "publish_script", "gitignore", "site_yml", "design")]
    + [("weekly", "cron"), ("master", "external")]
    + [("publish.collect", "step"), ("publish.worktree", "step"),
       ("publish.changed", "decision"), ("publish.push", "step")]
    + [(f"ci.{k}", "step") for k in _SITE_CI]
    + [("ci.concurrency", "note"), ("ci.stops", "note")]
    + [
        ("build.read_only", "note"),
        ("build.cli", "step"),
        ("build.out_dir", "decision"),
        ("build.scan", "step"),
        ("build.usable", "decision"),
        ("build.renderable", "decision"),
        ("build.rows", "step"),
        ("build.verdict", "decision"),
        ("build.counts", "step"),
        ("build.lists", "step"),
        ("build.detail", "step"),
        ("build.render", "step"),
        ("build.reader", "note"),
    ]
    + [(p, "output") for p in _SITE_PAGES]
    + [("serve.pages", "external"), ("serve.published_site", "output")]
)

# Node -> phrases its block must show (compared after check.normalize).
_SITE_TEXT: dict[str, list[str]] = {
    "sidecars": ["reports/YYYY-MM-DD/analysis/TICKER.json", "bot analyze"],
    "gitignore": ["reports/*/analysis/*.json"],
    "weekly": ["Saturdays 10:00", "only when the previous one succeeded"],
    "publish.collect": ["reports/*/analysis/*.json", "exit 0"],
    "publish.worktree": [".cache/site-publish", "origin/master", "only the sidecars",
                         "never committed"],
    "publish.changed": ["no commit, exit 0"],
    "publish.push": ["chore(site): publish analyses YYYY-MM-DD", "origin master", "exit 1"],
    "ci": ["on every push to master"],
    "ci.concurrency": ["cancels"],
    "ci.stops": ["nothing is deployed"],
    "build.read_only": ["ADR) 0008 (Implemented)", "read-only"],
    "build.cli": ["--out", "--reports-dir", "--base-url", "one leading and one trailing slash"],
    "build.out_dir": ["reports directory", "not a directory", ".bot-site", "exit code 2"],
    "build.scan": ["date = the folder name", "ticker = the file stem", "newest analysis first"],
    "build.usable": ["YYYY-MM-DD", "1 to 12", "schema_version 1", "analysis.ticker",
                     "skipped with a warning"],
    "build.renderable": ["skipped with a warning", "dropped"],
    "build.rows": ["newest analysis", "red and yellow flags"],
    "build.verdict": ["≥ 1.3: undervalued", "≥ 1.0: fair", "< 1.0: overvalued", "none: na",
                      "verdict text the sidecar carries", "recomputed"],
    "build.counts": ["all = every company"],
    "build.lists": ["filter \u00d7 sort \u00d7 direction", "ties by ticker ascending",
                    "without a margin of safety always last"],
    "build.detail": ["sources in words", "tornado", "grid of verdicts",
                     "pass, warning, fail or not evaluated"],
    "build.render": ["base URL"],
    "build.reader": ["verdict filter", "sources", "tornado", "grid", "flags"],
    "not_found": ["404.html", "any missing path"],
    "robots": ["robots.txt", "f/", "rows/"],
    "list_pages": ["l/<filter>-<sort>-<direction>.html"],
    "row_fragments": ["rows/<filter>-<sort>-<direction>.html"],
    "company_pages": ["c/TICKER.html", "c/TICKER/YYYY-MM-DD.html"],
    "detail_fragments": ["f/TICKER.html", "f/TICKER/YYYY-MM-DD.html"],
    "serve.pages": ["GitHub Pages"],
}


@pytest.mark.parametrize(("key", "cls"), _SITE_NODES)
def test_site_nodes(key: str, cls: str) -> None:
    assert _node_class(_site(), key) == cls


@pytest.mark.parametrize("key", list(_SITE_TEXT))
def test_site_text(key: str) -> None:
    block = _check().normalize(_site_block(key))
    missing = [w for w in _SITE_TEXT[key] if _check().normalize(w) not in block]
    assert missing == []


@pytest.mark.parametrize(
    ("src", "dst"),
    [
        ("weekly", "publish.collect"),
        ("sidecars", "publish.collect"),
        ("publish.push", "master"),
        ("master", "ci.checkout"),
        ("site_yml", "ci"),
        ("ci.site", "build.cli"),
        ("build.scan", "build.usable"),
        ("build.usable", "build.renderable"),
        ("build.render", "index_page"),
        ("ci.deploy", "serve.pages"),
    ],
)
def test_site_flow_edges(src: str, dst: str) -> None:
    assert _edge_line(_site(), src, dst) is not None


def _label(block: str) -> str:
    """The quoted label of a node block's declaration line."""
    m = re.match(r'[^:]*:\s*"((?:[^"\\]|\\.)*)"', block.splitlines()[0])
    return m.group(1) if m else ""


def test_site_ci_steps_match_workflow() -> None:
    workflow = (_ROOT / ".github" / "workflows" / "site.yml").read_text(encoding="utf-8")
    needles = [
        ("actions/checkout", "check out"),
        ("uv sync --frozen", "uv sync --frozen"),
        ("ruff check", "ruff check"),
        ("mypy src", "mypy src"),
        ("pytest -q", "pytest -q"),
        ("bot site --out site --base-url", "bot site --out site --base-url"),
        ("upload-pages-artifact", "upload"),
        ("deploy-pages", "deploy"),
    ]
    positions = [workflow.index(needle) for needle, _ in needles]
    assert positions == sorted(positions)
    for n, (key, (_, words)) in enumerate(zip(_SITE_CI, needles, strict=True), 1):
        label = _label(_site_block(f"ci.{key}"))
        assert label.startswith(f"{n}. ") and words in label, key


def test_site_publish_matches_script() -> None:
    script = (_ROOT / "scripts" / "publish_site.sh").read_text(encoding="utf-8")
    for words in (".cache/site-publish", 'checkout -q --detach "$REMOTE/$BRANCH"',
                  "diff --cached --quiet", "chore(site): publish analyses"):
        assert words in script, words
    weekly = (_ROOT / "scripts" / "weekly.sh").read_text(encoding="utf-8")
    assert weekly.index("bot analyze --from-screen") < weekly.index('"$SCRIPT_DIR/publish_site.sh"')


def test_site_verdict_sources_match_code() -> None:
    from bot.web import views

    assert 'ref.data["verdict"]' in inspect.getsource(views.row_view)
    assert "verdict_of(" in inspect.getsource(views.value_line)
    assert "verdict_of(" in inspect.getsource(views.scenario_grid)
    block = _site_block("build.verdict")
    assert "list rows" in block and "value line and grid cells" in block


def test_site_ticker_rule_matches_code() -> None:
    from bot.web.index import TICKER_RE

    assert TICKER_RE.pattern == r"^[A-Z0-9.\-]{1,12}$"
    assert "1 to 12" in _site_block("build.usable")


def test_pipeline_links_the_site_board() -> None:
    block = _block(_overview(), "site")
    assert block is not None and re.search(r'(?m)^\s*link:\s*"\./site\.svg"\s*$', block)


_AVOIDED = ("local currency", "trading currency", "reported currency", "functional currency")


def test_boards_use_context_vocabulary() -> None:
    bad = []
    for stem, board in _boards().items():
        vis = _check().visible(board)
        bad += [f"{stem}: {w}" for w in _AVOIDED if w in vis.lower()]
        for m in re.finditer(r"(?<![\w])quality[ -]?gates?(?![\w])", vis, re.I):
            if m.group(0) not in ("quality gate", "quality gates", "Quality gate", "Quality gates"):
                bad.append(f"{stem}: {m.group(0)}")
    assert bad == []


_ADR_RE = re.compile(r"\bADR\)?\s+(\d{4})(?:\s*\((Accepted|Implemented|Not implemented|Superseded)\))?")


def _adr_status_text(number: str) -> str:
    path = next((_ROOT / "docs" / "adr").glob(f"{number}-*.md"), None)
    assert path is not None, f"no docs/adr/{number}-*.md"
    text = path.read_text(encoding="utf-8")
    if "## Status" in text:
        section = text[text.index("## Status") :].split("\n## ", 1)[0]
    else:  # ADR 0001-0003 state it on one line
        section = next(line for line in text.splitlines() if line.startswith("**Status:**"))
    return _collapsed(section)


_STATUS_RE = re.compile(r"Accepted|Implemented|Not implemented|Superseded")


def _current_status(number: str) -> str:
    """The status word the ADR's status text states last: Implemented outranks Accepted."""
    words = _STATUS_RE.findall(_adr_status_text(number))
    assert words, f"ADR {number} states no status"
    return words[-1]


def test_adr_mentions_carry_their_status() -> None:
    bad = []
    for stem, board in _boards().items():
        for m in _ADR_RE.finditer(_check().visible(board)):
            number, status = m.group(1), m.group(2)
            if status is None:
                bad.append(f"{stem}: ADR {number} without a status")
            elif status != _current_status(number):
                bad.append(f"{stem}: ADR {number} is {_current_status(number)}, not {status}")
    assert bad == []


_GOVERNING_ADRS = {
    "0001": "pipeline", "0004": "portfolio", "0005": "refresh",
    "0006": "screen", "0007": "refresh", "0008": "site",
}


def test_governing_adrs_are_named() -> None:
    missing = [
        f"ADR {n} on {stem}"
        for n, stem in _GOVERNING_ADRS.items()
        if n not in {m.group(1) for m in _ADR_RE.finditer(_check().visible(_boards().get(stem, "")))}
    ]
    assert missing == []


_KEY_RE = re.compile(r"^(\s*)([\w.]+)\s*:")
_ATTRIBUTES = {"class", "link", "label", "direction", "shape", "near", "style", "tooltip"}
_EDGE_RE = re.compile(r"^\s*([\w.]+)\s*->\s*([\w.]+)\s*:\s*\S")


def _nodes(text: str) -> dict[str, tuple[int, str | None]]:
    """Dotted path -> (declaration line index, class), from indentation and braces."""
    lines = _check()._scan(text)
    stack: list[tuple[int, str]] = []
    out: dict[str, tuple[int, str | None]] = {}
    for i, ln in enumerate(lines):
        m = _KEY_RE.match(ln.code)
        if not m or "->" in ln.code or m.group(2).split(".")[0] in _ATTRIBUTES:
            continue
        indent = len(m.group(1))
        while stack and stack[-1][0] >= indent:
            stack.pop()
        path = ".".join([k for _, k in stack] + [m.group(2)])
        nxt = lines[i + 1].code if i + 1 < len(lines) else ""
        cls = re.search(r"\{\s*class:\s*(\w+)", ln.code) or re.match(r"\s*class:\s*(\w+)", nxt)
        out[path] = (i, cls.group(1) if cls else None)
        if ln.code.rstrip().endswith("{"):
            stack.append((indent, m.group(2)))
    return out


# A number token read whole: sign, digits with thousands separators, decimals, unit.
_NUMBER_RE = re.compile(
    r"(?<![\w.\-\u2212/])([-\u2212]?\d[\d,]*(?:\.\d+)?)(\s?%|\s?bps\b|[KMB]\b)?(?![\w/.]|-\w)"
)
_ORDINAL_RE = re.compile(r"(?<![\d.])\d+[a-z]?\.(?=\s)")
_UNITS = {"%": 0.01, "bps": 0.0001, "K": 1e3, "M": 1e6, "B": 1e9}


def _cited_values(board: str) -> dict[int, list[float]]:
    """Source line number -> numeric values of its @const / @param directives."""
    def flat(v: Any) -> list[float]:
        if isinstance(v, (list, tuple)):
            return [x for y in v for x in flat(y)]
        ok = isinstance(v, (int, float)) and not isinstance(v, bool)
        return [float(v)] if ok else []

    out: dict[int, list[float]] = {}
    for d in _check().directives(board):
        if d.kind == "const":
            out.setdefault(d.line, []).extend(flat(_resolve(d.argument)))
        elif d.kind == "param":
            out.setdefault(d.line, []).extend(flat(_preset_params().get(d.argument)))
    return out


def _uncited_numbers(label: str, cited: list[float]) -> list[str]:
    text = _ORDINAL_RE.sub("", label.replace("\\n", " "))
    bad = []
    for m in _NUMBER_RE.finditer(text):
        value = float(m.group(1).replace(",", "").replace("\u2212", "-"))
        value *= _UNITS.get((m.group(2) or "").strip(), 1.0)
        if abs(value) in (0.0, 1.0, 100.0):
            continue
        if not any(math.isclose(abs(value), abs(c), rel_tol=1e-9) for c in cited):
            bad.append(m.group(0).strip())
    return bad


def test_every_step_has_purpose_and_edges() -> None:
    problems = []
    for stem, board in _boards().items():
        nodes = _nodes(board)
        edges = [m.groups() for line in _check().visible(board).splitlines()
                 if (m := _EDGE_RE.match(line))]
        cited = _cited_values(board)

        def touches(end: str, path: str) -> bool:
            return end == path or end.startswith(path + ".") or path.startswith(end + ".")

        for path, (i, cls) in nodes.items():
            if cls != "step":
                continue
            block = _block(board, path) or ""
            label = _label(block)
            if len(label.replace("\\n", " ").split()) < 3:
                problems.append(f"{stem} {path}: no purpose line")
            if not any(touches(dst, path) for _, dst in edges) and "No incoming edge" not in block:
                problems.append(f"{stem} {path}: no incoming edge")
            if not any(touches(src, path) for src, _ in edges) and "No outgoing edge" not in block:
                problems.append(f"{stem} {path}: no outgoing edge")
            if bad := _uncited_numbers(label, cited.get(i + 1, [])):
                problems.append(f"{stem} {path}: uncited numbers {bad}")
    assert problems == []


def test_step_audit_reads_numbers_whole() -> None:
    assert _uncited_numbers("1. within 380 days, 91.3-day steps, 5-year path", [380.0]) == []
    assert _uncited_numbers("fewer than 2 years", []) == ["2"]
    assert _uncited_numbers("> \u22125% or 100M", [-0.05, 1e8]) == []
    assert _uncited_numbers("score = 100 \u00d7 (0.40 \u00d7 value)", [0.4]) == []
    assert _uncited_numbers("revenue_t\u22121 \u00d7 (1 + g)", []) == []


_PLANO = "docs/plano/part-data.js"
_LECCION = "docs/leccion/index.html"

# (board, gap node) -> ({document: phrases still in it}, phrases the note shows).
# When a document is fixed its phrase disappears and the test asks to remove the gap.
_DOC_GAPS: dict[tuple[str, str], tuple[dict[str, list[str]], list[str]]] = {
    ("pipeline", "duckdb.plano_tables"): (
        {_PLANO: ["Las quince:"]}, ["plano duckdb", "16", "holding_marks"]),
    ("refresh", "damodaran.download.plano_hash"): (
        {_PLANO: ["El refresco es por hash", "hash mensual"]},
        ["plano damodaran", "a-download", "hash"]),
    ("refresh", "region.plano_label"): (
        {_PLANO: ["el parámetro de región es solo la etiqueta"]}, ["plano damodaran", "refuse"]),
    ("screen", "coverage_gate.gate.plano_caveat"): (
        {_PLANO: ["el motor todavía resuelve los huecos capa por capa"]},
        ["plano damodaran", "layer by layer", "coverage gate"]),
    ("screen", "coverage_gate.gate.plano_wacc"): (
        {_PLANO: ["Su único consumidor es el filtro de ROIC contra WACC"]},
        ["plano a-wacc", "coverage gate", "sector_recalibrated"]),
    ("screen", "snapshot.load.plano_restated"): (
        {_PLANO: ["El screener usa siempre el último"]}, ["plano sec", "is_restated"]),
    ("screen", "quality_gates.plano_bounds"): (
        {_PLANO: ["Más de USD 100 millones", "menor a 4", "mayor a 2",
                  "Menos del 50% del activo"]},
        ["plano g-cap", "g-debt", "g-cover", "g-gw", "equality"]),
    ("screen", "trap_detection.revenue_not_declining.docs_bound"): (
        {_PLANO: ["No más de 5% anual promedio"], _LECCION: ["no caen en promedio más de"]},
        ["plano t-rev", "leccion cap-4", "\u22125%"]),
    ("analyze", "assumptions.plano_sources"): (
        {_PLANO: ["rule_based · unresolved", "el default es el promedio histórico"]},
        ["plano assumptions", "a-growth", "story_pattern"]),
    ("analyze", "story_type.distressed.altman"): (
        {_PLANO: ["El Altman Z decide la clasificación"]}, ["plano s-ds", "a-default"]),
    ("analyze", "dcf.equity.adjustments"): (
        {_PLANO: ["más ajustes por minoritarios"]}, ["plano dcf"]),
    ("analyze", "reports.markdown.plano_header"): (
        {_PLANO: ["las versiones de datos que usó"]}, ["plano reports", "generation date"]),
    ("portfolio", "events.new_filing.no_auto_analyze"): (
        {_PLANO: ["vuelve a correr el análisis de la Capa C solo"]}, ["plano monitor"]),
    ("portfolio", "events.dividend.plano_unfed"): (
        {_PLANO: ["nada los alimenta"]}, ["plano events", "Flex"]),
    ("pipeline", "weekly.plano_cron"): (
        {_PLANO: ["el script de instalación todavía no existe"]},
        ["plano reports", "install_cron.sh", "analyzes and publishes"]),
}


@pytest.mark.parametrize("key", list(_DOC_GAPS), ids=[f"{b}-{n}" for b, n in _DOC_GAPS])
def test_document_gaps_are_current(key: tuple[str, str]) -> None:
    stem, node = key
    documents, shown = _DOC_GAPS[key]
    for doc, phrases in documents.items():
        text = html.unescape((_ROOT / doc).read_text(encoding="utf-8"))
        stale = [p for p in phrases if p not in text]
        assert stale == [], f"{doc} no longer says {stale}: remove or update the gap"
    board = _boards().get(stem, "")
    assert _node_class(board, node) == "gap", f"{stem}.d2 has no gap {node}"
    block = _check().normalize(_block(board, node) or "")
    assert "Gap:" in block
    assert [w for w in shown if _check().normalize(w) not in block] == []


def test_svgs_show_their_step_labels() -> None:
    missing = []
    for stem, board in _boards().items():
        svg_path = _PIPELINE / f"{stem}.svg"
        svg = html.unescape(svg_path.read_text(encoding="utf-8")) if svg_path.exists() else ""
        for path, (_, cls) in _nodes(board).items():
            if cls != "step":
                continue
            first = _label(_block(board, path) or "").split("\\n")[0].replace('\\"', '"')
            if first.strip() not in svg:
                missing.append(f"{stem}.svg: {first.strip()}")
    assert missing == []


def test_pipeline_svg_links_the_five_stage_boards() -> None:
    svg = (_PIPELINE / "pipeline.svg").read_text(encoding="utf-8")
    hrefs = set(re.findall(r'href="([^"]+)"', svg))
    assert hrefs == {f"./{stage}.svg" for stage in _STAGES}
    for stage in _STAGES:
        assert (_PIPELINE / f"{stage}.svg").exists(), stage
