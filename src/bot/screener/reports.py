"""Report writers for the screener — Markdown + CSV (M3.8)."""

from __future__ import annotations

import csv
from pathlib import Path

from bot.screener.engine import ScreenRun


def _fmt(v: float | None, fmt: str = ".2f", suffix: str = "") -> str:
    return f"{v:{fmt}}{suffix}" if v is not None else "—"


def _fmt_pct(v: float | None) -> str:
    return f"{v:.1%}" if v is not None else "—"


def _fmt_cap(v: float | None) -> str:
    if v is None:
        return "—"
    if v >= 1e12:
        return f"{v / 1e12:.1f}T"
    if v >= 1e9:
        return f"{v / 1e9:.1f}B"
    if v >= 1e6:
        return f"{v / 1e6:.1f}M"
    return f"{v:,.0f}"


_MD_HEADER = (
    "| Rank | Ticker | Name | Score | Value | Quality | Growth | MoS "
    "| Sector | Mkt Cap | P/E | EV/EBITDA | P/BV | ROE | FCF Yield |"
)
_MD_SEP = (
    "|------|--------|------|------:|------:|--------:|-------:|-----:"
    "|--------|--------:|----:|----------:|-----:|----:|----------:|"
)

_CSV_FIELDS = [
    "rank",
    "ticker",
    "name",
    "score",
    "score_value",
    "score_quality",
    "score_growth",
    "score_mos",
    "sector",
    "market_cap",
    "pe_ratio",
    "ev_ebitda",
    "pbv",
    "roe",
    "fcf_yield",
]


def write_markdown(run: ScreenRun, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        f"# Screener Report: {run.preset}",
        "",
        f"**Date:** {run.run_date}  |  **Run ID:** `{run.run_id}`  |  "
        f"**Candidates:** {len(run.candidates)}",
        "",
        _MD_HEADER,
        _MD_SEP,
    ]
    for c in run.candidates:
        sc = c.scored
        km = c.key_metrics
        lines.append(
            f"| {run.candidates.index(c) + 1} "
            f"| {c.ticker} "
            f"| {c.name} "
            f"| {_fmt(sc.composite_score)} "
            f"| {_fmt(sc.value_score)} "
            f"| {_fmt(sc.quality_score)} "
            f"| {_fmt(sc.growth_score)} "
            f"| {_fmt(sc.margin_of_safety)} "
            f"| {c.sector or '—'} "
            f"| {_fmt_cap(km.get('market_cap'))} "
            f"| {_fmt(km.get('pe_ratio'))} "
            f"| {_fmt(km.get('ev_ebitda'))} "
            f"| {_fmt(km.get('pbv'))} "
            f"| {_fmt_pct(km.get('roe'))} "
            f"| {_fmt_pct(km.get('fcf_yield'))} |"
        )
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_csv(run: ScreenRun, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_CSV_FIELDS)
        writer.writeheader()
        for rank_pos, c in enumerate(run.candidates, start=1):
            sc = c.scored
            km = c.key_metrics
            writer.writerow(
                {
                    "rank": rank_pos,
                    "ticker": c.ticker,
                    "name": c.name,
                    "score": sc.composite_score,
                    "score_value": sc.value_score,
                    "score_quality": sc.quality_score,
                    "score_growth": sc.growth_score,
                    "score_mos": sc.margin_of_safety,
                    "sector": c.sector or "",
                    "market_cap": km.get("market_cap") or "",
                    "pe_ratio": km.get("pe_ratio") or "",
                    "ev_ebitda": km.get("ev_ebitda") or "",
                    "pbv": km.get("pbv") or "",
                    "roe": km.get("roe") or "",
                    "fcf_yield": km.get("fcf_yield") or "",
                }
            )


def write_reports(run: ScreenRun, reports_dir: Path) -> tuple[Path, Path]:
    """Write MD + CSV to reports_dir/YYYY-MM-DD/screen/<preset>.{md,csv}.

    Returns (md_path, csv_path).
    """
    base = reports_dir / run.run_date / "screen"
    md_path = base / f"{run.preset}.md"
    csv_path = base / f"{run.preset}.csv"
    write_markdown(run, md_path)
    write_csv(run, csv_path)
    return md_path, csv_path
