"""Replay of the analyze model's broken rule OnlyTheCommandStopsTheBatch (#169).

TLC's shortest path: a ticker is chosen, its override file is picked, the company is
loaded and classified, then the override file is read and is not valid YAML, or holds
a value float() refuses with a TypeError. The model says the command crashes; the rule
says a failing ticker never stops the batch.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from click.testing import Result
from typer.testing import CliRunner

from bot.cli import app
from bot.storage.db import apply_schema, connect
from tests.unit.test_cli_analyze import _seed

_MALFORMED = [
    pytest.param("revenue_growth: [0.1\n", yaml.YAMLError, id="not-yaml"),
    pytest.param("terminal_growth:\n", TypeError, id="empty-value"),
    pytest.param("tax_rate: [0.2]\n", TypeError, id="list-for-a-number"),
]


def _run_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, override: str
) -> tuple[Result, Path]:
    db_path = tmp_path / "bot.duckdb"
    reports_dir = tmp_path / "reports"
    assumptions_dir = tmp_path / "assumptions"
    assumptions_dir.mkdir()
    (assumptions_dir / "AAPL.yaml").write_text(override)
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


@pytest.mark.parametrize(("override", "error"), _MALFORMED)
def test_a_malformed_override_raises_out_of_the_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, override: str, error: type[Exception]
) -> None:
    """What the code does today (#180): the error escapes and MSFT is never analysed."""
    result, reports_dir = _run_batch(tmp_path, monkeypatch, override)
    assert isinstance(result.exception, error)
    assert result.exit_code == 1
    assert not list(reports_dir.glob("*/analysis/MSFT.md"))


@pytest.mark.xfail(strict=True, reason="#180: a malformed override file stops the batch")
@pytest.mark.parametrize(("override", "error"), _MALFORMED)
def test_a_malformed_override_leaves_the_batch_going(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, override: str, error: type[Exception]
) -> None:
    """The rule: the failing ticker exits with its code and the next one is analysed."""
    result, reports_dir = _run_batch(tmp_path, monkeypatch, override)
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert list(reports_dir.glob("*/analysis/MSFT.md"))
