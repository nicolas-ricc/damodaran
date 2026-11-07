"""Vendored assets of the web viewer: fonts, licenses, htmx (issue #92)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_WEB = Path(__file__).resolve().parents[2] / "src" / "bot" / "web"
_STATIC = _WEB / "static"


@pytest.mark.parametrize("font", ["switzer-400", "switzer-500", "geist-mono-400"])
def test_fonts_are_local_woff2(font: str) -> None:
    path = _STATIC / "fonts" / f"{font}.woff2"
    assert path.read_bytes()[:4] == b"wOF2"


@pytest.mark.parametrize(
    ("license_file", "phrase"),
    [("OFL-GeistMono.txt", "SIL OPEN FONT LICENSE"), ("ITF-FFL-Switzer.txt", "LICENSE")],
)
def test_fonts_ship_their_license(license_file: str, phrase: str) -> None:
    text = (_STATIC / "fonts" / license_file).read_text()
    assert phrase in text.upper()


def test_only_the_fonts_in_use_are_shipped() -> None:
    css = (_STATIC / "app.css").read_text()
    for woff in (_STATIC / "fonts").glob("*.woff2"):
        assert f"fonts/{woff.name}" in css, woff.name
    base = (_WEB / "templates" / "base.html").read_text()
    assert base.count('rel="preload"') == 2


def test_htmx_2_is_vendored() -> None:
    assert (_STATIC / "htmx.min.js").stat().st_size > 10_000
    assert re.search(r"htmx 2\.\d+\.\d+", (_STATIC / "VERSIONS").read_text())


@pytest.mark.parametrize(
    "template", ["base.html", "list.html", "_rows.html", "_controls.html", "detail.html"]
)
def test_templates_exist(template: str) -> None:
    assert (_WEB / "templates" / template).is_file()


def test_nothing_is_loaded_from_a_cdn() -> None:
    sheets = [_STATIC / "app.css", _STATIC / "theme.css"]
    for sheet in sheets:
        assert "@import" not in sheet.read_text(), sheet
    for path in [*sheets, *(_WEB / "templates").glob("*.html")]:
        assert not re.search(r"https?://", path.read_text()), path


def test_css_reads_daisyui_variables_only() -> None:
    css = (_STATIC / "app.css").read_text()
    for literal in ("oklch(", "rgb(", "hsl("):
        assert literal not in css, literal
    assert not re.search(r"#[0-9a-fA-F]{3,8}\b", css)
    assert (
        "--ink-soft: color-mix(in oklab, var(--color-base-content) 80%, var(--color-base-100));"
        in css
    )
    assert "--rule-faint: color-mix(in oklab, var(--color-base-content) 12%, transparent);" in css
    assert "Hallmark" not in css
    assert "prefers-reduced-motion" in css
    assert "tabular-nums" in css
    assert "@font-face" in css
    assert "[hidden]" in css


def test_hand_drawn_controls_are_gone() -> None:
    # DaisyUI draws the list pane's controls now (issue #259); the layout rules stay.
    css = (_STATIC / "app.css").read_text()
    for gone in (
        ".bar {",
        ".bar .note",
        ".brand {",
        "#filter a",
        "#count {",
        "box-shadow: inset",
        ".list tr.selected td",
        ".empty a",
        ".empty-detail a",
        ".list .none a",
    ):
        assert gone not in css, gone
    assert "\na { color: inherit" not in css
    for kept in (
        ".empty .hero-content > div, .empty-detail .hero-content > div { display: grid; justify-items: start; gap: var(--space-sm); }",
        "a:not(.btn) {",
        "a:not(.btn):hover { text-decoration: underline; }",
        "[hidden] { display: none !important; }",
        ".sr {",
        ".split {",
        "body.page-list .detail-pane { display: none; }",
        "@media (max-width: 699px)",
        "@media (min-width: 1100px) and (max-width: 1599px)",
        ".list tr.selected .ticker::before",
        ".list thead th[aria-sort] a { border-bottom-color: var(--color-primary); }",
        ".list { display: table;",
    ):
        assert kept in css, kept


def test_list_pane_rules_restore_what_daisyui_overrides() -> None:
    # Each rule answers a DaisyUI default measured in the browser (issue #259 review).
    css = (_STATIC / "app.css").read_text()
    for rule in (
        ".flags .badge .glyph { stroke: currentColor; }",
        ".flags .badge .mark { width: 0.75rem; height: 0.75rem; }",
        ".flags .badge + .badge { margin-left: 2px; }",
        ".list tbody tr { font-size: inherit; }",
        ".history { gap: var(--space-2xs) var(--space-sm); font-family: var(--font-mono); }",
        "#filter .btn-active { color: var(--color-primary); border-bottom-color: var(--color-primary); }",
    ):
        assert rule in css, rule


def test_search_box_width_rule() -> None:
    css = (_STATIC / "app.css").read_text()
    assert "#search { width: 14rem; max-width: 100%; }" in css
    assert "[hidden] { display: none !important; }" in css
