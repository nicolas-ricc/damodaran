"""Replay of the analyze model's broken rule OnlyTheCommandStopsTheBatch (#169).

TLC's shortest path: a ticker is chosen, its override file is picked, the company is
loaded and classified, then the override file is read and is not valid YAML. The
model says the command crashes; the rule says a failing ticker never stops the batch.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from bot.cli import app
from bot.storage.db import apply_schema, connect
from tests.unit.test_cli_analyze import _seed


def _run_batch(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[object, Path]:
    db_path = tmp_path / "bot.duckdb"
    reports_dir = tmp_path / "reports"
    assumptions_dir = tmp_path / "assumptions"
    assumptions_dir.mkdir()
    (assumptions_dir / "AAPL.yaml").write_text("revenue_growth: [0.1\n")
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_ASSUMPTIONS_DIR", str(assumptions_dir))
    conn = connect(db_path)
    apply_schema(conn)
    _seed(conn, "AAPL")
    _seed(conn, "MSFT")
    conn.close()
    result = CliRunner().invoke(app, ["analyze", "AAPL", "MSFT"])
    return result, reports_dir


def test_a_malformed_override_raises_out_of_the_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """What the code does today: the YAML error escapes and MSFT is never analysed."""
    result, reports_dir = _run_batch(tmp_path, monkeypatch)
    assert isinstance(result.exception, yaml.YAMLError)  # type: ignore[attr-defined]
    assert result.exit_code == 1  # type: ignore[attr-defined]
    assert not list(reports_dir.glob("*/analysis/MSFT.md"))


@pytest.mark.xfail(strict=True, reason="#180: a malformed override file stops the batch")
def test_a_malformed_override_leaves_the_batch_going(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The rule: the failing ticker exits with its code and the next one is analysed."""
    result, reports_dir = _run_batch(tmp_path, monkeypatch)
    assert result.exception is None or isinstance(result.exception, SystemExit)  # type: ignore[attr-defined]
    assert list(reports_dir.glob("*/analysis/MSFT.md"))
