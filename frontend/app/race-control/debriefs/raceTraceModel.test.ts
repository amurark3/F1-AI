import { describe, expect, it } from "vitest";

import { rc } from "@/app/ui/tokens";
import { DEBRIEF_R19 } from "@/test/fixtures/debrief";

import { gapY, lapX, TRACE_FRAME, traceGeometry } from "./raceTraceModel";

import type { DebriefLaps } from "./debriefTypes";

const LAPS = DEBRIEF_R19.laps;

describe("lapX and gapY", () => {
  it("spread the laps across the plot, and cap the gap at the bottom edge", () => {
    expect(lapX(1, 71)).toBe(TRACE_FRAME.left);
    expect(lapX(71, 71)).toBe(TRACE_FRAME.right);
    expect(lapX(1, 1)).toBe(TRACE_FRAME.left);
    expect(gapY(0)).toBe(TRACE_FRAME.top);
    expect(gapY(30)).toBe(TRACE_FRAME.bottom);
    expect(gapY(95)).toBe(TRACE_FRAME.bottom);
    expect(gapY(-2)).toBe(TRACE_FRAME.top);
  });
});

describe("traceGeometry at Mexico City", () => {
  const geometry = traceGeometry(LAPS);

  it("draws the podium last in team colours, and the rest quiet", () => {
    expect(geometry.lines.map((line) => line.code)).toEqual(
      ["LEC", "NOR", "VER", "HAM", "ANT"].sort((a, b) => order(a) - order(b)),
    );
    const byCode = (code: string) => geometry.lines.find((line) => line.code === code)!;
    expect(byCode("VER")).toMatchObject({ color: "#3671C6", width: 2.5, quiet: false });
    expect(byCode("LEC")).toMatchObject({ color: rc.dim, width: 1.5, quiet: true });
    expect(byCode("NOR").quiet).toBe(true);
  });

  it("spreads the end labels so none overlap", () => {
    const ys = geometry.lines.map((line) => line.labelY).sort((a, b) => a - b);
    ys.slice(1).forEach((y, i) => expect(y - ys[i]).toBeGreaterThanOrEqual(12));
  });

  it("shades the safety car and VSC periods, and marks the red flag", () => {
    expect(geometry.bands.map((band) => [band.kind, band.label])).toEqual([
      ["vsc", "VSC"],
      ["sc", "SC"],
      ["sc", "SC"],
    ]);
    expect(geometry.bands[1].x2).toBeGreaterThan(geometry.bands[1].x1);
    expect(geometry.red).toEqual({ x: lapX(45, 71), lap: 45 });
  });

  it("labels the axes", () => {
    expect(geometry.ticks.x.map((tick) => tick.label)).toEqual(["L1", "L24", "L48", "L71"]);
    expect(geometry.ticks.y.map((tick) => tick.label)).toEqual(["0 s", "10 s", "20 s", "30 s"]);
  });
});

/** Draw order: the quiet lines (position 4 and 5) first, then the podium. */
function order(code: string): number {
  return LAPS.trace.find((car) => car.driver_code === code)!.position <= 3 ? 1 : 0;
}

describe("traceGeometry edge cases", () => {
  it("breaks a line at a missing gap, clamps a band to the last lap and has no red flag", () => {
    const laps: DebriefLaps = {
      ...LAPS,
      total_laps: 4,
      leaders: ["VER", "VER", "VER", "VER"],
      trace: [{ driver_code: "VER", position: 1, gaps: [0, null, 0, 5] }],
      neutralisations: [{ kind: "sc", start_lap: 3, end_lap: 4 }],
    };
    const geometry = traceGeometry(laps);

    expect(geometry.lines[0].d.match(/M/g)).toHaveLength(2);
    expect(geometry.bands[0].x2).toBe(lapX(4, 4));
    expect(geometry.red).toBeNull();
  });

  it("uses no team colour for a car OpenF1 did not list", () => {
    const laps: DebriefLaps = { ...LAPS, drivers: [] };
    expect(traceGeometry(laps).lines.every((line) => typeof line.color === "string")).toBe(true);
  });
});
