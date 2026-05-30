"""Render an :class:`Analysis` as a self-contained HTML report (spec §6.5, M6.1).

The §7.7 analysis already renders to Markdown (:mod:`bot.reporting.analysis_report`).
This module is the one place that turns that report into a single, self-contained
HTML file: the Markdown is converted to HTML (tables included) and a Matplotlib
*tornado* chart is rendered to PNG and inlined as a ``data:`` URI, so the file
opens in a browser via ``xdg-open`` with no external assets to fetch.

The chart is a faithful picture of the textual tornado of M4.3
(:func:`bot.valuator.sensitivity.tornado`): it reads the *same* ordered
:class:`~bot.valuator.sensitivity.TornadoEntry` list the Markdown table renders,
so the bars share the table's ordering (descending by impact) and values
(``intrinsic_low``/``intrinsic_high`` per axis).

Everything here is pure: :func:`render_analysis_html` takes an :class:`Analysis`
and returns a string; writing the file to disk is the CLI's job.
"""

from __future__ import annotations

import base64
from collections.abc import Sequence
from datetime import date
from io import BytesIO

import markdown as md_lib
import matplotlib

# Use the non-interactive Agg backend: this runs head-less (CI, xdg-open user),
# never opens a window, and must be selected before pyplot is imported.
matplotlib.use("Agg")

import matplotlib.pyplot as plt

from bot.reporting.analysis_report import render_analysis
from bot.valuator.analysis import Analysis
from bot.valuator.sensitivity import TornadoEntry

#: Markdown extensions: ``tables`` for the §7.7 grids, ``fenced_code`` for safety.
_MD_EXTENSIONS = ("tables", "fenced_code", "sane_lists")

#: Minimal print-friendly stylesheet, inlined so the file stays self-contained.
_STYLE = """
:root { color-scheme: light dark; }
body {
  font-family: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
  max-width: 56rem;
  margin: 2rem auto;
  padding: 0 1.25rem;
  line-height: 1.55;
}
h1, h2, h3 { line-height: 1.25; }
table { border-collapse: collapse; margin: 0.75rem 0; }
th, td { border: 1px solid #8884; padding: 0.3rem 0.6rem; text-align: right; }
th:first-child, td:first-child { text-align: left; }
img.tornado { max-width: 100%; height: auto; margin: 1rem 0; }
code, pre { font-family: ui-monospace, "SFMono-Regular", Menlo, monospace; }
""".strip()


def tornado_chart_png(tornado: Sequence[TornadoEntry]) -> bytes:
    """Render the tornado sensitivity chart to PNG bytes (spec §7.4, M4.3).

    Draws one horizontal bar per :class:`TornadoEntry`, spanning from the axis's
    intrinsic value at -20% to its value at +20%. The entries are plotted in the
    order given — :func:`bot.valuator.sensitivity.tornado` returns them descending
    by impact — with the widest bar at the top, so the chart and the Markdown
    table share ordering and values.

    Args:
        tornado: The ordered tornado entries from the analysis.

    Returns:
        The chart encoded as PNG image bytes.
    """
    # Top-to-bottom = widest-to-narrowest: reverse so y=0 (top) is the first entry.
    entries = list(tornado)
    labels = [entry.axis.value for entry in entries][::-1]
    lows = [entry.intrinsic_low for entry in entries][::-1]
    highs = [entry.intrinsic_high for entry in entries][::-1]

    positions = range(len(entries))
    lefts = [min(low, high) for low, high in zip(lows, highs, strict=True)]
    widths = [abs(high - low) for low, high in zip(lows, highs, strict=True)]

    fig, ax = plt.subplots(figsize=(8.0, 0.5 * len(entries) + 1.5), dpi=120)
    try:
        ax.barh(list(positions), widths, left=lefts, color="#3b7dd8", height=0.6)
        ax.set_yticks(list(positions))
        ax.set_yticklabels(labels)
        ax.set_xlabel("Intrinsic value per share (±20% per assumption)")
        ax.set_title("Sensitivity — tornado (ranked by impact)")
        ax.grid(axis="x", linestyle=":", alpha=0.4)
        fig.tight_layout()
        buffer = BytesIO()
        fig.savefig(buffer, format="png")
    finally:
        plt.close(fig)
    return buffer.getvalue()


def _data_uri(png: bytes) -> str:
    encoded = base64.b64encode(png).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def render_analysis_html(analysis: Analysis, *, generated_on: date | None = None) -> str:
    """Render ``analysis`` as a self-contained HTML report (M6.1).

    The §7.7 Markdown report is converted to HTML and a base64-inlined tornado
    chart (matching the textual one) is injected after the Sensitivity section's
    table. The result references no external assets.

    Args:
        analysis: The completed analysis to render.
        generated_on: Date stamped in the report header; defaults to today.

    Returns:
        A complete, self-contained HTML document as a string.
    """
    report_md = render_analysis(analysis, generated_on=generated_on)
    body = md_lib.markdown(report_md, extensions=list(_MD_EXTENSIONS), output_format="html")

    chart_img = (
        f'<img class="tornado" alt="Tornado sensitivity chart for {analysis.ticker}" '
        f'src="{_data_uri(tornado_chart_png(analysis.tornado))}">'
    )

    return (
        "<!doctype html>\n"
        '<html lang="en">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{analysis.ticker} — analysis</title>\n"
        f"<style>\n{_STYLE}\n</style>\n"
        "</head>\n"
        "<body>\n"
        f"{body}\n"
        f"{chart_img}\n"
        "</body>\n"
        "</html>\n"
    )
