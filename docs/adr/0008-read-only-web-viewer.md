# 0008 — Read-only web viewer over committed analysis JSON

## Status

Accepted (2026-10-04). Implemented (2026-10-04, `bot site` in src/bot/web/site.py and
.github/workflows/site.yml; issue #92).

## Context

Spec §15 left the web dashboard out of scope: the bot is CLI and local. Reading a
shortlist of analyses still means opening one Markdown or HTML report per company. A
public, read-only page that lists the analysed companies and shows why each got its
verdict is useful and does not require operating the bot from a browser.

## Decision

A static site, built by `bot site` and published to GitHub Pages on every push to
`master`. It is a read-only surface; the bot stays CLI and local (spec §15 still
excludes an operating dashboard).

- **Source of data: a JSON sidecar, not the DB.** `bot analyze` writes
  `reports/<date>/analysis/<TICKER>.json` (`schema_version` 1) next to the Markdown and
  HTML reports. The `.gitignore` lets only those files through. The DuckDB file is local,
  large and not committed; a CI runner cannot rebuild it, and the site should not depend
  on it. The sidecar carries everything the pages show, so the site is a pure function of
  committed files.
- **CI does not run `analyze`.** The runner has no DuckDB, no EDGAR/Tiingo access and no
  keys. Analysis runs locally; its output is committed. CI only runs ruff, mypy, pytest,
  then `bot site`, then deploys.
- **No env vars for `bot site`.** `bot site --out site --reports-dir reports --base-url /`
  reads files only. `--base-url` is `/<repo>/` on Pages.
- **Output.** An index, 30 `rows/` fragments (htmx swaps `<tbody>`), 30 `l/` full list pages
  (the `href` of filter and sort links, so they work with JavaScript disabled), and `c/`
  and `f/` pages per ticker and date. `viewer.js` is small and optional.
- **Verdict.** One reading of the MoS, from `margin_verdict` (single source), shared by
  the reports and the site.
- **Safety.** `bot site` never deletes `out_dir` itself, only its children, and refuses a
  non-site directory or one that contains `--reports-dir`. The file stem is the ticker
  identity; a sidecar whose `analysis.ticker` disagrees is skipped.

## Consequences

- Manual prerequisite, once: Settings -> Pages -> Source = GitHub Actions. Without it the
  deploy job fails.
- Published analyses are public. Only commit sidecars you are willing to show.
- The viewer is only as fresh as the last commit of `reports/*/analysis/*.json`.
- Changing the sidecar shape means bumping `SCHEMA_VERSION` and teaching `web/index.py`
  to handle or skip older versions.
- Known visual residuals: tornado text is small at 1440px wide; on mobile the value line
  and drivers scroll inside their box.
