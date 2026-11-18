/**
 * Geometry and wording for the title-race chart, kept apart from the markup so
 * it is tested directly. The numbers follow `docs/design/redesign/standings.html`.
 */

import { getTeamColor } from "@/app/lib/teamColors";
import { driverLabel, type NameDirectory } from "@/app/ui/names/names";
import { spreadLabels } from "@/app/ui/slopeLayout";
import { rc } from "@/app/ui/tokens";

import { venueOf, type Clinched, type ProgressionEntrant, type ProgressionRound } from "./standingsModel";
import { formatPoints } from "./teamsModel";

/** The chart's frame, in viewBox units. */
export const FRAME = { width: 480, height: 300, left: 30, right: 426, top: 8, bottom: 278, labelX: 432 } as const;

const LABEL_GAP = 12;
const LINES = 5;

/** The y axis: its top is the largest value rounded up to a step of 25, 50 or 100. */
export function yScale(max: number): { top: number; ticks: number[] } {
  let step = 100;
  if (max <= 100) step = 25;
  else if (max <= 200) step = 50;
  const top = Math.max(step, Math.ceil(max / step) * step);
  return { top, ticks: Array.from({ length: top / step + 1 }, (_, i) => i * step) };
}

/** Indices of the rounds the x axis labels: four evenly spread, without repeats. */
export function xTicks(count: number): number[] {
  return [...new Set([0, 1, 2, 3].map((k) => Math.round((k * (count - 1)) / 3)))];
}

/** One path per run of known points; a run of one is drawn as a dot (a round linecap on a zero-length line). */
export function linePath(
  values: ReadonlyArray<number | null>,
  x: (i: number) => number,
  y: (v: number) => number,
): string {
  const runs: string[][] = [];
  let current: string[] | null = null;
  values.forEach((value, i) => {
    if (value === null) {
      current = null;
      return;
    }
    if (current === null) {
      current = [];
      runs.push(current);
    }
    current.push(`${x(i)} ${y(value)}`);
  });
  return runs.map((run) => `M${run[0]} L${(run.length === 1 ? run : run.slice(1)).join(" L")}`).join(" ");
}

export interface ChartLine {
  key: string;
  color: string;
  width: number;
  /** Not the story: drawn in the dim tone. */
  quiet: boolean;
  d: string;
  label: string;
  labelY: number;
}

export interface ChartMarker {
  cx: number;
  cy: number;
  label: string;
  anchor: "start" | "end";
  labelX: number;
  labelY: number;
}

export interface ChartGeometry {
  lines: ChartLine[];
  ticks: { x: Array<{ x: number; label: string }>; y: Array<{ y: number; label: string }> };
  marker: ChartMarker | null;
}

const lastValue = (points: ReadonlyArray<number | null>): number => points.findLast((p) => p !== null) ?? 0;

/** The top five lines (the leader last, so it sits on top), their end labels and the clinch marker. */
export function chartGeometry(
  rounds: readonly ProgressionRound[],
  entrants: readonly ProgressionEntrant[],
  clinched: Clinched | null,
): ChartGeometry {
  const shown = entrants.slice(0, LINES);
  const scale = yScale(Math.max(0, ...shown.map((e) => lastValue(e.points))));
  const x = (i: number) =>
    rounds.length > 1 ? FRAME.left + ((FRAME.right - FRAME.left) * i) / (rounds.length - 1) : FRAME.left;
  const y = (v: number) => FRAME.bottom - ((FRAME.bottom - FRAME.top) * v) / scale.top;

  const labelYs = spreadLabels(
    shown.map((e) => y(lastValue(e.points)) + 4),
    LABEL_GAP,
    [FRAME.top, FRAME.bottom],
  );
  const lines = shown.map<ChartLine>((entrant, index) => ({
    key: entrant.key,
    color: index === 0 ? getTeamColor(entrant.team) : rc.dim,
    width: index === 0 ? 3 : 1.5,
    quiet: index !== 0,
    d: linePath(entrant.points, x, y),
    label: `${entrant.key} ${formatPoints(lastValue(entrant.points))}`,
    labelY: labelYs[index],
  }));

  return {
    lines: [...lines.slice(1), ...lines.slice(0, 1)],
    ticks: {
      x: xTicks(rounds.length).map((i) => ({ x: x(i), label: `R${rounds[i].round}` })),
      y: scale.ticks.map((v) => ({ y: y(v), label: String(v) })),
    },
    marker: markerOf(rounds, shown[0], clinched, { x, y }),
  };
}

function markerOf(
  rounds: readonly ProgressionRound[],
  leader: ProgressionEntrant | undefined,
  clinched: Clinched | null,
  { x, y }: { x: (i: number) => number; y: (v: number) => number },
): ChartMarker | null {
  const index = clinched ? rounds.findIndex((r) => r.round === clinched.round) : -1;
  const points = leader?.points[index];
  if (!clinched || points == null) return null;
  const cx = x(index);
  const anchor = cx > (FRAME.left + FRAME.right) / 2 ? "end" : "start";
  return {
    cx,
    cy: y(points),
    label: `Clinched · R${clinched.round} ${venueOf(rounds, clinched.round)}`,
    anchor,
    labelX: anchor === "end" ? cx - 8 : cx + 8,
    labelY: y(points) - 12,
  };
}

/** The finding as a sentence, from where the leader took the lead for good. */
export function titleRaceTitle(
  leader: ProgressionEntrant,
  rounds: readonly ProgressionRound[],
  decided: boolean,
  directory?: NameDirectory,
): string {
  const who = driverLabel({ name: leader.name, code: leader.key }, "last", directory);
  const from = leader.positions.findLastIndex((p) => p !== 1) + 1;
  const where = from === 0 ? "the first round" : venueOf(rounds, from + 1);
  return decided ? `${who} led from ${where} and never gave it back` : `${who} has led since ${where}`;
}

export function titleRaceSub(rounds: readonly ProgressionRound[], lines: number): string {
  const last = rounds.at(-1);
  const base = `Cumulative points by round · top ${lines}`;
  return last?.provisional ? `${base} · round ${last.round} provisional` : base;
}
