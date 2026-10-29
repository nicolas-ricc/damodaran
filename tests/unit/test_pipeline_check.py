"""docs/pipeline/check.py flags diagram citations that no longer match the repo (#145)."""

from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_CHECK = _ROOT / "docs" / "pipeline" / "check.py"


@pytest.fixture(scope="module")
def check() -> ModuleType:
    spec = importlib.util.spec_from_file_location("pipeline_check", _CHECK)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def idx(check: ModuleType) -> dict[str, tuple[str, int]]:
    return check.indice()


@pytest.fixture(scope="module")
def tables(check: ModuleType) -> set[str]:
    return check.tablas((_ROOT / "src" / "bot" / "storage" / "schema.sql").read_text())


def _board(folder: Path, text: str, *, stem: str = "pipeline", render: bool = True) -> Path:
    """Write one board (plus classes.d2) and, unless told not to, its SVG and a fresh hash."""
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "classes.d2").write_text("classes: {\n  step: {shape: rectangle}\n}\n")
    (folder / f"{stem}.d2").write_text(text)
    if render:
        (folder / f"{stem}.svg").write_text("<svg/>")
        digest = hashlib.sha256(
            b"".join(p.read_bytes() for p in sorted(folder.glob("*.d2")))
        ).hexdigest()
        (folder / "rendered.sha256").write_text(digest + "\n")
    return folder


# --------------------------------------------------------------------------- #
# The symbol index and the schema tables
# --------------------------------------------------------------------------- #


def test_index_resolves_modules_functions_classes_and_methods(idx: dict) -> None:
    assert idx["bot.cli"][0] == "src/bot/cli.py"
    assert idx["bot.cli.refresh"][0] == "src/bot/cli.py"
    assert idx["bot.screener.rules.MinMarketCap"][0] == "src/bot/screener/rules.py"
    assert "bot.screener.rules.MinMarketCap.evaluate" in idx
    assert "bot.notifier" in idx  # package __init__


def test_tablas_reads_every_create_table(check: ModuleType, tables: set[str]) -> None:
    assert len(tables) == 16
    assert {"prices_daily", "screener_candidates", "holding_marks"} <= tables
    sql = "CREATE TABLE IF NOT EXISTS a (\n x INT\n);\nCREATE TABLE IF NOT EXISTS b (y INT);\n"
    assert check.tablas(sql) == {"a", "b"}


# --------------------------------------------------------------------------- #
# Directive parsing
# --------------------------------------------------------------------------- #


def test_trailing_directive_pairs_with_its_line(check: ModuleType) -> None:
    text = 'a: "Refresh" {class: step}  # @symbol bot.cli.refresh\n'
    assert check.directives(text) == [
        check.Directive("symbol", "bot.cli.refresh", 'a: "Refresh" {class: step}', 1)
    ]


def test_directive_only_line_applies_to_next_code_line(check: ModuleType) -> None:
    text = "# @table prices_daily\n\n# plain comment\nprices_daily: {class: store}\n"
    assert check.directives(text) == [
        check.Directive("table", "prices_daily", "prices_daily: {class: store}", 4)
    ]


def test_several_directives_in_one_comment(check: ModuleType) -> None:
    text = 'v: "MoS 1.3 / 1.0"  # @const bot.web.views.MOS_UNDERVALUED @const bot.web.views.MOS_FAIR\n'
    found = check.directives(text)
    assert [(d.kind, d.argument) for d in found] == [
        ("const", "bot.web.views.MOS_UNDERVALUED"),
        ("const", "bot.web.views.MOS_FAIR"),
    ]
    assert {d.line for d in found} == {1}


def test_md_blocks_are_skipped(check: ModuleType) -> None:
    text = (
        "n: |md\n"
        "  # Heading @symbol bot.nowhere.Fake\n"
        "  text # @table not_a_table\n"
        "|\n"
        "b: x  # @file README.md\n"
    )
    assert [(d.kind, d.argument, d.line) for d in check.directives(text)] == [
        ("file", "README.md", 5)
    ]


def test_one_line_md_block_keeps_trailing_directive(check: ModuleType) -> None:
    text = "n: |md MoS # ≥ 1.3 | {class: note}  # @const bot.web.views.MOS_UNDERVALUED\n"
    (d,) = check.directives(text)
    assert d.kind == "const"
    assert "≥ 1.3" in d.text  # md content is visible text, its '#' is not a comment


def test_hash_inside_quotes_is_not_a_comment(check: ModuleType) -> None:
    text = 'a: "#1 step @symbol bot.fake" {style.fill: "#fff"}  # @file README.md\n'
    (d,) = check.directives(text)
    assert d == check.Directive(
        "file", "README.md", 'a: "#1 step @symbol bot.fake" {style.fill: "#fff"}', 1
    )


def test_every_kind_is_parsed(check: ModuleType) -> None:
    text = "".join(f"x{i}: y  # @{k} arg{i}\n" for i, k in enumerate(check.KINDS))
    assert [d.kind for d in check.directives(text)] == list(check.KINDS)
    assert set(check.KINDS) == {"symbol", "table", "file", "rule", "param", "const", "enum"}


def test_visible_drops_comments_keeps_md(check: ModuleType) -> None:
    text = 'a: "A"  # hidden SEC\nn: |md\n  shown EDGAR\n|\n'
    vis = check.visible(text)
    assert "hidden" not in vis and "SEC" not in vis
    assert "shown EDGAR" in vis


def test_links_outside_md_blocks(check: ModuleType) -> None:
    text = 'refresh: {\n  link: refresh.svg\n}\nn: |md\n  link: nope.svg\n|\nscreen.link: "screen.svg"\n'
    assert check.links(text) == [("refresh.svg", 2), ("screen.svg", 7)]


# --------------------------------------------------------------------------- #
# Renderings and "shown"
# --------------------------------------------------------------------------- #


def test_renderings_of_a_large_integral_float(check: ModuleType) -> None:
    assert {"100000000", "100,000,000", "100M"} <= check.renderings(100_000_000.0)


def test_renderings_of_fractions(check: ModuleType) -> None:
    assert {"0.08", "8%"} <= check.renderings(0.08)
    assert "-5%" in check.renderings(-0.05)
    assert {"1%", "100 bps"} <= check.renderings(0.01)
    assert {"0.5%"} <= check.renderings(0.005)
    assert {"4"} <= check.renderings(4)
    assert {"1.81"} <= check.renderings(1.81)


def test_renderings_of_tuples_and_strings(check: ModuleType) -> None:
    assert {"350", "380"} <= check.renderings((350, 380))
    assert check.renderings("US") == {"US"}


def test_shown(check: ModuleType) -> None:
    assert check.shown(1.3, "MoS ≥ 1.3  potentially undervalued")
    assert check.shown(-0.05, "growth > \u22125%")  # U+2212 minus maps to '-'
    assert check.shown(100_000_000.0, "market cap ≥ USD   100M")
    assert check.shown((350, 380), "annual = 350\u2013380 days")
    assert not check.shown((350, 380), "annual = 350 days")
    assert not check.shown(1.0, "potentially overvalued below the floor")


# --------------------------------------------------------------------------- #
# revisar(): each error kind on synthetic boards
# --------------------------------------------------------------------------- #


def test_clean_board_has_no_errors(
    check: ModuleType, idx: dict, tables: set[str], tmp_path: Path
) -> None:
    folder = _board(
        tmp_path,
        "...@classes\n"
        'r: "refresh" {class: step}  # @symbol bot.cli.refresh\n'
        "prices_daily: {class: store}  # @table prices_daily\n"
        'u: "universe" {class: step}  # @file src/bot/ingest/universe_default.csv\n',
    )
    errors, count = check.revisar(folder, idx, tables)
    assert errors == []
    assert count == 3


def test_unknown_symbol_is_an_error(
    check: ModuleType, idx: dict, tables: set[str], tmp_path: Path
) -> None:
    folder = _board(tmp_path, "a: x  # @symbol bot.cli.no_such_command\n")
    errors, _ = check.revisar(folder, idx, tables)
    assert errors == ["pipeline.d2:1 unknown @symbol bot.cli.no_such_command"]


def test_unknown_table_is_an_error(
    check: ModuleType, idx: dict, tables: set[str], tmp_path: Path
) -> None:
    folder = _board(tmp_path, "\n# @table no_such_table\nt: {class: store}\n")
    errors, _ = check.revisar(folder, idx, tables)
    assert errors == ["pipeline.d2:3 unknown @table no_such_table"]


def test_missing_file_is_an_error(
    check: ModuleType, idx: dict, tables: set[str], tmp_path: Path
) -> None:
    folder = _board(tmp_path, "f: x  # @file scripts/no_such_script.sh\n")
    errors, _ = check.revisar(folder, idx, tables)
    assert errors == ["pipeline.d2:1 missing @file scripts/no_such_script.sh"]


def test_missing_link_target_is_an_error(
    check: ModuleType, idx: dict, tables: set[str], tmp_path: Path
) -> None:
    folder = _board(tmp_path, "refresh: {\n  link: refresh.svg\n}\n")
    errors, _ = check.revisar(folder, idx, tables)
    assert errors == ["pipeline.d2:2 missing link target refresh.svg"]
    (folder / "refresh.svg").write_text("<svg/>")
    assert check.revisar(folder, idx, tables)[0] == []


def test_unknown_directive_kind_is_an_error(
    check: ModuleType, idx: dict, tables: set[str], tmp_path: Path
) -> None:
    folder = _board(tmp_path, "t: {class: store}  # @tabel prices_daily\n")
    errors, _ = check.revisar(folder, idx, tables)
    assert errors == ["pipeline.d2:1 unknown directive @tabel"]


def test_board_without_svg_is_an_error(
    check: ModuleType, idx: dict, tables: set[str], tmp_path: Path
) -> None:
    folder = _board(tmp_path, "a: x\n")
    (folder / "pipeline.svg").unlink()
    errors, _ = check.revisar(folder, idx, tables)
    assert errors == ["pipeline.d2 has no pipeline.svg"]


def test_stale_hash_is_an_error(
    check: ModuleType, idx: dict, tables: set[str], tmp_path: Path
) -> None:
    folder = _board(tmp_path, "a: x\n")
    (folder / "pipeline.d2").write_text("a: y\n")
    errors, _ = check.revisar(folder, idx, tables)
    assert errors == ["rendered.sha256 is stale: run docs/pipeline/build.sh"]


def test_missing_hash_is_an_error(
    check: ModuleType, idx: dict, tables: set[str], tmp_path: Path
) -> None:
    folder = _board(tmp_path, "a: x\n")
    (folder / "rendered.sha256").unlink()
    errors, _ = check.revisar(folder, idx, tables)
    assert errors == ["rendered.sha256 missing"]


def test_source_hash_covers_every_d2_sorted_by_name(check: ModuleType, tmp_path: Path) -> None:
    (tmp_path / "b.d2").write_text("B")
    (tmp_path / "a.d2").write_text("A")
    (tmp_path / "classes.d2").write_text("C")
    assert check.source_hash(tmp_path) == hashlib.sha256(b"ABC").hexdigest()
    assert [p.name for p in check.boards(tmp_path)] == ["a.d2", "b.d2"]


# --------------------------------------------------------------------------- #
# The CLI
# --------------------------------------------------------------------------- #


def test_main_exit_codes(
    check: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    good = _board(tmp_path / "good", "a: x  # @symbol bot.cli.refresh\n")
    assert check.main([str(good)]) == 0
    assert "check | 1 boards, 1 citations, 0 errors" in capsys.readouterr().out

    bad = _board(tmp_path / "bad", "a: x  # @table nope\n")
    assert check.main([str(bad)]) == 1
    out = capsys.readouterr().out
    assert "error  pipeline.d2:1 unknown @table nope" in out
    assert "1 errors" in out
