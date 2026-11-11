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
        ".history { font-family: var(--font-mono); }",
        "#filter .btn-active { color: var(--color-primary); border-bottom-color: var(--color-primary); }",
    ):
        assert rule in css, rule


def test_search_box_width_rule() -> None:
    css = (_STATIC / "app.css").read_text()
    assert "#search { width: 14rem; max-width: 100%; }" in css
    assert "[hidden] { display: none !important; }" in css


def test_detail_facts_rules() -> None:
    css = (_STATIC / "app.css").read_text()
    for rule in (
        ".facts .stat-value { font-weight: 500; letter-spacing: -0.03em; }",
        ".facts .stat-value.word { font-size: var(--text-lg); }",
    ):
        assert rule in css, rule
    narrow = css[css.index("@container (max-width: 44rem) {") :]
    narrow = narrow[: narrow.index("\n}")]
    assert (
        ".facts.stats { grid-auto-flow: row; grid-template-columns: repeat(2, minmax(0, 1fr)); }"
    ) in narrow
    assert ".facts .lead-figure { grid-column: 1 / -1; }" in narrow
    assert (
        ".facts.stats .stat:not(:nth-last-child(-n+2)) { border-inline-end: none; "
        "border-block-end: var(--border) dashed var(--rule-faint); }"
    ) in narrow
    assert ".facts.stats .stat:nth-last-child(2) { border-inline-end: none; border-block-end: none; }" in narrow
    for gone in (
        ".facts dd",
        ".facts dt",
        ".facts > div",
        "@container (min-width: 28rem)",
        "@container (min-width: 44rem)",
    ):
        assert gone not in css, gone


def test_detail_rules_have_no_top_borders() -> None:
    css = (_STATIC / "app.css").read_text()
    for sel in (".head-row", ".facts", ".dcf summary"):
        rule = re.search(r"(?m)^" + re.escape(sel) + r" \{([^}]*)\}", css)
        assert rule is not None, sel
        assert "border-top" not in rule.group(1), sel
    assert ".divider { margin: 0 0 var(--space-xs); }" in css
    assert "#detail > .divider + .dcf { margin-top: 0; }" in css


def test_history_link_rules_are_gone() -> None:
    assert ".history a" not in (_STATIC / "app.css").read_text()


def test_detail_table_rules_restore_what_daisyui_overrides() -> None:
    css = (_STATIC / "app.css").read_text()
    assert ".table-xs tr { font-size: inherit; }" in css
    grid = re.search(r"(?m)^\.scenario-grid \{([^}]*)\}", css)
    assert grid is not None
    assert "width: auto;" in grid.group(1)
    assert "border-spacing: 2px;" in grid.group(1)
    assert ".scenario-grid th, .scenario-grid td { padding: 0; border: 0;" in css
    assert ".tornado td.track { width: 100%;" in css
    assert ".assumptions tr { display: grid;" in css


def test_flag_severity_colours_are_gone() -> None:
    css = (_STATIC / "app.css").read_text()
    assert ".flag-list .severity" not in css
    assert ".flag-not-evaluated .severity" not in css


def test_detail_rules_fit_the_instrument() -> None:
    # Measured in the browser over the 80 published companies at 1440px (issue #260):
    # DaisyUI's 2rem values and 1.5rem stat padding overflow the instrument, its thead
    # nowrap widens the scenario grid, and .table drops the assumptions to .875rem.
    css = (_STATIC / "app.css").read_text()
    for rule in (
        ".facts { max-width: 100%; margin-top: var(--space-lg); }",
        ".facts .stat { padding-inline: var(--space-md); }",
        ".facts .stat-value.num { font-size: var(--text-xl); }",
        ".facts .lead-figure .stat-value { font-size: var(--text-3xl); }",
        ".scenario-grid thead { white-space: normal; }",
        ".assumptions-table { font-size: var(--text-md); }",
    ):
        assert rule in css, rule


def test_detail_restores_what_the_stat_and_btn_defaults_override() -> None:
    # Dates stay mono (docs/DESIGN.md); Geist Mono ships 400 only, so .btn's 600 would be synthesised.
    css = (_STATIC / "app.css").read_text()
    assert ".facts time { font-family: var(--font-mono); }" in css
    assert ".history .btn { font-weight: 400; }" in css


# --- issue #262: findings of the impeccable critique and audit ---


def _blocks(css: str, header: str) -> str:
    """The bodies of every top-level block opened by ``header``, joined."""
    out = []
    start = css.find(header)
    while start != -1:
        depth, i = 0, css.index("{", start)
        for j in range(i, len(css)):
            depth += {"{": 1, "}": -1}.get(css[j], 0)
            if depth == 0:
                out.append(css[i + 1 : j])
                break
        start = css.find(header, start + 1)
    return "\n".join(out)


def _rule(css: str, selector: str) -> str:
    """The declarations of the first rule whose selector list is exactly ``selector``."""
    match = re.search(rf"(?:^|[}};\n])\s*{re.escape(selector)}\s*\{{([^}}]*)\}}", css)
    assert match, selector
    return match.group(1)


def test_facts_labels_meet_the_contrast_floor() -> None:
    rule = _rule((_STATIC / "app.css").read_text(), ".facts .stat-title")
    assert "color: var(--ink-soft)" in rule
    assert "font-size: var(--text-sm)" in rule


def test_search_placeholder_and_border_meet_the_contrast_floor() -> None:
    css = (_STATIC / "app.css").read_text()
    placeholder = _rule(css, "#search input::placeholder")
    assert "color: var(--ink-soft)" in placeholder
    assert "opacity: 1" in placeholder
    border = re.search(
        r"#search\s*\{[^}]*border-color: color-mix\(in oklab, var\(--color-base-content\) (\d+)%, transparent\)",
        css,
    )
    assert border and int(border.group(1)) >= 55


def test_search_draws_one_focus_ring() -> None:
    css = (_STATIC / "app.css").read_text()
    assert "outline: none" in _rule(css, "#search input:focus-visible")
    assert "outline: 2px solid var(--color-primary)" in _rule(css, "#search:focus-within")


def test_search_input_is_16px_on_touch_screens() -> None:
    coarse = _blocks((_STATIC / "app.css").read_text(), "@media (pointer: coarse)")
    assert "font-size: 16px" in _rule(coarse, "#search input")


def test_history_dates_are_at_least_12px() -> None:
    assert "font-size: var(--text-sm)" in _rule((_STATIC / "app.css").read_text(), ".history .btn")


def test_facts_use_two_columns_in_a_narrow_pane() -> None:
    narrow = _blocks((_STATIC / "app.css").read_text(), "@container (max-width: 44rem)")
    assert "grid-template-columns: repeat(2, minmax(0, 1fr))" in _rule(narrow, ".facts.stats")
    assert "grid-column: 1 / -1" in _rule(narrow, ".facts .lead-figure")


def test_story_column_leaves_the_split_ledger_at_every_width() -> None:
    wide = _blocks((_STATIC / "app.css").read_text(), "@media (min-width: 1100px) {")
    assert "display: none" in _rule(wide, '.list th:nth-child(7), .list td[data-label="Story"]')


def test_intrinsic_column_leaves_the_split_ledger() -> None:
    wide = _blocks((_STATIC / "app.css").read_text(), "@media (min-width: 1100px) {")
    assert "display: none" in _rule(wide, '.list th:nth-child(6), .list td[data-label="Intrinsic"]')


def test_phone_row_is_one_link() -> None:
    phone = _blocks((_STATIC / "app.css").read_text(), "@media (max-width: 699px)")
    assert "position: relative" in _rule(phone, ".list tbody tr")
    overlay = _rule(phone, ".list td.ticker a::after")
    for decl in ('content: ""', "position: absolute", "inset: 0"):
        assert decl in overlay, decl


def test_sort_arrow_is_not_part_of_the_column_name() -> None:
    css = (_STATIC / "app.css").read_text()
    for arrow in ("2193", "2191"):
        assert f'content: "\\{arrow}"; content: "\\{arrow}" / "";' in css, arrow


def test_no_dead_tokens() -> None:
    css = (_STATIC / "app.css").read_text()
    assert "--z-raised" not in css
    motion = _blocks(css, "@media (prefers-reduced-motion: reduce)")
    assert "#detail, #rows { transition: none; }" not in motion
    assert "#detail.htmx-settling > * { animation: none; }" not in motion


def test_skip_link_rules() -> None:
    css = (_STATIC / "app.css").read_text()
    assert "transform: translateY(-200%)" in _rule(css, ".skip")
    assert "transform: none" in _rule(css, ".skip:focus")
    assert "outline: none" in _rule(css, "#detail:focus")
    narrow = _blocks(css, "@media (max-width: 1099px)")
    assert "display: none" in _rule(narrow, "body.page-list .skip")


def test_scroll_box_is_shared() -> None:
    assert "overflow-x: auto" in _rule((_STATIC / "app.css").read_text(), ".scroll")


def test_scenario_grid_shrinks_to_fit_a_phone_pane() -> None:
    narrow = _blocks((_STATIC / "app.css").read_text(), "@container (max-width: 28rem)")
    heads = _rule(narrow, ".scenario-grid th")
    assert "font-size: 0.75rem" in heads
    assert "padding-inline: 3px" in _rule(narrow, ".scenario-grid thead tr:last-child th")
    assert "width: 2rem" in _rule(narrow, ".scenario-grid .cell")
    assert "height: 2rem" in _rule(narrow, ".scenario-grid .cell")


def test_drivers_shock_wraps_under_the_input_in_a_phone_pane() -> None:
    narrow = _blocks((_STATIC / "app.css").read_text(), "@container (max-width: 28rem)")
    shock = _rule(narrow, ".tornado .shock")
    assert "display: block" in shock
    assert "margin-left: 0" in shock


def test_drivers_cells_tighten_in_a_phone_pane() -> None:
    narrow = _blocks((_STATIC / "app.css").read_text(), "@container (max-width: 28rem)")
    assert "padding-inline: var(--space-2xs)" in _rule(narrow, ".tornado th, .tornado td")


def test_drivers_numbers_shrink_in_a_phone_pane() -> None:
    narrow = _blocks((_STATIC / "app.css").read_text(), "@container (max-width: 28rem)")
    assert "font-size: 0.75rem" in _rule(narrow, ".tornado th, .tornado td")


def test_drivers_high_column_keeps_a_gap_from_the_price_line() -> None:
    narrow = _blocks((_STATIC / "app.css").read_text(), "@container (max-width: 28rem)")
    rule = _rule(narrow, ".tornado td.high, .tornado thead th.num:last-child")
    assert "padding-inline-start: 3px" in rule


def test_drivers_head_and_track_share_one_scale_in_a_narrow_pane() -> None:
    narrow = _blocks((_STATIC / "app.css").read_text(), "@container (max-width: 28rem)")
    assert "padding-inline: 2px" in _rule(narrow, ".tornado td.track")
    assert "padding-inline: 2px" in _rule(narrow, ".tornado thead .track-head")
