"""Render the static analysis viewer from ``reports/*/analysis/*.json`` (issue #92)."""

from __future__ import annotations

import shutil
from collections import Counter
from collections.abc import Callable
from importlib import resources
from pathlib import Path
from typing import Any

import structlog
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
    DetailView,
    RowView,
    detail_view,
    filter_sort,
    row_view,
)

MARKER = ".bot-site"
_DEFAULT = ("all", "mos", "desc")

log = structlog.get_logger(__name__)


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
        # The marker goes last, so a cleanup that fails midway leaves a dir the next run can retry.
        for child in sorted(children, key=lambda c: c.name == MARKER):
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


def _renderable(entry: CompanyEntry) -> CompanyEntry | None:
    """``entry`` without the analyses whose sidecar lacks a field the views read.

    ``index.scan`` only checks the envelope; a sidecar missing an ``analysis``
    field must not abort the whole build, so it is skipped like a malformed one.
    """
    kept = []
    for ref in entry.history:
        try:
            row_view(ref)
            detail_view(CompanyEntry(ticker=entry.ticker, history=(ref,)), ref)
        except (KeyError, TypeError, ValueError, IndexError) as exc:
            log.warning(
                "web.sidecar_skipped",
                ticker=entry.ticker,
                date=ref.date.isoformat(),
                reason=f"incomplete analysis: {exc!r}",
            )
            continue
        kept.append(ref)
    return CompanyEntry(ticker=entry.ticker, history=tuple(kept)) if kept else None


def build(reports_dir: Path, out_dir: Path, base_url: str) -> int:
    """Write the whole site into ``out_dir``; return the number of companies."""
    base_url = normalize_base_url(base_url)
    out = _prepare_out_dir(out_dir, reports_dir)
    entries = [e for e in map(_renderable, scan(reports_dir)) if e is not None]
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
        detail: DetailView | None = None,
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

    def list_page(rows: list[RowView], active: tuple[str, str, str]) -> str:
        """A full list page showing the detail of its own first row."""
        if not rows:
            return list_tpl.render(**context(rows, active))
        entry = by_ticker[rows[0].ticker]
        detail = detail_view(entry, entry.latest)
        return list_tpl.render(**context(rows, active, detail, entry.ticker))

    default_rows = filter_sort(all_rows, *_DEFAULT)
    _write(out / "index.html", list_page(default_rows, _DEFAULT))

    for f in FILTERS:
        for s in SORTS:
            for d in DIRECTIONS:
                rows = filter_sort(all_rows, f, s, d)
                name = f"{f}-{s}-{d}.html"
                _write(out / "rows" / name, rows_tpl.render(**context(rows, (f, s, d))))
                _write(out / "l" / name, list_page(rows, (f, s, d)))

    for entry in entries:
        _write_company(out, entry, default_rows, context, list_tpl, detail_tpl)

    _copy_static(out)
    return len(entries)


def _write_company(
    out: Path,
    entry: CompanyEntry,
    default_rows: list[RowView],
    context: Callable[..., dict[str, Any]],
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
