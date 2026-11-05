"""``bot.utils.finance.cagr``: undefined is ``None``, never ``0.0`` or complex (#215)."""

from __future__ import annotations

import pytest

from bot.utils.finance import cagr


@pytest.mark.parametrize(
    "series",
    [
        pytest.param((100.0, -50.0), id="negative-last"),
        pytest.param((100.0, -50.0, -20.0), id="negative-last-two-periods"),
        pytest.param((100.0, 0.0), id="zero-last"),
        pytest.param((0.0, 10.0), id="zero-first"),
        pytest.param((10.0,), id="one-point"),
        pytest.param((), id="empty"),
    ],
)
def test_cagr_is_none_when_undefined(series: tuple[float, ...]) -> None:
    rate = cagr(series)
    assert rate is None
    assert not isinstance(rate, complex)


def test_cagr_of_one_period() -> None:
    assert cagr((100.0, 121.0)) == pytest.approx(0.21)


def test_cagr_of_a_sawtooth_is_geometric_not_the_mean_of_yearly_growth() -> None:
    assert cagr((100.0, 150.0, 100.0, 150.0)) == pytest.approx(1.5 ** (1 / 3) - 1)
    assert cagr((100.0, 150.0, 100.0, 150.0)) == pytest.approx(0.1447, abs=1e-4)


def test_cagr_reads_only_the_endpoints() -> None:
    assert cagr((100.0, -50.0, 121.0)) == pytest.approx(0.1)
