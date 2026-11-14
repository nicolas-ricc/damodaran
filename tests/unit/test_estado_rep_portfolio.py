"""The ``rep-portfolio`` card of the status plan describes ``portfolio.md`` (#354).

``portfolio.md`` gained a detected-events section (#352) and suggested reviews
derived from the day's derived events (#353). The card's note must say so, its
line pointer must still land on ``build_report``, and the page rendered from it
(``estado.html`` is git-ignored, so the test renders it into a temp dir) must
carry it.
"""

from __future__ import annotations

import html
import importlib.util
import sys
from functools import cache
from pathlib import Path
from types import ModuleType

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_PLANO = _ROOT / "docs" / "plano"


@cache
def _estado() -> ModuleType:
    spec = importlib.util.spec_from_file_location("plano_estado", _PLANO / "estado.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _card() -> tuple[str, str, str, str, str]:
    for _, _, cards in _estado().INVENTARIO.values():
        for card in cards:
            if card[0] == "rep-portfolio":
                return card
    raise AssertionError("no rep-portfolio card")


def test_rep_portfolio_describes_detected_events_and_reviews() -> None:
    note = _card()[4]
    missing = [
        p
        for p in [
            "eventos detectados",
            "misma tabla que alerts.md",
            "nuevo filing",
            "valor intrínseco",
            "bandera roja",
            "compuerta de calidad",
            "sector recalibrado",
            "nunca sugieren una revisión",
        ]
        if p not in note
    ]
    assert missing == []


def test_rep_portfolio_points_at_build_report() -> None:
    path, _, line = _card()[3].partition(":")
    assert path == "portfolio/report.py"
    source = (_ROOT / "src" / "bot" / path).read_text(encoding="utf-8").splitlines()
    assert source[int(line) - 1].startswith("def build_report(")


@pytest.fixture(scope="module")
def _build_estado() -> ModuleType:
    """Load build_estado once, undoing the sys.path entry and bare imports it adds."""
    path, modules = list(sys.path), set(sys.modules)
    spec = importlib.util.spec_from_file_location("plano_build_estado", _PLANO / "build_estado.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = path
        for name in set(sys.modules) - modules:
            del sys.modules[name]
    return module


def test_estado_html_carries_the_rep_portfolio_note(
    _build_estado: ModuleType, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(_build_estado, "AQUI", tmp_path)
    _build_estado.main()
    page = (tmp_path / "estado.html").read_text(encoding="utf-8")
    note = next(
        card[4]
        for _, _, cards in _build_estado.estado.INVENTARIO.values()
        for card in cards
        if card[0] == "rep-portfolio"
    )
    missing = [ln for ln in _build_estado.estado.wrap(note, 108) if html.escape(ln) not in page]
    assert missing == []
