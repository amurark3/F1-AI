# F1-AI

## Visual and design work

The `design-director` skill (`.claude/skills/design-director/`) applies to new pages, components, charts, decks and reports. In this repo the existing design system wins: elevate within it — hierarchy, spacing, data presentation — rather than restyling the app.

- **Tokens live in `frontend/app/globals.css`**: `:root` variables plus the Tailwind v4 `@theme inline` block. New pages and components must use them. Add any new token there instead of hard-coding colors, fonts or animations inline.
- **Theme is dark only:** `--background`, `--surface` / `--surface-raised`, `--border-subtle` / `--border-dim`, `--foreground`.
- **Type:** Geist Sans (`--font-sans`) and Geist Mono (`--font-mono`), loaded via `next/font` in `frontend/app/layout.tsx`.
- **Accent:** `--f1-red` (#e10600) is the one brand accent.
- **Timing colors carry F1 meaning:**
  - `--f1-sector-best` (purple) = fastest overall
  - `--f1-sector-pb` (green) = personal best
  - `--f1-sector-slow` (yellow) = no improvement
  - `--f1-drs` = DRS

  Use them only with those meanings, never as decoration or generic chart-series colors.

- **Glows and animations** (`--f1-*-glow`, `--animate-*`) are part of the established look. Reuse them where existing components do, but don't add new glow effects or looping animations.
