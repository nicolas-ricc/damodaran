# Pipeline boards

Six d2 boards document the investment-bot pipeline. `classes.d2` holds the nine node classes and
is not a board. Every board starts with `...@classes` and imports nothing else.

Boards: `pipeline.svg` (overview: cron schedules, the five stages, external services, DuckDB
tables, outputs), `refresh.svg`, `screen.svg`, `analyze.svg`, `portfolio.svg`, `site.svg` (one per
stage). Reading order: `pipeline.svg` first; its stage nodes link the stage boards in the order
refresh, screen, analyze, portfolio, site.

## Commands

- Render: `docs/pipeline/build.sh` (run it after editing any `.d2`)
- Check: `python3 docs/pipeline/check.py`

`D2_VERSION` pins d2 v0.9.0, which bundles the TALA layout engine. Rendering happens in the
`pipeline-diagram` workflow on every push (artifact `pipeline-render`), or locally when `d2` at
that version is on `PATH`.

`rendered.sha256` is the hash of the `.d2` sources. `check.py` and CI fail when it differs from the
sources or an SVG is missing. Never edit an SVG or the hash by hand. PNGs are for looking only:
git-ignored, never committed.

## Models

TLA+ models of the stages, checked by TLC in the `models` job: see `models/README.md`.

## Directives

A citation is a d2 line comment, trailing the line it describes or alone on the line before it:
`# @kind argument`. Never inside a `|md ... |` block; outside directives, no `@` starts a word in a
comment. `link:` targets must exist in this folder (`check.py`).

| Directive | Cites | Checked by |
| --- | --- | --- |
| `@symbol` | dotted path of a module, function, class or method | `check.py` |
| `@table` | table in `schema.sql` | `check.py` |
| `@file` | path from the repository root | `check.py` |
| `@rule` | registered screener rule | `tests/unit/test_pipeline_diagram.py` |
| `@param` | value in the preset YAML, shown on the line | `tests/unit/test_pipeline_diagram.py` |
| `@const` | module constant, its value shown on the line | `tests/unit/test_pipeline_diagram.py` |
| `@enum` | Enum whose member values appear on the board | `tests/unit/test_pipeline_diagram.py` |

## Conventions

- `class:` is a node's first attribute; expand every acronym at first use.
- Follow every ADR mention with its status: `ADR 0006 (Implemented)`.
- A gap note starts `Gap:` and names the document: `plano <card>`, `leccion cap-N`, spec §.
- Cite every digit on a step label with `@const`/`@param` on that line, except 0, 1, 100, ordinals
  and digits inside words (10-K); write counts in words.
- Stage links are `link: "./<stage>.svg"`: d2 v0.9.0 drops `link: <stage>.svg` on a board that has
  a node keyed `<stage>`.

## How to add a step

1. Add its directive comment first.
2. Declare the node with its class and label.
3. Declare its labelled edges at top level, after all nodes.
4. Render with `docs/pipeline/build.sh`, or push and take the SVGs from `pipeline-render`; commit
   them with `rendered.sha256`.
