"""`bot site` runs with no environment at all (issue #92)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from bot.cli import app
from tests.web_sidecars import make_sidecar, write_sidecar


@pytest.fixture
def bare_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for key in list(os.environ):
        if key.startswith("BOT_"):
            monkeypatch.delenv(key)

    def boom(*_: object, **__: object) -> None:
        raise AssertionError("bot site must not load Settings")

    monkeypatch.setattr("bot.cli.load_settings", boom)
    monkeypatch.setattr("bot.cli._open_db", boom)


def test_site_builds_without_settings(tmp_path: Path, bare_env: None) -> None:
    reports = tmp_path / "reports"
    for ticker in ("AAA", "BBB", "CCC"):
        write_sidecar(reports, "2026-10-01", make_sidecar(ticker))
    out = tmp_path / "site"

    result = CliRunner().invoke(
        app, ["site", "--out", str(out), "--reports-dir", str(reports), "--base-url", "/"]
    )

    assert result.exit_code == 0, result.output
    assert "Built 3 companies" in result.output
    assert (out / "index.html").is_file()


def test_site_refuses_a_foreign_out_dir(tmp_path: Path, bare_env: None) -> None:
    out = tmp_path / "precious"
    out.mkdir()
    (out / "keep.txt").write_text("x")

    result = CliRunner().invoke(
        app, ["site", "--out", str(out), "--reports-dir", str(tmp_path / "reports")]
    )

    assert result.exit_code == 2
    assert (out / "keep.txt").exists()
