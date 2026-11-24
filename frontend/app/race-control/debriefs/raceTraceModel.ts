/** Geometry of the race trace, kept apart from the markup. */

import { getTeamColor } from "@/app/lib/teamColors";
import { spreadLabels } from "@/app/ui/slopeLayout";
import { rc } from "@/app/ui/tokens";

import { linePath, xTicks } from "../standings/titleRaceModel";

import type { DebriefLaps } from "./debriefTypes";

/** The chart's frame, in viewBox units. */
export const TRACE_FRAME = {
  width: 900,
  height: 300,
  left: 34,
  right: 840,
  top: 10,
  bottom: 276,
  labelX: 848,
} as const;

/** Gaps above this are drawn at the bottom edge. */
export const GAP_CAP_SECONDS = 30;
const GAP_TICKS = [0, 10, 20, 30];
const LABEL_GAP = 12;
const PODIUM = 3;

export interface TraceLine {
  code: string;
  color: string;
  width: number;
  /** Not on the podium: drawn in the dim tone. */
  quiet: boolean;
  d: string;
  labelY: number;
}

export interface TraceBand {
  kind: "sc" | "vsc";
  x1: number;
  x2: number;
  label: string;
}

export interface TraceGeometry {
  lines: TraceLine[];
  bands: TraceBand[];
  /** The red flag's rule and label; null when the race had none. */
  red: { x: number; lap: number } | null;
  ticks: { x: Array<{ x: number; label: string }>; y: Array<{ y: number; label: string }> };
}

/** The x of a lap's line crossing, evenly spaced from the first lap to the last. */
export function lapX(lap: number, total: number): number {
  const { left, right } = TRACE_FRAME;
  return total > 1 ? left + ((right - left) * (lap - 1)) / (total - 1) : left;
}

/** The y of a gap in seconds: the leader on top, capped gaps on the bottom edge. */
export function gapY(gap: number): number {
  const { top, bottom } = TRACE_FRAME;
  return top + ((bottom - top) * Math.min(Math.max(gap, 0), GAP_CAP_SECONDS)) / GAP_CAP_SECONDS;
}

/** The last known gap, for the end label's height. */
const lastGap = (gaps: ReadonlyArray<number | null>): number => gaps.findLast((gap) => gap !== null) ?? 0;

export function traceGeometry(laps: DebriefLaps): TraceGeometry {
  const total = laps.total_laps;
  const teamOf = (code: string) => laps.drivers.find((driver) => driver.driver_code === code)?.team ?? "";
  const labelYs = spreadLabels(
    laps.trace.map((car) => gapY(lastGap(car.gaps)) + 4),
    LABEL_GAP,
    [TRACE_FRAME.top, TRACE_FRAME.bottom],
  );
  const lines = laps.trace.map<TraceLine>((car, index) => ({
    code: car.driver_code,
    color: car.position <= PODIUM ? getTeamColor(teamOf(car.driver_code)) : rc.dim,
    width: car.position <= PODIUM ? 2.5 : 1.5,
    quiet: car.position > PODIUM,
    d: linePath(car.gaps, (i) => lapX(i + 1, total), gapY),
    labelY: labelYs[index],
  }));
  const bands = laps.neutralisations.flatMap<TraceBand>((period) =>
    period.kind === "red"
      ? []
      : [
          {
            kind: period.kind,
            x1: lapX(period.start_lap, total),
            x2: lapX(Math.min(period.end_lap + 1, total), total),
            label: period.kind === "vsc" ? "VSC" : "SC",
          },
        ],
  );
  const flag = laps.neutralisations.find((period) => period.kind === "red");
  return {
    // The podium is drawn last, so it sits on top of the quiet lines.
    lines: [...lines.filter((line) => line.quiet), ...lines.filter((line) => !line.quiet)],
    bands,
    red: flag ? { x: lapX(flag.start_lap, total), lap: flag.start_lap } : null,
    ticks: {
      x: xTicks(total).map((i) => ({ x: lapX(i + 1, total), label: `L${i + 1}` })),
      y: GAP_TICKS.map((gap) => ({ y: gapY(gap), label: `${gap} s` })),
    },
  };
}
