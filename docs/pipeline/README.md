# Pipeline boards

Six d2 boards and four sub-boards document the investment-bot pipeline.
`classes.d2` holds the nine node classes and is not a board. Every board starts with
`...@classes` and imports nothing else.

Boards: `pipeline.svg` (overview: cron schedules, the five stages, external services, DuckDB
tables, outputs), `refresh.svg`, `screen.svg`, `analyze.svg`, `portfolio.svg`, `site.svg` (one per
stage). Reading order: `pipeline.svg` first; its stage nodes link the stage boards in the order
refresh, screen, analyze, portfolio, site. The `site` board links four sub-boards
(`site-publish.svg`, `site-ci.svg`, `site-scan.svg`, `site-views.svg`); the `refresh` board links
five (`refresh-damodaran.svg`, `refresh-fundamentals.svg`, `refresh-facts.svg`,
`refresh-prices.svg`, `refresh-fx.svg`).

## Commands

- Render: `docs/pipeline/build.sh` (run it after editing any `.d2`)
- Check: `python3 docs/pipeline/check.py`

`D2_VERSION` pins d2 v0.9.0, which bundles the TALA layout engine. Rendering happens in the
`pipeline-diagram` workflow on every push (artifact `pipeline-render`), or locally when `d2` at
that version is on `PATH`.

`rendered.sha256` is the hash of the `.d2` sources. `check.py` and CI fail when it differs from the
sources or an SVG is missing. Never edit an SVG or the hash by hand. PNGs are for looking only:
git-ignored, never committed.

## Sub-boards

A sub-board is a stage's checked statechart drawn in d2: `docs/pipeline/<stage>-<sub>.d2`, where
`<sub>` is a group of the stage's model. It shows flow only. Stores, files and services are
top-level nodes at the edge of the flow, never a container.

- Three fixed nodes. `objective` (note, one line `Objective: ...`). `back` (note `back to the
  <stage> board`, link `./<stage>.svg`). `out` (output, `Comes out: ...`, link to the next
  sub-board, or `./<stage>.svg` on the last).
- Navigation: stage board, then sub-board, then back to the stage or on to the next sub-board. The
  order is the order of the groups in the model's view. The stage board puts `link:` on the
  expanded container or node only; `pipeline.d2` keeps its five stage links.
- Origin: one node per model state of the group, its first line the `states` label. One edge per
  model step, its first line the `steps` label with the [condition]; further lines say how, digits
  cited. The statechart is in `models/`; `tests/unit/test_pipeline_models.py` (`_SUBBOARDED`)
  matches the labels.
- A state is a `decision` when two or more steps leaving it carry a [condition], else a `step`.
  Every edge leaving a decision has a [condition]; an edge whose label has no [condition] gets one
  on its second line.
- A step that crosses groups is drawn on both boards. Its far end is a neighbour node that links
  its own sub-board; a `step` neighbour or terminal state carries `No incoming edge` or `No
  outgoing edge` as a trailing comment.
- Every step and decision node carries a directive. Gap notes stay on the stage board.
- At most 24 edges per board, aim for 20. Over that, split the group in the model (groups and
  colours only, not the TLA+ logic). Tests: `tests/unit/test_pipeline_subboards.py`.

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
