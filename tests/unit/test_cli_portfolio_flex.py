"""``bot portfolio`` needs the Flex credentials and reports a Flex failure (#256)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest
from typer.testing import CliRunner

import bot.cli
from bot.cli import app
from bot.ingest.ibkr_flex import FlexError
from bot.storage.db import apply_schema, connect


def _env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, *, token: str, query_id: str) -> Path:
    db_path = tmp_path / "bot.duckdb"
    reports_dir = tmp_path / "reports"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv(
        "BOT_PRESETS_DIR", str(Path(__file__).resolve().parents[2] / "config" / "presets")
    )
    monkeypatch.setenv("BOT_IBKR_FLEX_TOKEN", token)
    monkeypatch.setenv("BOT_IBKR_FLEX_QUERY_ID", query_id)
    conn = connect(db_path)
    apply_schema(conn)
    conn.close()
    return reports_dir


@pytest.mark.parametrize(
    ("token", "query_id"), [("", "123"), ("tok", ""), ("  ", "  ")]
)
def test_portfolio_requires_flex_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, token: str, query_id: str
) -> None:
    reports_dir = _env(tmp_path, monkeypatch, token=token, query_id=query_id)

    result = CliRunner().invoke(app, ["portfolio"])

    assert result.exit_code == 2
    assert "BOT_IBKR_FLEX_TOKEN" in result.output
    assert "BOT_IBKR_FLEX_QUERY_ID" in result.output
    assert not list(reports_dir.glob("*/*.md"))


class _FailingFlexClient:
    @classmethod
    def from_settings(cls, settings: object, **kwargs: object) -> _FailingFlexClient:
        return cls()

    def as_of(self) -> date:
        raise FlexError("1020 Invalid request or unable to validate request")


def test_portfolio_flex_failure_exits_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    reports_dir = _env(tmp_path, monkeypatch, token="tok", query_id="123")
    monkeypatch.setattr(bot.cli, "FlexPortfolioClient", _FailingFlexClient)

    result = CliRunner().invoke(app, ["portfolio"])

    assert result.exit_code == 1
    assert "IBKR Flex statement unavailable" in result.output
    assert "1020 Invalid request" in result.output
    assert not list(reports_dir.glob("*/*.md"))
