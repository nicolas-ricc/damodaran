# Pipeline models

TLA+ models of the pipeline stages, checked by TLC. There is one model per stage. Each follows one
unit (a company, a sidecar) through one run of the stage. The variable `phase` is the reader's
state, and the groups are the stage's sub-boards. Each rule is an `INVARIANT` that carries the
reader's sentence. TLC checks every rule on every reachable state, and the statechart skill turns
the result into a report and a chart.

## Files

Fixed files:

- `check.sh`: checks every model in the folder.
- `TLA_VERSION`, `TLA_SHA256`: the pinned TLC release and the hash of its `tla2tools.jar`.
- `STATECHART_COMMIT`: the pinned commit of the statechart skill (`pstack/skills/statechart` in
  `cursor/plugins`). CI clones it; it is never vendored here.
- `README.md`: this file.

Per stage, `<stem>.tla`, `<stem>.cfg` and `<stem>.view.js`: the model, its constants and
`INVARIANT` list, and the labels for the chart. `site`, `refresh` and `screen` are modelled.

## Conventions

- A model defines `Next`, `Done` and `Spec`. The environment (a push refused, a workflow failing)
  is a named action, not hidden nondeterminism.
- One `INVARIANT` per rule. The reader's sentence is a `\*` comment directly above the definition.
  `\*` is reserved for the rule sentence and its `\* broken:` marker; helpers and actions are
  commented with `(* ... *)`. Each action, and each rule above its sentence, carries a
  `(* ... *)` citation of the code it mirrors.
- The view maps (`states`, `steps`, `groups`) are plain `const`, not exported: the skill's view
  loader rejects any export beyond `state`, `step`, `group`, `colors` and `title`.
- A model extends no standard module. With `EXTENDS FiniteSets`, the skill's export step
  (SANY's XML exporter) fails with a `NullPointerException`; write "at most one" as
  `\A x, y \in S : x = y` instead of `Cardinality(S) <= 1`.
- Groups are named `<stage>-<sub>`. Aim for about 20 arrows per group; the cap is 24.

Labels are written for the reader of the chart:

- A state is in the reader's words: "the push is refused".
- A step says what happens: "the script commits the sidecar". A condition goes at the end, in
  brackets: "the push fails [master refuses it]".
- Expand an acronym at its first use.
- Never use a variable, function or action name.

## Running

CI runs the job `models` of the `pipeline-diagram` workflow on every push. To run it locally you
need Java 11 or later (CI uses 21) and Node 22.18 to 22.x or 23.6+, a `tla2tools.jar` at the pinned version, and a
clone of the skill at the pinned commit:

```
TLA2TOOLS=/path/to/tla2tools.jar STATECHART=/path/to/statechart/scripts/statechart docs/pipeline/models/check.sh /tmp/out
```

`check.sh` prints one line per failing model, `error  <model>: <why>`, then a summary,
`models | N models, R rules, E errors`, and exits non-zero when E is not zero. A model fails when
its `.cfg` or `.view.js` is missing, the launcher fails or writes no `report.md`, the report has no
`## Rules that hold`, or it has a `## <rule> breaks`, `## Rules not checked` or `## TLC stopped`
section.

## Reading the artifact

CI uploads `/tmp/models` as the artifact `pipeline-models`, even when a model fails:

```
gh run download <id> -n pipeline-models -D /tmp/models
```

It holds one folder per stage:

- `report.md`, with these sections: `## Rules that hold`; `## <rule> breaks`, with the shortest
  path to the violation; `## Rules not checked`; `## TLC stopped`.
- `chart.mmd`: a working check of the labels. It is never committed.
- `tlc.out`: the raw TLC output.

## When a rule breaks

1. Replay the shortest path as a pytest against the real code.
2. If the code behaves differently, the model is wrong. Fix the model; never weaken the rule.
3. If the code really breaks the rule, open an issue labelled `bug`. Keep the rule in the `.tla`
   and remove it from the `.cfg`. Add `\* broken: #<issue>` to the `\*` comments directly above its
   definition in the `.tla`, and add a row to the table below.

Model work never changes the pipeline code.

## Known broken rules

| Stage | Rule | Reader's sentence | Issue |
| --- | --- | --- | --- |
| analyze | `OnlyTheCommandStopsTheBatch` | Only refused arguments or an empty screen stop the whole command; a failing ticker never does. | #180 |
