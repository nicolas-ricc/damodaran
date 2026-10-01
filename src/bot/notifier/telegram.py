"""Telegram Bot API notifier backend."""

from __future__ import annotations

import httpx


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
        raise NotImplementedError
