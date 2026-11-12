"""CLI test for ``bot portfolio`` (M5, #29).

Monkeypatches the Flex portfolio client with an in-memory fake so the command runs the
full sync -> diff -> report cycle without a live Flex download, then asserts both
report artefacts are written under the dated directory.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

import bot.cli
from bot.cli import app
from bot.ingest.ibkr import CashBalance, PortfolioPosition, TradeExecution
from bot.ingest.ibkr_flex import CorporateActionRecord
from bot.notifier import NotificationError
from bot.storage.db import apply_schema, connect


class _FakeFlexClient:
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
    def from_settings(cls, settings: object, **kwargs: object) -> _FakeFlexClient:
        return cls()

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def accounts(self) -> list[str]:
        return ["DU1"]

    def as_of(self) -> date:
        return date.today()

    def corporate_actions(self) -> list[CorporateActionRecord]:
        return []

    def positions(self, account_id: str) -> list[PortfolioPosition]:
        return list(self._positions)

    def cash_balances(self, account_id: str) -> list[CashBalance]:
        return [CashBalance(account="DU1", currency="USD", amount=5000.0)]

    def trades(
        self, account_id: str, since: datetime | None = None
    ) -> list[TradeExecution]:
        return [
            TradeExecution(
                account="DU1",
                exec_id="E1",
                con_id=1,
                symbol="AAPL",
                sec_type="STK",
                currency="USD",
                side="BOT",
                quantity=100.0,
                price=120.0,
                executed_at=datetime(2026, 6, 1, 14, 0, tzinfo=UTC),
                perm_id=1,
            )
        ]


def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "bot.duckdb"
    reports_dir = tmp_path / "reports"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_FMP_API_KEY", "test-key")
    monkeypatch.setenv(
        "BOT_PRESETS_DIR", str(Path(__file__).resolve().parents[2] / "config" / "presets")
    )
    monkeypatch.setenv("BOT_IBKR_FLEX_TOKEN", "tok")
    monkeypatch.setenv("BOT_IBKR_FLEX_QUERY_ID", "123")
    monkeypatch.setattr(bot.cli, "FlexPortfolioClient", _FakeFlexClient)
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


def test_portfolio_records_trades(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _env(tmp_path, monkeypatch)

    result = CliRunner().invoke(app, ["portfolio"])

    assert result.exit_code == 0, result.stdout
    assert "Recorded 1 new trade(s)" in result.stdout
    conn = connect(tmp_path / "bot.duckdb")
    assert conn.execute("SELECT exec_id FROM trades").fetchall() == [("E1",)]
    conn.close()


def test_portfolio_passes_preset_gates_including_trap_detection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _env(tmp_path, monkeypatch)
    captured: dict[str, object] = {}
    real_run_portfolio = bot.cli.run_portfolio

    def _spy(*args: Any, **kwargs: Any) -> Any:
        captured.update(kwargs)
        return real_run_portfolio(*args, **kwargs)

    monkeypatch.setattr(bot.cli, "run_portfolio", _spy)

    result = CliRunner().invoke(app, ["portfolio"])

    assert result.exit_code == 0, result.stdout
    gates = captured["quality_gates"]
    assert isinstance(gates, list)
    assert gates
    names = {g.name for g in gates}
    assert "roic_above_sector_wacc" in names
    assert "min_market_cap" in names


def test_portfolio_passes_loaded_broker_symbols(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _env(tmp_path, monkeypatch)
    overrides = tmp_path / "broker_symbols.yaml"
    overrides.write_text("BRK B: BRK-B\n")
    monkeypatch.setenv("BOT_BROKER_SYMBOLS_PATH", str(overrides))
    captured: dict[str, object] = {}
    real_run_portfolio = bot.cli.run_portfolio

    def _spy(*args: Any, **kwargs: Any) -> Any:
        captured.update(kwargs)
        return real_run_portfolio(*args, **kwargs)

    monkeypatch.setattr(bot.cli, "run_portfolio", _spy)

    result = CliRunner().invoke(app, ["portfolio"])

    assert result.exit_code == 0, result.stdout
    table = captured["symbol_overrides"]
    assert isinstance(table, Mapping)
    assert dict(table) == {"BRK B": "BRK-B"}


def test_portfolio_fails_when_preset_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _env(tmp_path, monkeypatch)
    monkeypatch.setenv("BOT_PRESETS_DIR", str(tmp_path / "nope"))

    result = CliRunner().invoke(app, ["portfolio"])

    assert result.exit_code == 2
    assert "Screener config not found" in result.output


class _RecordingNotifier:
    def __init__(self) -> None:
        self.sent: list[str] = []

    def send(self, text: str) -> None:
        self.sent.append(text)


def test_portfolio_sends_alerts_when_notifier_configured(tmp_path, monkeypatch) -> None:
    reports_dir = _env(tmp_path, monkeypatch)
    rec = _RecordingNotifier()
    monkeypatch.setattr(bot.cli, "build_notifier", lambda settings: rec)

    result = CliRunner().invoke(app, ["portfolio"])

    assert result.exit_code == 0, result.output
    alerts = next(reports_dir.glob("*/alerts.md")).read_text()
    assert rec.sent == [alerts]
    assert "Sent alerts via" in result.stdout


def test_portfolio_default_notifier_sends_nothing(tmp_path, monkeypatch) -> None:
    _env(tmp_path, monkeypatch)
    monkeypatch.setenv("BOT_NOTIFIER", "none")  # process env beats a developer's .env

    result = CliRunner().invoke(app, ["portfolio"])

    assert result.exit_code == 0, result.output
    assert "Sent alerts" not in result.stdout


def test_portfolio_skips_empty_alerts(tmp_path, monkeypatch) -> None:
    _env(tmp_path, monkeypatch)
    rec = _RecordingNotifier()
    monkeypatch.setattr(bot.cli, "build_notifier", lambda settings: rec)
    real_run_portfolio = bot.cli.run_portfolio

    def _quiet_day(*args: Any, **kwargs: Any) -> Any:
        result = real_run_portfolio(*args, **kwargs)
        result.alerts_path.write_text("")  # what run_portfolio writes on a day with no events
        return result

    monkeypatch.setattr(bot.cli, "run_portfolio", _quiet_day)

    result = CliRunner().invoke(app, ["portfolio"])

    assert result.exit_code == 0, result.output
    assert rec.sent == []
    assert "Sent alerts" not in result.stdout


def test_portfolio_misconfigured_notifier_fails_before_sync(tmp_path, monkeypatch) -> None:
    reports_dir = _env(tmp_path, monkeypatch)
    monkeypatch.setenv("BOT_NOTIFIER", "telegram")
    monkeypatch.setenv("BOT_TELEGRAM_BOT_TOKEN", "")  # empty env beats a developer's .env
    monkeypatch.setenv("BOT_TELEGRAM_CHAT_ID", "")

    result = CliRunner().invoke(app, ["portfolio"])

    assert result.exit_code == 2
    assert "Notifier misconfigured" in result.output
    assert "BOT_TELEGRAM_BOT_TOKEN" in result.output
    assert not list(reports_dir.glob("*/*.md"))


def test_portfolio_send_failure_exits_1_and_keeps_reports(tmp_path, monkeypatch) -> None:
    reports_dir = _env(tmp_path, monkeypatch)

    class _Failing:
        def send(self, text: str) -> None:
            raise NotificationError("Telegram sendMessage HTTP 400: chat not found")

    monkeypatch.setattr(bot.cli, "build_notifier", lambda settings: _Failing())

    result = CliRunner().invoke(app, ["portfolio"])

    assert result.exit_code == 1
    assert "Alerts not sent: Telegram sendMessage HTTP 400: chat not found" in result.output
    assert len(list(reports_dir.glob("*/alerts.md"))) == 1
