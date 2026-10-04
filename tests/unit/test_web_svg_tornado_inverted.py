"""Tornado bars whose low/high are inverted (issue #92)."""

from __future__ import annotations

import re

from bot.web.svg import tornado_svg
from bot.web.views import TornadoBar


def test_inverted_bar_labels_follow_extents() -> None:
    svg = str(
        tornado_svg(
            [TornadoBar("cost_of_equity", 227.91, 103.82), TornadoBar("tax_rate", 150.0, 135.0)],
            price=95.0,
            seed=1,
        )
    )
    xs = {
        m.group(2): float(m.group(1))
        for m in re.finditer(r'<text x="(-?[\d.]+)" y="[\d.]+"[^>]*>([^<]*)</text>', svg)
    }
    assert all(0 <= x <= 640 for x in xs.values())
    assert xs["103.82"] < xs["227.91"]
    assert 'data-role="price"' not in svg
