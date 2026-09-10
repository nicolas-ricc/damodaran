"""Shared pytest fixtures.

``BOT_FMP_API_KEY`` is optional (default ``""``) — it's only required when
``BOT_DATA_PROVIDER=fmp``. Tests that exercise the FMP adapter still expect a
key to be present without threading it through every test, so we provide a
harmless default value for the whole suite. Tests that assert on the key
being absent simply ``delenv`` it.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _default_fmp_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide a default BOT_FMP_API_KEY so settings load in unrelated tests."""
    monkeypatch.setenv("BOT_FMP_API_KEY", "test-fmp-key")
