"""Unregistered markers fail collection under the repo's pytest config (#112)."""

from __future__ import annotations

import shlex
import tomllib
from pathlib import Path
from typing import Any

import pytest
from packaging.requirements import Requirement

pytest_plugins = ["pytester"]

_PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def _pyproject() -> dict[str, Any]:
    return tomllib.loads(_PYPROJECT.read_text())


def _ini_options() -> dict[str, Any]:
    options: dict[str, Any] = _pyproject()["tool"]["pytest"]["ini_options"]
    return options


def _run(pytester: pytest.Pytester, marker: str) -> pytest.RunResult:
    # The whole repo pyproject.toml: an ini key that needs repo files will break this sandbox.
    pytester.makepyprojecttoml(_PYPROJECT.read_text())
    pytester.makepyfile(
        test_bogus=f"import pytest\n\n@pytest.mark.{marker}\ndef test_marked():\n    pass\n"
    )
    return pytester.runpytest("test_bogus.py")


def test_unregistered_marker_fails_collection(pytester: pytest.Pytester) -> None:
    result = _run(pytester, "bogus")
    assert result.ret == pytest.ExitCode.INTERRUPTED
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*'bogus' not found in `markers` configuration option*"])


def test_registered_marker_still_collects(pytester: pytest.Pytester) -> None:
    result = _run(pytester, "integration")
    result.assert_outcomes(passed=1)
    assert "PytestUnknownMarkWarning" not in result.stdout.str()


def test_strict_markers_ini_key_is_set() -> None:
    options = _ini_options()
    assert options["strict_markers"] is True
    assert "strict" not in options


def test_addopts_has_no_strict_marker_flag() -> None:
    addopts = _ini_options()["addopts"]
    tokens = shlex.split(addopts) if isinstance(addopts, str) else addopts
    assert "--strict-markers" not in tokens
    assert "--strict" not in tokens


def test_pytest_floor_is_9() -> None:
    (spec,) = [
        req
        for req in map(Requirement, _pyproject()["dependency-groups"]["dev"])
        if req.name == "pytest"
    ]
    assert not spec.specifier.contains("8.4.2")
    assert spec.specifier.contains(pytest.__version__)
