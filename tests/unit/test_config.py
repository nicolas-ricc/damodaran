from pathlib import Path

import pytest

from bot.config import Settings


def test_settings_loads_from_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "test.duckdb"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Test User test@example.com")
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("BOT_LOG_LEVEL", "DEBUG")

    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.db_path == tmp_path / "test.duckdb"
    assert s.sec_user_agent == "Test User test@example.com"
    assert s.reports_dir == tmp_path / "reports"
    assert s.log_level == "DEBUG"


def test_settings_requires_sec_user_agent(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("BOT_SEC_USER_AGENT", raising=False)
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "test.duckdb"))
    with pytest.raises(Exception) as exc:
        Settings(_env_file=None)  # type: ignore[call-arg]
    assert "sec_user_agent" in str(exc.value).lower()


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "X Y x@y.com")
    monkeypatch.setenv("BOT_DB_PATH", str(tmp_path / "x.duckdb"))
    monkeypatch.delenv("BOT_LOG_LEVEL", raising=False)
    monkeypatch.delenv("BOT_REPORTS_DIR", raising=False)
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.log_level == "INFO"
    assert isinstance(s.reports_dir, Path)
