# Broker-symbol resolver and the snapshot price seam Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A `BRK B` position at IBKR gets priced from the `BRK-B` universe row, through one resolver (separator normalisation plus a YAML override table) that later children reuse.

**Architecture:** A pure `path -> mapping` loader in `bot.reference.broker_symbols` reads `config/broker_symbols.yaml` like `bot.reference.currencies` reads its file. A resolver in `bot.portfolio.symbols` turns broker symbols into universe tickers against `companies.ticker`. `sync_portfolio` builds one `SymbolMap` per account and uses it only for the price key. The stored `portfolio_snapshots.ticker` stays the raw broker symbol. The override table is threaded CLI -> `run_portfolio` -> `sync_portfolio`.

**Tech Stack:** Python 3.12, DuckDB, PyYAML (`SafeLoader` subclass), structlog, Typer, pydantic-settings, pytest.

**Spec:** GitHub issue #338 (child of story #84). Its "Shared design decisions" section is binding and fixes every public name below.

## Global Constraints

- Public names are a contract for #339–#341: `DEFAULT_BROKER_SYMBOLS_PATH = Path("config/broker_symbols.yaml")`, `type BrokerSymbolTable = Mapping[str, str | None]`, `load_broker_symbols(path: Path | None = None) -> BrokerSymbolTable`, `SymbolMap`, `resolve_symbols`, `load_symbol_map`, `held_symbols`.
- Settings field: `broker_symbols_path: Path = Path("./config/broker_symbols.yaml")` (env `BOT_BROKER_SYMBOLS_PATH`), placed next to `currencies_path`.
- Log events: `broker_symbols.absent`, `broker_symbols.malformed` (warnings), `broker_symbols.loaded` (info).
- Candidate spellings: only `s`, `re.sub(r"[ .\-]", "-", s)` and `re.sub(r"[ .\-]", ".", s)`, in that order and de-duplicated. No separator removal and no suffix stripping.
- `portfolio_snapshots.ticker` stays the raw `pos.symbol`.
- `mypy --strict` typing; tests use in-memory DuckDB plus `apply_schema`; `uv run pytest -q`, `uv run ruff check .`, `uv run mypy src` pass.
- Commits: `feat(#338): ...` / `test(#338): ...`.

## Review Focus

1. **YAML 1.1 booleans as keys or values.** PyYAML reads unquoted `ON`, `NO`, `YES` and `OFF` as booleans, and `ON` is a real US ticker. A boolean key or value is malformed: the file degrades to empty with a warning and never raises. The file header tells curators to quote such symbols. Test: `ON: ON-X` gives `{}` plus `broker_symbols.malformed`, and `"ON": "ON-X"` loads (Task 1).
2. **Two keys that are equal after normalisation** (`brk b: X` and `BRK B: Y`). Treated as a duplicate key, so the file is malformed (the `default_spreads` duplicate-rating pattern). Test in Task 1.
3. **Repeated or blank broker symbols in the input.** The same symbol twice (two accounts, or `aapl` and `AAPL`) yields one entry. A blank or whitespace-only symbol is skipped, so it is neither resolved nor unresolved. Test in Task 2.
4. **A universe ticker stored lower-case in `companies`.** `known` is `UPPER(ticker)`, so it still resolves. Test in Task 2 (`load_symbol_map` with `brk-b` in `companies`).
5. **Existing sync tests price tickers that are absent from `companies`** (e.g. `AAPL` with only a `prices_daily` row). An unresolved symbol falls through `ticker()` unchanged, so those positions stay priced. This is covered by running the existing `test_portfolio_sync.py` unchanged (Task 3).

---

### Task 1: Override file, loader and setting

**Files:**
- Create: `config/broker_symbols.yaml`
- Create: `src/bot/reference/broker_symbols.py`
- Modify: `src/bot/config.py` (field after `currencies_path`)
- Modify: `tests/conftest.py` (env var plus default-path monkeypatch)
- Test: `tests/unit/test_broker_symbols.py`

**Interfaces:**
- Produces: `DEFAULT_BROKER_SYMBOLS_PATH`, `BrokerSymbolTable`, `load_broker_symbols(path: Path | None = None) -> BrokerSymbolTable` (a read-only `MappingProxyType`), `Settings.broker_symbols_path`.

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_broker_symbols.py` (use `structlog.testing.capture_logs`, and a `_write(tmp_path, text)` helper like `test_currencies.py`):
  - `test_loads_and_normalises_a_mapping`: `"brk b: brk-b\n"` gives `{"BRK B": "BRK-B"}`; `" BRK B : BRK-B "` gives the same.
  - `test_null_value_marks_ignored`: `"SPY: ~\n"` gives `{"SPY": None}`.
  - `test_missing_file_warns_and_is_empty`: exactly one `broker_symbols.absent`.
  - `test_comments_only_file_is_empty_without_warning`: `"# nothing\n"` gives `{}`, and no event in the logs has `log_level == "warning"`.
  - `test_malformed_file_warns_and_is_empty`, parametrised with `"- BRK B\n"` (not-a-mapping), `"123: AAPL\n"` (non-string key), `"FOO: ''\n"` (empty value), `"FOO: '  '\n"` (blank value), `"'  ': BAR\n"` (blank key), `"FOO: 12\n"` (non-string value), `"FOO: BAR\nFOO: BAZ\n"` (duplicate), `"brk b: X\nBRK B: Y\n"` (duplicate after normalisation), `"ON: ON-X\n"` (boolean key), `"FOO: [unclosed\n"` (unparsable). Each gives `{}` and logs `broker_symbols.malformed`.
  - `test_quoted_boolean_like_symbol_loads`: `'"ON": "ON-X"\n'` gives `{"ON": "ON-X"}`.
  - `test_unreadable_path_warns_and_is_empty`: a directory as path gives `{}` and a warning, no raise.
  - `test_table_is_immutable`: item assignment raises `TypeError`.
  - `test_repo_file_is_comments_only`: `load_broker_symbols(REPO_FILE) == {}` and the file text contains `BRK B` and `~`.
  - `test_settings_broker_symbols_path_default_and_override`: with `BOT_BROKER_SYMBOLS_PATH` deleted, `Settings(_env_file=None).broker_symbols_path == Path("./config/broker_symbols.yaml")`; with it set to `x.yaml`, the field is `Path("x.yaml")`. Mirror `test_settings_currencies_path_default_and_override`.
  - `test_default_path_is_used_when_none`: `load_broker_symbols()` reads `DEFAULT_BROKER_SYMBOLS_PATH`. Monkeypatch it to a tmp file `FOO: BAR`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_broker_symbols.py -q`. Expected: FAIL (`ModuleNotFoundError: bot.reference.broker_symbols`).
- [ ] **Step 3: Implement** `src/bot/reference/broker_symbols.py`, mirroring `currencies.py`: module docstring, `log = structlog.get_logger(__name__)`, `_MalformedError`, and the `_UniqueKeyLoader` copied from `default_spreads.py` (with the unhashable-key guard). `_parse(data: Any) -> dict[str, str | None]`:
  - `None` (comments-only) gives `{}`.
  - A non-dict is malformed.
  - Each key must be a `str` (a `bool` fails this check because it is not a `str`) that is non-blank after `strip()`; it is stored as `key.strip().upper()`. A key already seen after normalisation is malformed.
  - Each value is either `None` or a non-blank `str`, stored stripped and upper-cased. Anything else is malformed.

  `load_broker_symbols` follows `load_currency_table`'s `absent` / `malformed` / `loaded` flow and catches `(yaml.YAMLError, _MalformedError, OSError, UnicodeDecodeError)`. It has no bounds checks, so it never raises.
- [ ] **Step 4: Write `config/broker_symbols.yaml`**, comments only, with a header in the `currencies.yaml` style. It covers: the purpose (#84 / #338); the format `BROKER SYMBOL: UNIVERSE_TICKER`, with both sides upper-cased on load; that a space, `.` or `-` share-class separator is normalised automatically (`BRK B`, `BRK.B` and `BRK-B` all find `BRK-B`), so the file is only for renamed listings and for ignores; that `~` (null) marks a holding intentionally outside the universe (an ETF, a bond), which is ignored and never reported as unresolved; that symbols YAML reads as booleans (`ON`, `NO`, `YES`, `OFF`) must be quoted; that duplicates or a malformed file make the whole table empty with a warning; the `BOT_BROKER_SYMBOLS_PATH` override; and the commented examples `# BRK B: BRK-B` and `# SPY: ~`.
- [ ] **Step 5: Add `Settings.broker_symbols_path`** with `Field(default=Path("./config/broker_symbols.yaml"), description="Broker symbol -> universe ticker overrides; ~ ignores a holding (#338).")`.
- [ ] **Step 6: Update `tests/conftest.py`.** Add an autouse `_broker_symbols_path` fixture that sets `BOT_BROKER_SYMBOLS_PATH` to `REPO_ROOT / "config" / "broker_symbols.yaml"`. Add `monkeypatch.setattr(broker_symbols, "DEFAULT_BROKER_SYMBOLS_PATH", ...)` to `_config_defaults_on_repo_root`, and update that fixture's docstring to name the new file.
- [ ] **Step 7: Run** `uv run pytest tests/unit/test_broker_symbols.py tests/unit/test_currencies.py -q`. Expected: PASS.
- [ ] **Step 8: Commit** `feat(#338): config/broker_symbols.yaml and its loader`.

### Task 2: Resolver

**Files:**
- Create: `src/bot/portfolio/symbols.py`
- Test: `tests/unit/test_portfolio_symbols.py`

**Interfaces:**
- Consumes: `BrokerSymbolTable` from Task 1 (the `overrides` type is `Mapping[str, str | None]`, the same alias).
- Produces:
  - `@dataclass(frozen=True) class SymbolMap` with the fields `resolved: Mapping[str, str]`, `unresolved: tuple[str, ...]` and `ignored: tuple[str, ...]`, and the method `ticker(self, symbol: str) -> str`.
  - `resolve_symbols(symbols: Iterable[str], known: Collection[str], overrides: Mapping[str, str | None]) -> SymbolMap`
  - `load_symbol_map(conn: duckdb.DuckDBPyConnection, symbols: Iterable[str], overrides: Mapping[str, str | None]) -> SymbolMap`
  - `held_symbols(conn: duckdb.DuckDBPyConnection, snapshot_date: date) -> list[str]`

- [ ] **Step 1: Write the failing tests** in `tests/unit/test_portfolio_symbols.py`:
  - `test_share_class_separators_resolve_to_the_hyphen_ticker`, parametrised over `"BRK B"`, `"BRK.B"` and `"BRK-B"`: `resolve_symbols([s], {"BRK-B"}, {}).resolved == {s: "BRK-B"}`, with empty `unresolved` and `ignored`.
  - `test_share_class_separators_resolve_to_a_dot_ticker`: the same three symbols with `known={"BRK.B"}` resolve to `"BRK.B"`.
  - `test_identity_resolution_and_case_insensitive_ticker`: `m = resolve_symbols(["AAPL"], {"AAPL"}, {})`; `m.resolved == {"AAPL": "AAPL"}` and `m.ticker("aapl") == "AAPL"`.
  - `test_as_is_candidate_wins_over_normalised`: `resolve_symbols(["BRK.B"], {"BRK.B", "BRK-B"}, {}).ticker("BRK.B") == "BRK.B"`.
  - `test_override_wins`: `resolve_symbols(["FOO"], {"BAR", "FOO-X"}, {"FOO": "BAR"}).ticker("FOO") == "BAR"`.
  - `test_override_is_not_corrected`: `m = resolve_symbols(["BRK B"], {"BRK-B"}, {"BRK B": "XYZ"})`; `m.unresolved == ("BRK B",)` and `m.ticker("BRK B") == "BRK B"`.
  - `test_null_override_is_ignored_not_unresolved`: `m = resolve_symbols(["SPY"], set(), {"SPY": None})`; `m.ignored == ("SPY",)`, `m.unresolved == ()` and `m.ticker("spy") == "SPY"`.
  - `test_unresolved_falls_through_upper_cased`: `m = resolve_symbols(["zzz q"], {"AAPL"}, {})`; `m.unresolved == ("ZZZ Q",)` and `m.ticker(" zzz q ") == "ZZZ Q"`.
  - `test_no_other_spellings`: `resolve_symbols(["BRKB"], {"BRK-B"}, {}).unresolved == ("BRKB",)` and `resolve_symbols(["BRK B"], {"BRKB"}, {}).unresolved == ("BRK B",)`.
  - `test_unresolved_and_ignored_are_sorted_and_deduplicated`: `resolve_symbols(["ZZZ", "aaa", "AAA", "QQQ", "IEF"], set(), {"QQQ": None, "IEF": None})` gives `unresolved == ("AAA", "ZZZ")` and `ignored == ("IEF", "QQQ")`.
  - `test_blank_symbols_are_skipped`: `resolve_symbols(["", "  "], {"AAPL"}, {})` has empty `resolved`, `unresolved` and `ignored`.
  - `test_load_symbol_map_reads_companies`: in-memory DuckDB plus `apply_schema`; run `INSERT INTO companies (ticker, name, source) VALUES ('BRK-B', 'Berkshire B', 'sec_edgar')`; then `load_symbol_map(conn, ["BRK B"], {}).ticker("BRK B") == "BRK-B"`.
  - `test_load_symbol_map_upper_cases_companies`: the same with the ticker `'brk-b'` resolves to `"BRK-B"`.
  - `test_held_symbols_distinct_upper_sorted_for_the_day`: insert `portfolio_snapshots` rows (`snapshot_date, account, ticker, qty`; read the NOT NULL columns in `schema.sql` first) for `"BRK B"` in two accounts, `"aapl"` and, on another date, `"MSFT"`. Then `held_symbols(conn, day) == ["AAPL", "BRK B"]`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_portfolio_symbols.py -q`. Expected: FAIL (`ModuleNotFoundError`).
- [ ] **Step 3: Implement `src/bot/portfolio/symbols.py`.** Module docstring: the vocabulary (broker symbol and universe ticker) and the rule that only the universe-joining seams resolve. `resolve_symbols` follows decision 2 of the issue, with candidates de-duplicated in order (e.g. `dict.fromkeys`). Blank symbols after `strip()` are skipped. `resolved` holds a `MappingProxyType`. `unresolved` and `ignored` are `tuple(sorted(set))`. `ticker()` is exactly `self.resolved.get(symbol.strip().upper(), symbol.strip().upper())`. `load_symbol_map` builds `known` from `SELECT UPPER(ticker) FROM companies`. `held_symbols` runs the decision-2 SQL.
- [ ] **Step 4: Run** the step-2 command. Expected: PASS.
- [ ] **Step 5: Commit** `feat(#338): broker-symbol resolver`.

### Task 3: Snapshot price seam, threading and docs

**Files:**
- Modify: `src/bot/portfolio/sync.py` (`value_positions` and `sync_portfolio`)
- Modify: `src/bot/portfolio/command.py` (`run_portfolio`)
- Modify: `src/bot/cli.py` (`portfolio` command)
- Modify: `README.md` (Portfolio sync section), `CONTEXT.md` (Domain language)
- Test: `tests/unit/test_portfolio_sync.py`, `tests/unit/test_cli_portfolio.py`, `tests/integration/test_portfolio_command.py`

**Interfaces:**
- Consumes: `load_symbol_map` and `SymbolMap` (Task 2); `BrokerSymbolTable` and `load_broker_symbols` (Task 1).
- Produces:
  - `value_positions(positions, prices, fx, symbols: SymbolMap | None = None)`
  - `sync_portfolio(conn, client, *, snapshot_date=None, symbol_overrides: BrokerSymbolTable = MappingProxyType({}))`
  - `run_portfolio(..., symbol_overrides: BrokerSymbolTable = MappingProxyType({}))`

- [ ] **Step 1: Write the failing tests.**
  - `test_portfolio_sync.py::test_share_class_position_priced_from_universe_ticker`: seed `companies` with `BRK-B` and `prices_daily` with (`BRK-B`, 2026-06-01, 400.0, USD). Use the existing `_seed_price`, which upper-cases. Sync a `_position("DU1", "BRK B", 3.0, 300.0)` on `date(2026, 6, 2)`. Then `SELECT ticker, market_value FROM portfolio_snapshots` gives `[("BRK B", approx 1200.0)]` and `summary.unpriced == 0`.
  - `test_portfolio_sync.py::test_override_prices_a_renamed_listing`: seed `companies` with `NEWCO` and price `NEWCO` only; a position `OLDCO`. With `symbol_overrides={"OLDCO": "NEWCO"}`, `market_value == qty * close` and the stored ticker is `"OLDCO"`. On a fresh connection without the override, `market_value IS NULL` and `unpriced == 1`.
  - `test_portfolio_sync.py::test_value_positions_uses_symbol_map`: pure; `value_positions([pos BRK B], {"BRK-B": _PriceQuote(10.0, "USD")}, fx, resolve_symbols(["BRK B"], {"BRK-B"}, {}))` is priced, and the same call without `symbols` is `None`.
  - `test_portfolio_command.py::test_run_portfolio_forwards_symbol_overrides`: monkeypatch `bot.portfolio.command.sync_portfolio` with a spy that records kwargs and delegates. Call `run_portfolio(..., symbol_overrides={"OLDCO": "NEWCO"})` and assert that the spy saw `symbol_overrides == {"OLDCO": "NEWCO"}`. Reuse the file's existing client and helpers.
  - `test_cli_portfolio.py::test_portfolio_passes_loaded_broker_symbols`: in `_env`, write `tmp_path/"broker_symbols.yaml"` as `"BRK B: BRK-B\n"` and set `BOT_BROKER_SYMBOLS_PATH` to it. Spy on `bot.cli.run_portfolio` as `test_portfolio_passes_preset_gates_including_trap_detection` does, and assert `dict(captured["symbol_overrides"]) == {"BRK B": "BRK-B"}`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_portfolio_sync.py tests/unit/test_cli_portfolio.py tests/integration/test_portfolio_command.py -q`. Expected: the five new tests FAIL, and the existing ones pass.
- [ ] **Step 3: Implement the sync seam.**
  - `value_positions`: the price key is `symbols.ticker(pos.symbol)` if `symbols is not None`, else `pos.symbol.upper()`; update the docstring.
  - `sync_portfolio`: inside the account loop, after `client.positions(account)`, build `load_symbol_map(conn, (p.symbol for p in positions), symbol_overrides)` and pass it to `value_positions`. Document `symbol_overrides` in Args.
  - `_insert_positions` is untouched (raw `pos.symbol`).
- [ ] **Step 4: Thread it through.** `run_portfolio` gets the keyword (with a docstring Arg) and forwards it to `sync_portfolio`. The CLI `portfolio` command passes `symbol_overrides=load_broker_symbols(settings.broker_symbols_path)`, next to `currencies=`.
- [ ] **Step 5: Docs.**
  - README: under "Portfolio sync via Flex Web Service" (after the env block), add a `#### Broker symbols that differ from the universe ticker` subsection of a few lines. It says that space, `.` and `-` share-class separators are normalised against `companies`, and that `config/broker_symbols.yaml` maps renamed listings (`OLDCO: NEWCO`). It also covers `~` to ignore an ETF or bond, quoting boolean-like symbols, and `BOT_BROKER_SYMBOLS_PATH`. Only the price lookup uses the resolver so far.
  - CONTEXT.md Domain language: add **Broker symbol** and **Universe ticker** with the issue's definitions, each with an `_Avoid_:` line in the file's style.
- [ ] **Step 6: Run** the step-2 command and expect PASS. Then run `uv run pytest -q`, `uv run ruff check .` and `uv run mypy src`; all must pass.
- [ ] **Step 7: Commit** `feat(#338): snapshot prices broker symbols through the resolver`.
