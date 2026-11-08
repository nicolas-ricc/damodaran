"""CLI integration test for `bot analyze <TICKER>` (issue #16, spec §7.7).

Seeds an in-memory-equivalent DuckDB file with a fixture company, runs
``bot analyze``, then parses the written Markdown report and asserts the key
§7.7 sections are present.
"""

from __future__ import annotations

import errno
import json
from datetime import date
from pathlib import Path
from typing import Any

import duckdb
import pytest
from structlog.testing import capture_logs
from typer.testing import CliRunner

import bot.cli
from bot.cli import app
from bot.storage.db import apply_schema, connect

# Fixture money and share counts are written in millions; the valuator refuses
# share counts below 1,000,000, so seeds are scaled up by this factor.
_MILLIONS = 1_000_000.0


def _seed(conn: duckdb.DuckDBPyConnection, ticker: str = "AAPL") -> None:
    conn.execute(
        "INSERT INTO companies "
        "(ticker, name, country, currency, industry_damodaran, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [ticker, f"{ticker} Inc", "United States", "USD", "Computers/Peripherals", "sec_edgar"],
    )
    conn.execute(
        "INSERT INTO damodaran_country (country, year, erp, tax_rate, region) "
        "VALUES (?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
        ["United States", 2026, 0.045, 0.21, "US"],
    )
    conn.execute(
        "INSERT INTO damodaran_industry "
        "(industry, region, year, wacc, cost_of_equity, cost_of_debt, beta_levered, "
        "debt_to_equity, op_margin, sales_to_capital, pe, ev_sales) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT DO NOTHING",
        ["Computers/Peripherals", "US", 2026, 0.085, 0.09, 0.045, 1.05, 0.20, 0.28,
         2.5, 22.0, 5.0],
    )
    for year, revenue in {2022: 380_000.0, 2023: 395_000.0, 2024: 410_000.0, 2025: 430_000.0}.items():
        conn.execute(
            "INSERT INTO financials_annual "
            "(ticker, fiscal_year, revenue, ebit, net_income, total_debt, cash, "
            "shares_diluted, is_restated, source, currency) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'USD')",
            [ticker, year, revenue * _MILLIONS, revenue * 0.30 * _MILLIONS,
             100_000.0 * _MILLIONS, 110_000.0 * _MILLIONS, 60_000.0 * _MILLIONS,
             15_500.0 * _MILLIONS, False, "sec_edgar"],
        )
    conn.execute(
        "INSERT INTO prices_daily (ticker, date, close, currency, source) "
        "VALUES (?, ?, ?, ?, ?)",
        [ticker, "2026-05-29", 150.0, "USD", "fmp"],
    )


def test_analyze_writes_report(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "bot.duckdb"
    reports_dir = tmp_path / "reports"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    conn = connect(db_path)
    apply_schema(conn)
    _seed(conn)
    conn.close()

    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "AAPL"])
    assert result.exit_code == 0, result.stdout

    # Exactly one report under reports/<date>/analysis/AAPL.md.
    reports = list(reports_dir.glob("*/analysis/AAPL.md"))
    assert len(reports) == 1
    md = reports[0].read_text()

    for heading in (
        "# AAPL",
        "Executive summary",
        "Story type",
        "Assumptions",
        "DCF detail",
        "Sensitivity",
        "Narrative flags",
        "Sanity check",
    ):
        assert heading in md, f"missing section {heading!r}"
    # The CLI echoes the path it wrote to.
    assert "AAPL.md" in result.stdout


def test_analyze_writes_html_alongside_md(tmp_path: Path, monkeypatch) -> None:
    """The HTML report (M6.1) is produced next to the Markdown one."""
    db_path = tmp_path / "bot.duckdb"
    reports_dir = tmp_path / "reports"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    conn = connect(db_path)
    apply_schema(conn)
    _seed(conn)
    conn.close()

    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "AAPL"])
    assert result.exit_code == 0, result.stdout

    md_reports = list(reports_dir.glob("*/analysis/AAPL.md"))
    html_reports = list(reports_dir.glob("*/analysis/AAPL.html"))
    assert len(md_reports) == 1
    assert len(html_reports) == 1
    # Same directory: the HTML sits right beside the Markdown.
    assert html_reports[0].parent == md_reports[0].parent

    html = html_reports[0].read_text()
    assert html.lstrip().lower().startswith("<!doctype html>")
    # Self-contained: the tornado chart is inlined, no external assets.
    assert "data:image/png;base64," in html
    assert "<h1" in html
    # The CLI echoes the HTML path it wrote to.
    assert "AAPL.html" in result.stdout


def test_analyze_unknown_ticker_exits_nonzero(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "bot.duckdb"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    conn = connect(db_path)
    apply_schema(conn)
    conn.close()

    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "NOPE"])
    assert result.exit_code != 0


def test_analyze_applies_override(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "bot.duckdb"
    reports_dir = tmp_path / "reports"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    conn = connect(db_path)
    apply_schema(conn)
    _seed(conn)
    conn.close()

    override = tmp_path / "AAPL.yaml"
    override.write_text(
        "operating_margin: 0.35\nnotes: Services mix lifts steady-state margin.\n"
    )

    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "AAPL", "--override", str(override)])
    assert result.exit_code == 0, result.stdout

    md = next(reports_dir.glob("*/analysis/AAPL.md")).read_text()
    assert "Services mix lifts steady-state margin." in md
    assert "manual" in md


def test_analyze_picks_up_config_assumptions_by_convention(
    tmp_path: Path, monkeypatch
) -> None:
    """Without ``--override``, `analyze` looks for `<assumptions_dir>/<TICKER>.yaml`."""
    db_path = tmp_path / "bot.duckdb"
    reports_dir = tmp_path / "reports"
    assumptions_dir = tmp_path / "assumptions"
    assumptions_dir.mkdir()
    (assumptions_dir / "AAPL.yaml").write_text("notes: convention override\n")

    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_ASSUMPTIONS_DIR", str(assumptions_dir))

    conn = connect(db_path)
    apply_schema(conn)
    _seed(conn)
    conn.close()

    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "AAPL"])
    assert result.exit_code == 0, result.stdout

    md = next(reports_dir.glob("*/analysis/AAPL.md")).read_text()
    assert "convention override" in md


def test_analyze_accepts_multiple_tickers(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "bot.duckdb"
    reports_dir = tmp_path / "reports"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    conn = connect(db_path)
    apply_schema(conn)
    _seed(conn, "AAPL")
    _seed(conn, "MSFT")
    conn.close()

    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "AAPL", "MSFT"])
    assert result.exit_code == 0, result.stdout

    out_dir = next((reports_dir).glob("*/analysis"))
    assert (out_dir / "AAPL.md").exists()
    assert (out_dir / "MSFT.md").exists()


def test_analyze_from_screen_uses_the_latest_run(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "bot.duckdb"
    reports_dir = tmp_path / "reports"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    conn = connect(db_path)
    apply_schema(conn)
    _seed(conn, "AAPL")
    _seed(conn, "MSFT")

    # Older run: shortlist would be wrong if picked.
    conn.execute(
        "INSERT INTO screener_candidates (run_id, preset, ticker, rank, passed, created_at) "
        "VALUES (?, ?, ?, ?, TRUE, TIMESTAMP '2026-01-01 00:00:00')",
        ["old-run", "damodaran_value", "AAPL", 1],
    )
    # Latest run: MSFT ranked ahead of AAPL.
    conn.execute(
        "INSERT INTO screener_candidates (run_id, preset, ticker, rank, passed, created_at) "
        "VALUES (?, ?, ?, ?, TRUE, TIMESTAMP '2026-06-01 00:00:00')",
        ["new-run", "damodaran_value", "MSFT", 1],
    )
    conn.execute(
        "INSERT INTO screener_candidates (run_id, preset, ticker, rank, passed, created_at) "
        "VALUES (?, ?, ?, ?, TRUE, TIMESTAMP '2026-06-01 00:00:01')",
        ["new-run", "damodaran_value", "AAPL", 2],
    )
    conn.close()

    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "--from-screen"])
    assert result.exit_code == 0, result.stdout
    assert result.output.index("MSFT") < result.output.index("AAPL")


def test_analyze_from_screen_without_runs_fails_clearly(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "bot.duckdb"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    conn = connect(db_path)
    apply_schema(conn)
    conn.close()

    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "--from-screen"])
    assert result.exit_code == 2
    assert "bot screen" in result.output


def test_analyze_from_screen_with_empty_shortlist_says_so(
    tmp_path: Path, monkeypatch
) -> None:
    """The latest run persisted but shortlisted nothing (all rows failed).

    This must be reported differently from "no screen was ever persisted" —
    the run happened, it just did not pass anything.
    """
    db_path = tmp_path / "bot.duckdb"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    conn = connect(db_path)
    apply_schema(conn)
    conn.execute(
        "INSERT INTO screener_candidates (run_id, preset, ticker, rank, passed, created_at) "
        "VALUES (?, ?, ?, ?, FALSE, TIMESTAMP '2026-06-01 00:00:00')",
        ["new-run", "damodaran_value", "AAPL", 1],
    )
    conn.close()

    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "--from-screen"])
    assert result.exit_code == 2
    assert "No screen has been persisted" not in result.output
    assert "did not leave any candidates" in result.output


def test_analyze_explicit_override_with_many_tickers_is_rejected(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "bot.duckdb"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(tmp_path / "reports"))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    conn = connect(db_path)
    apply_schema(conn)
    _seed(conn, "AAPL")
    _seed(conn, "MSFT")
    conn.close()

    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "AAPL", "MSFT", "--override", "x.yaml"])
    assert result.exit_code == 2
    assert "exactly one ticker" in result.output


def test_analyze_explicit_override_that_does_not_exist_is_rejected(
    tmp_path: Path, monkeypatch
) -> None:
    """A typo in ``--override`` stops the command before the DB is opened (#214)."""
    db_path = tmp_path / "bot.duckdb"
    reports_dir = tmp_path / "reports"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    missing = tmp_path / "does" / "not" / "exist.yaml"
    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "AAPL", "--override", str(missing)])
    assert result.exit_code == 2
    assert f"--override {missing}: no such file." in result.output
    assert not db_path.exists()
    assert list(reports_dir.glob("*/analysis/*")) == []


def test_analyze_explicit_override_that_is_a_directory_is_rejected(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "bot.duckdb"
    reports_dir = tmp_path / "reports"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    conn = connect(db_path)
    apply_schema(conn)
    _seed(conn, "AAPL")
    conn.close()

    directory = tmp_path / "assumptions"
    directory.mkdir()
    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "AAPL", "--override", str(directory)])
    assert result.exit_code == 2
    assert f"--override {directory}: no such file." in result.output
    assert list(reports_dir.glob("*/analysis/*")) == []


def test_analyze_explicit_override_wins_over_convention(
    tmp_path: Path, monkeypatch
) -> None:
    """An explicit ``--override`` beats the conventional `<assumptions_dir>` file."""
    db_path = tmp_path / "bot.duckdb"
    reports_dir = tmp_path / "reports"
    assumptions_dir = tmp_path / "assumptions"
    assumptions_dir.mkdir()
    (assumptions_dir / "AAPL.yaml").write_text("notes: convention override\n")

    explicit_override = tmp_path / "explicit.yaml"
    explicit_override.write_text("notes: explicit override\n")

    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_ASSUMPTIONS_DIR", str(assumptions_dir))

    conn = connect(db_path)
    apply_schema(conn)
    _seed(conn)
    conn.close()

    runner = CliRunner()
    result = runner.invoke(
        app, ["analyze", "AAPL", "--override", str(explicit_override)]
    )
    assert result.exit_code == 0, result.stdout

    md = next(reports_dir.glob("*/analysis/AAPL.md")).read_text()
    assert "explicit override" in md
    assert "convention override" not in md


def test_analyze_writes_json_sidecar(tmp_path: Path, monkeypatch) -> None:
    """Issue #92: a ``<TICKER>.json`` sidecar lands next to the ``.md``/``.html``."""
    import json

    from bot.reporting.analysis_report import margin_verdict

    db_path = tmp_path / "bot.duckdb"
    reports_dir = tmp_path / "reports"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    conn = connect(db_path)
    apply_schema(conn)
    _seed(conn)
    conn.close()

    result = CliRunner().invoke(app, ["analyze", "AAPL"])
    assert result.exit_code == 0, result.stdout

    sidecars = list(reports_dir.glob("*/analysis/AAPL.json"))
    assert len(sidecars) == 1
    assert sidecars[0].with_suffix(".md").exists()
    payload = json.loads(sidecars[0].read_text())
    assert payload["schema_version"] == 1
    assert payload["verdict"] == margin_verdict(payload["analysis"]["margin_of_safety"])
    assert "AAPL.json" in result.stdout


def test_analyze_refuses_implausible_shares_and_continues_batch(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "bot.duckdb"
    reports_dir = tmp_path / "reports"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")

    conn = connect(db_path)
    apply_schema(conn)
    _seed(conn, "MCD")
    _seed(conn, "AAPL")
    # MCD's filer tagged the latest year's diluted shares in millions (#124).
    conn.execute(
        "UPDATE financials_annual SET shares_diluted = 732.3 "
        "WHERE ticker = 'MCD' AND fiscal_year = 2025"
    )
    conn.close()

    runner = CliRunner()
    result = runner.invoke(app, ["analyze", "MCD", "AAPL"])
    assert result.exit_code == 1, result.output
    assert "MCD: cannot value" in result.output
    assert "implausible diluted share count" in result.output

    out_dir = next(reports_dir.glob("*/analysis"))
    assert (out_dir / "AAPL.md").exists()
    assert not (out_dir / "MCD.md").exists()


@pytest.mark.parametrize(
    "body",
    [
        pytest.param("revenue_growth: [0.1\n", id="not-yaml"),
        pytest.param("terminal_growth:\n", id="empty-value"),
        pytest.param("tax_rate: [0.2]\n", id="list-for-a-number"),
        pytest.param("terminal_growth: .nan\n", id="nan"),
        pytest.param("1: 2\nfoo: 3\n", id="non-string-key"),
    ],
)
def test_analyze_malformed_override_fails_its_ticker_and_continues_batch(
    tmp_path: Path, monkeypatch, body: str
) -> None:
    """A malformed override is a failing ticker, not a failing command (#180)."""
    db_path = tmp_path / "bot.duckdb"
    reports_dir = tmp_path / "reports"
    assumptions_dir = tmp_path / "assumptions"
    assumptions_dir.mkdir()
    (assumptions_dir / "AAPL.yaml").write_text(body)
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_ASSUMPTIONS_DIR", str(assumptions_dir))

    conn = connect(db_path)
    apply_schema(conn)
    _seed(conn, "AAPL")
    _seed(conn, "MSFT")
    conn.close()

    result = CliRunner().invoke(app, ["analyze", "AAPL", "MSFT"])
    assert isinstance(result.exception, SystemExit), result.exception
    assert result.exit_code == 1, result.output
    assert "AAPL: cannot value" in result.output

    out_dir = next(reports_dir.glob("*/analysis"))
    assert (out_dir / "MSFT.md").exists()
    assert not (out_dir / "AAPL.md").exists()


def test_analyze_with_a_missing_default_spreads_file_values_with_p_zero(
    tmp_path: Path, monkeypatch
) -> None:
    db_path = tmp_path / "bot.duckdb"
    reports_dir = tmp_path / "reports"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_DEFAULT_SPREADS_PATH", str(tmp_path / "missing.yaml"))

    conn = connect(db_path)
    apply_schema(conn)
    _seed(conn)
    # A known interest coverage, so the chain reaches the (empty) table.
    conn.execute("UPDATE financials_annual SET interest_expense = ebit / 0.6")
    conn.close()

    override = tmp_path / "AAPL.yaml"
    override.write_text("story_type: distressed\n")

    # The CLI's logging setup would replace the capture_logs processors.
    monkeypatch.setattr(bot.cli, "configure_logging", lambda **_: None)
    with capture_logs() as logs:
        result = CliRunner().invoke(app, ["analyze", "AAPL", "--override", str(override)])
    assert result.exit_code == 0, result.stdout
    assert [e["event"] for e in logs].count("default_spreads.absent") == 1

    md = next(reports_dir.glob("*/analysis/AAPL.md")).read_text()
    assert (
        "**Probability of bankruptcy chain:** distressed, but the default-spread table is empty"
        in md
    )
    assert "| Probability of bankruptcy | 0.0% | rule_based |" in md


def _batch_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    db_path = tmp_path / "bot.duckdb"
    reports_dir = tmp_path / "reports"
    monkeypatch.setenv("BOT_DB_PATH", str(db_path))
    monkeypatch.setenv("BOT_REPORTS_DIR", str(reports_dir))
    monkeypatch.setenv("BOT_SEC_USER_AGENT", "Tester t@x.com")
    monkeypatch.setenv("BOT_ASSUMPTIONS_DIR", str(tmp_path / "assumptions"))
    conn = connect(db_path)
    apply_schema(conn)
    _seed(conn, "AAPL")
    _seed(conn, "MSFT")
    conn.close()
    return reports_dir


def _analysis_dir(reports_dir: Path) -> Path:
    return reports_dir / date.today().isoformat() / "analysis"


def _names(out_dir: Path) -> list[str]:
    return sorted(p.name for p in out_dir.iterdir()) if out_dir.exists() else []


def _fail_html_write(monkeypatch: pytest.MonkeyPatch) -> None:
    real = Path.write_text

    def write_text(self: Path, *args: object, **kwargs: object) -> int:
        if "AAPL.html" in self.name:
            raise OSError(errno.ENOSPC, "No space left on device")
        return real(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "write_text", write_text)


_MSFT_SET = ["MSFT.html", "MSFT.json", "MSFT.md"]


def test_batch_html_write_error_fails_the_ticker_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reports_dir = _batch_env(tmp_path, monkeypatch)
    _fail_html_write(monkeypatch)
    result = CliRunner().invoke(app, ["analyze", "AAPL", "MSFT"])
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert result.exit_code == 1
    assert "AAPL: cannot write report" in result.stderr
    assert "AAPL.html" in result.stderr
    assert "No space left on device" in result.stderr
    assert _names(_analysis_dir(reports_dir)) == _MSFT_SET


def test_batch_json_render_error_fails_the_ticker_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reports_dir = _batch_env(tmp_path, monkeypatch)
    real = bot.cli.render_analysis_json

    def render(analysis: Any, *, generated_on: date) -> str:
        if analysis.ticker == "AAPL":
            return json.dumps(float("nan"), allow_nan=False)
        return real(analysis, generated_on=generated_on)

    monkeypatch.setattr(bot.cli, "render_analysis_json", render)
    result = CliRunner().invoke(app, ["analyze", "AAPL", "MSFT"])
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert result.exit_code == 1
    assert "AAPL: cannot render report" in result.stderr
    assert _names(_analysis_dir(reports_dir)) == _MSFT_SET


def test_batch_mkdir_error_fails_each_ticker(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reports_dir = _batch_env(tmp_path, monkeypatch)
    real = Path.mkdir

    def mkdir(self: Path, *args: Any, **kwargs: Any) -> None:
        if self.name == "analysis":
            raise OSError(errno.EACCES, "Permission denied")
        real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mkdir)
    result = CliRunner().invoke(app, ["analyze", "AAPL", "MSFT"])
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert result.exit_code == 1
    assert "AAPL: cannot write report" in result.stderr
    assert "MSFT: cannot write report" in result.stderr
    assert "Permission denied" in result.stderr
    assert not _analysis_dir(reports_dir).exists()


def test_batch_success_output_is_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    reports_dir = _batch_env(tmp_path, monkeypatch)
    result = CliRunner().invoke(app, ["analyze", "AAPL", "MSFT"])
    assert result.exit_code == 0, result.output
    out_dir = _analysis_dir(reports_dir)
    wrote = [line for line in result.stdout.splitlines() if line.startswith("Wrote ")]
    assert wrote == [
        f"Wrote {out_dir / name}"
        for ticker in ("AAPL", "MSFT")
        for name in (f"{ticker}.md", f"{ticker}.html", f"{ticker}.json")
    ]
    assert _names(out_dir) == ["AAPL.html", "AAPL.json", "AAPL.md", *_MSFT_SET]
    assert result.stderr == ""


def test_batch_reports_are_all_or_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every ticker of a batch ends with its three reports or none of them."""
    reports_dir = _batch_env(tmp_path, monkeypatch)
    _fail_html_write(monkeypatch)
    CliRunner().invoke(app, ["analyze", "AAPL", "MSFT"])
    names = _names(_analysis_dir(reports_dir))
    assert not [n for n in names if n.endswith(".tmp")]
    for ticker in ("AAPL", "MSFT"):
        mine = {n for n in names if n.startswith(f"{ticker}.")}
        assert mine in (set(), {f"{ticker}.md", f"{ticker}.html", f"{ticker}.json"}), ticker


def _fail_override_read(monkeypatch: pytest.MonkeyPatch) -> None:
    real = Path.read_text

    def read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        if self.name == "AAPL.yaml":
            raise PermissionError(errno.EACCES, "Permission denied")
        return real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)


def test_batch_unreadable_conventional_override_fails_the_ticker_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An override that exists but cannot be read is "cannot value", not a crash (#227)."""
    reports_dir = _batch_env(tmp_path, monkeypatch)
    override = tmp_path / "assumptions" / "AAPL.yaml"
    override.parent.mkdir()
    override.write_text("notes: unreadable\n")
    _fail_override_read(monkeypatch)
    result = CliRunner().invoke(app, ["analyze", "AAPL", "MSFT"])
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert result.exit_code == 1
    assert "AAPL: cannot value" in result.stderr
    assert str(override) in result.stderr
    assert _names(_analysis_dir(reports_dir)) == _MSFT_SET


def test_batch_directory_conventional_override_fails_the_ticker_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A directory named ``AAPL.yaml`` is refused as unreadable; MSFT still runs (#227)."""
    reports_dir = _batch_env(tmp_path, monkeypatch)
    override = tmp_path / "assumptions" / "AAPL.yaml"
    override.mkdir(parents=True)
    result = CliRunner().invoke(app, ["analyze", "AAPL", "MSFT"])
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert result.exit_code == 1
    assert "AAPL: cannot value" in result.stderr
    assert str(override) in result.stderr
    assert _names(_analysis_dir(reports_dir)) == _MSFT_SET


def test_analyze_unreadable_explicit_override_cannot_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An explicit ``--override`` that exists but cannot be read is exit 1, not a traceback (#227)."""
    reports_dir = _batch_env(tmp_path, monkeypatch)
    override = tmp_path / "explicit" / "AAPL.yaml"
    override.parent.mkdir()
    override.write_text("notes: unreadable\n")
    _fail_override_read(monkeypatch)
    result = CliRunner().invoke(app, ["analyze", "AAPL", "--override", str(override)])
    assert isinstance(result.exception, SystemExit), result.exception
    assert result.exit_code == 1
    assert "AAPL: cannot value" in result.stderr
    assert str(override) in result.stderr
    assert _names(_analysis_dir(reports_dir)) == []
