"""Unit tests for the additional screener presets (spec §6.6, issue M3.9).

Covers the two extra presets shipped alongside ``damodaran_value``:

- ``deep_value`` — more Graham than Damodaran (relaxes growth, tightens cheapness).
- ``qarp`` — Quality at Reasonable Price (tightens quality, relaxes cheapness).

Each test asserts the preset loads and resolves against the rule registry, that
its trap-detection layer is shared verbatim with ``damodaran_value``, and that —
run over one fixture universe — it produces a *different* shortlist than
``damodaran_value`` (the core acceptance criterion). Both YAML files must also
carry a leading documentation comment explaining their philosophy.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from bot.screener.config import ScreenerConfig, load_screener_config
from bot.screener.engine import run_screen
from bot.screener.rules import Rule
from bot.storage.db import apply_schema

_PRESETS_DIR = Path(__file__).resolve().parents[2] / "config" / "presets"
_DAMODARAN = _PRESETS_DIR / "damodaran_value.yaml"
_DEEP_VALUE = _PRESETS_DIR / "deep_value.yaml"
_QARP = _PRESETS_DIR / "qarp.yaml"

_EXTRA_PRESETS = (_DEEP_VALUE, _QARP)


# --------------------------------------------------------------------------- #
# Fixture universe — a spread of cheap/expensive, high/low-quality companies so
# different threshold profiles select visibly different shortlists.
# --------------------------------------------------------------------------- #

_SECTOR = "Software (System & Application)"


def _seed_sector(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(
        "INSERT INTO damodaran_country (country, year, region) VALUES (?, ?, ?)",
        ["United States", 2026, "US"],
    )
    conn.execute(
        "INSERT INTO damodaran_industry "
        "(industry, region, year, wacc, roe, pe, pbv, ev_ebitda) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        [_SECTOR, "US", 2026, 0.085, 0.15, 22.0, 4.0, 12.0],
    )


def _add_company(
    conn: duckdb.DuckDBPyConnection,
    ticker: str,
    *,
    close: float,
    eps: float,
    book_per_share: float = 2.0,
    revenue_growth: float = 0.10,
    fcf: float = 600_000_000.0,
    ebitda: float = 1_000_000_000.0,
    op_margin: float = 0.35,
    interest: float = 50_000_000.0,
    net_debt: float = 0.0,
    market_cap: float = 5_000_000_000.0,
    years: int = 8,
    shares: float = 1_000_000_000.0,
) -> None:
    conn.execute(
        "INSERT INTO companies (ticker, name, country, industry, industry_damodaran, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [ticker, f"{ticker} Corp", "United States", _SECTOR, _SECTOR, "fmp"],
    )
    net_income = eps * shares
    total_debt = max(net_debt, 0.0)
    cash = max(-net_debt, 0.0)
    for offset in range(years):
        rev = 1_000_000_000.0 * ((1.0 + revenue_growth) ** offset)
        # ebit tracks revenue at a constant op margin so the margin-not-contracting
        # trap detector (shared §6.4 filter) passes for every fixture company.
        conn.execute(
            "INSERT INTO financials_annual "
            "(ticker, fiscal_year, revenue, ebit, ebitda, interest_expense, net_income, "
            "total_assets, total_debt, cash, total_equity, goodwill, operating_cashflow, "
            "free_cashflow, shares_diluted, is_restated, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                ticker, 2020 + offset, rev, rev * op_margin, ebitda, interest,
                net_income, 6_000_000_000.0, total_debt, cash,
                book_per_share * shares, 500_000_000.0, fcf + 100_000_000.0,
                fcf, shares, False, "fmp",
            ],
        )
    conn.execute(
        "INSERT INTO prices_daily (ticker, date, close, market_cap, currency, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [ticker, "2026-05-29", close, market_cap, "USD", "fmp"],
    )


def _seed_universe(conn: duckdb.DuckDBPyConnection) -> None:
    # Sector US medians (0.7x cheap thresholds): PE<15.4, EV/EBITDA<8.4, PBV<2.8.
    # ROE median 0.15; ROE here = eps / book_per_share.
    _seed_sector(conn)
    # DEEP: very cheap (PE 4, FCF yield 16%), modest growth, ROE 0.30 — a deep-value
    # favourite. Survives damodaran_value too but ranks far higher under deep_value.
    _add_company(
        conn, "DEEP", close=4.0, eps=1.0, book_per_share=3.3,
        revenue_growth=0.06, fcf=800_000_000.0,
    )
    # QUALY: high quality (ROE 0.30, FCF yield 18%), strong growth, but priced near
    # the sector median (PE 14) so it is NOT deep-value cheap. The qarp sweet spot.
    _add_company(
        conn, "QUALY", close=14.0, eps=1.0, book_per_share=3.3,
        revenue_growth=0.18, fcf=400_000_000.0, ebitda=500_000_000.0,
    )
    # BALAN: balanced — cheap-ish (PE 10) and decent quality (ROE 0.22), the
    # damodaran_value sweet spot.
    _add_company(
        conn, "BALAN", close=10.0, eps=1.0, book_per_share=4.5,
        revenue_growth=0.10, fcf=600_000_000.0,
    )


@pytest.fixture
def conn() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect(":memory:")
    apply_schema(c)
    _seed_universe(c)
    return c


def _shortlist(conn: duckdb.DuckDBPyConnection, path: Path) -> tuple[str, ...]:
    cfg = load_screener_config(path)
    result = run_screen(conn, cfg)
    return tuple(c.ticker for c in result.shortlist)


# --------------------------------------------------------------------------- #
# Each preset exists, loads, and carries a philosophy comment.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("path", _EXTRA_PRESETS, ids=lambda p: p.stem)
def test_preset_file_exists(path: Path) -> None:
    assert path.is_file(), f"missing preset at {path}"


@pytest.mark.parametrize("path", _EXTRA_PRESETS, ids=lambda p: p.stem)
def test_preset_loads_and_resolves(path: Path) -> None:
    config = load_screener_config(path)
    assert isinstance(config, ScreenerConfig)
    assert config.name == path.stem
    for spec in config.rule_specs():
        assert issubclass(spec.resolve(), Rule)
    # Every rule also instantiates with its declared params.
    config.quality_gates.build()
    config.value_indicators.build()
    config.trap_detection.build()


@pytest.mark.parametrize("path", _EXTRA_PRESETS, ids=lambda p: p.stem)
def test_preset_has_leading_documentation_comment(path: Path) -> None:
    first_line = path.read_text(encoding="utf-8").splitlines()[0]
    assert first_line.startswith("#"), "preset must open with a doc comment"
    assert len(first_line.strip("# ").strip()) > 0


@pytest.mark.parametrize("path", _EXTRA_PRESETS, ids=lambda p: p.stem)
def test_preset_must_keep_some_value_and_quality_rules(path: Path) -> None:
    config = load_screener_config(path)
    assert config.quality_gates.rules, "quality gates must not be empty"
    assert config.value_indicators.rules, "value indicators must not be empty"


# --------------------------------------------------------------------------- #
# Shared trap-detection layer (spec §6.4 / issue: "share the trap detection
# layer with damodaran_value").
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("path", _EXTRA_PRESETS, ids=lambda p: p.stem)
def test_trap_detection_shared_with_damodaran_value(path: Path) -> None:
    base = load_screener_config(_DAMODARAN)
    preset = load_screener_config(path)
    assert preset.trap_detection.rules == base.trap_detection.rules


# --------------------------------------------------------------------------- #
# Core acceptance: each preset yields a different shortlist than damodaran_value.
# --------------------------------------------------------------------------- #


def test_deep_value_shortlist_differs_from_damodaran(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    base = _shortlist(conn, _DAMODARAN)
    deep = _shortlist(conn, _DEEP_VALUE)
    assert deep != base


def test_qarp_shortlist_differs_from_damodaran(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    base = _shortlist(conn, _DAMODARAN)
    qarp = _shortlist(conn, _QARP)
    assert qarp != base


def test_extra_presets_differ_from_each_other(
    conn: duckdb.DuckDBPyConnection,
) -> None:
    assert _shortlist(conn, _DEEP_VALUE) != _shortlist(conn, _QARP)
