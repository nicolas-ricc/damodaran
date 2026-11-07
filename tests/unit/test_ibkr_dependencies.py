"""IBKR is read through the Flex Web Service only: no socket library (ADR 0010, #256)."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
_SOCKET_LIBRARIES = {"ib-async", "ibapi"}


def _locked_packages() -> set[str]:
    lock = tomllib.loads((ROOT / "uv.lock").read_text())
    return {pkg["name"] for pkg in lock["package"]}


def test_no_ibkr_socket_library_declared() -> None:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    declared = {
        re.sub(r"[-_.]+", "-", re.split(r"[^A-Za-z0-9._-]", dep)[0]).lower()
        for dep in project["dependencies"]
    }
    assert declared.isdisjoint(_SOCKET_LIBRARIES)


def test_no_ibkr_socket_library_locked() -> None:
    assert _locked_packages().isdisjoint(_SOCKET_LIBRARIES)
    assert "ib_async" not in (ROOT / "uv.lock").read_text()


def test_ib_async_not_mentioned_in_src() -> None:
    mentions = [
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "src").rglob("*")
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
        and "ib_async" in path.read_text(encoding="utf-8", errors="ignore")
    ]
    assert mentions == []
