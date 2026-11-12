"""Broker-symbol overrides: IBKR symbol -> universe ticker (#84, #338).

``config/broker_symbols.yaml`` holds the hand-curated exceptions to the automatic
symbol matching: listings the broker names differently from the universe, and
holdings to ignore (a ``null`` value). The loader is a pure ``path -> mapping``
function that degrades to an empty mapping when the file is missing or
malformed, and never raises.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType
from typing import Any

import structlog
import yaml

log = structlog.get_logger(__name__)

DEFAULT_BROKER_SYMBOLS_PATH = Path("config/broker_symbols.yaml")

#: Upper-cased broker symbol -> upper-cased universe ticker, or ``None`` to ignore.
type BrokerSymbolTable = Mapping[str, str | None]


class _MalformedError(Exception):
    pass


class _UniqueKeyLoader(yaml.SafeLoader):
    """``SafeLoader`` that rejects a repeated key instead of keeping the last one."""

    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Any, Any]:
        seen: set[Any] = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            try:
                hash(key)
            except TypeError:
                raise _MalformedError(f"unhashable key {key!r}") from None
            if key in seen:
                raise _MalformedError(f"duplicate key {key!r}")
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def _parse(data: Any) -> dict[str, str | None]:
    if data is None:
        return {}
    if not isinstance(data, dict):
        raise _MalformedError("top level is not a mapping")
    table: dict[str, str | None] = {}
    for key, value in data.items():
        if not isinstance(key, str) or not key.strip():
            raise _MalformedError(f"key {key!r} is not a non-blank string")
        symbol = key.strip().upper()
        if symbol in table:
            raise _MalformedError(f"duplicate key {symbol!r} after normalisation")
        if value is None:
            table[symbol] = None
        elif isinstance(value, str) and value.strip():
            table[symbol] = value.strip().upper()
        else:
            raise _MalformedError(f"{symbol}: value is not null or a non-blank string")
    return table


def load_broker_symbols(path: Path | None = None) -> BrokerSymbolTable:
    """Load the broker-symbol override table.

    Args:
        path: YAML location; ``None`` reads :data:`DEFAULT_BROKER_SYMBOLS_PATH`.

    Returns:
        A read-only mapping, empty (with one warning) when the file is absent,
        unreadable or malformed. A ``None`` value marks a holding to ignore.
    """
    target = path if path is not None else DEFAULT_BROKER_SYMBOLS_PATH
    if not target.exists():
        log.warning("broker_symbols.absent", path=str(target))
        return MappingProxyType({})
    try:
        table = _parse(yaml.load(target.read_text(), Loader=_UniqueKeyLoader))
    except (yaml.YAMLError, _MalformedError, OSError, UnicodeDecodeError) as exc:
        log.warning("broker_symbols.malformed", path=str(target), reason=str(exc))
        return MappingProxyType({})
    log.info("broker_symbols.loaded", path=str(target), entries=len(table))
    return MappingProxyType(table)
