/**
 * Chart chrome (axes, grid, hover cursor, tooltip, rule lines) for Recharts
 * and for hand-drawn SVG, drawn from the redesign tokens. It follows the chart
 * mockups in `docs/design/redesign/` (standings, debrief, stints): Geist Mono
 * 500 at 10 px in the tertiary ink for ticks, faint ink hairlines for the grid,
 * no axis or tick lines, and tooltips on the raised surface with a hairline
 * border.
 *
 * Each part is a plain props object, so one spread styles either renderer:
 *
 *     <YAxis {...chartTheme.axis} />          <text {...chartTheme.axis.tick}>100</text>
 *     <CartesianGrid {...chartTheme.grid} />  <line {...chartTheme.grid} x1={…} />
 *     <Tooltip {...chartTheme.tooltip} />     <div style={chartTheme.tooltip.contentStyle}>…</div>
 *     <ReferenceLine {...chartTheme.rule} />
 *
 * Series colours are deliberately absent: team colours carry data, and the
 * timing colours keep their F1 meaning (`tokens.ts`).
 */
import { f1, font, rc } from "./tokens";

import type { CSSProperties } from "react";

/** The grid's hairlines: the ink at this opacity, as the mockups draw them. */
const GRID_OPACITY = 0.06;
/** The hover guide over a line chart. */
const CURSOR_LINE_OPACITY = 0.12;
/** The hover band behind a bar. */
const CURSOR_BAND_OPACITY = 0.04;

/** Tick and axis-label text: Geist Mono 500 at 10 px in the tertiary ink. */
const tick = { fill: rc.ink3, fontFamily: font.mono, fontSize: 10, fontWeight: 500 } as const;

const tooltipContent: CSSProperties = {
  background: rc.raised,
  border: `1px solid ${rc.line}`,
  borderRadius: 4,
  padding: "10px 12px",
  color: rc.ink,
  fontFamily: font.sans,
  fontSize: 12,
  lineHeight: 1.5,
};

export const chartTheme = {
  /** Spread onto `<XAxis>` / `<YAxis>`; `axis.tick` alone styles an SVG `<text>`. */
  axis: { tick, axisLine: false, tickLine: false },
  /** Spread onto `<CartesianGrid>` (add `vertical={false}` as needed) or an SVG `<line>`. */
  grid: { stroke: rc.ink, strokeOpacity: GRID_OPACITY },
  /** Spread onto `<Tooltip>`; `contentStyle` also styles a custom tooltip's box. */
  tooltip: {
    contentStyle: tooltipContent,
    labelStyle: { color: rc.ink, fontWeight: 600 },
    itemStyle: { color: rc.ink2, padding: 0 },
    cursor: { stroke: rc.ink, strokeOpacity: CURSOR_LINE_OPACITY },
  },
  /** Replaces `tooltip.cursor` on a bar chart: a faint band instead of a guide line. */
  barCursor: { fill: rc.ink, fillOpacity: CURSOR_BAND_OPACITY },
  /** A rule across the plot (the selected round, a threshold): red fill-and-rule colour. */
  rule: { stroke: f1.red, strokeWidth: 2 },
} as const;
