"""Transport-neutral IBKR portfolio records (M5).

Plain frozen dataclasses for positions, cash balances and trade executions.
They are filled by :mod:`bot.ingest.ibkr_flex` from a Flex Web Service
statement (ADR 0010, #256); the sync layers in :mod:`bot.portfolio` consume them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class PortfolioPosition:
    """A single open position in an account."""

    account: str
    con_id: int
    symbol: str
    sec_type: str
    currency: str
    exchange: str
    quantity: float
    avg_cost: float


@dataclass(frozen=True)
class CashBalance:
    """A per-currency cash balance for an account."""

    account: str
    currency: str
    amount: float


@dataclass(frozen=True)
class TradeExecution:
    """A single trade execution (fill) in an account."""

    account: str
    exec_id: str
    con_id: int
    symbol: str
    sec_type: str
    currency: str
    side: str
    quantity: float
    price: float
    executed_at: datetime
    perm_id: int
