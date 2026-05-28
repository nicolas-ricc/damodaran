"""Render `bot show <TICKER>` output to a string."""

from __future__ import annotations

from typing import Any


def _fmt_money(value: Any) -> str:
    if value is None:
        return "—"
    if abs(value) >= 1e9:
        return f"{value / 1e9:,.2f}B"
    if abs(value) >= 1e6:
        return f"{value / 1e6:,.2f}M"
    return f"{value:,.0f}"


def format_company_summary(company: dict[str, Any], annual_rows: list[dict[str, Any]]) -> str:
    """Render a plain-text summary of a company and its last N years of annual financials."""
    lines: list[str] = []
    lines.append(f"{company['ticker']} — {company.get('name', '(no name)')}")
    lines.append(
        f"CIK={company.get('cik') or '—'}  "
        f"Country={company.get('country') or '—'}  "
        f"Currency={company.get('currency') or '—'}"
    )
    lines.append("")

    if not annual_rows:
        lines.append("(no financials in DB for this ticker)")
        return "\n".join(lines)

    rows = sorted(annual_rows, key=lambda r: r["fiscal_year"], reverse=True)[:5]
    metrics = [
        ("revenue", "Revenue"),
        ("ebit", "EBIT"),
        ("net_income", "Net Income"),
        ("operating_cashflow", "OCF"),
        ("free_cashflow", "FCF"),
        ("total_debt", "Total Debt"),
        ("cash", "Cash"),
        ("total_assets", "Total Assets"),
        ("total_equity", "Equity"),
    ]
    header = f"{'Metric':<14}" + "".join(f"{r['fiscal_year']:>16}" for r in rows)
    lines.append(header)
    lines.append("-" * len(header))
    for key, label in metrics:
        row_str = f"{label:<14}"
        for r in rows:
            row_str += f"{_fmt_money(r.get(key)):>16}"
        lines.append(row_str)
    return "\n".join(lines)
