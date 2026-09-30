"""The IBKR client speaks the TWS wire protocol through ib_async only (ADR 0004)."""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _locked_packages() -> set[str]:
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    return {pkg["name"] for pkg in lock["package"]}


def test_ib_async_is_a_declared_dependency() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    assert any(dep.startswith("ib-async") for dep in project["dependencies"])


def test_ibapi_is_not_locked() -> None:
    assert "ib-async" in _locked_packages()
    assert "ibapi" not in _locked_packages()
