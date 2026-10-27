"""Drivers table layout edge cases (issue #92)."""

from __future__ import annotations

import re

from bot.web.svg import tornado_table
from bot.web.views import TornadoBar


def _rects(html: str) -> list[tuple[float, float]]:
    return [
        (float(m.group(1)), float(m.group(2)))
        for m in re.finditer(r'<rect x="(-?[\d.]+)" y="2" width="(-?[\d.]+)"', html)
    ]


def _price_x(html: str) -> list[float]:
    return [
        float(m.group(1)) for m in re.finditer(r'<line x1="(-?[\d.]+)"[^>]*data-role="price"', html)
    ]


def test_bars_stay_inside_the_track() -> None:
    html = str(
        tornado_table(
            [TornadoBar("cost_of_equity", 227.91, 103.82), TornadoBar("tax_rate", 150.0, 135.0)],
            price=95.0,
        )
    )
    for x, width in _rects(html):
        assert 0 <= x <= 100
        assert 0 <= x + width <= 100
        assert width > 0


def test_price_line_present_in_every_row_even_outside_bars() -> None:
    bars = [TornadoBar("a", 100.0, 120.0), TornadoBar("b", 110.0, 115.0)]
    for price in (95.0, 110.0, 500.0):
        html = str(tornado_table(bars, price=price))
        xs = _price_x(html)
        assert len(xs) == 2
        assert all(0 <= x <= 100 for x in xs)
        assert len(set(xs)) == 1
    assert 'data-role="price"' not in str(tornado_table(bars, price=None))
    assert "price 110.00" in str(tornado_table(bars, price=110.0))


def test_low_and_high_are_real_text_cells() -> None:
    html = str(tornado_table([TornadoBar("tax_rate", 1234.56, 1500.0)], price=None))
    assert '<td class="num low">1,234.56</td>' in html
    assert '<td class="num high">1,500.00</td>' in html
    assert '<th scope="row">tax_rate</th>' in html
