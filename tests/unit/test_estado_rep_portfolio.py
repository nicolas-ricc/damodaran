"""The ``rep-portfolio`` card of the status plan describes ``portfolio.md`` (#354).

``portfolio.md`` gained a detected-events section (#352) and suggested reviews
derived from the day's derived events (#353). The card's note must say so, its
line pointer must still land on ``build_report``, and ``estado.html`` must be
regenerated from it.
"""

from __future__ import annotations

import html
import importlib.util
from functools import cache
from pathlib import Path
from types import ModuleType

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


def test_estado_html_carries_the_rep_portfolio_note() -> None:
    page = (_PLANO / "estado.html").read_text(encoding="utf-8")
    missing = [ln for ln in _estado().wrap(_card()[4], 108) if html.escape(ln) not in page]
    assert missing == []
