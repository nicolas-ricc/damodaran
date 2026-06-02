"""CLI test for ``bot portfolio`` (M5, #29).

Monkeypatches the IBKR client with an in-memory fake so the command runs the
full sync -> diff -> report cycle without a live TWS socket, then asserts both
report artefacts are written under the dated directory.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

import bot.cli
from bot.cli import app
from bot.ingest.ibkr import CashBalance, PortfolioPosition
from bot.storage.db import apply_schema, connect


class _FakeIbkrClient:
    def __init__(self, *args: object, **kwargs: object) -> None:
        self._positions = [
            PortfolioPosition(
                account="DU1",
                con_id=1,
                symbol="AAPL",
                sec_type="STK",
                currency="USD",
                exchange="NASDAQ",
                quantity=100.0,
                avg_cost=120.0,
            ),
            PortfolioPosition(
                account="DU1",
                con_id=2,
                symbol="MSFT",
                sec_type="STK",
                currency="USD",
                exchange="NASDAQ",
                quantity=10.0,
                avg_cost=300.0,
            ),
        ]

    @classmethod
    def from_settings(cls, settings: object, **kwargs: object) -> _FakeIbkrClient:
        return cls()

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def accounts(self) -> list[str]:
        return ["DU1"]

    def positions(self, account_id: str) -> list[PortfolioPosition]:
        return list(self._positions)

    def cash_balances(self, account_id: str) -> list[CashBalance]:
        return [CashBalance(account="DU1", currency="USD", amount=5000.0)]


def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "bot.duckdb"
    reports_dir = tmp_path / "reports"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_FMP_API_KEY", "test-key")
    monkeypatch.setattr(bot.cli, "IbkrClient", _FakeIbkrClient)
    conn = connect(db_path)
    apply_schema(conn)
    conn.close()
    return reports_dir


def test_portfolio_writes_both_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reports_dir = _env(tmp_path, monkeypatch)

    runner = CliRunner()
    result = runner.invoke(app, ["portfolio"])
    assert result.exit_code == 0, result.stdout

    portfolio_reports = list(reports_dir.glob("*/portfolio.md"))
    alerts_reports = list(reports_dir.glob("*/alerts.md"))
    assert len(portfolio_reports) == 1
    assert len(alerts_reports) == 1

    body = portfolio_reports[0].read_text()
    assert "# Portfolio" in body
    assert "## Positions" in body
    assert "## Concentration" in body
    assert "AAPL" in body
    # The CLI echoes both paths.
    assert "portfolio.md" in result.stdout
    assert "alerts.md" in result.stdout


def test_portfolio_history_and_concentration_flags(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reports_dir = _env(tmp_path, monkeypatch)

    runner = CliRunner()
    result = runner.invoke(app, ["portfolio", "--history", "--concentration"])
    assert result.exit_code == 0, result.stdout

    body = next(reports_dir.glob("*/portfolio.md")).read_text()
    assert "## P&L history" in body
    assert "## Concentration breakdown" in body
