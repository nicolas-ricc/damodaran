# Company profiles: what each company does, and the industries it lives on

**Date:** 2026-11-08
**Status:** design, pending approval
**Scope:** a committed data file of per-company descriptions and industry tags, how it is
produced once, how the read-only viewer (`bot site`, `src/bot/web/`) shows it, and how the
viewer's search box (#263) matches on it.

## 1. Intent

Opening a company's analysis page today shows a ticker, a name and numbers. The reader has
to already know what the company does. Two things are missing:

1. **A plain description** of the business, readable right below the ticker and name.
2. **Industry tags** so the search box finds companies by what they do: typing `cybersec`
   lists the companies that live on cybersecurity.

The existing sector labels cannot do this. Each company carries a SEC SIC description and a
Damodaran industry, both too coarse: CrowdStrike, Adobe and Oracle all map to
"Software (System & Application)".

## 2. The tagging rule (decided with the user)

A tag means **the company lives on that business**, not that it touches it.

- A tag is given only when that business is **at least ~10% of the company's revenue**. The
  threshold mirrors the SEC's reportable-segment rule (ASC 280), so most of the time the
  number is published.
- The share is measured on the latest 10-K's fiscal year.
- The share comes, in this order of preference, from the 10-K's **reportable segments** or
  its **revenue disaggregation** note. When neither isolates the business, the share is a
  **judgment** made reading the 10-K, and it is recorded as such.
- Each tag records its approximate revenue share and its source kind (`segment`,
  `disaggregation`, `judgment`). The company records the fiscal year and the EDGAR accession
  number of the 10-K all its tags came from (one filing per company).
- A business buried inside a broader reported line and not separable stays untagged. The
  user's example: Apple reports Services (~25%) but does not break out streaming, so Apple
  does not get a `streaming` tag. This is accepted.
- Every company has at least one tag (its main business). Shares of one company's tags sum
  to at most 100%.

## 3. Goals

- Every company in the default universe (`src/bot/ingest/universe_default.csv`, ~500
  tickers, not only the ~80 analysed today) has a description and tags.
- The detail page shows the description and the tags under the `<h1>`.
- The search box matches a query against tags as well as ticker and name.
- The data is generated **once**, committed, and editable by hand. The bot never calls an
  LLM or any new service at run time.

## 4. Non-goals

- Automatic refresh. Profiles go stale until someone regenerates or edits them.
- Showing tags in the list table. The search matches them; the list does not display them
  (my call: the table is already nine columns).
- Spanish text or Spanish search terms. The site is English; the user searches in English.
- Feeding tags into the screener, valuation or Damodaran industry mapping. Display and
  search only.
- Fuzzy or synonym search beyond substring matching.

## 5. Anti-goals

- A tag on a company where that business is a sideline. A search for `cybersecurity` that
  returns Microsoft and Cisco next to CrowdStrike has failed, even if Microsoft really sells
  security products.
- A tag or share presented as a fact when it was a judgment.
- Free-text tags that split one industry into variants (`cyber-security`, `infosec`,
  `security-software`).

## 6. Data

Two files under `config/` (my call on location: they are hand-editable reference data, like
`config/default_spreads.yaml`).

### 6.1 `config/industry_tags.yaml`: the vocabulary

A fixed list, targeting ~60–100 tags. The count is a target, not a cap: when it conflicts
with "every company has at least one tag at ≥10% of revenue", coverage wins and the list
grows (my call). Sectors where narrowness does not serve search (utilities, REITs, banks)
may use broad tags. Each entry: a kebab-case `slug` (`cybersecurity`,
`semiconductors`, `cloud-infrastructure`), a display `label` ("Cybersecurity") and a
one-sentence `description` used as the chip's tooltip. Granularity target: narrow enough
that the anti-goal holds (cybersecurity is its own tag, not "software"), broad enough that
most tags have several S&P 500 members. The builder drafts the vocabulary first, from the
universe, before tagging any company. The user does not sign it off beforehand (decided by
the user): the work runs in one pass, and the vocabulary is reviewed with the rest in the
PR.

### 6.2 `config/company_profiles.yaml`: one entry per ticker

```yaml
CRWD:
  description: >-
    Sells cloud-delivered endpoint security: software that runs on companies' laptops and
    servers to detect and stop intrusions, plus identity and cloud-workload protection,
    sold as subscriptions.
  fiscal_year: 2026
  accession: 0001535527-26-000012
  tags:
    - {tag: cybersecurity, share: 0.95, source: segment}
AAPL:
  description: >-
    ...
  fiscal_year: 2025
  accession: 0000320193-25-000079
  tags:
    - {tag: smartphones, share: 0.51, source: disaggregation}
    - {tag: digital-services, share: 0.25, source: disaggregation}
    - {tag: personal-computers, share: 0.10, source: disaggregation}
```

- `description`: 2–3 plain-English sentences on what the company sells and to whom. No
  marketing language, no valuation opinion.
- `share`: fraction of revenue, rounded to two decimals; `>= 0.10`.
- `source`: one of `segment`, `disaggregation`, `judgment`.
- `accession`: the EDGAR accession number of the 10-K read (format `##########-##-######`),
  so a reviewer can open the filing and check a share (my call). Accession numbers in the
  example above are illustrative.
- Ticker keys use the universe's format (`BRK-B`).

### 6.3 Validation

A loader in `src/bot/` (location left to the builder) parses both files and rejects: a tag
not in the vocabulary, a share below 0.10 or above 1, a company's shares summing above 1, an
unknown source, an empty tag list, an empty description, a malformed accession number. A test runs the loader on the
committed files. A test also asserts every ticker in `universe_default.csv` has a profile;
it may allow an explicit, listed set of exceptions if a 10-K is unavailable.

## 7. Generating the profiles (one time)

Done by an agent session, not by bot code: for each ticker, read the latest 10-K's Item 1
(Business) and the segment / revenue-disaggregation note from SEC EDGAR, write the
description, pick tags from the vocabulary, and record share, source and fiscal year. How the
agent fetches and batches the filings is left to the builder. Spot-check a sample by hand
(at least the conglomerates and the obvious edge cases: AAPL, AMZN, GOOGL, MSFT, BRK-B, GE,
a cybersecurity pure play). The output is the two YAML files; nothing else is committed from
the generation.

No `anthropic` or other LLM dependency enters `pyproject.toml`.

## 8. Viewer

`bot site` reads `config/company_profiles.yaml` and `config/industry_tags.yaml` in addition
to the sidecars. The site stays a pure function of committed files (ADR 0008). A missing
profile for a ticker is not an error: the page renders without the description and tags.

### 8.1 Detail page

Below the `<h1>` (ticker and name) in `detail.html`:

- the description as a paragraph;
- the tags as DaisyUI badges, in descending share. Each badge shows the label. Its tooltip
  (the glossary/tooltip pattern merged in #267) gives the tag's description and the share
  and source in words, e.g. "~95% of revenue, reported segment, FY2026" or "~30% of revenue,
  estimated from the 10-K, FY2025".

Styling follows `docs/DESIGN.md` (DaisyUI synthwave). Exact component choice is left to the
builder within that system.

### 8.2 Search

The search box (#263, `viewer.js` `applySearch`) today matches the query as a substring of
the ticker or name cell. It also matches it as a substring of any of the row's tag slugs or
labels. The tags reach the row as a data attribute on the `<tr>` (e.g. `data-tags`), so
they are searchable but not displayed. Matching stays case-insensitive substring: `cybersec`
matches `cybersecurity`. Composition with the verdict filter, the count, and the no-match
row are unchanged. The search placeholder / label mentions industry.

## 9. Delivery

A new issue, built on top of #257 (the DaisyUI restyle and search), which must be merged
first. #267 (tooltips) is on master but not on the #257 branch and both touch
`detail.html`, so #257 is merged or rebased onto master before the viewer step. Suggested split, left to the builder: (1) vocabulary + loader + validation tests,
(2) generated profiles, (3) viewer and search. `ruff check`, `mypy`, `pytest` green. Do not
run `ruff format` on the tree.

## 10. Left to the builder

- Module and function names for the loader; where it is wired into `site.py`.
- The exact tag vocabulary (reviewed by the user in the PR).
- How the generation agent fetches EDGAR filings and batches ~500 companies.
- Badge styling within DaisyUI synthwave.
