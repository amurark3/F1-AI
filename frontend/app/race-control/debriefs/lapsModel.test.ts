import { describe, expect, it } from "vitest";

import { DIRECTORY_2026 } from "@/test/fixtures";
import { DEBRIEF_R19 } from "@/test/fixtures/debrief";

import {
  leaderRuns,
  overtakesTitle,
  penaltySub,
  penaltyTitle,
  stripRuns,
  stripSub,
  stripTitle,
  traceTitle,
} from "./lapsModel";

import type { DebriefLaps, DebriefOvertakes, DebriefPenalties, OvertakeDriver } from "./debriefTypes";
import type { Neutralisation } from "../grand-prix/strategyModel";

const LAPS = DEBRIEF_R19.laps;

function laps(changes: Partial<DebriefLaps>): DebriefLaps {
  return { ...LAPS, ...changes };
}

describe("leaderRuns", () => {
  it("groups consecutive laps, including laps with no timing", () => {
    expect(leaderRuns(["A", "A", null, "B", "A"])).toEqual([
      { code: "A", startLap: 1, endLap: 2 },
      { code: null, startLap: 3, endLap: 3 },
      { code: "B", startLap: 4, endLap: 4 },
      { code: "A", startLap: 5, endLap: 5 },
    ]);
  });

  it("finds Mexico City's three leaders", () => {
    expect(leaderRuns(LAPS.leaders).map((run) => [run.code, run.startLap, run.endLap])).toEqual([
      ["LEC", 1, 27],
      ["ANT", 28, 43],
      ["VER", 44, 71],
    ]);
  });
});

describe("the lap strip", () => {
  it("says where the winner took the lead for good", () => {
    expect(stripTitle(LAPS, DIRECTORY_2026)).toBe("Verstappen led from lap 44 to the flag");
  });

  it("says a driver led every lap", () => {
    expect(stripTitle(laps({ leaders: ["LEC", "LEC"] }), DIRECTORY_2026)).toBe("Leclerc led every lap");
  });

  it("has no title when the last lap has no leader", () => {
    expect(stripTitle(laps({ leaders: ["LEC", null] }))).toBeNull();
  });

  it("counts laps led, most first", () => {
    expect(stripSub(LAPS, DIRECTORY_2026)).toBe(
      "Each block is one lap, coloured by who led it at the line · Verstappen 28, Leclerc 27, Antonelli 16 laps",
    );
  });

  it("counts the laps with no timing", () => {
    expect(stripSub(laps({ leaders: ["LEC", null, null] }), DIRECTORY_2026)).toContain(" · 2 laps without timing");
    expect(stripSub(laps({ leaders: ["LEC", null] }), DIRECTORY_2026)).toContain(" · 1 lap without timing");
  });

  it("reads out the runs in full names, skipping untimed laps", () => {
    expect(stripRuns(LAPS)).toEqual([
      { range: "Laps 1–27", name: "Charles Leclerc" },
      { range: "Laps 28–43", name: "Kimi Antonelli" },
      { range: "Laps 44–71", name: "Max Verstappen" },
    ]);
    expect(stripRuns(laps({ leaders: ["LEC", null, "ZZZ"] }))).toEqual([
      { range: "Lap 1", name: "Charles Leclerc" },
      { range: "Lap 3", name: "ZZZ" },
    ]);
  });
});

describe("traceTitle", () => {
  const period = (kind: Neutralisation["kind"], start: number): Neutralisation => ({
    kind,
    start_lap: start,
    end_lap: start,
  });

  it("counts each kind, red flag last", () => {
    expect(traceTitle(LAPS.neutralisations)).toBe("A VSC, 2 Safety Cars and a red flag after lap 45");
  });

  it("pluralises and joins two", () => {
    expect(traceTitle([period("vsc", 1), period("vsc", 5), period("sc", 9)])).toBe("2 VSCs and a Safety Car");
    expect(traceTitle([period("red", 3), period("red", 9)])).toBe("2 red flags");
  });

  it("says when there was nothing", () => {
    expect(traceTitle([])).toBe("No Safety Car, VSC or red flag");
  });
});

describe("penalties", () => {
  const penalties = DEBRIEF_R19.penalties;

  it("counts the distinct drivers penalised", () => {
    expect(penaltyTitle(penalties)).toBe("7 drivers penalised");
    expect(penaltyTitle({ ...penalties, post_race: [], in_race: penalties.in_race.slice(0, 1) })).toBe(
      "1 driver penalised",
    );
    expect(penaltyTitle({ ...penalties, post_race: [], in_race: [] })).toBe("No penalties");
  });

  it("names the FIA document behind the post-race rows, or f1db without it", () => {
    expect(penaltySub(penalties)).toBe(
      "In-race from race control · post-race from the FIA final classification (doc 86)",
    );
    const numberless: DebriefPenalties = { ...penalties, fia_document: { number: null, url: "u" } };
    expect(penaltySub(numberless)).toBe("In-race from race control · post-race from the FIA final classification");
    expect(penaltySub({ ...penalties, fia_document: null })).toBe(
      "In-race from race control · post-race from f1db's time penalties",
    );
  });
});

describe("overtakesTitle", () => {
  const board = DEBRIEF_R19.overtakes;
  const driver = (code: string, made: number): OvertakeDriver => ({
    driver_code: code,
    driver_name: `${code} Driver`,
    team: "Team",
    made,
  });
  const with_ = (drivers: OvertakeDriver[]): DebriefOvertakes => ({ ...board, drivers });

  it("names the driver with the most", () => {
    expect(overtakesTitle(board, DIRECTORY_2026)).toBe("Hadjar made the most position changes");
  });

  it("names two tied, and counts more", () => {
    expect(overtakesTitle(with_([driver("AAA", 5), driver("BBB", 5), driver("CCC", 1)]))).toBe(
      "AAA Driver and BBB Driver made the most position changes",
    );
    expect(overtakesTitle(with_([driver("AAA", 5), driver("BBB", 5), driver("CCC", 5)]))).toBe("3 drivers tied on 5");
  });

  it("has no title without drivers", () => {
    expect(overtakesTitle(with_([]))).toBeNull();
  });
});
