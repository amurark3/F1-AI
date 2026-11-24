# F1-AI

## Project rules

The November 2026 redesign, data platform and backend hardening are complete (finished 2026-11-23). Their plans, task briefs and HTML mockups were deleted afterwards; read them in git history at `9a814aa` if you need the old reasoning. The shipped code is now the reference for how each page looks.

- **Hosting:** Render (backend) + Supabase (Postgres + pgvector) + Vercel (frontend). A cron-job.org GET on `/api/health/deep` every 5 minutes keeps Render warm. The Oracle VM move is deferred, not scheduled: see `docs/plans/oracle-deferred/PLAN.md`, and don't start it unless the user says they have a VM.
- **Data rules:** `docs/DATA_SOURCES.md`, mandatory before any data task. The FIA final classification is the authority. Label every special state (retired, did not start, disqualified, red-flag change, pit-lane start, provisional, stop time not published). Never infer finish status from laps or stints. OpenF1 goes through `app/data/openf1/client.get_json` and its pacer only; FIA pages through `app/data/power_units/fia_site.PoliteFetcher`.
- **Names:** f1db is canonical (`driver.name` / `last_name` / `abbreviation`, the constructor id), resolved on the read path, with no identity table. Full name in heroes, code + surname in tables, code on chart axes, always via `DriverName` / `TeamName`.
- **Loading:** no page awaits backend data at page level. The shell renders at once; each data section is its own Suspense boundary or `useSection` fetch with its own skeleton. A section that has data keeps it, marked stale, when a refresh fails. One endpoint per independent section. The server-warm-up notice never blocks a page.
- **Homepage** (`/`) is static: it fetches nothing and shows no live or baked-in data.
- **Navigation:** one top bar, grouped by job: Race Control, then menus Races, Season and Reference, with AI Engineer on the right; the race pages share a "This race" switcher.
- **Frontend gates:** `npm run lint` (clean, never `eslint-disable`), `typecheck`, `test:coverage` (literal 100 % per file across `app/**`, no coverage-ignore comments; delete dead code instead), `build`, `npx playwright test`. Prettier only on changed files.
- **Backend gates:** `.venv/bin/python -m pytest -q` (100 %), Ruff lint/format. Build `.venv` from `requirements-ingest.txt` + `requirements-dev.txt`; keep `requests==2.33.1`; one FastF1 lock (`app/utils/fastf1_lock.py`).
- **Running locally:** `backend/.env` holds no production credentials; production values live in the untracked `backend/.env.production`, opted into with `.venv/bin/dotenv -f .env.production run -- …`. After `next dev`, delete the untracked `frontend/AGENTS.md` it writes.
- **TDD:** write the failing test first for every model, hook, parser and resolver.

## Visual and design work

The `design-director` skill (`.claude/skills/design-director/`) applies to new pages, components, charts, decks and reports. In this repo the design system below and the shipped pages win: elevate within them — hierarchy, spacing, data presentation — rather than inventing a new look. The logo is B1 "Apex" (`app/ui/BrandLockup.tsx`).

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
  - `--rc-silver` / `--rc-bronze` = P2 / P3 finishes only
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
