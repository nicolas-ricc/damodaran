"""Render the static analysis viewer from ``reports/*/analysis/*.json`` (issue #92)."""

from __future__ import annotations

import shutil
from collections import Counter
from collections.abc import Mapping
from importlib import resources
from pathlib import Path
from typing import Any

from jinja2 import Environment, PackageLoader, Template

from bot.reporting.analysis_report import fmt_ratio
from bot.web.index import CompanyEntry, scan
from bot.web.svg import (
    flag_mark,
    scenario_grid_svg,
    seed_of,
    tornado_svg,
    value_line_svg,
    verdict_mark,
)
from bot.web.views import (
    DIRECTIONS,
    FILTERS,
    SORTS,
    RowView,
    detail_view,
    filter_sort,
    row_view,
)

MARKER = ".bot-site"
_DEFAULT = ("all", "mos", "desc")


def normalize_base_url(raw: str) -> str:
    """Return ``raw`` with exactly one leading and one trailing slash."""
    stripped = raw.strip().strip("/")
    return f"/{stripped}/" if stripped else "/"


def _prepare_out_dir(out_dir: Path, reports_dir: Path) -> Path:
    """Validate ``out_dir`` and empty it (never removing the directory itself)."""
    out = out_dir.resolve()
    reports = reports_dir.resolve()
    if out == reports or out in reports.parents:
        raise ValueError(f"refusing to build into {out}: it contains the reports directory")
    if out.exists():
        if not out.is_dir():
            raise ValueError(f"{out} exists and is not a directory")
        children = list(out.iterdir())
        if children and not (out / MARKER).is_file():
            raise ValueError(f"refusing to empty {out}: not empty and not a bot site output")
        for child in children:
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()
    else:
        out.mkdir(parents=True)
    (out / MARKER).write_text("", encoding="utf-8")
    return out


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _copy_static(out: Path) -> None:
    with resources.as_file(resources.files("bot.web").joinpath("static")) as src:
        shutil.copytree(src, out / "static", ignore=shutil.ignore_patterns("__pycache__"))


def _environment(base_url: str) -> Environment:
    env = Environment(
        loader=PackageLoader("bot.web", "templates"),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.globals.update(
        value_line_svg=value_line_svg,
        scenario_grid_svg=scenario_grid_svg,
        tornado_svg=tornado_svg,
        verdict_mark=verdict_mark,
        flag_mark=flag_mark,
        seed_of=seed_of,
        fmt_ratio=fmt_ratio,
        rows_href=lambda f, s, d: f"{base_url}rows/{f}-{s}-{d}.html",
        list_href=lambda f, s, d: f"{base_url}l/{f}-{s}-{d}.html",
    )
    return env


def build(reports_dir: Path, out_dir: Path, base_url: str) -> int:
    """Write the whole site into ``out_dir``; return the number of companies."""
    base_url = normalize_base_url(base_url)
    out = _prepare_out_dir(out_dir, reports_dir)
    entries = scan(reports_dir)
    by_ticker = {e.ticker: e for e in entries}
    all_rows = [row_view(e.latest) for e in entries]
    counts: dict[str, int] = {"all": len(all_rows), **dict.fromkeys(FILTERS[1:], 0)}
    counts.update(Counter(r.verdict.value for r in all_rows))

    env = _environment(base_url)
    list_tpl = env.get_template("list.html")
    rows_tpl = env.get_template("rows_fragment.html")
    detail_tpl = env.get_template("detail.html")

    def context(
        rows: list[RowView],
        active: tuple[str, str, str],
        detail: Any = None,
        selected: str | None = None,
        page_class: str = "page-list",
    ) -> dict[str, Any]:
        return {
            "base_url": base_url,
            "rows": rows,
            "counts": counts,
            "total": len(all_rows),
            "active": active,
            "detail": detail,
            "selected": selected,
            "page_class": page_class,
        }

    def render_list(tpl: Template, ctx: Mapping[str, Any]) -> str:
        return tpl.render(**ctx)

    def first_detail(rows: list[RowView]) -> Any:
        if not rows:
            return None
        entry = by_ticker[rows[0].ticker]
        return detail_view(entry, entry.latest)

    default_rows = filter_sort(all_rows, *_DEFAULT)
    default_ctx = context(default_rows, _DEFAULT, first_detail(default_rows))
    default_ctx["selected"] = default_rows[0].ticker if default_rows else None
    _write(out / "index.html", render_list(list_tpl, default_ctx))

    for f in FILTERS:
        for s in SORTS:
            for d in DIRECTIONS:
                rows = filter_sort(all_rows, f, s, d)
                name = f"{f}-{s}-{d}.html"
                _write(out / "rows" / name, render_list(rows_tpl, context(rows, (f, s, d))))
                page = context(rows, (f, s, d), first_detail(rows))
                page["selected"] = rows[0].ticker if rows else None
                _write(out / "l" / name, render_list(list_tpl, page))

    for entry in entries:
        _write_company(out, entry, default_rows, context, list_tpl, detail_tpl)

    _copy_static(out)
    return len(entries)


def _write_company(
    out: Path,
    entry: CompanyEntry,
    default_rows: list[RowView],
    context: Any,
    list_tpl: Template,
    detail_tpl: Template,
) -> None:
    latest = entry.latest
    for ref in entry.history:
        view = detail_view(entry, ref)
        ctx = context(default_rows, _DEFAULT, view, entry.ticker, "page-detail")
        targets = [f"{entry.ticker}/{ref.date.isoformat()}.html"]
        if ref is latest:
            targets.append(f"{entry.ticker}.html")
        for target in targets:
            _write(out / "c" / target, list_tpl.render(**ctx))
            _write(out / "f" / target, detail_tpl.render(**ctx))
