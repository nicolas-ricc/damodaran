"""``bot.utils.finance.cagr``: undefined is ``None``, never ``0.0`` or complex (#215)."""

from __future__ import annotations

import pytest

from bot.utils.finance import cagr, latest_contiguous_run


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


# --------------------------------------------------------------------------- #
# latest_contiguous_run (#125)                                                 #
# --------------------------------------------------------------------------- #


def test_years_apart_yield_only_the_latest_point() -> None:
    run = latest_contiguous_run([(2013, 100.0), (2019, 300.0)])
    assert run == (300.0,)
    assert cagr(run) is None


def test_null_in_the_middle_keeps_only_the_years_after_it() -> None:
    run = latest_contiguous_run(
        [(2015, 100.0), (2016, 110.0), (2017, None), (2018, 200.0), (2019, 220.0)]
    )
    assert run == (200.0, 220.0)
    assert cagr(run) == pytest.approx(0.1)  # one period


def test_contiguous_series_is_unchanged() -> None:
    assert latest_contiguous_run([(2020, 1.0), (2021, 2.0), (2022, 4.0)]) == (1.0, 2.0, 4.0)


def test_trailing_null_is_skipped() -> None:
    points = [(2016, 1.0), (2017, 2.0), (2018, 3.0), (2019, None)]
    assert latest_contiguous_run(points) == (1.0, 2.0, 3.0)


def test_no_values_yield_an_empty_run() -> None:
    assert latest_contiguous_run([]) == ()
    assert latest_contiguous_run([(2020, None), (2021, None)]) == ()
