# F1-AI

## Active plan (Nov 2026): read this first

Work on accuracy fixes, the data platform and the site-wide redesign follows `docs/plans/2026-11-redesign/PLAN.md`. Progress lives in `docs/plans/2026-11-redesign/STATUS.md`.

- **Before any work,** follow PLAN.md's "How to run this plan": check git, open STATUS.md, and re-verify any `in_progress` task before continuing it. Never continue from memory.
- **Visual spec:** `docs/design/redesign/` (start at `index.html`).
- **Data rules:** `docs/DATA_SOURCES.md`. The FIA final classification is the authority, and every special state (retired, red-flag change, pit-lane start, provisional) is labelled.
- **Design rules:** the "Visual and design work" section below reflects PLAN.md's "Locked decisions": Barlow Condensed display titles, the B1 logo, legends allowed.

## Visual and design work

The `design-director` skill (`.claude/skills/design-director/`) applies to new pages, components, charts, decks and reports. In this repo the design system below and the mockups in `docs/design/redesign/` win: elevate within them — hierarchy, spacing, data presentation — rather than inventing a new look.

- **UI kit first:** before building a component, look in `frontend/app/ui/` (`PageHero`, `StatTile(s)`, `PanelHeading`, `SectionHead`, `Segmented`, `DeltaChip`, `Countdown`, `Legend`, `RankBars`, `Gauge`, `SlopeChart`, `SourceBadge`, `Tooltip` …). Extend a kit part rather than building a look-alike.
- **Tokens live in `frontend/app/globals.css`**: `:root` variables plus the Tailwind v4 `@theme inline` block (`text-rc-ink-2`, `bg-rc-gain`, `bg-f1-red`, `font-display` …). New pages and components must use them. Add any new token there instead of hard-coding colors, fonts or animations inline.
- **SVG and Recharts** read the same values from `frontend/app/ui/tokens.ts` (`rc`, `f1`, `font`). `tokens.test.ts` parses `globals.css` and fails on any drift, so change both together.
- **Theme is dark only:** `--background` (page), `--surface` (panels), `--rc-hero` (hero band), `--rc-raised` (tooltips, popovers), `--rc-line` / `--rc-line-soft` (hairlines, row dividers), `--rc-dim` (marks that aren't the story).
- **Type:** Barlow Condensed (`--font-display`) for page titles and section heads, Geist Sans (`--font-sans`) for UI and body, Geist Mono (`--font-mono`) for labels and data. All three load via `next/font` in `frontend/app/layout.tsx`; `app/ui/typography.ts` holds the `EYEBROW` / `DISPLAY` recipes.
- **Text tones:** `--rc-ink` (primary), `--rc-ink-2` (secondary), `--rc-ink-3` (labels, units, captions), each at least 4.5:1 on `--surface`.
- **Red:** `--f1-red` (#e10600) is the one brand accent, for fills and rules only. Red text and live states use `--rc-red-text` (#ff4655).
- **Colors carry meaning, never decoration:**
  - `--rc-gold` = wins, titles, the leader
  - `--rc-blue` = upcoming, info
  - `--rc-gain` = positions gained, and nothing else (not the DRS green)
  - team colors = data only
- **Timing colors carry F1 meaning:**
  - `--f1-sector-best` (purple) = fastest overall
  - `--f1-sector-pb` (green) = personal best
  - `--f1-sector-slow` (yellow) = no improvement
  - `--f1-drs` = DRS

  Use them only with those meanings, never as decoration or generic chart-series colors.

- **Charts:** Recharts takes `chartTheme` and `useChartAnimation` from `app/ui/`. Legends are welcome when they add data points (`app/ui/Legend.tsx`). Every chart title is computed from data, never written by hand.
- **Motion:** entrance only (`animate-fade-up`, `animate-fill-x`, `animate-track-draw` …), behind `motion-safe:` or framer-motion's `useReducedMotion`. Existing glows and loops stay where they are; don't add new glow effects or looping animations.
- **Focus:** one keyboard focus ring, in `globals.css` `@layer base` (2 px `--rc-red-text` outline, 2 px offset). Don't add bespoke rings; a control flush against a clipping edge draws it inside with `focus-visible:-outline-offset-2`.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:

- When graphify-out/graph.json exists, run `graphify query "<question>"` before your first grep, search or source-file read for a codebase question, and put this rule in every subagent prompt that explores code. Read raw files only for lines the graph or an earlier read already located. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
