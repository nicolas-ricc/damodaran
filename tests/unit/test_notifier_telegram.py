import json
import logging

import httpx
import pytest

from bot.notifier import NotificationError
from bot.notifier.telegram import MAX_MESSAGE_LEN, TelegramNotifier, split_message
from bot.utils.logging import configure_logging

TOKEN = "123456:SECRET-token"


def _notifier(handler) -> TelegramNotifier:
    return TelegramNotifier(bot_token=TOKEN, chat_id="-100", transport=httpx.MockTransport(handler))


def test_send_posts_plain_text_to_send_message() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"ok": True, "result": {}})

    text = "# Alerts — 2026-06-01\n\n| Type | Ticker |\n| position_opened | AAPL |\n"
    _notifier(handler).send(text)

    assert len(seen) == 1
    req = seen[0]
    assert req.method == "POST"
    assert str(req.url) == f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    body = json.loads(req.content)
    assert body["chat_id"] == "-100"
    assert body["text"] == text
    assert "parse_mode" not in body


def test_long_text_is_split_into_ordered_messages() -> None:
    texts: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        texts.append(json.loads(request.content)["text"])
        return httpx.Response(200, json={"ok": True, "result": {}})

    lines = [f"| position_opened | T{i:04d} | {'x' * 60} |" for i in range(200)]
    text = "\n".join(lines) + "\n"
    _notifier(handler).send(text)

    assert len(texts) > 1
    assert all(len(t.encode("utf-16-le")) // 2 <= MAX_MESSAGE_LEN for t in texts)
    assert "".join(texts) == text


def test_split_message_hard_splits_an_overlong_line() -> None:
    chunks = split_message("a" * 10 + "\n", limit=4)
    assert chunks == ["aaaa", "aaaa", "aa\n"]


def test_split_message_counts_utf16_units() -> None:
    # "😀" is two UTF-16 code units: three of them do not fit in a 4-unit chunk.
    assert split_message("😀😀😀", limit=4) == ["😀😀", "😀"]


def test_api_error_raises_without_leaking_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"ok": False, "description": "Bad Request: chat not found"})

    with pytest.raises(NotificationError) as exc:
        _notifier(handler).send("hello")
    assert "chat not found" in str(exc.value)
    assert TOKEN not in str(exc.value)
    assert exc.value.__cause__ is None or TOKEN not in str(exc.value.__cause__)


def test_transport_error_raises_without_leaking_token() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with pytest.raises(NotificationError) as exc:
        _notifier(handler).send("hello")
    assert TOKEN not in str(exc.value)


def test_send_does_not_log_token_through_httpx(caplog: pytest.LogCaptureFixture) -> None:
    configure_logging("INFO")
    caplog.set_level(logging.INFO)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True, "result": {}})

    _notifier(handler).send("hello")
    assert TOKEN not in caplog.text


def test_malformed_token_raises_without_leaking_token() -> None:
    bad = "12 3\n:SECRET"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    notifier = TelegramNotifier(bot_token=bad, chat_id="-100", transport=httpx.MockTransport(handler))
    with pytest.raises(NotificationError) as exc:
        notifier.send("hello")
    assert "SECRET" not in str(exc.value)
