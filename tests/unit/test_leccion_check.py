"""docs/leccion/check.py flags lesson citations that no longer match src/bot/ (#120)."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_CHECK = _ROOT / "docs" / "leccion" / "check.py"


@pytest.fixture(scope="module")
def check() -> ModuleType:
    spec = importlib.util.spec_from_file_location("leccion_check", _CHECK)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def idx(check: ModuleType) -> dict[str, tuple[str, int]]:
    return check.indice()


def test_index_resolves_modules_functions_classes_and_methods(idx: dict) -> None:
    assert idx["bot.screener.rules"][0] == "src/bot/screener/rules.py"
    assert idx["bot.screener.rules.MinMarketCap"][0] == "src/bot/screener/rules.py"
    assert idx["bot.valuator.dcf.dcf"][0] == "src/bot/valuator/dcf.py"
    assert "bot.screener.rules.MinMarketCap.evaluate" in idx
    assert "bot.ingest" in idx  # package __init__


def test_citas_pairs_symbol_with_following_location(check: ModuleType) -> None:
    html = (
        '<code data-symbol="bot.valuator.dcf.dcf">bot.valuator.dcf.dcf</code> · '
        '<code class="at">src/bot/valuator/dcf.py:159</code>'
        '<code data-symbol="bot.storage.db">bot.storage.db</code>'
    )
    assert check.citas(html) == [
        ("bot.valuator.dcf.dcf", "src/bot/valuator/dcf.py", 159),
        ("bot.storage.db", None, None),
    ]


def test_missing_symbol_is_an_error(check: ModuleType, idx: dict) -> None:
    html = '<code data-symbol="bot.screener.rules.NoSuchRule">x</code>'
    errores, avisos = check.revisar(html, idx)
    assert errores == ["falta: bot.screener.rules.NoSuchRule"]
    assert avisos == []


def test_wrong_file_is_an_error(check: ModuleType, idx: dict) -> None:
    html = (
        '<code data-symbol="bot.valuator.dcf.dcf">x</code> '
        '<code class="at">src/bot/valuator/sensitivity.py:1</code>'
    )
    errores, _ = check.revisar(html, idx)
    assert len(errores) == 1 and errores[0].startswith("archivo: bot.valuator.dcf.dcf")


def test_moved_line_is_only_a_warning(check: ModuleType, idx: dict) -> None:
    _, real = idx["bot.valuator.dcf.dcf"]
    html = (
        '<code data-symbol="bot.valuator.dcf.dcf">x</code> '
        f'<code class="at">src/bot/valuator/dcf.py:{real + 7}</code>'
    )
    errores, avisos = check.revisar(html, idx)
    assert errores == []
    assert avisos == [
        f"línea movida: bot.valuator.dcf.dcf citado en src/bot/valuator/dcf.py:{real + 7}, "
        f"ahora src/bot/valuator/dcf.py:{real}"
    ]


def test_main_exit_codes(check: ModuleType, tmp_path: Path) -> None:
    good = tmp_path / "good.html"
    good.write_text('<code data-symbol="bot.storage.db">bot.storage.db</code>', encoding="utf-8")
    bad = tmp_path / "bad.html"
    bad.write_text('<code data-symbol="bot.nope.Nada">x</code>', encoding="utf-8")
    assert check.main([str(good)]) == 0
    assert check.main([str(bad)]) == 1
