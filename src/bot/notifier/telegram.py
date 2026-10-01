"""Telegram Bot API notifier backend."""

from __future__ import annotations

import httpx

from bot.notifier.base import NotificationError

API_BASE = "https://api.telegram.org"
MAX_MESSAGE_LEN = 4096
"""Telegram's per-message limit, in UTF-16 code units."""


def _units(text: str) -> int:
    return sum(2 if ord(c) > 0xFFFF else 1 for c in text)


def split_message(text: str, limit: int = MAX_MESSAGE_LEN) -> list[str]:
    """Split ``text`` into chunks of at most ``limit`` UTF-16 code units.

    Breaks at line boundaries; a line longer than ``limit`` is cut by character so a
    surrogate pair is never split. ``"".join(chunks) == text``.
    """
    chunks: list[str] = []
    current = ""
    current_len = 0
    for line in text.splitlines(keepends=True):
        line_len = _units(line)
        if current and current_len + line_len > limit:
            chunks.append(current)
            current, current_len = "", 0
        if line_len <= limit:
            current += line
            current_len += line_len
            continue
        piece, piece_len = "", 0
        for ch in line:
            width = 2 if ord(ch) > 0xFFFF else 1
            if piece_len + width > limit:
                chunks.append(piece)
                piece, piece_len = "", 0
            piece += ch
            piece_len += width
        current, current_len = piece, piece_len
    if current:
        chunks.append(current)
    return chunks


class TelegramNotifier:
    """Sends the alerts text to a Telegram chat."""

    def __init__(
        self,
        *,
        bot_token: str,
        chat_id: str,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._bot_token = bot_token
        self.chat_id = chat_id
        self._transport = transport
        self._timeout = timeout

    def send(self, text: str) -> None:
        try:
            with httpx.Client(
                base_url=API_BASE, transport=self._transport, timeout=self._timeout
            ) as client:
                for chunk in split_message(text):
                    response = client.post(
                        f"/bot{self._bot_token}/sendMessage",
                        json={
                            "chat_id": self.chat_id,
                            "text": chunk,
                            "disable_web_page_preview": True,
                        },
                    )
                    if not response.is_success:
                        raise NotificationError(
                            f"Telegram sendMessage HTTP {response.status_code}: "
                            f"{_description(response)}"
                        )
        except httpx.HTTPError as exc:
            raise NotificationError(f"Telegram request failed: {type(exc).__name__}") from None


def _description(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return "no description"
    description = body.get("description") if isinstance(body, dict) else None
    return str(description) if description else "no description"
