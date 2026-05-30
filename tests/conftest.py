"""Shared pytest fixtures.

``BOT_FMP_API_KEY`` is a *required* setting (no default) as of M2. To keep the
pre-existing M1 tests — which only care about SEC/Damodaran — green without
threading the key through every test, we provide a harmless default value for
the whole suite. Tests that assert on the key being absent simply ``delenv`` it.
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _default_fmp_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide a default BOT_FMP_API_KEY so settings load in unrelated tests."""
    monkeypatch.setenv("BOT_FMP_API_KEY", "test-fmp-key")
