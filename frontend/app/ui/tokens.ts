/**
 * Design tokens for code that cannot use a CSS class: SVG attributes and
 * Recharts props. Elsewhere use the Tailwind classes that `globals.css`
 * exposes (`text-rc-ink-2`, `bg-f1-red`, `font-display`).
 *
 * Every value mirrors a custom property in `app/globals.css`, and
 * `tokens.test.ts` parses that file so the two cannot drift. Change both
 * together.
 */

/**
 * Redesign palette (`docs/design/redesign/system.css`). Key `ink2` is
 * `--rc-ink-2` in `:root` and `text-rc-ink-2` in Tailwind.
 *
 * Every colour carries a meaning; none is decoration.
 */
export const rc = {
  /** Hero band, and the tile of the B1 logo mark (`app/icon.svg`). */
  hero: "#0b0f18",
  /** Primary text. */
  ink: "#f0f2f6",
  /** Secondary text. */
  ink2: "#aeb6c6",
  /** Tertiary text: labels, units, captions. Still ≥ 4.5:1 on a panel. */
  ink3: "#7f8797",
  /** Red read as text, and live. Fills and rules use `f1.red`. */
  redText: "#ff4655",
  /** Wins, titles, the leader. */
  gold: "#ffc93c",
  /** Upcoming, info. */
  blue: "#4c8dff",
  /** Positions gained, only. Not the DRS green. */
  gain: "#00d66b",
} as const;

/**
 * The F1 brand red and timing colours (`--f1-*` in `:root`). The timing
 * colours keep their F1 meaning and are never generic series colours.
 */
export const f1 = {
  /** The one brand accent: fills and rules. */
  red: "#e10600",
  /** DRS. */
  drs: "#00ff78",
  /** Fastest overall. */
  sectorBest: "#be3aff",
  /** Personal best. */
  sectorPb: "#00cc00",
  /** No improvement. */
  sectorSlow: "#fff200",
} as const;

/** Font stacks, equal to the `--font-*` entries in `@theme inline`. */
export const font = {
  /** Barlow Condensed: page titles and section heads. */
  display: 'var(--font-barlow), "Arial Narrow", sans-serif',
  /** Geist Sans: UI and body. */
  sans: "var(--font-geist-sans)",
  /** Geist Mono: labels and data. */
  mono: "var(--font-geist-mono)",
} as const;
