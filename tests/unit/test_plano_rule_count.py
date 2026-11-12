"""The architecture plan counts the screener's seventeen rules (#286)."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from bot.screener.rules import registered_rules

_ROOT = Path(__file__).resolve().parents[2]
_PLANO = _ROOT / "docs" / "plano"
_STALE = re.compile(r"diecis[eé]is|sixteen|16 reglas", re.IGNORECASE)
_QARP = "qarp usa dieciséis reglas: omite EV/EBITDA sin comentarlo."


def _tracked_sources() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "docs/plano"], cwd=_ROOT, capture_output=True, text=True, check=True
    ).stdout
    return [p for p in out.splitlines() if not p.startswith("docs/plano/fonts/")]


def test_registry_has_seventeen_rules() -> None:
    assert len(registered_rules()) == 17


def test_plano_sources_only_qarp_says_sixteen() -> None:
    hits = [
        (path, line.strip())
        for path in _tracked_sources()
        for line in (_ROOT / path).read_text("utf-8").splitlines()
        if _STALE.search(line)
    ]
    assert [path for path, _ in hits] == ["docs/plano/estado.py"], hits
    assert _QARP in hits[0][1]


@pytest.mark.parametrize(
    ("name", "phrase"),
    [
        ("build.py", '"diecisiete reglas, cero subjetividad"'),
        ("part-body.html", "Un embudo de cuatro etapas y diecisiete reglas"),
        ("part-data.js", "Cuatro etapas, diecisiete reglas, cero subjetividad."),
        ("part-meta.js", "Las diecisiete reglas del screener"),
        ("iso.py", ">17 reglas</text>"),
    ],
)
def test_plano_sources_say_seventeen(name: str, phrase: str) -> None:
    assert phrase in (_PLANO / name).read_text("utf-8")


def _build(script: str, output: str) -> str:
    result = subprocess.run(
        [sys.executable, str(_PLANO / script)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return (_PLANO / output).read_text(encoding="utf-8")


def test_build_plano_says_seventeen() -> None:
    html = _build("build.py", "plano.html")
    assert "diecisiete reglas, cero subjetividad" in html
    assert "Las diecisiete reglas del screener" in html
    assert ">17 reglas</text>" in html
    assert "dieciséis reglas, cero subjetividad" not in html


def test_build_estado_runs() -> None:
    assert ">17 reglas</text>" in _build("build_estado.py", "estado.html")


def test_part_meta_counts_no_other_rules() -> None:
    text = (_PLANO / "part-meta.js").read_text("utf-8")
    assert "sin las demás. Por eso" in text
    assert "otras quince" not in text
