---
version: 1
slug: "src-bot-web-templates-base-html"
primary_target: "src/bot/web/templates/base.html"
related_targets: []
---

# Surface: analysis web viewer (`bot web`)

Mode: Operate. Audience: Nicolás and technical guests. Job: scan analysed companies, see why each got its MoS verdict. Spec: `docs/superpowers/specs/2026-10-04-web-viewer-design.md`.

## Direction contract

THESIS: The verdict is a position on a hand-drawn value line, not a badge. Refuses the fintech default of KPI cards and green/red pills.

OWN-WORLD: `docs/DESIGN.md` unchanged: tonal sheet on kraft desk, bistre ink, earth pigments as semantic roles (olive selecciona = undervalued, ochre datos = fair, terracotta elimina = overvalued, indigo valúa = intrinsic), Shantell Sans / Literata / Sometype Mono, wobble-filtered SVG groups, server-jittered paths in the list.

STORY: Visitor sees the shortlist sorted by MoS, opens one, reads price vs intrinsic, scenario robustness n/25, drivers, assumption sources, flags. No prose.

FIRST VIEWPORT: Desktop split: list ≈40% left (single-select verdict filter with counts, sortable table with mini value lines); right detail: ticker + name in Shantell, verdict mark + MoS, full-width value line, 5×5 scenario grid beside tornado. No CTAs. Static export, htmx swaps pre-rendered fragments.

FORM: list-detail split, standard table and controls; signature move = value line (full in detail, mini in list). Seed key: 07bd6c47 (composition pinned by spec; world pinned by user).

FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance

FINISH RESULT (Task 8 verdict, recorded 2026-10-04): browser script 5/5 PASS at 1440 and 390; `impeccable detect` returned no findings; `docs/DESIGN.md` unchanged. Known residuals: tornado text is small at 1440; on mobile the value line and the drivers scroll inside their box.
