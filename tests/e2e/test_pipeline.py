"""E2E (spec §12): refresh -> screen -> analyze sobre UNA base compartida, sin red.

Siembra Damodaran desde los fixtures existentes (``tests/fixtures/damodaran/``,
patrón de ``test_damodaran_import.py``) y tres empresas US vía el importer de FMP
con un ``FmpClient`` fake (patrón de ``test_fmp_import.py``): GOODCO (sólida y
barata — sobrevive el screen), TRAPCO (margen operativo colapsando > 200bps —
cae por el detector de trampas) y NOCOVCO (industria sin fila Damodaran — cae
por el gate de cobertura, ADR 0006). Después ejercita los comandos reales del
CLI (``screen`` y ``analyze --from-screen``) contra esa DB compartida y verifica
que la cadena completa — refresh, screen, analyze — deja rastro consistente:
el shortlist, los artefactos §6.1/§7.7, y ``screener_candidates``/``refresh_log``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import duckdb
import pytest
from typer.testing import CliRunner

from bot.cli import app
from bot.ingest.damodaran import import_damodaran_from_files
from bot.ingest.fmp import CompanyInfo, import_company_from_fmp
from bot.storage.db import apply_schema, connect

FIXTURES = Path(__file__).parent.parent / "fixtures" / "damodaran"

# The Damodaran fixtures map "Software" -> this canonical sector (see
# src/bot/ingest/industry_mapping.csv), and the fixture's WACC file gives it a
# non-NULL WACC for region "US" — everything the coverage gate (ADR 0006)
# needs. GOODCO/TRAPCO's numbers below are set relative to that WACC.
_SECTOR = "Software (System & Application)"
_YEAR = 2026


class _FakeFmpClient:
    """Duck-typed stand-in for :class:`bot.ingest.fmp.FmpClient` — no network.

    ``import_company_from_fmp`` only ever calls ``lookup_company`` and the three
    per-period statement getters on the object passed as ``client``; it never
    constructs one itself when a client is supplied, so this fake never needs a
    real API key or an HTTP transport.
    """

    def __init__(
        self,
        profile: CompanyInfo | None,
        annual: tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]],
    ) -> None:
        self._profile = profile
        self._income_a, self._balance_a, self._cashflow_a = annual

    def lookup_company(self, _ticker: str) -> CompanyInfo | None:
        return self._profile

    def income_statement(self, _ticker: str, *, period: str, limit: int = 10) -> list[dict[str, Any]]:
        return self._income_a if period == "annual" else []

    def balance_sheet(self, _ticker: str, *, period: str, limit: int = 10) -> list[dict[str, Any]]:
        return self._balance_a if period == "annual" else []

    def cash_flow(self, _ticker: str, *, period: str, limit: int = 10) -> list[dict[str, Any]]:
        return self._cashflow_a if period == "annual" else []


def _fabricated_statements(
    ticker: str,
    *,
    years: list[int],
    revenue_start: float,
    revenue_growth: float,
    op_margins: list[float],
    interest: float,
    total_debt: float,
    cash: float,
    total_equity: float,
    goodwill: float,
    total_assets: float,
    operating_cashflow: float,
    free_cashflow: float,
    shares: float,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Build synthetic FMP income/balance/cash-flow arrays (annual, FY only).

    ``op_margins`` has one entry per year in ``years`` (oldest first) so a
    caller can shape a stable or a contracting margin history. Every other
    input is held constant across years — this is a controlled fixture, not a
    realistic filing history.
    """
    income: list[dict[str, Any]] = []
    balance: list[dict[str, Any]] = []
    cashflow: list[dict[str, Any]] = []
    for i, year in enumerate(years):
        period_end = f"{year}-12-31"
        revenue = revenue_start * ((1.0 + revenue_growth) ** i)
        ebit = revenue * op_margins[i]
        ebitda = ebit * 1.2
        net_income = (ebit - interest) * 0.75
        income.append(
            {
                "date": period_end,
                "symbol": ticker,
                "reportedCurrency": "USD",
                "fillingDate": period_end,
                "calendarYear": str(year),
                "period": "FY",
                "revenue": revenue,
                "operatingIncome": ebit,
                "ebitda": ebitda,
                "interestExpense": interest,
                "netIncome": net_income,
                "weightedAverageShsDilOut": shares,
            }
        )
        balance.append(
            {
                "date": period_end,
                "symbol": ticker,
                "reportedCurrency": "USD",
                "calendarYear": str(year),
                "period": "FY",
                "totalAssets": total_assets,
                "totalDebt": total_debt,
                "cashAndCashEquivalents": cash,
                "totalStockholdersEquity": total_equity,
                "goodwill": goodwill,
            }
        )
        cashflow.append(
            {
                "date": period_end,
                "symbol": ticker,
                "reportedCurrency": "USD",
                "calendarYear": str(year),
                "period": "FY",
                "operatingCashFlow": operating_cashflow,
                "freeCashFlow": free_cashflow,
            }
        )
    return income, balance, cashflow


def _seed_damodaran_from_fixtures(conn: duckdb.DuckDBPyConnection) -> None:
    # ``wacc_sample.xls`` + ``ctryprem_sample.xls`` alone carry the WACC the
    # coverage gate needs, but ``analyze`` also needs a sector operating margin
    # and sales-to-capital (spec §7.1/§7.2) — those live in the other Damodaran
    # files, so pull them in too (mirrors what the real ``import_damodaran``
    # merges from the full download; here it is the same fixtures the other
    # Capa A tests already use).
    extra_industry_paths = {
        "margin": FIXTURES / "margin_sample.xls",
        "capex": FIXTURES / "capex_sample.xls",
        "pedata": FIXTURES / "pedata_sample.xls",
        "pbvdata": FIXTURES / "pbvdata_sample.xls",
        "vebitda": FIXTURES / "vebitda_sample.xls",
        "psdata": FIXTURES / "psdata_sample.xls",
    }
    result = import_damodaran_from_files(
        conn,
        industry_path=FIXTURES / "wacc_sample.xls",
        country_path=FIXTURES / "ctryprem_sample.xls",
        region="US",
        year=_YEAR,
        extra_industry_paths=extra_industry_paths,
    )
    assert result.is_success(), result.error_message
    wacc, op_margin, sales_to_capital = conn.execute(
        "SELECT wacc, op_margin, sales_to_capital FROM damodaran_industry "
        "WHERE industry = ? AND region = 'US' ORDER BY year DESC LIMIT 1",
        [_SECTOR],
    ).fetchone()
    assert wacc is not None, f"{_SECTOR!r}/US must carry a non-NULL WACC for the coverage gate"
    assert op_margin is not None and sales_to_capital is not None, (
        f"{_SECTOR!r}/US must carry sector op_margin/sales_to_capital for `analyze`"
    )


def _seed_company_via_fmp_importer(
    conn: duckdb.DuckDBPyConnection,
    *,
    ticker: str,
    industry: str | None,
    op_margins: list[float],
    market_cap: float,
    close: float,
) -> None:
    years = list(range(_YEAR - 6, _YEAR))
    profile = CompanyInfo(
        ticker=ticker,
        name=f"{ticker} Inc",
        exchange="NASDAQ",
        exchange_short_name="NASDAQ",
        country="United States",  # matches damodaran_country.country from the fixtures
        currency="USD",
        sector="Technology",
        industry=industry,
        is_actively_trading=True,
    )
    statements = _fabricated_statements(
        ticker,
        years=years,
        revenue_start=1_000_000_000.0,
        revenue_growth=0.10,
        op_margins=op_margins,
        interest=20_000_000.0,
        total_debt=0.0,
        cash=0.0,
        total_equity=2_000_000_000.0,
        goodwill=200_000_000.0,
        total_assets=3_000_000_000.0,
        operating_cashflow=550_000_000.0,
        free_cashflow=500_000_000.0,
        shares=1_000_000_000.0,
    )
    client = _FakeFmpClient(profile, statements)
    result = import_company_from_fmp(conn, ticker=ticker, api_key="unused", client=client)
    assert result.is_success(), result.error

    conn.execute(
        "INSERT INTO prices_daily (ticker, date, close, market_cap, currency, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [ticker, f"{_YEAR}-05-29", close, market_cap, "USD", "fmp"],
    )


def test_pipeline_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db_path = tmp_path / "bot.duckdb"
    reports = tmp_path / "reports"
    env = {
        "BOT_DB_PATH": str(db_path),
        "BOT_REPORTS_DIR": str(reports),
        "BOT_SEC_USER_AGENT": "test test@example.com",
        "BOT_FMP_API_KEY": "test-key",
        "BOT_PRESETS_DIR": str(Path(__file__).resolve().parents[2] / "config" / "presets"),
    }
    conn = connect(db_path)
    apply_schema(conn)

    # 1. Capa A: Damodaran desde fixtures (patrón de test_damodaran_import) +
    #    tres empresas: una que debe sobrevivir el screen (GOODCO), una que
    #    debe caer por un trap de margen (TRAPCO), y una que debe caer por el
    #    gate de cobertura (NOCOVCO, spec §6.1/ADR 0006).
    _seed_damodaran_from_fixtures(conn)
    # GOODCO: márgenes estables al 30% (ROIC bien por encima de la WACC
    # sectorial ~9.3%, FCF yield 500M/5B = 10% > 8%).
    _seed_company_via_fmp_importer(
        conn,
        ticker="GOODCO",
        industry="Software",
        op_margins=[0.30, 0.30, 0.30, 0.30, 0.30, 0.30],
        market_cap=5_000_000_000.0,
        close=10.0,
    )
    # TRAPCO: mismo perfil salvo el margen operativo, que se contrae >200bps
    # en los últimos 3 años (26% -> 18%, i.e. -800bps) — el trap detector debe
    # excluirlo aunque su FCF yield y su ROIC (todavía > WACC) pasarían solos.
    _seed_company_via_fmp_importer(
        conn,
        ticker="TRAPCO",
        industry="Software",
        op_margins=[0.30, 0.28, 0.26, 0.24, 0.22, 0.18],
        market_cap=5_000_000_000.0,
        close=10.0,
    )
    # NOCOVCO: industria que no mapea a ningún sector Damodaran -> ninguna fila
    # de benchmark -> excluido por el gate de cobertura (ADR 0006), no por un
    # veredicto normal.
    _seed_company_via_fmp_importer(
        conn,
        ticker="NOCOVCO",
        industry="Unmapped Provider Sector",
        op_margins=[0.30, 0.30, 0.30, 0.30, 0.30, 0.30],
        market_cap=5_000_000_000.0,
        close=10.0,
    )
    conn.close()

    runner = CliRunner()

    # 2. Capa B por el CLI real.
    result = runner.invoke(app, ["screen", "--preset", "damodaran_value"], env=env)
    assert result.exit_code == 0, result.output
    screen_md = next(reports.rglob("screen/damodaran_value.md")).read_text()
    assert "GOODCO" in screen_md
    assert "TRAPCO" not in screen_md
    assert "Excluded (no sector benchmark, ADR 0006): 1" in screen_md

    # 3. La conexión de fases: analyze --from-screen sobre la misma DB.
    result = runner.invoke(app, ["analyze", "--from-screen"], env=env)
    assert result.exit_code == 0, result.output
    analysis_md = next(reports.rglob("analysis/GOODCO.md")).read_text()
    assert "margin of safety" in analysis_md.lower() or "Intrinsic" in result.output

    # 4. La DB compartida quedó con la historia completa.
    conn = connect(db_path)
    passed = conn.execute(
        "SELECT ticker FROM screener_candidates WHERE passed"
    ).fetchall()
    not_passed = conn.execute(
        "SELECT ticker FROM screener_candidates WHERE NOT passed"
    ).fetchall()
    refresh_rows = conn.execute("SELECT count(*) FROM refresh_log").fetchone()
    conn.close()

    assert ("GOODCO",) in passed
    assert len(passed) >= 1
    assert ("TRAPCO",) in not_passed
    assert len(not_passed) >= 1
    assert refresh_rows is not None and refresh_rows[0] >= 1
