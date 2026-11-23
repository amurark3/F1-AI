/** Geometry of the lap chart, kept apart from the markup. The numbers follow `docs/design/redesign/race-rewind.html`. */

import { getTeamColor } from "@/app/lib/teamColors";
import { spreadLabels } from "@/app/ui/slopeLayout";
import { rc } from "@/app/ui/tokens";

import { leaderRuns } from "../debriefs/lapsModel";
import { linePath, xTicks } from "../standings/titleRaceModel";

import { leaders, stepKind } from "./rewindModel";

import type { RaceRewind } from "./rewindTypes";

export const CHART_FRAME = {
  width: 900,
  height: 560,
  left: 40,
  right: 860,
  top: 14,
  bottom: 518,
  labelX: 866,
  axisY: 546,
} as const;

const LABEL_GAP = 12;
const PLACE_TICKS = [1, 5, 10, 15, 20];

export interface ChartLine {
  code: string;
  d: string;
  color: string;
  width: number;
  leader: boolean;
}

export interface ChartBand {
  x1: number;
  x2: number;
  label: string;
}

export interface ChartGeometry {
  lines: ChartLine[];
  /** Where each retired car's line ends. */
  crosses: Array<{ code: string; x: number; y: number }>;
  bands: ChartBand[];
  red: { x: number; lap: number } | null;
  ticks: { x: Array<{ x: number; label: string }>; y: Array<{ y: number; label: string }> };
  /** The leaders' codes at the right edge, spread apart. */
  labels: Array<{ code: string; y: number; color: string }>;
  leaders: Array<{ code: string; color: string }>;
}

/** The x of the line after `lap` laps (0 = the grid). */
export function lapX(lap: number, total: number): number {
  const { left, right } = CHART_FRAME;
  return left + ((right - left) * lap) / total;
}

/** The y of a place among `cars`: P1 on top. */
export function placeY(place: number, cars: number): number {
  const { top, bottom } = CHART_FRAME;
  return top + ((bottom - top) * (place - 1)) / Math.max(cars - 1, 1);
}

/** A car's place after the grid and every lap, null where it has none. */
function placesOf(data: RaceRewind, code: string): Array<number | null> {
  const place = (order: readonly string[]) => (order.includes(code) ? order.indexOf(code) + 1 : null);
  return [place(data.grid.order), ...data.laps.map((lap) => place(lap.order))];
}

function teamOf(data: RaceRewind, code: string): string {
  return data.drivers.find((driver) => driver.driver_code === code)?.team ?? "";
}

function lineFor(data: RaceRewind, code: string, leader: boolean): ChartLine {
  const cars = data.drivers.length;
  return {
    code,
    d: linePath(
      placesOf(data, code),
      (i) => lapX(i, data.total_laps),
      (place) => placeY(place, cars),
    ),
    color: leader ? getTeamColor(teamOf(data, code)) : rc.dim,
    width: leader ? 2.5 : 1.2,
    leader,
  };
}

function endOf(data: RaceRewind, code: string): { x: number; y: number } {
  const places = placesOf(data, code);
  const index = places.findLastIndex((place) => place !== null);
  return { x: lapX(index, data.total_laps), y: placeY(places[index] ?? 1, data.drivers.length) };
}

export function chartGeometry(data: RaceRewind): ChartGeometry {
  const { total_laps: total, drivers } = data;
  const led = [...new Set(leaderRuns(leaders(data)).flatMap((run) => (run.code ? [run.code] : [])))];
  const codes = drivers.map((driver) => driver.driver_code);
  // The leaders are drawn last, so they sit on top of the dim lines.
  const lines = [
    ...codes.filter((code) => !led.includes(code)).map((code) => lineFor(data, code, false)),
    ...led.map((code) => lineFor(data, code, true)),
  ];
  const ends = led.map((code) => endOf(data, code));
  const labelYs = spreadLabels(
    ends.map((end) => end.y + 4),
    LABEL_GAP,
    [CHART_FRAME.top, CHART_FRAME.bottom],
  );
  const red = data.neutralisations.find((period) => period.kind === "red");
  return {
    lines,
    crosses: drivers
      .filter((driver) => driver.status === "dnf")
      .map((driver) => ({ code: driver.driver_code, ...endOf(data, driver.driver_code) })),
    bands: data.neutralisations.flatMap((period) =>
      period.kind === "red"
        ? []
        : [
            {
              x1: lapX(period.start_lap - 1, total),
              x2: lapX(period.end_lap, total),
              label: period.kind === "vsc" ? "VSC" : "SC",
            },
          ],
    ),
    red: red ? { x: lapX(red.start_lap, total), lap: red.start_lap } : null,
    ticks: {
      x: xTicks(total).map((i) => ({ x: lapX(i + 1, total), label: `L${i + 1}` })),
      y: PLACE_TICKS.filter((place) => place <= drivers.length).map((place) => ({
        y: placeY(place, drivers.length),
        label: `P${place}`,
      })),
    },
    labels: led.map((code, index) => ({ code, y: labelYs[index], color: getTeamColor(teamOf(data, code)) })),
    leaders: led.map((code) => ({ code, color: getTeamColor(teamOf(data, code)) })),
  };
}

/** The cursor's x: the grid at 0, a lap at its number, the final step at the flag. */
export function cursorX(data: RaceRewind, step: number): number {
  const at = stepKind(step, data);
  if (at.kind === "grid") return lapX(0, data.total_laps);
  return lapX(at.kind === "lap" ? at.lap : data.total_laps, data.total_laps);
}
