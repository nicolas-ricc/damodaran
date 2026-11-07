"""The viewer's local script and the htmx wiring it relies on (issue #92)."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

_WEB = Path(__file__).resolve().parents[2] / "src" / "bot" / "web"
_SCRIPT = _WEB / "static" / "viewer.js"


def test_viewer_script_is_local_and_loaded() -> None:
    script = (_WEB / "static" / "viewer.js").read_text()
    assert not re.search(r"https?://", script)
    assert "static/viewer.js" in (_WEB / "templates" / "base.html").read_text()


def test_rows_do_not_gate_the_click_in_the_template() -> None:
    assert "matchMedia" not in (_WEB / "templates" / "_rows.html").read_text()


def test_detail_links_settle_long_enough_for_the_arrival_animation() -> None:
    for name in ("_rows.html", "detail.html"):
        assert 'hx-swap="innerHTML settle:220ms"' in (_WEB / "templates" / name).read_text()
    assert "swap:" not in (_WEB / "templates" / "_rows.html").read_text()


def test_focus_is_restored_after_a_filter_swap() -> None:
    script = (_WEB / "static" / "viewer.js").read_text()
    assert "htmx:beforeRequest" in script
    assert "htmx:afterSettle" in script
    assert "focus(" in script
    assert "announce" in script


def test_mark_selected_toggles_the_highlight() -> None:
    script = (_WEB / "static" / "viewer.js").read_text()
    assert 'row.classList.toggle("selected", on);' in script
    assert 'row.classList.toggle("bg-base-300", on);' in script


def test_empty_detail_replacement_keeps_the_hero() -> None:
    script = (_WEB / "static" / "viewer.js").read_text()
    assert (
        '<div class="hero-content"><div><p>Pick a company from the list to read its analysis.</p></div></div>'
        in script
    )


def test_search_wiring_in_the_script() -> None:
    script = _SCRIPT.read_text()
    for needle in (
        'removeAttribute("hidden")',
        'addEventListener("input"',
        '"Escape"',
        "preventDefault()",
        "search-empty",
        "No company matches",
        "Clear search",
        "dataset.total",
        "td.ticker",
        "td.name",
        "toLowerCase()",
        "trim()",
    ):
        assert needle in script, needle


def test_after_settle_reapplies_the_search() -> None:
    script = _SCRIPT.read_text()
    settle = script.index('"htmx:afterSettle"')
    branch = script[script.index('id === "rows"', settle) : script.index('id === "detail"', settle)]
    assert "applySearch();" in branch
    assert "restoreFocus();" in branch
    assert branch.index("applySearch();") < branch.index("restoreFocus();")


def test_no_match_row_writes_the_query_as_text() -> None:
    script = _SCRIPT.read_text()
    assert (
        '<td colspan="9" class="none">No company matches "<span></span>". '
        '<button type="button" class="btn btn-link btn-xs">Clear search</button></td>'
    ) in script
    assert ".textContent = " in script
    assert not re.search(r"innerHTML\s*=[^;]*\+", script)


def test_search_matches_each_cell_separately() -> None:
    script = _SCRIPT.read_text()
    body = script[script.index("function applySearch") : script.index("function announceDetail")]
    assert '+ " " +' not in body
    assert "ticker.textContent.toLowerCase().indexOf(q)" in body
    assert "name.textContent.toLowerCase().indexOf(q)" in body


def test_search_box_is_found_again_after_history_restore() -> None:
    # htmx's Back restores the page by replacing the body, so no node may be kept from load.
    script = _SCRIPT.read_text()
    assert 'document.querySelector("#search input")' in script
    assert 'search.querySelector("input")' not in script
    restore = script[script.index('"htmx:historyRestore"') :]
    assert "initSearch" in restore[: restore.index(")")]


def test_mark_selected_skips_hidden_rows() -> None:
    assert "if (row.hidden) return;" in _SCRIPT.read_text()


def test_search_stores_nothing() -> None:
    script = _SCRIPT.read_text()
    for needle in ("localStorage", "sessionStorage", "pushState", "replaceState", "location."):
        assert needle not in script, needle


def test_viewer_script_parses() -> None:
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")
    result = subprocess.run([node, "--check", str(_SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_announce_reads_the_stat_value() -> None:
    script = _SCRIPT.read_text()
    assert '"#detail .facts .lead-figure .stat-value"' in script
    assert ".lead-figure dd" not in script
