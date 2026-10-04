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
_URL_ATTR = re.compile(r'\b(href|src|hx-get|hx-push-url)="([^"]*)"')


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


def test_wobble_only_in_detail(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    for path in (out / "rows").glob("*.html"):
        assert "filter=" not in path.read_text(), path
    assert 'filter="url(#wobble-' in (out / "f" / "AAA.html").read_text()


@pytest.mark.parametrize("page", ["index.html", "c/AAA.html", "l/all-ticker-asc.html"])
def test_ids_are_unique_per_page(reports: Path, tmp_path: Path, page: str) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    html = (out / page).read_text()
    for element_id in ("rows", "filter", "list-head", "count", "detail"):
        assert html.count(f'id="{element_id}"') == 1, element_id


def test_filter_with_no_match_shows_zero_of_n(reports: Path, tmp_path: Path) -> None:
    out = tmp_path / "site"
    build(reports, out, "/")
    assert "0 of 3" in (out / "rows" / "fair-mos-desc.html").read_text()


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
    assert "<title>red</title>" in rows
