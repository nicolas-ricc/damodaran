"""The written record of the dilution M&A exception (issue #280, story #62).

Presets, pipeline boards, lesson, plano card and estado entry say what
``ShareCountNotDiluting`` does: the share-growth cap lifts when cash paid for
acquisitions over the last ``ma_window`` fiscal years reaches ``ma_materiality``
of total assets.
"""

from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest
import yaml

from bot.screener.config import load_screener_config
from bot.screener.rules import ShareCountNotDiluting

_ROOT = Path(__file__).resolve().parents[2]
_PRESETS = _ROOT / "config" / "presets"
_PIPELINE = _ROOT / "docs" / "pipeline"
_PLANO = _ROOT / "docs" / "plano"
_LESSON = _ROOT / "docs" / "leccion" / "index.html"
_RULES = _ROOT / "src" / "bot" / "screener" / "rules.py"
_RULE = "share_count_not_diluting"


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(f"plano_{name}", _PLANO / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(_PLANO))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(_PLANO))
    return module


def _board(stem: str) -> str:
    return (_PIPELINE / f"{stem}.d2").read_text(encoding="utf-8")


def _rule_line(stem: str) -> str:
    lines = [ln for ln in _board(stem).splitlines() if ln.lstrip().startswith(f"{_RULE}:")]
    assert len(lines) == 1, lines
    return lines[0]


@pytest.mark.parametrize("preset", ["damodaran_value", "deep_value", "qarp"])
def test_presets_build_share_count_rule_with_ma_params(preset: str) -> None:
    path = _PRESETS / f"{preset}.yaml"
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    spec = next(r for r in raw["trap_detection"]["rules"] if r["name"] == _RULE)
    assert spec["params"] == {"max_annual_growth": 0.05, "ma_window": 3, "ma_materiality": 0.10}
    rules = [r for r in load_screener_config(path).trap_detection.build() if r.name == _RULE]
    assert len(rules) == 1
    rule = rules[0]
    assert isinstance(rule, ShareCountNotDiluting)
    assert rule.max_annual_growth == 0.05
    assert rule.ma_window == 3
    assert rule.ma_materiality == 0.10


def test_lesson_row_shows_ma_params() -> None:
    html = _LESSON.read_text(encoding="utf-8")
    assert f'data-param="{_RULE}.max_annual_growth" value="0.05"' in html
    assert f'data-param="{_RULE}.ma_window" value="3"' in html
    assert f'data-param="{_RULE}.ma_materiality" value="0.10"' in html


def test_screen_board_has_no_mergers_gap() -> None:
    board = _board("screen")
    assert "mergers:" not in board
    assert "exempts dilution" not in board


@pytest.mark.parametrize("stem", ["screen", "screen-traps"])
def test_boards_cite_ma_params(stem: str) -> None:
    line = _rule_line(stem)
    for directive in (
        f"@rule {_RULE}",
        f"@param {_RULE}.max_annual_growth",
        f"@param {_RULE}.ma_window",
        f"@param {_RULE}.ma_materiality",
    ):
        assert directive in line, directive
    if stem == "screen-traps":
        assert "@symbol bot.screener.rules._avg_growth_rate" in line
    label = line.split('"')[1]
    assert "acquisitions" in label
    assert "3 fiscal years" in label
    assert "10%" in label


def test_screen_traps_edge_count_unchanged() -> None:
    edges = [ln for ln in _board("screen-traps").splitlines()
             if "->" in ln.split("#", 1)[0]]
    assert len(edges) == 22


def test_snapshot_histories_list_acquisitions() -> None:
    assert "operating margin, acquisitions" in _board("screen")


def test_plano_card_describes_ma_exception() -> None:
    result = subprocess.run(
        [sys.executable, str(_PLANO / "build.py")], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr
    html = (_PLANO / "plano.html").read_text(encoding="utf-8")
    assert "adquisición material" in html
    assert "ma_window: 3" in html
    assert "ma_materiality: 0.10" in html


def test_estado_traps_entry_describes_ma_exception() -> None:
    estado = _load("estado")
    rows = {row[0]: row for _, _, items in estado.INVENTARIO.values() for row in items}
    _, _, _, evidence, note = rows["traps-4"]
    assert evidence == "screener/rules.py:528-760"
    assert "excepción por adquisición justificada del spec §6.4" in note
    assert "no implementa la excepción" not in note
    lines = _RULES.read_text(encoding="utf-8").splitlines()
    assert lines[527].startswith("class RevenueNotDeclining(")
    tail = lines[760:]
    assert re.match(r"\S", next((ln for ln in tail if ln.strip()), "end")), (
        "line 760 must close ShareCountNotDiluting, the last trap rule"
    )
    body = "\n".join(lines[527:760])
    assert "class ShareCountNotDiluting(" in body
