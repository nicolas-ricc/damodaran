"""The ``live`` marker: skipped at collection unless BOT_LIVE_TESTS=1."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest_plugins = ["pytester"]

# Copied into the pytester sandbox, so it must not import from ``tests``.
_ROOT_CONFTEST = Path(__file__).parent.parent / "conftest.py"

_LIVE_TEST = """
import pytest

@pytest.mark.live
def test_hits_the_network():
    assert True
"""


def _run(pytester: pytest.Pytester) -> pytest.RunResult:
    pytester.makeconftest(_ROOT_CONFTEST.read_text())
    pytester.makeini("[pytest]\naddopts = --strict-markers\nmarkers =\n    live: x\n")
    pytester.makepyfile(_LIVE_TEST)
    return pytester.runpytest("-q")


def test_live_tests_are_skipped_by_default(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("BOT_LIVE_TESTS", raising=False)
    _run(pytester).assert_outcomes(skipped=1)


def test_live_tests_run_when_opted_in(
    pytester: pytest.Pytester, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("BOT_LIVE_TESTS", "1")
    _run(pytester).assert_outcomes(passed=1)


def test_live_marker_is_registered(pytestconfig: pytest.Config) -> None:
    markers = pytestconfig.getini("markers")
    assert any(m.startswith("live:") for m in markers)
