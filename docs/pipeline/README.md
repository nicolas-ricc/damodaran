# Pipeline boards

d2 diagrams of the whole investment-bot pipeline. `pipeline.d2` is the overview
(cron schedules, the five stages, external services, DuckDB tables, outputs);
each stage gets its own board later (`refresh.d2`, `screen.d2`, `analyze.d2`,
`portfolio.d2`, `site.d2`). `classes.d2` holds the nine node classes and is not a
board. Every board starts with `...@classes` and imports nothing else.

## Commands

- Render: `docs/pipeline/build.sh` (run it after editing any `.d2`; CI fails on a stale SVG)
- Check: `python3 docs/pipeline/check.py`

Rendering needs `d2` at the version in `D2_VERSION`. It happens in the
`pipeline-diagram` workflow (artifact `pipeline-render`) or locally when `d2` at
that version is on `PATH`. The SVG and `rendered.sha256` are never edited by hand.

## Directives

A citation is a d2 line comment, trailing the line it describes, or alone on the
line before it: `# @kind argument`. Never inside a `|md ... |` block.

| Directive | Cites | Checked by |
| --- | --- | --- |
| `@symbol` | dotted path of a function or class | `check.py` |
| `@table` | table in `schema.sql` | `check.py` |
| `@file` | path from the repository root | `check.py` |
| `@rule` | registered screener rule | `tests/unit/test_pipeline_diagram.py` |
| `@param` | value in the preset YAML, shown on the line | `tests/unit/test_pipeline_diagram.py` |
| `@const` | module constant, its value shown on the line | `tests/unit/test_pipeline_diagram.py` |
| `@enum` | Enum whose member values appear on the board | `tests/unit/test_pipeline_diagram.py` |

Convention: `class:` is a node's first attribute. Expand every acronym at first use.
