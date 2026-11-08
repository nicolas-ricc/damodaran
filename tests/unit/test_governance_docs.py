"""The status plan and the lesson describe the governance trap detector (#277, story #61)."""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from types import ModuleType
from typing import Any

from bot.screener.rules import registered_rules

_ROOT = Path(__file__).resolve().parents[2]
_PLANO = _ROOT / "docs" / "plano"
_SRC = _ROOT / "src" / "bot"
_LESSON = _ROOT / "docs" / "leccion" / "index.html"

_TRAPS_5 = (
    "traps-5",
    "Cinco de los seis trap detectors",
    "hecho",
    "screener/rules.py:529-804",
    "Ingresos, margen, accruals, dilución y gobernanza. El detector de gobernanza lee de "
    "filings_log los 8-K ítem 4.01 (cambio de auditor) y los avisos NT 10-K/10-Q de los "
    "últimos dos años, que el proveedor EDGAR guarda desde el índice de submissions; fuera "
    "de la región US no hay índice y el detector se saltea, y saltearse elimina (ADR 0006). "
    "El tope de dilución no implementa la excepción por adquisición justificada que pide el "
    "spec, y lo dice en su propio docstring.",
)
_REGISTRO = (
    "Los tres presets cargan y construyen sin error. qarp usa dieciséis reglas: "
    "omite EV/EBITDA sin comentarlo."
)
_MOTOR_TRAP = (
    "motor-trap",
    "La rama que elimina por trampa",
    "hecho",
    "screener/engine.py:779-787",
    "El test de motor que faltaba existe: run_screen rechaza una empresa sembrada con un "
    "aviso NT 10-K reciente y la deja en rejected con auditor_changes_and_late_filings "
    "entre sus reglas falladas (tests/unit/test_screener_engine.py).",
)
_TRAP_PARAGRAPH = (
    "<p>Tres aclaraciones sobre cómo leer esto. El ratio de Sloan mira cuánto de la ganancia "
    "declarada no se cobró en efectivo; si es mucho, las ganancias son de papel. La dilución "
    "cuenta el crecimiento promedio de acciones: una empresa que emite acciones todos los "
    "años le va regalando tu parte. Y el detector de gobernanza busca dos señales rojas ante "
    "la SEC: cambiar de auditor y pedir más tiempo para presentar un balance. Las dos quedan "
    "en el índice de presentaciones de la empresa, que solo existe para las que reportan en "
    "Estados Unidos; a una empresa de afuera el detector la saltea, y como saltearse "
    "elimina, queda descartada.</p>"
)


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"plano_gov_{name}", _PLANO / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _capa_b() -> list[tuple[Any, ...]]:
    items: list[tuple[Any, ...]] = _load("estado").INVENTARIO["capa-b"][2]
    return items


def _card(card_id: str) -> tuple[Any, ...]:
    matches = [c for c in _capa_b() if c[0] == card_id]
    assert len(matches) == 1, f"{card_id}: {len(matches)} cards"
    return matches[0]


def _cited_range(evidence: str, path: str) -> tuple[list[str], int, int]:
    match = re.fullmatch(rf"{re.escape(path)}:(\d+)(?:-(\d+))?", evidence)
    assert match is not None, f"{evidence!r} does not cite {path}"
    start = int(match.group(1))
    end = int(match.group(2) or start)
    lines = (_SRC / path).read_text("utf-8").splitlines()
    assert 1 <= start <= end <= len(lines), f"{evidence} out of bounds ({len(lines)} lines)"
    return lines, start, end


def test_capa_b_subtitle_counts_seventeen_rules() -> None:
    assert _load("estado").INVENTARIO["capa-b"][1] == "diecisiete reglas, cero subjetividad"


def test_traps_card_counts_five_of_six() -> None:
    assert _capa_b()[2] == _TRAPS_5


def test_traps_4_is_gone() -> None:
    ids = [c[0] for _, _, items in _load("estado").INVENTARIO.values() for c in items]
    assert "traps-4" not in ids


def test_registro_counts_sixteen_qarp_rules() -> None:
    assert _card("registro")[4] == _REGISTRO


def test_motor_trap_is_done() -> None:
    assert _card("motor-trap") == _MOTOR_TRAP


def test_traps_block_is_done() -> None:
    assert _load("estado").BLOQUES["traps"] == "hecho"


def test_registered_rules_are_seventeen() -> None:
    assert len(registered_rules()) == 17


def test_touched_cards_cite_real_lines() -> None:
    lines, start, end = _cited_range(_card("traps-5")[3], "screener/rules.py")
    assert lines[start - 1] == "@register"
    assert lines[start].startswith("class RevenueNotDeclining(")
    assert end == len(lines)
    cited = "\n".join(lines[start - 1 : end])
    for cls in (
        "OperatingMarginNotContracting",
        "SloanAccrualsBelow",
        "ShareCountNotDiluting",
        "AuditorChangesAndLateFilings",
    ):
        assert f"\nclass {cls}(" in cited

    lines, start, end = _cited_range(_card("motor-trap")[3], "screener/engine.py")
    assert lines[start - 1] == "    for detector in trap_detection:"
    assert lines[end - 1] == "            passed = False"
    defs = [i for i, ln in enumerate(lines[:start], 1) if ln.startswith("def ")]
    assert lines[defs[-1] - 1].startswith("def evaluate_company(")
    assert not any(ln.startswith("def ") for ln in lines[start - 1 : end])

    lines, start, _ = _cited_range(_card("registro")[3], "screener/config.py")
    assert lines[start - 1].startswith("def load_screener_config(")


def test_build_estado_says_seventeen_rules() -> None:
    text = (_PLANO / "build_estado.py").read_text("utf-8")
    assert "diecisiete reglas reales" in text
    assert "dieciséis reglas reales" not in text


def test_trap_paragraph_has_three_clarifications() -> None:
    text = _LESSON.read_text("utf-8")
    assert "Dos aclaraciones sobre cómo leer esto." not in text
    paragraphs = [
        ln.strip() for ln in text.splitlines() if ln.strip().startswith("<p>Tres aclaraciones")
    ]
    assert paragraphs == [_TRAP_PARAGRAPH]


def test_cuatro_motivos_stays() -> None:
    assert "aunque parezca barata por cuatro motivos" in _LESSON.read_text("utf-8")
