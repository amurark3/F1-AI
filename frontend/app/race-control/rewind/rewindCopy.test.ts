import { describe, expect, it } from "vitest";

import { DIRECTORY_2026 } from "@/test/fixtures";
import { REWIND_R19 as r19 } from "@/test/fixtures/rewind";
import { change, driver, finalOf, lap, race } from "@/test/fixtures/rewindHandBuilt";

import {
  changesTitle,
  finalSource,
  finalTitle,
  lapChartTitle,
  penaltyText,
  rewindHeadline,
  rewindMeta,
  sourceNote,
  surnameFn,
  towerHeading,
} from "./rewindCopy";

import type { RaceRewind, RewindChange, RewindFinalRow } from "./rewindTypes";

const ALL = ["AAA", "BBB", "CCC", "DDD"];

/** A four-car race whose leaders are `codes`, lap by lap, with the given stops. */
function led(codes: string[], stops: Array<[string, number]> = []): RaceRewind {
  return race({
    total_laps: codes.length,
    drivers: ALL.map((code) => driver(code)),
    grid: { order: ALL, pit_lane: [], source: "f1db", document: null },
    laps: codes.map((code, index) => lap(index + 1, [code, ...ALL.filter((other) => other !== code)])),
    stops: stops.map(([driver_code, stopLap]) => ({ driver_code, lap: stopLap })),
  });
}

describe("the headline and the meta", () => {
  it("reads R19 as two lead changes, both at a stop", () => {
    expect(rewindHeadline(r19, DIRECTORY_2026)).toBe("The lead changed twice, both times at a stop");
    expect(rewindMeta(r19, DIRECTORY_2026)).toBe(
      "Leclerc led to lap 27, Antonelli to lap 43, Verstappen from lap 44 to the flag. Drag the scrubber to replay the order at the line, lap by lap; the last step is the FIA final classification.",
    );
    expect(lapChartTitle(r19, DIRECTORY_2026)).toBe("Verstappen led every lap from 44");
  });

  it("counts the lead changes, and how many came at a stop", () => {
    expect(rewindHeadline(led(["AAA", "AAA"]))).toBe("Alfa Alpha led every lap");
    expect(rewindHeadline(led(["AAA", "BBB"]))).toBe("The lead changed once");
    expect(rewindHeadline(led(["AAA", "BBB", "CCC"]))).toBe("The lead changed twice");
    expect(rewindHeadline(led(["AAA", "BBB", "CCC", "DDD"]))).toBe("The lead changed 3 times");
    expect(rewindHeadline(led(["AAA", "BBB"], [["AAA", 1]]))).toBe("The lead changed once, at a stop");
    expect(rewindHeadline(led(["AAA", "BBB", "CCC"], [["AAA", 1]]))).toBe(
      "The lead changed 2 times, 1 of them at a stop",
    );
    expect(
      rewindHeadline(
        led(
          ["AAA", "BBB", "CCC", "DDD"],
          [
            ["AAA", 1],
            ["BBB", 2],
            ["CCC", 3],
          ],
        ), // fmt: skip
      ),
    ).toBe("The lead changed 3 times, each time at a stop");
  });

  it("tells a one-leader race and a two-run race plainly", () => {
    expect(rewindMeta(led(["AAA", "AAA"]))).toMatch(/^Alfa Alpha led every lap\. Drag/);
    expect(rewindMeta(led(["AAA", "BBB"]))).toMatch(
      /^Alfa Alpha led to lap 1, Bravo Bell from lap 2 to the flag\. Drag/,
    );
    expect(lapChartTitle(led(["AAA", "AAA"]))).toBe("Alfa Alpha led every lap");
    expect(lapChartTitle(race({ laps: [] }))).toBe(" led every lap");
  });

  it("names the classification the last step shows, or stops the sentence without one", () => {
    const openf1 = race({ final: finalOf({ source: "openf1-session-result", provisional: true }) });
    const jolpica = race({ final: finalOf({ source: "jolpica-results", provisional: true }) });

    expect(rewindMeta(openf1)).toMatch(/; the last step is OpenF1's provisional classification\.$/);
    expect(rewindMeta(jolpica)).toMatch(/; the last step is Jolpica's provisional classification\.$/);
    expect(rewindMeta(race({ final: null }))).toMatch(/, lap by lap\.$/);
  });

  it("names a driver by surname, and no one by nothing", () => {
    const name = surnameFn(r19, DIRECTORY_2026);

    expect(name("VER")).toBe("Verstappen");
    expect(name("QQQ")).toBe("QQQ");
    expect(name(null)).toBe("");
  });
});

describe("the tower heading", () => {
  it("names the pole sitter and the grid's source", () => {
    expect(towerHeading(r19, 0, DIRECTORY_2026)).toEqual({
      eyebrow: "Starting grid",
      title: "Hamilton on pole",
      sub: "FIA final starting grid (doc 67)",
    });
    const grid = (source: string, document: number | null) =>
      race({ grid: { order: ALL, pit_lane: [], source, document } });
    expect(towerHeading(grid("fia_starting_grid", null), 0).sub).toBe("FIA final starting grid");
    expect(towerHeading(grid("f1db", null), 0).sub).toBe("Official grid (f1db)");
    expect(towerHeading(grid("openf1-position", null), 0).sub).toBe("Order at the start, from OpenF1 positions");
  });

  it("reads lap 44, lap 28 and lap 1 by who led and why", () => {
    expect(towerHeading(r19, 44, DIRECTORY_2026)).toEqual({
      eyebrow: "Order after lap 44",
      title: "Verstappen leads; Antonelli stopped",
      sub: "+/− = places vs lap 43",
    });
    expect(towerHeading(r19, 28, DIRECTORY_2026).title).toBe("Antonelli leads; Leclerc stopped");
    expect(towerHeading(r19, 1, DIRECTORY_2026)).toMatchObject({
      title: "Leclerc leads; Hamilton lost the lead",
      sub: "+/− = places vs the grid",
    });
  });

  it("says when the old leader retired, and counts the cars in the pits behind a steady leader", () => {
    const retired = led(["AAA", "BBB"]);
    const gone = { ...retired, laps: [retired.laps[0], lap(2, ["BBB", "CCC", "DDD"])] };
    expect(towerHeading(gone, 2).title).toBe("Bravo Bell leads; Alfa Alpha retired");
    expect(towerHeading(led(["AAA", "AAA"]), 2).title).toBe("Alfa Alpha leads");
    expect(towerHeading(led(["AAA", "AAA"], [["BBB", 2]]), 2).title).toBe("Alfa Alpha leads; 1 car in the pits");
    expect(
      towerHeading(
        led(
          ["AAA", "AAA"],
          [
            ["BBB", 2],
            ["CCC", 1],
          ],
        ), // fmt: skip
        2,
      ).title,
    ).toBe("Alfa Alpha leads; 2 cars in the pits");
  });

  it("names the winner at the final step", () => {
    expect(towerHeading(r19, 72, DIRECTORY_2026)).toEqual({
      eyebrow: "Classification",
      title: "Verstappen wins",
      sub: "+/− = places vs the road order at the flag",
    });
    expect(towerHeading(race({ final: finalOf({ rows: [] }) }), 4).title).toBe(" wins");
  });
});

describe("the changes title", () => {
  it("names the stop that moved the top of the order", () => {
    expect(changesTitle(r19, 44, DIRECTORY_2026)).toBe("Antonelli's stop moved the top four");
    expect(changesTitle(r19, 28, DIRECTORY_2026)).toBe("Leclerc's stop moved the top six");
    expect(changesTitle(r19, 1, DIRECTORY_2026)).toBe("Leclerc took the lead from Hamilton");
  });

  it("says when nothing changed, and counts the reasons otherwise", () => {
    expect(changesTitle(led(["AAA", "AAA"]), 2)).toBe("No position changes on lap 2");
    expect(changesTitle(r19, 47, DIRECTORY_2026)).toBe("12 position changes: 12 passes");
    expect(changesTitle(r19, 59, DIRECTORY_2026)).toBe("10 position changes: 3 at a stop, 7 from a retirement");
  });

  it("counts every kind, one at a time", () => {
    const base = led(["AAA", "AAA", "AAA"]);
    const make = (changes: RewindChange[], track: "sc" | "vsc" | "red" | null) => ({
      ...base,
      laps: [base.laps[0], { ...base.laps[1], changes, track }, base.laps[2]],
    });
    const one = (kind: Partial<RewindChange>) => change("BBB", 3, 2, kind);

    expect(changesTitle(make([one({ kind: "pass" })], null), 2)).toBe("1 position change: 1 pass");
    expect(changesTitle(make([one({ kind: "own_stop" }), one({ kind: "rival_stop" }), one({})], null), 2)).toBe(
      "3 position changes: 2 at a stop, 1 other",
    );
    expect(changesTitle(make([one({ kind: "neutralised" })], "sc"), 2)).toBe(
      "1 position change: 1 under the Safety Car",
    );
    expect(changesTitle(make([one({ kind: "neutralised" })], "vsc"), 2)).toBe("1 position change: 1 under the VSC");
    expect(changesTitle(make([one({ kind: "neutralised" })], "red"), 2)).toBe(
      "1 position change: 1 under the red flag",
    );
    expect(changesTitle(make([one({ kind: "neutralised" })], null), 2)).toBe(
      "1 position change: 1 under the neutralisation",
    );
    expect(changesTitle(make([one({ kind: "retirement" })], null), 2)).toBe("1 position change: 1 from a retirement");
  });

  it("counts the places in words up to ten and in digits beyond", () => {
    const base = led(["AAA", "BBB"]);
    const own = (to: number) => ({
      ...base,
      laps: [base.laps[0], { ...base.laps[1], changes: [change("AAA", 1, to, { kind: "own_stop" as const })] }],
    });

    expect(changesTitle(own(10), 2)).toBe("Alfa Alpha's stop moved the top ten");
    expect(changesTitle(own(12), 2)).toBe("Alfa Alpha's stop moved the top 12");
  });
});

describe("the final card", () => {
  const row = (code: string, position: number | null, road: number | null, penalties = 0): RewindFinalRow => ({
    driver_code: code,
    position,
    status: "finished",
    laps: 3,
    road_position: road,
    penalties: Array.from({ length: penalties }, () => ({
      ruling: "10 second time penalty",
      seconds: 10,
      document: 1,
    })),
  });
  const title = (...rows: RewindFinalRow[]) => finalTitle(finalOf({ rows }));

  it("counts the penalties that moved the order, and the places they moved", () => {
    expect(finalTitle(r19.final!)).toBe("Three post-race penalties reshuffled 7th to 17th");
    expect(title(row("A", 1, 2, 1), row("B", 2, 1))).toBe("One post-race penalty moved 1st to 2nd");
    expect(title(row("A", 1, 2, 1), row("B", 2, 1, 1))).toBe("Two post-race penalties reshuffled 1st to 2nd");
  });

  it("falls back to the plain move, or says the road order stood", () => {
    expect(title(row("A", 1, 2), row("B", 2, 1))).toBe("The classification moved 1st to 2nd");
    expect(title(row("A", 1, 1), row("B", 2, 2), row("C", null, 3), row("D", 4, null))).toBe("The road order stood");
  });

  it("writes the penalty as the FIA printed it", () => {
    expect(penaltyText({ ruling: "x", seconds: 10, document: 79 })).toBe("10 s · FIA doc 79");
    expect(penaltyText({ ruling: "Drive through", seconds: null, document: 80 })).toBe("Drive through · FIA doc 80");
    expect(penaltyText({ ruling: "Drive through", seconds: null, document: null })).toBe("Drive through");
    expect(penaltyText({ ruling: "x", seconds: 5, document: null })).toBe("5 s");
  });
});

describe("the source note", () => {
  it("cites the FIA document, and links it", () => {
    expect(finalSource(r19.final!)).toEqual({
      name: "FIA final classification",
      doc: "doc 86",
      url: expect.stringContaining("fia.com") as string,
    });
    expect(sourceNote(r19)).toMatch(/ · final order: FIA final classification \(doc 86\)$/);
  });

  it("labels a provisional source, a missing document and a missing classification", () => {
    const noDoc = race({ final: finalOf({ document: null, url: null }) });
    const openf1 = race({ final: finalOf({ source: "openf1-session-result", provisional: true }) });
    const jolpica = race({ final: finalOf({ source: "jolpica-results", provisional: true }) });

    expect(sourceNote(noDoc)).toMatch(/final order: FIA final classification$/);
    expect(sourceNote(openf1)).toMatch(/final order: OpenF1 session result, provisional$/);
    expect(sourceNote(jolpica)).toMatch(/final order: Jolpica, provisional$/);
    expect(sourceNote(race({ final: null }))).toMatch(/explains the change$/);
  });
});
