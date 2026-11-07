"""Tests for parse_statement: positions, cash and trades from a Flex statement (#256)."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from bot.ingest.ibkr import CashBalance, PortfolioPosition, TradeExecution
from bot.ingest.ibkr_flex import FlexError, parse_statement

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ibkr_flex" / "statement_sample.xml"
NY = ZoneInfo("America/New_York")


def _stmt(
    account: str = "U1",
    *,
    positions: str | None = "",
    cash: str | None = "",
    trades: str | None = "",
    to_date: str = "20261106",
) -> str:
    parts = [f'<FlexStatement accountId="{account}" fromDate="20261030" toDate="{to_date}">']
    for tag, body in (("OpenPositions", positions), ("CashReport", cash), ("Trades", trades)):
        if body is not None:
            parts.append(f"<{tag}>{body}</{tag}>")
    parts.append("</FlexStatement>")
    return "".join(parts)


def _doc(*statements: str) -> str:
    return (
        '<FlexQueryResponse queryName="q" type="AF"><FlexStatements>'
        + "".join(statements)
        + "</FlexStatements></FlexQueryResponse>"
    )


def _pos(
    account: str = "U1",
    symbol: str = "AAPL",
    *,
    conid: str = "265598",
    position: str = "100",
    cost: str = "150.5",
    report: str = "20261106",
    level: str | None = "SUMMARY",
) -> str:
    lod = f' levelOfDetail="{level}"' if level is not None else ""
    return (
        f'<OpenPosition accountId="{account}" conid="{conid}" symbol="{symbol}" '
        f'assetCategory="STK" currency="USD" listingExchange="NASDAQ" position="{position}" '
        f'costBasisPrice="{cost}" reportDate="{report}"{lod} />'
    )


def _trade(
    *,
    level: str = "EXECUTION",
    date_time: str | None = "20261105;093000",
    order_id: str = "42",
    exec_id: str = "E1",
) -> str:
    dt = f' dateTime="{date_time}"' if date_time is not None else ""
    return (
        f'<Trade accountId="U1" conid="265598" symbol="AAPL" assetCategory="STK" '
        f'currency="USD" buySell="BUY" quantity="10" tradePrice="171.5"{dt} '
        f'ibExecID="{exec_id}" ibOrderID="{order_id}" levelOfDetail="{level}" />'
    )


def test_positions_long_short_per_account() -> None:
    xml = _doc(
        _stmt("U1", positions=_pos("U1", "AAPL") + _pos("U1", "TSLA", conid="76", position="-20", cost="240")),
        _stmt("U2", positions=_pos("U2", "KO", conid="8894", position="50", cost="60")),
    )
    result = parse_statement(xml, tz=NY)
    assert result.accounts == ["U1", "U2"]
    assert result.positions == [
        PortfolioPosition("U1", 265598, "AAPL", "STK", "USD", "NASDAQ", 100.0, 150.5),
        PortfolioPosition("U1", 76, "TSLA", "STK", "USD", "NASDAQ", -20.0, 240.0),
        PortfolioPosition("U2", 8894, "KO", "STK", "USD", "NASDAQ", 50.0, 60.0),
    ]


def test_cash_skips_base_summary() -> None:
    cash = (
        '<CashReportCurrency accountId="U1" currency="BASE_SUMMARY" endingCash="9" levelOfDetail="Currency" />'
        '<CashReportCurrency accountId="U1" currency="USD" endingCash="1234.5" levelOfDetail="Currency" />'
        '<CashReportCurrency accountId="U1" currency="EUR" endingCash="7" levelOfDetail="Summary" />'
    )
    result = parse_statement(_doc(_stmt(cash=cash)), tz=NY)
    assert result.cash == [CashBalance("U1", "USD", 1234.5)]


def test_trades_only_executions() -> None:
    order = '<Order accountId="U1" conid="1" levelOfDetail="ORDER" dateTime="20261105;093000" />'
    trades = _trade() + _trade(level="ORDER") + _trade(level="CLOSED_LOT") + order
    result = parse_statement(_doc(_stmt(trades=trades)), tz=NY)
    assert result.trades == [
        TradeExecution(
            account="U1",
            exec_id="E1",
            con_id=265598,
            symbol="AAPL",
            sec_type="STK",
            currency="USD",
            side="BUY",
            quantity=10.0,
            price=171.5,
            executed_at=datetime(2026, 11, 5, 14, 30, tzinfo=UTC),
            perm_id=42,
        )
    ]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("20261105;093000", datetime(2026, 11, 5, 14, 30, tzinfo=UTC)),
        ("20261030;093000", datetime(2026, 10, 30, 13, 30, tzinfo=UTC)),
    ],
)
def test_trade_time_zone_conversion(raw: str, expected: datetime) -> None:
    result = parse_statement(_doc(_stmt(trades=_trade(date_time=raw))), tz=NY)
    executed_at = result.trades[0].executed_at
    assert executed_at == expected
    assert executed_at.utcoffset() == UTC.utcoffset(None)


def test_bad_trade_datetime_raises() -> None:
    xml = _doc(_stmt(trades=_trade(date_time="2026-11-05 09:30:00")))
    with pytest.raises(FlexError, match=r"yyyyMMdd;HHmmss"):
        parse_statement(xml, tz=NY)


def test_absent_trade_datetime_raises() -> None:
    with pytest.raises(FlexError, match="dateTime"):
        parse_statement(_doc(_stmt(trades=_trade(date_time=None))), tz=NY)


@pytest.mark.parametrize("section", ["OpenPositions", "CashReport", "Trades"])
def test_missing_section_raises(section: str) -> None:
    kwargs = {"positions": "", "cash": "", "trades": ""}
    key = {"OpenPositions": "positions", "CashReport": "cash", "Trades": "trades"}[section]
    kwargs[key] = None  # type: ignore[assignment]
    with pytest.raises(FlexError, match=section):
        parse_statement(_doc(_stmt(**kwargs)), tz=NY)  # type: ignore[arg-type]


def test_empty_open_positions_is_flat_book() -> None:
    xml = _doc(_stmt().replace("<OpenPositions></OpenPositions>", "<OpenPositions />"))
    result = parse_statement(xml, tz=NY)
    assert result.positions == []


def test_as_of_is_max_report_date() -> None:
    xml = _doc(
        _stmt("U1", positions=_pos("U1", report="20261105")),
        _stmt("U2", positions=_pos("U2", "KO", report="20261106")),
        _stmt("U3", to_date="20261101"),
    )
    assert parse_statement(xml, tz=NY).as_of == date(2026, 11, 6)


def test_as_of_fallback_to_date() -> None:
    xml = _doc(_stmt(to_date="20261106"))
    assert parse_statement(xml, tz=NY).as_of == date(2026, 11, 6)


def test_as_of_missing_raises() -> None:
    xml = _doc(_stmt(to_date=""))
    with pytest.raises(FlexError, match=r"reportDate|toDate"):
        parse_statement(xml, tz=NY)


def test_empty_order_id_is_zero() -> None:
    result = parse_statement(_doc(_stmt(trades=_trade(order_id=""))), tz=NY)
    assert result.trades[0].perm_id == 0


def test_bad_number_raises() -> None:
    with pytest.raises(FlexError, match="position"):
        parse_statement(_doc(_stmt(positions=_pos(position=""))), tz=NY)


def test_position_without_conid_raises() -> None:
    with pytest.raises(FlexError, match="conid"):
        parse_statement(_doc(_stmt(positions=_pos(conid=""))), tz=NY)


def test_lot_rows_skipped() -> None:
    positions = _pos(level="SUMMARY") + _pos(level="LOT") + _pos(level="LOT")
    result = parse_statement(_doc(_stmt(positions=positions)), tz=NY)
    assert len(result.positions) == 1


def test_position_without_level_of_detail_is_kept() -> None:
    result = parse_statement(_doc(_stmt(positions=_pos(level=None))), tz=NY)
    assert len(result.positions) == 1


def test_fixture_parses() -> None:
    result = parse_statement(FIXTURE.read_text(encoding="utf-8"), tz=NY)
    assert result.accounts == ["U1234567", "U7654321"]
    assert result.as_of == date(2026, 9, 30)
    assert [r.action_id for r in result.corporate_actions] == [
        "ca:1001", "ca:1002", "ca:1003", "ct:2001", "ct:2003",
    ]
    assert result.positions == [
        PortfolioPosition("U1234567", 265598, "AAPL", "STK", "USD", "NASDAQ", 100.0, 150.25),
        PortfolioPosition("U1234567", 76792991, "TSLA", "STK", "USD", "NASDAQ", -20.0, 240.0),
        PortfolioPosition("U7654321", 8894, "KO", "STK", "USD", "NYSE", 50.0, 60.0),
    ]
    assert result.cash == [
        CashBalance("U1234567", "USD", 12345.67),
        CashBalance("U1234567", "EUR", 500.0),
        CashBalance("U7654321", "USD", 1000.0),
    ]
    assert [(t.symbol, t.side, t.quantity, t.price, t.executed_at, t.perm_id) for t in result.trades] == [
        ("AAPL", "BUY", 100.0, 150.25, datetime(2026, 9, 15, 13, 35, tzinfo=UTC), 1234567890),
        ("TSLA", "SELL", -20.0, 240.0, datetime(2026, 9, 29, 19, 30, tzinfo=UTC), 1234567891),
    ]
