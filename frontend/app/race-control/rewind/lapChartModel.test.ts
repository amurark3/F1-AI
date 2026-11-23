import { describe, expect, it } from "vitest";

import { getTeamColor } from "@/app/lib/teamColors";
import { rc } from "@/app/ui/tokens";
import { REWIND_R19 as r19 } from "@/test/fixtures/rewind";
import { driver, lap, race } from "@/test/fixtures/rewindHandBuilt";

import { CHART_FRAME, chartGeometry, cursorX, lapX, placeY } from "./lapChartModel";

describe("the frame", () => {
  it("spreads the laps across the plot, the grid at the left edge", () => {
    expect(lapX(0, 71)).toBe(CHART_FRAME.left);
    expect(lapX(71, 71)).toBe(CHART_FRAME.right);
    expect(placeY(1, 22)).toBe(CHART_FRAME.top);
    expect(placeY(22, 22)).toBe(CHART_FRAME.bottom);
    expect(placeY(1, 1)).toBe(CHART_FRAME.top);
  });

  it("puts the cursor on the grid, the lap and the flag", () => {
    expect(cursorX(r19, 0)).toBe(CHART_FRAME.left);
    expect(cursorX(r19, 44)).toBe(lapX(44, 71));
    expect(cursorX(r19, 72)).toBe(CHART_FRAME.right);
  });
});

describe("R19's chart", () => {
  const geometry = chartGeometry(r19);

  it("draws the three leaders last, in their team colours, over the dim field", () => {
    expect(geometry.lines).toHaveLength(22);
    const leaders = geometry.lines.filter((line) => line.leader);
    expect(geometry.lines.slice(-3)).toEqual(leaders);
    expect(leaders.map((line) => line.code).sort()).toEqual(["ANT", "LEC", "VER"]);
    expect(leaders.every((line) => line.width === 2.5)).toBe(true);
    expect(leaders.find((line) => line.code === "VER")?.color).toBe(getTeamColor("Red Bull Racing"));
    const others = geometry.lines.filter((line) => !line.leader);
    expect(others.every((line) => line.color === rc.dim && line.width === 1.2)).toBe(true);
  });

  it("marks the five retirements where their lines end", () => {
    expect(geometry.crosses.map((cross) => cross.code).sort()).toEqual(["ALO", "BEA", "BOT", "LIN", "STR"]);
    const lin = geometry.crosses.find((cross) => cross.code === "LIN");
    expect(lin?.x).toBe(lapX(58, 71));
  });

  it("shades the Safety Car and VSC laps and rules the red flag", () => {
    expect(geometry.bands.map((band) => band.label)).toEqual(["VSC", "SC", "SC"]);
    expect(geometry.bands[1]).toMatchObject({ x1: lapX(43, 71), x2: lapX(44, 71) });
    expect(geometry.red).toEqual({ x: lapX(45, 71), lap: 45 });
  });

  it("ticks P1 to P20 and four laps, and spreads the leaders' end labels", () => {
    expect(geometry.ticks.y.map((tick) => tick.label)).toEqual(["P1", "P5", "P10", "P15", "P20"]);
    expect(geometry.ticks.x.map((tick) => tick.label)).toEqual(["L1", "L24", "L48", "L71"]);
    const ys = geometry.labels.map((label) => label.y).sort((a, b) => a - b);
    expect(ys[1] - ys[0]).toBeGreaterThanOrEqual(12);
    expect(geometry.leaders).toHaveLength(3);
  });
});

describe("a small chart", () => {
  it("has no bands, no red flag and only the ticks its field reaches", () => {
    const geometry = chartGeometry(race());

    expect(geometry.bands).toEqual([]);
    expect(geometry.red).toBeNull();
    expect(geometry.ticks.y.map((tick) => tick.label)).toEqual(["P1"]);
  });

  it("ends a retired car that never had a place at the left of the plot", () => {
    const data = race({
      drivers: [driver("AAA"), driver("BBB"), driver("CCC"), driver("DDD", { status: "dnf", laps: 0 })],
      laps: [lap(1, ["AAA", "BBB", "CCC"]), lap(2, ["AAA", "BBB", "CCC"]), lap(3, ["AAA", "BBB", "CCC"])],
    });

    expect(chartGeometry(data).crosses).toEqual([{ code: "DDD", x: lapX(-1, 3), y: CHART_FRAME.top }]);
  });

  it("draws a leader the entry list lacks in the neutral team colour, and skips a lap nobody led", () => {
    const data = race({ laps: [lap(1, ["ZZZ", "AAA"]), lap(2, []), lap(3, ["AAA"])] });
    const geometry = chartGeometry(data);

    expect(geometry.leaders.map((leader) => leader.code)).toEqual(["ZZZ", "AAA"]);
    expect(geometry.leaders[0].color).toBe(getTeamColor(""));
  });
});
