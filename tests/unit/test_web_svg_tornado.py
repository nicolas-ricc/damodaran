"""Tornado layout edge cases (issue #92)."""

from __future__ import annotations

import re

from bot.web.svg import tornado_svg
from bot.web.views import TornadoBar

NAME_END = 196.0
CHAR_W = 0.6 * 12


def _labels(svg: str) -> dict[str, float]:
    return {
        m.group(2): float(m.group(1))
        for m in re.finditer(r'<text x="(-?[\d.]+)" y="[\d.]+"[^>]*>([^<]*)</text>', svg)
    }


def test_inverted_bar_labels_follow_extents() -> None:
    svg = str(
        tornado_svg(
            [TornadoBar("cost_of_equity", 227.91, 103.82), TornadoBar("tax_rate", 150.0, 135.0)],
            price=95.0,
            seed=1,
        )
    )
    xs = _labels(svg)
    assert all(0 <= x <= 640 for x in xs.values())
    assert xs["103.82"] < xs["227.91"]


def test_price_tick_present_even_outside_bars() -> None:
    bars = [TornadoBar("a", 100.0, 120.0)]
    for price in (95.0, 110.0, 500.0):
        svg = str(tornado_svg(bars, price=price, seed=1))
        assert 'data-role="price"' in svg
        assert all(0 <= x <= 640 for x in _labels(svg).values())
    assert 'data-role="price"' not in str(tornado_svg(bars, price=None, seed=1))


def test_four_digit_low_label_clears_name_column() -> None:
    svg = str(tornado_svg([TornadoBar("tax_rate", 1234.56, 1500.0)], price=None, seed=1))
    m = re.search(r'<text x="([\d.]+)"[^>]*class="val"[^>]*>([^<]*)</text>', svg)
    assert m
    x, text = float(m.group(1)), m.group(2)
    assert x - CHAR_W * len(text) > NAME_END
    assert max(_labels(svg).values()) <= 640
