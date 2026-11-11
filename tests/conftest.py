"""Shared pytest fixtures.

``BOT_FMP_API_KEY`` is optional (default ``""``) — it's only required when
``BOT_DATA_PROVIDER=fmp``. Tests that exercise the FMP adapter still expect a
key to be present without threading it through every test, so we provide a
harmless default value for the whole suite. Tests that assert on the key
being absent simply ``delenv`` it. Recording FMP cassettes uses the exported
real key instead: see the session-scoped ``fmp_api_key`` fixture.

pytest-socket (``addopts`` in ``pyproject.toml``) refuses non-loopback
connections so the suite stays offline. Two exemptions lift the guard, by
adding the ``enable_socket`` marker at collection: ``live`` tests when
``BOT_LIVE_TESTS=1`` (otherwise they are skipped), and every test when
``--vcr-record`` names a recording mode other than ``none``. The guard
patches ``socket.connect`` in fixture setup and the test body only: child
processes, fixture finalizers and ``connect_ex`` are not covered.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from bot.reference import currencies, default_spreads
from tests.vcr_settings import DUMMY_FMP_KEY, record_option

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _default_fmp_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Provide a default BOT_FMP_API_KEY so settings load in unrelated tests."""
    monkeypatch.setenv("BOT_FMP_API_KEY", DUMMY_FMP_KEY)


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Lift the network guard for re-recording runs and opted-in ``live`` tests.

    ``live`` tests are skipped unless ``BOT_LIVE_TESTS=1``: the default run stays offline.
    """
    recording = record_option(config) not in (None, "none")
    live_enabled = os.environ.get("BOT_LIVE_TESTS") == "1"
    skip = pytest.mark.skip(reason="live test; set BOT_LIVE_TESTS=1 to run")
    for item in items:
        if recording:
            item.add_marker(pytest.mark.enable_socket)
        if item.get_closest_marker("live") is not None:
            item.add_marker(pytest.mark.enable_socket if live_enabled else skip)


@pytest.fixture(autouse=True)
def _currencies_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the CLI at the repo's currency file, whatever the CWD (#109)."""
    monkeypatch.setenv("BOT_CURRENCIES_PATH", str(REPO_ROOT / "config" / "currencies.yaml"))


@pytest.fixture(autouse=True)
def _config_defaults_on_repo_root(monkeypatch: pytest.MonkeyPatch) -> None:
    """Point the default currency and spread files at the repo's config, whatever the CWD."""
    monkeypatch.setattr(
        currencies, "DEFAULT_CURRENCIES_PATH", REPO_ROOT / "config" / "currencies.yaml"
    )
    monkeypatch.setattr(
        default_spreads, "DEFAULT_SPREADS_PATH", REPO_ROOT / "config" / "default_spreads.yaml"
    )


@pytest.fixture(autouse=True)
def _no_notifier(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pin `BOT_NOTIFIER=none` so a notifier in a developer's `.env` never fails `bot doctor` tests.

    `Settings` reads `.env` (`env_file=".env"`); real env vars win over it. Tests that need a
    channel set it, and its variables, themselves.
    """
    monkeypatch.setenv("BOT_NOTIFIER", "none")


@pytest.fixture(autouse=True)
def _no_flex_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Blank the IBKR Flex settings so `bot portfolio` tests never reach IBKR.

    The token expiry is blanked too: a past date in a developer's `.env` would fail `bot doctor`.
    """
    monkeypatch.setenv("BOT_IBKR_FLEX_TOKEN", "")
    monkeypatch.setenv("BOT_IBKR_FLEX_QUERY_ID", "")
    monkeypatch.setenv("BOT_IBKR_FLEX_TOKEN_EXPIRES", "")
