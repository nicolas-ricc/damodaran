"""`bot.web.site.build` renders the static viewer (issue #92)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from bot.web.site import build, normalize_base_url
from tests.web_sidecars import make_sidecar, write_sidecar

_FILTERS = ("all", "undervalued", "fair", "overvalued", "na")
_SORTS = ("ticker", "mos", "date")
_DIRS = ("asc", "desc")
# same-page fragment links (the skip link) are not site URLs
_URL_ATTR = re.compile(r'\b(href|src|hx-get|hx-push-url)="(?!#)([^"]*)"')


@pytest.fixture
def reports(tmp_path: Path) -> Path:
    root = tmp_path / "reports"
    write_sidecar(root, "2026-09-01", make_sidecar("AAA", mos=1.2))
    write_sidecar(root, "2026-10-01", make_sidecar("AAA", mos=1.5))
    write_sidecar(root, "2026-10-01", make_sidecar("BBB", mos=0.7, red_flag=True))
    write_sidecar(root, "2026-10-01", make_sidecar("CCC", mos=None))
    return root


def _html_files(out: Path) -> list[Path]:
    return sorted(out.rglob("*.html"))


def test_generates_every_file(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    assert build(reports, out, "/") == 3

    assert (out / "index.html").is_file()
    for f in _FILTERS:
        for s in _SORTS:
            for d in _DIRS:
                assert (out / "rows" / f"{f}-{s}-{d}.html").is_file()
                assert (out / "l" / f"{f}-{s}-{d}.html").is_file()
    assert len(list((out / "rows").glob("*.html"))) == 30
    for kind in ("c", "f"):
        for ticker in ("AAA", "BBB", "CCC"):
            assert (out / kind / f"{ticker}.html").is_file()
            assert (out / kind / ticker / "2026-10-01.html").is_file()
        assert (out / kind / "AAA" / "2026-09-01.html").is_file()
    assert (out / "static" / "app.css").is_file()
    assert (out / "static" / "htmx.min.js").is_file()


def test_fragments_are_not_pages(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    for path in [*(out / "f").rglob("*.html"), *(out / "rows").glob("*.html")]:
        assert "<html" not in path.read_text(), path
    for path in [out / "index.html", *(out / "c").rglob("*.html"), *(out / "l").glob("*.html")]:
        assert "<html" in path.read_text(), path


def test_every_link_is_prefixed_with_base_url(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/damodaran/")
    seen = 0
    for path in _html_files(out):
        for attr, value in _URL_ATTR.findall(path.read_text()):
            seen += 1
            assert value.startswith("/damodaran/"), f"{path}: {attr}={value!r}"
    assert seen > 100


def test_links_point_at_files_that_exist(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/x/")
    for path in _html_files(out):
        for _, value in _URL_ATTR.findall(path.read_text()):
            target = out / value.removeprefix("/x/")
            if value.endswith("/"):
                target = target / "index.html"
            assert target.is_file(), f"{path}: {value}"


def test_rows_link_to_full_page_and_fragment(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    rows = (out / "rows" / "all-mos-desc.html").read_text()
    assert 'href="/c/AAA.html"' in rows
    assert 'hx-get="/f/AAA.html"' in rows
    assert 'hx-target="#detail"' in rows


def test_list_is_sorted_by_mos_desc_by_default(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    index = (out / "index.html").read_text()
    positions = [index.index(f"/c/{t}.html") for t in ("AAA", "BBB", "CCC")]
    assert positions == sorted(positions)


def test_history_dates_link_from_detail(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    detail = (out / "f" / "AAA.html").read_text()
    assert "/c/AAA/2026-09-01.html" in detail
    single = (out / "f" / "BBB.html").read_text()
    assert "/c/BBB/" not in single


def test_no_price_shows_na_without_value_line_or_scenarios(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    detail = (out / "f" / "CCC.html").read_text()
    assert "n/a" in detail
    assert 'data-role="intrinsic"' not in detail
    assert "Scenarios" not in detail
    aaa = (out / "f" / "AAA.html").read_text()
    assert 'data-role="intrinsic"' in aaa
    assert "Scenarios" in aaa


def test_charts_are_tables_with_html_labels(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    detail = (out / "f" / "AAA.html").read_text()
    assert "filter=" not in detail
    assert '<table class="table table-xs tornado" aria-label="Drivers">' in detail
    assert '<table class="table table-xs scenario-grid" aria-label="Scenarios ' in detail
    assert 'class="axis-label price' in detail


def test_404_and_robots_are_written(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/sub/")
    page = (out / "404.html").read_text()
    assert "No analysis at this address" in page
    assert 'href="/sub/index.html"' in page
    assert (
        out / "robots.txt"
    ).read_text() == "User-agent: *\nDisallow: /sub/f/\nDisallow: /sub/rows/\n"


def test_empty_filter_swaps_in_an_empty_detail(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    fragment = (out / "rows" / "fair-mos-desc.html").read_text()
    assert 'id="detail" hx-swap-oob="true"' in fragment
    assert "No company is fair yet" in fragment
    assert 'id="detail"' not in (out / "rows" / "all-mos-desc.html").read_text()
    page = (out / "l" / "fair-mos-desc.html").read_text()
    assert "No company is fair yet" in page
    assert "<title>Fair · by margin of safety ↓ · Analyses</title>" in page


@pytest.mark.parametrize("page", ["index.html", "c/AAA.html", "l/all-ticker-asc.html"])
def test_ids_are_unique_per_page(reports: Path, tmp_path: Path, page: str) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    html = (out / page).read_text()
    for element_id in ("rows", "filter", "search", "list-head", "count", "detail"):
        assert html.count(f'id="{element_id}"') == 1, element_id


def test_filter_with_no_match_shows_zero_of_n(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    fragment = (out / "rows" / "fair-mos-desc.html").read_text()
    assert "0 of 3" in fragment
    assert "No company is fair yet" in fragment


def test_empty_reports_dir_renders_the_empty_state(tmp_path: Path) -> None:
    out = tmp_path / "site"
    assert build(tmp_path / "missing", out, "/") == 0
    index = (out / "index.html").read_text()
    assert "No analyses" in index
    assert "bot analyze --from-screen" in index


def test_invalid_ticker_is_omitted(reports: Path, tmp_path: Path) -> None:
    (reports / "2026-10-01" / "analysis" / "aapl.json").write_text("{}")
    out = tmp_path / "site"
    assert build(reports, out, "/") == 3
    assert not (out / "c" / "aapl.html").exists()


def test_rebuild_drops_stale_pages(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    (reports / "2026-10-01" / "analysis" / "BBB.json").unlink()
    assert build(reports, out, "/") == 2
    assert not (out / "c" / "BBB.html").exists()


def test_refuses_to_empty_a_foreign_directory(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "precious"
    out.mkdir()
    (out / "keep.txt").write_text("x")
    with pytest.raises(ValueError):
        build(reports, out, "/")
    assert (out / "keep.txt").exists()


def test_refuses_an_out_dir_that_contains_the_reports(reports: Path) -> None:
    with pytest.raises(ValueError):
        build(reports, reports.parent, "/")
    assert any(reports.rglob("*.json"))


def test_builds_into_an_existing_empty_directory(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "empty"
    out.mkdir()
    build(reports, out, "/")
    assert out.is_dir()
    assert (out / "index.html").is_file()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("/", "/"),
        ("", "/"),
        ("/damodaran", "/damodaran/"),
        ("damodaran/", "/damodaran/"),
        (" /damodaran/ ", "/damodaran/"),
    ],
)
def test_normalize_base_url(raw: str, expected: str) -> None:
    assert normalize_base_url(raw) == expected


def test_names_and_reasons_are_escaped(tmp_path: Path) -> None:
    reports = tmp_path / "reports"
    payload = make_sidecar("ATT", name="AT&T <Inc>")
    payload["analysis"]["narrative_flags"][0]["reason"] = "<script>x</script>"
    write_sidecar(reports, "2026-10-01", payload)
    out = tmp_path / "site"
    build(reports, out, "/")
    for path in _html_files(out):
        html = path.read_text()
        assert "<Inc>" not in html
        assert "<script>x" not in html
    assert "AT&amp;T &lt;Inc&gt;" in (out / "c" / "ATT.html").read_text()


def test_marks_pair_colour_with_a_title(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    rows = (out / "rows" / "all-mos-desc.html").read_text()
    assert "<title>potentially undervalued</title>" in rows or "<title>undervalued</title>" in rows
    assert "<title>fail: " in rows
    assert "<title>red</title>" not in rows


def test_dcf_lede_counts_the_sidecar_years(tmp_path: Path) -> None:
    # The lede follows the sidecar's own projections: ten years now, five in an
    # old sidecar written before #216.
    root = tmp_path / "reports"
    write_sidecar(root, "2026-10-01", make_sidecar("AAA"))
    old = make_sidecar("BBB")
    dcf = old["analysis"]["dcf_result"]
    dcf["projections"] = dcf["projections"][:5]
    write_sidecar(root, "2026-10-01", old)
    out = tmp_path / "site"
    build(root, out, "/")
    new_page = (out / "c" / "AAA" / "2026-10-01.html").read_text()
    old_page = (out / "c" / "BBB" / "2026-10-01.html").read_text()
    assert "10 years of projected free cash flow" in new_page
    assert "5 years of projected free cash flow" in old_page


_FILTER_NAV = re.compile(r"<nav id=\"filter\"[^>]*>.*?</nav>", re.S)


def _filter_nav(html: str) -> str:
    match = _FILTER_NAV.search(html)
    assert match is not None
    return match.group(0)


def _filter_links(html: str) -> list[str]:
    return re.findall(r"<a [^>]*>", _filter_nav(html))


def test_controls_are_daisyui_components(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    index = (out / "index.html").read_text()
    assert '<header class="navbar">' in index
    assert 'class="navbar-start"' in index
    assert 'class="navbar-end"' in index
    assert '<span class="badge badge-ghost"><span class="num">3</span> companies</span>' in index
    assert (
        '<output id="count" class="badge badge-neutral num" aria-live="polite" data-total="3"'
        in index
    )
    assert '<table class="table table-sm table-pin-rows list">' in index
    for path in _html_files(out):
        assert "table-zebra" not in path.read_text(), path.name

    one = tmp_path / "one"
    write_sidecar(one, "2026-10-01", make_sidecar("AAA"))
    build(one, tmp_path / "site-one", "/")
    single = (tmp_path / "site-one" / "index.html").read_text()
    assert '<span class="num">1</span> company</span>' in single


def test_filter_is_a_join_with_one_active_link(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    for page, current in (
        ("index.html", "all"),
        ("rows/undervalued-mos-desc.html", "undervalued"),
    ):
        html = (out / page).read_text()
        assert _filter_nav(html).startswith('<nav id="filter" class="join"'), page
        links = _filter_links(html)
        assert len(links) == 5, page
        for link in links:
            assert 'href="' in link
            assert 'hx-get="' in link
            assert 'hx-target="#rows"' in link
            assert "join-item" in link
        active = [link for link in links if 'aria-current="page"' in link]
        assert len(active) == 1, page
        assert "btn-active" in active[0]
        assert f"/{current}-mos-desc.html" in active[0]
        assert sum("btn-active" in link for link in links) == 1, page
    fragments = sorted((out / "rows").glob("*.html"))
    assert len(fragments) == 30
    for path in fragments:
        html = path.read_text()
        links = _filter_links(html)
        active = [link for link in links if "btn-active" in link]
        assert len(active) == 1, path.name
        assert 'aria-current="page"' in active[0], path.name
        assert re.search(r'<output id="count"[^>]*hx-swap-oob="true"', html), path.name


def test_selected_row_is_highlighted(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    page = (out / "c" / "AAA.html").read_text()
    assert page.count('<tr class="selected bg-base-300">') == 1
    assert re.search(
        r'<tr class="selected bg-base-300">\s*<td class="ticker"><a href="/c/AAA.html"', page
    )
    assert "selected" not in (out / "rows" / "all-mos-desc.html").read_text()


def test_flags_are_badges_by_tone(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    rows = (out / "rows" / "all-mos-desc.html").read_text()
    assert '<span class="badge badge-xs badge-error" title="fail: ' in rows
    for path in _html_files(out):
        assert "badge-info" not in path.read_text(), path.name

    # rows keep only red and yellow flags, so a yellow one stands in for a second tone
    yellow = tmp_path / "yellow"
    payload = make_sidecar("DDD")
    payload["analysis"]["narrative_flags"][3]["color"] = "yellow"
    write_sidecar(yellow, "2026-10-01", payload)
    build(yellow, tmp_path / "site-yellow", "/")
    rows = (tmp_path / "site-yellow" / "rows" / "all-mos-desc.html").read_text()
    assert '<span class="badge badge-xs badge-warning" title="warning: ' in rows


def test_empty_states_are_heroes(reports: Path, tmp_path: Path) -> None:
    empty = tmp_path / "empty-site"
    build(tmp_path / "missing", empty, "/")
    index = (empty / "index.html").read_text()
    assert '<main class="hero empty">' in index
    assert '<div class="hero-content">' in index
    assert "No analyses yet" in index
    assert "badge badge-ghost" not in index

    out = tmp_path / "site"
    build(reports, out, "/")
    page = (out / "l" / "fair-mos-desc.html").read_text()
    assert '<div class="hero empty-detail">' in page
    assert "No company is fair yet" in page
    assert '<a class="btn btn-link" href="/l/all-mos-desc.html"' in page
    fragment = (out / "rows" / "fair-mos-desc.html").read_text()
    assert '<td colspan="9" class="none">' in fragment
    assert '<a class="btn btn-link btn-xs" href="/l/all-mos-desc.html"' in fragment
    assert 'id="detail" hx-swap-oob="true"' in fragment
    missing = (out / "404.html").read_text()
    assert '<main class="hero empty">' in missing
    assert '<a class="btn btn-primary" href="/index.html">Show all companies</a>' in missing


def test_search_box_sits_between_filter_and_count(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    index = (out / "index.html").read_text()
    assert '<label class="input input-sm" id="search" hidden>' in index
    assert "Search by ticker or name" in index
    assert '<input type="search"' in index
    assert 'aria-controls="rows"' in index
    assert index.count('id="search"') == 1
    assert index.index('id="filter"') < index.index('id="search"') < index.index('id="count"')


def test_search_box_is_never_in_a_fragment(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    fragments = sorted((out / "rows").glob("*.html"))
    assert len(fragments) == 30
    for path in fragments:
        assert 'id="search"' not in path.read_text(), path.name
    empty = tmp_path / "empty-site"
    build(tmp_path / "missing", empty, "/")
    assert 'id="search"' not in (empty / "index.html").read_text()


def test_list_works_without_javascript(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    index = (out / "index.html").read_text()
    head = re.search(r'<thead id="list-head".*?</thead>', index, re.S)
    assert head is not None
    links = _filter_links(index) + re.findall(r"<a [^>]*>", head.group(0))
    assert len(links) == 8
    for link in links:
        assert 'href="' in link
        assert 'hx-get="' in link
    assert index.count('<td class="ticker">') == 3
    assert index.count('<td class="name">') == 3
    assert '<td colspan="9" class="none">' in (out / "rows" / "fair-mos-desc.html").read_text()


_DIVIDER = '<div class="divider" aria-hidden="true"></div>'


def test_detail_facts_are_stats(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    for page in ("f/AAA.html", "c/AAA.html"):
        html = (out / page).read_text()
        assert 'class="stats stats-vertical lg:stats-horizontal facts"' in html, page
        assert html.count('class="stat ') + html.count('class="stat"') == 5, page
        assert html.count('class="stat lead-figure"') == 1, page
        assert '<div class="stat-value text-secondary num">' in html, page
        assert html.count('class="stat-value word') == 2, page
        assert '<div class="stat-value word story">' in html, page
        assert re.search(r'<div class="stat-value word"><time datetime="2026-10-01">', html), page
    for path in _html_files(out):
        assert '<dl class="facts">' not in path.read_text(), path.name


def test_detail_sections_are_divided(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    aaa = (out / "f" / "AAA.html").read_text()
    assert aaa.count(_DIVIDER) >= 5
    flat = re.sub(r">\s+<", "><", aaa)
    assert flat.count('<div class="head-row">') == flat.count(_DIVIDER + '<div class="head-row">')
    assert _DIVIDER + '<details class="dcf">' in flat
    ccc = (out / "f" / "CCC.html").read_text()
    assert ccc.count(_DIVIDER) < aaa.count(_DIVIDER)


def _history_links(html: str) -> list[str]:
    nav = html[html.index('<nav class="history join"') :]
    nav = nav[: nav.index("</nav>")]
    return re.findall(r"<a [^>]*>[^<]*</a>", nav)


def test_detail_history_is_a_join(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    for page, current in (
        ("f/AAA.html", "2026-10-01"),
        ("c/AAA.html", "2026-10-01"),
        ("f/AAA/2026-09-01.html", "2026-09-01"),
    ):
        html = (out / page).read_text()
        assert '<nav class="history join" aria-label="Analysis date">' in html, page
        links = _history_links(html)
        assert len(links) == 2, page
        assert all('class="btn btn-xs join-item' in a for a in links), page
        active = [a for a in links if "btn-active" in a]
        assert len(active) == 1, page
        assert 'aria-current="page"' in active[0] and f">{current}</a>" in active[0], page
        assert sum('aria-current="page"' in a for a in links) == 1, page
        for a in links:
            for attr in (
                'href="/c/AAA',
                'hx-get="/f/AAA',
                'hx-target="#detail"',
                'hx-swap="innerHTML settle:220ms"',
                'hx-push-url="/c/AAA',
                'hx-indicator="#detail"',
            ):
                assert attr in a, (page, attr)
    assert 'class="history' not in (out / "f" / "BBB.html").read_text()


def test_detail_tables_are_daisyui_tables(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    for page in ("f/AAA.html", "c/AAA.html"):
        html = (out / page).read_text()
        assert '<table class="table table-xs assumptions-table">' in html, page
        assert '<table class="table table-xs">' in html, page
        detail = html[html.index('<header class="detail-head">') :]
        assert "<table>" not in detail, page


def test_detail_flags_are_badges(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    html = (out / "f" / "BBB.html").read_text()
    section = html[html.index('<section class="flag-list">') :]
    section = section[: section.index("</section>")]
    assert '<span class="badge badge-sm badge-error">fail</span>' in section
    assert 'class="mark"' not in section
    assert 'class="severity"' not in section
    items = re.findall(r'<li class="flag flag-[^"]*">(.*?)</li>', section, re.S)
    assert items
    for item in items:
        assert re.match(
            r'<span class="badge badge-sm badge-(success|warning|error|ghost)">[^<]+</span> '
            r'<span class="id">[^<]*</span> <span class="reason">',
            item,
        ), item


# --- issue #262: findings of the impeccable critique and audit ---

_TITLE = re.compile(r"<title>([^<]*)</title>")


def _page_title(path: Path) -> str:
    match = _TITLE.search(path.read_text())
    assert match, path
    return match.group(1)


def test_fragments_carry_their_page_title(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    pairs = [
        (out / "f" / "AAA.html", out / "c" / "AAA.html"),
        (out / "f" / "AAA" / "2026-09-01.html", out / "c" / "AAA" / "2026-09-01.html"),
        (out / "rows" / "fair-mos-desc.html", out / "l" / "fair-mos-desc.html"),
        (out / "rows" / "all-mos-desc.html", out / "l" / "all-mos-desc.html"),
    ]
    for fragment, page in pairs:
        text = fragment.read_text()
        title = f"<title>{_page_title(page)}</title>"
        if fragment.parent.name == "rows":
            # a leading <title> makes the browser's template parser drop <tbody>/<thead>, so rows end with it
            assert text.rstrip().endswith(title), fragment
        else:
            assert text.lstrip().startswith(title), fragment
        assert "<html" not in text
    assert _page_title(out / "c" / "AAA.html").startswith("AAA · ")


def test_filter_sort_and_show_all_push_their_list_url(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    for path in (out / "index.html", out / "rows" / "na-mos-desc.html", out / "rows" / "fair-date-asc.html"):
        links = re.findall(r'<a [^>]*hx-target="#rows"[^>]*>', path.read_text())
        assert links, path
        for link in links:
            href = re.search(r'\bhref="([^"]*)"', link)
            push = re.search(r'\bhx-push-url="([^"]*)"', link)
            assert href and push, link
            assert push.group(1) == href.group(1), link
            assert push.group(1).startswith("/l/"), link


def test_skip_link_leads_to_the_analysis(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    skip = '<a class="skip btn btn-sm btn-primary" href="#detail">Skip to analysis</a>'
    for path in (out / "index.html", out / "c" / "AAA.html"):
        html = path.read_text()
        body = html[html.index("<body") :]
        body = body[body.index("</svg>") + len("</svg>") :].lstrip()
        assert body.startswith(skip), path
        section = re.search(r'<section id="detail"[^>]*>', html)
        assert section, path
        assert 'tabindex="-1"' in section.group(0)
        assert 'aria-label="Analysis"' in section.group(0)
    assert "Skip to analysis" not in (out / "404.html").read_text()
    empty = (out / "rows" / "fair-mos-desc.html").read_text()
    section = re.search(r'<section id="detail"[^>]*>', empty)
    assert section, "fair has no company, so the fragment carries the empty detail"
    assert 'tabindex="-1"' in section.group(0)
    assert 'aria-label="Analysis"' in section.group(0)


def test_history_cache_is_off(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    for path in (out / "index.html", out / "c" / "AAA.html", out / "l" / "fair-mos-desc.html"):
        head = path.read_text().split("</head>")[0]
        assert """<meta name="htmx-config" content='{"historyCacheSize":0}'>""" in head, path
        assert head.index("htmx-config") < head.index("htmx.min.js")


def test_scenarios_take_the_wide_column(tmp_path: Path) -> None:
    root = tmp_path / "reports"
    write_sidecar(root, "2026-10-01", make_sidecar("AAA", mos=1.5))
    out = tmp_path / "site"
    build(root, out, "/")
    html = (out / "c" / "AAA.html").read_text()
    if 'class="scenarios"' not in html:
        pytest.skip("fixture sidecar has no scenario grid")
    grid = re.search(r'<div class="pair-grid([^"]*)">\s*<section class="scenarios">', html)
    assert grid, "scenarios open their pair grid"
    assert "wide-first" in grid.group(1)
