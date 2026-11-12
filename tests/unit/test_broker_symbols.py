"""The broker symbol -> universe ticker override table (#338, #84).

``config/broker_symbols.yaml`` maps an IBKR symbol to the universe ticker it
should join on, or to ``~`` for a holding deliberately outside the universe.
The loader degrades to an empty table on a missing or malformed file and never
raises.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from structlog.testing import capture_logs

from bot.config import Settings
from bot.reference import broker_symbols
from bot.reference.broker_symbols import load_broker_symbols

REPO_FILE = Path(__file__).resolve().parents[2] / "config" / "broker_symbols.yaml"


def _write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "broker_symbols.yaml"
    path.write_text(text)
    return path


@pytest.mark.parametrize("text", ["brk b: brk-b\n", " BRK B : BRK-B \n"])
def test_loads_and_normalises_a_mapping(tmp_path: Path, text: str) -> None:
    assert dict(load_broker_symbols(_write(tmp_path, text))) == {"BRK B": "BRK-B"}


def test_null_value_marks_ignored(tmp_path: Path) -> None:
    assert dict(load_broker_symbols(_write(tmp_path, "SPY: ~\n"))) == {"SPY": None}


def test_missing_file_warns_and_is_empty(tmp_path: Path) -> None:
    with capture_logs() as logs:
        table = load_broker_symbols(tmp_path / "absent.yaml")
    assert dict(table) == {}
    assert [e["event"] for e in logs].count("broker_symbols.absent") == 1


def test_comments_only_file_is_empty_without_warning(tmp_path: Path) -> None:
    with capture_logs() as logs:
        table = load_broker_symbols(_write(tmp_path, "# nothing\n"))
    assert dict(table) == {}
    assert [e for e in logs if e["log_level"] == "warning"] == []


@pytest.mark.parametrize(
    "text",
    [
        "- BRK B\n",
        "123: AAPL\n",
        "FOO: ''\n",
        "FOO: '  '\n",
        "'  ': BAR\n",
        "FOO: 12\n",
        "FOO: BAR\nFOO: BAZ\n",
        "brk b: X\nBRK B: Y\n",
        "ON: ON-X\n",
        "FOO: [unclosed\n",
    ],
    ids=[
        "not-a-mapping",
        "non-string-key",
        "empty-value",
        "blank-value",
        "blank-key",
        "non-string-value",
        "duplicate",
        "duplicate-after-normalisation",
        "boolean-key",
        "unparsable",
    ],
)
def test_malformed_file_warns_and_is_empty(tmp_path: Path, text: str) -> None:
    with capture_logs() as logs:
        table = load_broker_symbols(_write(tmp_path, text))
    assert dict(table) == {}
    assert "broker_symbols.malformed" in [e["event"] for e in logs]


def test_quoted_boolean_like_symbol_loads(tmp_path: Path) -> None:
    assert dict(load_broker_symbols(_write(tmp_path, '"ON": "ON-X"\n'))) == {"ON": "ON-X"}


def test_unreadable_path_warns_and_is_empty(tmp_path: Path) -> None:
    with capture_logs() as logs:
        table = load_broker_symbols(tmp_path)  # a directory, not a file
    assert dict(table) == {}
    assert [e for e in logs if e["log_level"] == "warning"]


def test_table_is_immutable(tmp_path: Path) -> None:
    table = load_broker_symbols(_write(tmp_path, "FOO: BAR\n"))
    with pytest.raises(TypeError):
        table["X"] = "Y"  # type: ignore[index]


def test_repo_file_is_comments_only() -> None:
    assert dict(load_broker_symbols(REPO_FILE)) == {}
    text = REPO_FILE.read_text()
    assert "BRK B" in text
    assert "~" in text


def test_settings_broker_symbols_path_default_and_override(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "test test@example.com")
    monkeypatch.delenv("BOT_BROKER_SYMBOLS_PATH", raising=False)
    assert Settings(_env_file=None).broker_symbols_path == Path("./config/broker_symbols.yaml")  # type: ignore[call-arg]
    monkeypatch.setenv("BOT_BROKER_SYMBOLS_PATH", str(tmp_path / "x.yaml"))
    assert Settings(_env_file=None).broker_symbols_path == tmp_path / "x.yaml"  # type: ignore[call-arg]


def test_default_path_is_used_when_none(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        broker_symbols, "DEFAULT_BROKER_SYMBOLS_PATH", _write(tmp_path, "FOO: BAR\n")
    )
    assert dict(load_broker_symbols()) == {"FOO": "BAR"}
