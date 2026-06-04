import json

import pytest

from bot.utils.logging import configure_logging, get_logger


def test_configure_logging_produces_json(capsys):
    configure_logging(level="INFO", json_output=True)
    logger = get_logger("test")
    logger.info("hello", extra_field="value")
    captured = capsys.readouterr()
    payload = json.loads(captured.out.strip().splitlines()[-1])
    assert payload["event"] == "hello"
    assert payload["extra_field"] == "value"
    assert payload["level"] == "info"


def test_configure_logging_respects_level(capsys):
    configure_logging(level="WARNING", json_output=True)
    logger = get_logger("test")
    logger.info("should_not_appear")
    logger.warning("should_appear")
    captured = capsys.readouterr()
    assert "should_not_appear" not in captured.out
    assert "should_appear" in captured.out


def test_configure_logging_raises_for_invalid_level():
    with pytest.raises(ValueError, match="Unknown log level"):
        configure_logging(level="VERBOSE")
