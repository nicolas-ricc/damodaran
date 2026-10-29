"""Redaction and type summary of a Flex statement (#138), over the synthetic sample.

Both functions are pure: the capture command of #139 feeds them the live
statement; here they only see ``statement_sample.xml`` and inline snippets.
"""

from __future__ import annotations

import dataclasses
import functools
import json
import re
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote, quote_plus

import httpx
import pytest
import vcr
import yaml
from click.testing import Result
from typer.testing import CliRunner

from bot import cli
from bot.config import Settings
from bot.ingest import ibkr_flex, ibkr_flex_capture
from bot.ingest.ibkr_flex import CorporateActionRecord, FlexError, parse_flex_statement
from bot.ingest.ibkr_flex_capture import (
    REDACTED_ACCOUNT,
    FlexSummary,
    _fake_number,
    redact_statement,
    summarize_statement,
)

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "ibkr_flex" / "statement_sample.xml"
MONEY_KEYS = ("amount", "proceeds", "quantity", "value")


@pytest.fixture
def sample() -> str:
    return FIXTURE.read_text(encoding="utf-8")


@pytest.fixture
def redacted(sample: str) -> str:
    return redact_statement(sample)


def _decimals(value: str) -> int:
    return len(value.split(".", 1)[1]) if "." in value else 0


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("75.00", "10.00"),
        ("-11.25", "-10.00"),
        ("48.50", "10.00"),
        ("4750", "1000"),
        ("-700", "-100"),
        ("300", "100"),
        ("-50", "-10"),
        ("1.00", "1.00"),
        ("0", "0"),
        ("0.75", "0.10"),
        ("", ""),
        ("-0.00", "-0.00"),
        ("-0.75", "-0.10"),
        ("1E+3", "1000"),
        ("1.5E+3", "1000"),
        ("7.5E-3", "0.1000"),
        ("007", "1"),
        ("1,234.56", "1,234.56"),
        ("abc", "abc"),
        (" 75.00 ", "10.00"),
        ("1E+5000", "1" + "0" * 5000),
    ],
)
def test_fake_number(value: str, expected: str) -> None:
    assert _fake_number(value) == expected


@pytest.mark.parametrize("value", ["NaN", "Infinity", "-Infinity", "sNaN"])
def test_fake_number_leaves_non_finite_unchanged(value: str) -> None:
    assert _fake_number(value) == value


def test_redaction_is_deterministic(sample: str, redacted: str) -> None:
    assert redact_statement(sample) == redacted
    assert redacted.startswith('<?xml version="1.0" encoding="UTF-8"?>\n')
    assert redacted.endswith("\n")


def test_redaction_leaves_only_placeholder_account(redacted: str) -> None:
    assert REDACTED_ACCOUNT == "U0000000"
    assert set(re.findall(r"\bU\d{6,9}\b", redacted)) == {"U0000000"}


def test_redacted_output_reparses(redacted: str) -> None:
    assert ET.fromstring(redacted).tag == "FlexQueryResponse"


def test_redaction_preserves_records(sample: str, redacted: str) -> None:
    original = parse_flex_statement(sample)
    after = parse_flex_statement(redacted)

    def key(r: CorporateActionRecord) -> tuple[object, ...]:
        return (r.action_id, r.action_type, r.ticker, r.effective_date, r.details["description"])

    assert [key(r) for r in after] == [key(r) for r in original]
    assert {r.account for r in after} == {"U0000000"}


def test_redaction_preserves_sign_and_shape(sample: str, redacted: str) -> None:
    pairs = list(zip(parse_flex_statement(sample), parse_flex_statement(redacted), strict=True))
    checked = 0
    for before, after in pairs:
        for k in MONEY_KEYS:
            if k not in before.details:
                continue
            old, new = before.details[k], after.details[k]
            assert new.startswith("-") == old.startswith("-"), (k, old, new)
            assert _decimals(new) == _decimals(old), (k, old, new)
            checked += 1
    assert checked > 0
    by_id = {r.action_id: r for r in parse_flex_statement(redacted)}
    assert by_id["ca:1002"].details["quantity"] == "-100"
    assert by_id["ct:2001"].details["amount"] == "10.00"


def test_redaction_blanks_alias() -> None:
    xml = (
        '<FlexQueryResponse><FlexStatements count="1">'
        '<FlexStatement accountId="U1234567" acctAlias="Mine" />'
        "</FlexStatements></FlexQueryResponse>"
    )
    statement = ET.fromstring(redact_statement(xml)).find(".//FlexStatement")
    assert statement is not None
    assert statement.get("acctAlias") == ""
    assert statement.get("accountId") == "U0000000"


def test_redact_rejects_other_root() -> None:
    with pytest.raises(ValueError, match="expected a FlexQueryResponse, got Foo"):
        redact_statement("<Foo/>")


SAMPLE_SUMMARY = FlexSummary(
    accounts=2,
    from_date="2026-09-01",
    to_date="2026-09-30",
    rows=7,
    corporate_action_types={"FS": 1, "RS": 1, "TC": 1},
    cash_transaction_types={
        "Dividends": 2,
        "Payment In Lieu Of Dividends": 1,
        "Withholding Tax": 1,
    },
    parsed=5,
    parsed_by_action_type={"dividend": 2, "split": 2, "tc": 1},
    skipped={"CashTransaction/Dividends": 1, "CashTransaction/Withholding Tax": 1},
)


def test_summary_of_sample(sample: str) -> None:
    assert summarize_statement(sample) == SAMPLE_SUMMARY


def test_summary_survives_redaction(redacted: str) -> None:
    assert summarize_statement(redacted) == SAMPLE_SUMMARY


def test_summary_dict_keys_sorted(sample: str) -> None:
    for value in dataclasses.asdict(summarize_statement(sample)).values():
        if isinstance(value, dict):
            assert list(value) == sorted(value)


def test_to_json_round_trips(sample: str) -> None:
    summary = summarize_statement(sample)
    text = summary.to_json()
    assert json.loads(text) == dataclasses.asdict(summary)
    assert text.endswith("\n")


def test_summary_dates_none_when_absent() -> None:
    xml = (
        "<FlexQueryResponse><FlexStatements>"
        '<FlexStatement accountId="U1" />'
        "</FlexStatements></FlexQueryResponse>"
    )
    summary = summarize_statement(xml)
    assert (summary.from_date, summary.to_date) == (None, None)
    assert (summary.accounts, summary.rows) == (1, 0)


def test_summary_dates_tolerate_padding() -> None:
    xml = (
        "<FlexQueryResponse><FlexStatements>"
        '<FlexStatement accountId="U1" fromDate=" 20260901" toDate="20260930 " />'
        "</FlexStatements></FlexQueryResponse>"
    )
    summary = summarize_statement(xml)
    assert (summary.from_date, summary.to_date) == ("2026-09-01", "2026-09-30")


def test_summary_missing_type_counts_under_empty() -> None:
    xml = (
        "<FlexQueryResponse><FlexStatements>"
        '<FlexStatement accountId="U1" fromDate="20260901" toDate="20260930">'
        '<CorporateActions><CorporateAction symbol="X" actionID="9" /></CorporateActions>'
        "</FlexStatement></FlexStatements></FlexQueryResponse>"
    )
    assert summarize_statement(xml).corporate_action_types == {"": 1}


def test_summarize_rejects_other_root() -> None:
    with pytest.raises(ValueError, match="expected a FlexQueryResponse, got Foo"):
        summarize_statement("<Foo/>")


TOKEN = "1234567890/abc+def=4567"  # not purely alphanumeric: httpx percent-encodes it in URLs
FORMS = (TOKEN, quote(TOKEN, safe=""), quote_plus(TOKEN, safe=""))
QUERY = "987654"
GET_URL = "https://ndcdyn.interactivebrokers.com/AccountManagement/FlexWebService/GetStatement"
SUCCESS = (
    "<FlexStatementResponse><Status>Success</Status><ReferenceCode>1234567890</ReferenceCode>"
    f"<Url>{GET_URL}</Url></FlexStatementResponse>"
)


def _error(status: str, code: str, message: str) -> str:
    return (
        f"<FlexStatementResponse><Status>{status}</Status>"
        f"<ErrorCode>{code}</ErrorCode><ErrorMessage>{message}</ErrorMessage>"
        "</FlexStatementResponse>"
    )


@pytest.fixture(autouse=True)
def _no_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ibkr_flex, "POLL_DELAY_SECONDS", 0.0)


def _transport(statement: str, send_body: str = SUCCESS) -> httpx.MockTransport:
    """SendRequest succeeds, GetStatement answers 1019 once, then *statement*."""
    bodies = iter([_error("Warn", "1019", "Statement generation in progress."), statement])

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/SendRequest"):
            return httpx.Response(200, text=send_body)
        return httpx.Response(200, text=next(bodies))

    return httpx.MockTransport(handler)


def _flex_settings(token: str = TOKEN, query_id: str = QUERY) -> Settings:
    return Settings(
        sec_user_agent="Test test@example.com",
        ibkr_flex_token=token,
        ibkr_flex_query_id=query_id,
        _env_file=None,  # type: ignore[call-arg]
    )


def _files(root: Path) -> set[Path]:
    return {p.relative_to(root) for p in root.rglob("*") if p.is_file()}


@pytest.fixture
def captured(sample: str, tmp_path: Path) -> FlexSummary:
    return ibkr_flex_capture.capture(_flex_settings(), root=tmp_path, transport=_transport(sample))


def test_fetch_flex_statement_returns_the_statement(sample: str) -> None:
    assert ibkr_flex.fetch_flex_statement(TOKEN, QUERY, transport=_transport(sample)) == sample


def test_capture_writes_exactly_the_three_paths(captured: FlexSummary, tmp_path: Path) -> None:
    assert _files(tmp_path) == {
        ibkr_flex_capture.CASSETTE_PATH,
        ibkr_flex_capture.REDACTED_XML_PATH,
        ibkr_flex_capture.SUMMARY_PATH,
    }
    assert Path("tests/fixtures/cassettes/ibkr_flex/statement_real.yaml") == ibkr_flex_capture.CASSETTE_PATH
    assert Path("tests/fixtures/ibkr_flex/statement_real_redacted.xml") == ibkr_flex_capture.REDACTED_XML_PATH
    assert Path("tests/fixtures/ibkr_flex/statement_real_summary.json") == ibkr_flex_capture.SUMMARY_PATH


def test_capture_cassette_is_scrubbed_and_redacted(captured: FlexSummary, tmp_path: Path) -> None:
    text = (tmp_path / ibkr_flex_capture.CASSETTE_PATH).read_text(encoding="utf-8")
    assert text.startswith(
        "# Recorded by bot flex-capture (#110): the Flex token is scrubbed and the statement is redacted.\n"
    )
    assert "t=SCRUBBED" in text
    for form in FORMS:
        assert form not in text
    assert "U1234567" not in text
    assert "U7654321" not in text
    cassette = yaml.safe_load(text)
    assert cassette["version"] == 1
    assert len(cassette["interactions"]) == 3


def test_capture_writes_redacted_xml_and_summary(sample: str, captured: FlexSummary, tmp_path: Path) -> None:
    redacted_text = (tmp_path / ibkr_flex_capture.REDACTED_XML_PATH).read_text(encoding="utf-8")
    summary_text = (tmp_path / ibkr_flex_capture.SUMMARY_PATH).read_text(encoding="utf-8")
    assert redacted_text == redact_statement(sample)
    assert summary_text == summarize_statement(sample).to_json()


def test_capture_returns_the_summary(sample: str, captured: FlexSummary) -> None:
    assert captured == summarize_statement(sample)


def test_capture_cassette_replays_through_vcr(sample: str, captured: FlexSummary, tmp_path: Path) -> None:
    path = tmp_path / ibkr_flex_capture.CASSETTE_PATH
    replayer = vcr.VCR(record_mode="none", filter_query_parameters=[("t", "SCRUBBED")])
    with replayer.use_cassette(str(path)):
        statement = ibkr_flex.fetch_flex_statement(TOKEN, QUERY)
    records = parse_flex_statement(statement)
    assert [r.action_id for r in records] == [r.action_id for r in parse_flex_statement(sample)]
    assert len(records) == 5
    assert {r.account for r in records} == {"U0000000"}


def test_capture_refuses_a_cassette_carrying_the_token(sample: str, tmp_path: Path) -> None:
    leaky = sample.replace("SPLIT 4 FOR 1", f"SPLIT 4 FOR 1 {TOKEN}")
    assert TOKEN in leaky
    with pytest.raises(ibkr_flex_capture.FlexCaptureError, match="token found in the rendered cassette"):
        ibkr_flex_capture.capture(_flex_settings(), root=tmp_path, transport=_transport(leaky))
    assert list(tmp_path.iterdir()) == []


def test_capture_propagates_flex_error_and_writes_nothing(sample: str, tmp_path: Path) -> None:
    transport = _transport(sample, send_body=_error("Fail", "1012", "Token has expired."))
    with pytest.raises(FlexError, match="1012"):
        ibkr_flex_capture.capture(_flex_settings(), root=tmp_path, transport=transport)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(("token", "query_id"), [("", ""), (TOKEN, ""), ("", QUERY), ("  ", QUERY)])
def test_capture_missing_settings_writes_nothing(tmp_path: Path, token: str, query_id: str) -> None:
    with pytest.raises(ibkr_flex_capture.FlexCaptureError) as excinfo:
        ibkr_flex_capture.capture(
            _flex_settings(token, query_id), root=tmp_path, transport=httpx.MockTransport(_refuse)
        )
    assert str(excinfo.value) == (
        "BOT_IBKR_FLEX_TOKEN and BOT_IBKR_FLEX_QUERY_ID must both be set (put them in .env); "
        "nothing was written"
    )
    assert excinfo.value.exit_code == 2
    assert list(tmp_path.iterdir()) == []


def _refuse(request: httpx.Request) -> httpx.Response:
    raise AssertionError("no HTTP call expected")


def _record(
    handler: Callable[[httpx.Request], httpx.Response],
) -> list[ibkr_flex_capture.Interaction]:
    recorder = ibkr_flex_capture.RecordingTransport(httpx.MockTransport(handler))
    with httpx.Client(transport=recorder) as client:
        client.get(f"{GET_URL}?q=1&t={quote(TOKEN, safe='')}&v=3")
    return list(recorder.interactions)


def test_render_cassette_keeps_only_content_type() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            headers={"Content-Type": "text/xml", "Set-Cookie": "s=1", "X-Other": "x"},
            text=SUCCESS,
        )

    interactions = _record(handler)
    text = ibkr_flex_capture.render_cassette(interactions, token=TOKEN)
    (interaction,) = yaml.safe_load(text)["interactions"]
    assert interaction["request"]["headers"] == {}
    assert interaction["request"]["body"] == ""
    assert interaction["request"]["method"] == "GET"
    assert interaction["request"]["uri"] == f"{GET_URL}?q=1&t=SCRUBBED&v=3"
    assert interaction["response"]["headers"] == {"Content-Type": ["text/xml"]}
    assert interaction["response"]["status"] == {"code": 200, "message": "OK"}
    assert "Set-Cookie" not in text
    assert "s=1" not in text


def test_render_cassette_leaves_non_statement_bodies_unchanged() -> None:
    body = _error("Warn", "1019", "Statement generation in progress.")
    interactions = _record(lambda request: httpx.Response(200, text=body))
    text = ibkr_flex_capture.render_cassette(interactions, token=TOKEN)
    (interaction,) = yaml.safe_load(text)["interactions"]
    assert interaction["response"]["body"]["string"] == body


def _invoke(args: list[str]) -> Result:
    return CliRunner().invoke(cli.app, args)


@pytest.fixture
def cli_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    return tmp_path


def _patch_capture(monkeypatch: pytest.MonkeyPatch, transport: httpx.BaseTransport) -> None:
    capture = functools.partial(ibkr_flex_capture.capture, transport=transport)
    monkeypatch.setattr(cli, "capture", capture)


def test_cli_missing_settings_exits_2(cli_env: Path) -> None:
    result = _invoke(["flex-capture"])
    assert result.exit_code == 2
    assert "BOT_IBKR_FLEX_TOKEN" in result.output
    assert "BOT_IBKR_FLEX_QUERY_ID" in result.output
    assert list(cli_env.iterdir()) == []


@pytest.mark.parametrize(
    "send",
    [
        lambda request: httpx.Response(200, text=_error("Fail", "1012", "Token has expired.")),
        lambda request: httpx.Response(500, text="oops"),
    ],
    ids=["fail-1012", "http-500"],
)
def test_cli_flex_error_exits_1_without_the_token(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch, send: Callable[[httpx.Request], httpx.Response]
) -> None:
    monkeypatch.setenv("BOT_IBKR_FLEX_TOKEN", TOKEN)
    monkeypatch.setenv("BOT_IBKR_FLEX_QUERY_ID", QUERY)
    _patch_capture(monkeypatch, httpx.MockTransport(send))
    result = _invoke(["flex-capture"])
    assert result.exit_code == 1
    assert "Flex capture failed:" in result.stderr
    for form in FORMS:
        assert form not in result.output
    assert list(cli_env.iterdir()) == []


def test_cli_success_prints_paths_and_summary(
    cli_env: Path, monkeypatch: pytest.MonkeyPatch, sample: str
) -> None:
    monkeypatch.setenv("BOT_IBKR_FLEX_TOKEN", TOKEN)
    monkeypatch.setenv("BOT_IBKR_FLEX_QUERY_ID", QUERY)
    _patch_capture(monkeypatch, _transport(sample))
    result = _invoke(["flex-capture"])
    assert result.exit_code == 0, result.output
    expected_paths = [
        cli_env / ibkr_flex_capture.CASSETTE_PATH,
        cli_env / ibkr_flex_capture.REDACTED_XML_PATH,
        cli_env / ibkr_flex_capture.SUMMARY_PATH,
    ]
    wrote = [line for line in result.stdout.splitlines() if line.startswith("Wrote ")]
    assert wrote == [f"Wrote {p}" for p in expected_paths]
    assert result.stdout.endswith(summarize_statement(sample).to_json())
    for form in FORMS:
        assert form not in result.output


def test_flex_capture_is_hidden() -> None:
    result = _invoke(["--help"])
    assert result.exit_code == 0
    assert "flex-capture" not in result.output


def test_render_cassette_without_a_token_has_nothing_to_refuse() -> None:
    interactions = _record(lambda request: httpx.Response(200, text=SUCCESS))
    text = ibkr_flex_capture.render_cassette(interactions, token="")
    assert len(yaml.safe_load(text)["interactions"]) == 1
