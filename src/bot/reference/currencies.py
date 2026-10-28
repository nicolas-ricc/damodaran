"""The curated per-currency risk-free / nominal-GDP table (ADR 0005 §4, #109).

``config/currencies.yaml`` is hand-curated: Damodaran's January table of
risk-free rates by currency (government bond rate net of the rating-based
default spread) and IMF WEO nominal-GDP growth. The loader is a pure
``path -> mapping`` function that degrades to an empty mapping when the file is
missing or malformed (spec §13.2) and fails loudly on out-of-range values.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import MappingProxyType
from typing import Any

import structlog
import yaml

log = structlog.get_logger(__name__)

DEFAULT_CURRENCIES_PATH = Path("config/currencies.yaml")

#: Open intervals: a value equal to a bound is rejected.
_RFR_BOUNDS = (-0.05, 0.30)
_GDP_BOUNDS = (-0.05, 0.25)

_CODE_RE = re.compile(r"[A-Z]{3}")
_FIELDS = ("risk_free_rate", "nominal_gdp_growth", "source", "gdp_source", "as_of")


@dataclass(frozen=True)
class CurrencyRates:
    """Risk-free rate and nominal GDP growth for one currency, as decimals."""

    risk_free_rate: float
    nominal_gdp_growth: float
    source: str
    gdp_source: str
    as_of: date


type CurrencyTable = Mapping[str, CurrencyRates]


def normalize_currency(code: str | None) -> str | None:
    """Strip and upper-case a currency code; blank or ``None`` gives ``None``."""
    if code is None:
        return None
    text = code.strip().upper()
    return text or None


class _MalformedError(Exception):
    pass


def _number(raw: Any, code: str, field: str) -> float:
    if isinstance(raw, bool) or not isinstance(raw, int | float):
        raise _MalformedError(f"{code}.{field}: not a number")
    return float(raw)


def _text(raw: Any, code: str, field: str) -> str:
    if not isinstance(raw, str) or not raw.strip():
        raise _MalformedError(f"{code}.{field}: missing or not a string")
    return raw.strip()


def _date(raw: Any, code: str) -> date:
    if isinstance(raw, date):
        return raw
    if isinstance(raw, str):
        try:
            return date.fromisoformat(raw.strip())
        except ValueError:
            pass
    raise _MalformedError(f"{code}.as_of: not a date")


def _check_bounds(
    path: Path, code: str, field: str, value: float, bounds: tuple[float, float]
) -> None:
    low, high = bounds
    if not low < value < high:
        raise ValueError(
            f"{path}: {code} {field}={value} outside the open interval ({low}, {high}); "
            "values are decimals (0.042, not 4.2)"
        )


def _parse(path: Path, data: Any) -> dict[str, CurrencyRates]:
    if not isinstance(data, dict):
        raise _MalformedError("top level is not a mapping")
    table: dict[str, CurrencyRates] = {}
    for code, row in data.items():
        if not isinstance(code, str) or not _CODE_RE.fullmatch(code):
            raise _MalformedError(f"key {code!r} is not a three-letter upper-case code")
        if not isinstance(row, dict):
            raise _MalformedError(f"{code}: row is not a mapping")
        for field in _FIELDS:
            if row.get(field) is None:
                raise _MalformedError(f"{code}.{field}: missing")
        rfr = _number(row["risk_free_rate"], code, "risk_free_rate")
        gdp = _number(row["nominal_gdp_growth"], code, "nominal_gdp_growth")
        rates = CurrencyRates(
            risk_free_rate=rfr,
            nominal_gdp_growth=gdp,
            source=_text(row["source"], code, "source"),
            gdp_source=_text(row["gdp_source"], code, "gdp_source"),
            as_of=_date(row["as_of"], code),
        )
        _check_bounds(path, code, "risk_free_rate", rfr, _RFR_BOUNDS)
        _check_bounds(path, code, "nominal_gdp_growth", gdp, _GDP_BOUNDS)
        table[code] = rates
    return table


def load_currency_table(path: Path | None = None) -> CurrencyTable:
    """Load the currency table.

    Args:
        path: YAML location; ``None`` reads :data:`DEFAULT_CURRENCIES_PATH`.

    Returns:
        A read-only mapping, empty (with one warning) when the file is absent or
        malformed.

    Raises:
        ValueError: A ``risk_free_rate`` outside (-0.05, 0.30) or a
            ``nominal_gdp_growth`` outside (-0.05, 0.25).
    """
    target = path if path is not None else DEFAULT_CURRENCIES_PATH
    if not target.exists():
        log.warning("currencies.absent", path=str(target))
        return MappingProxyType({})
    try:
        table = _parse(target, yaml.safe_load(target.read_text()))
    except (yaml.YAMLError, _MalformedError) as exc:
        log.warning("currencies.malformed", path=str(target), reason=str(exc))
        return MappingProxyType({})
    log.info("currencies.loaded", path=str(target), entries=len(table))
    return MappingProxyType(table)
