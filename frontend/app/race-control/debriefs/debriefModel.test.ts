import { describe, expect, it } from "vitest";

import { DIRECTORY_2026, SEASON_2026 } from "@/test/fixtures";
import { DEBRIEF_R19 } from "@/test/fixtures/debrief";

import {
  biggestClimb,
  completedRaces,
  debriefHeadline,
  debriefMeta,
  gridTitle,
  lastOf,
  podiumOf,
  resolveDebriefRound,
  resolveDefaultDebriefRace,
  retirementCount,
  retirementGroups,
  slopeItems,
  sourceNote,
  startPhrase,
  startSlot,
  winningMargin,
} from "./debriefModel";

import type { DebriefRow, DebriefSummary } from "./debriefTypes";

const R19 = DEBRIEF_R19.summary;
const ROWS = R19.classification;

function row(changes: Partial<DebriefRow>): DebriefRow {
  return { ...ROWS[0], ...changes };
}

function summary(changes: Partial<DebriefSummary>): DebriefSummary {
  return { ...R19, ...changes };
}

/** The first three rows, edited, then the rest as captured. */
function podium(first: Partial<DebriefRow>, second: Partial<DebriefRow> = {}, third: Partial<DebriefRow> = {}) {
  return summary({
    classification: [{ ...ROWS[0], ...first }, { ...ROWS[1], ...second }, { ...ROWS[2], ...third }, ...ROWS.slice(3)],
  });
}

describe("the calendar", () => {
  const races = SEASON_2026.schedule;

  it("lists only the races that have been run", () => {
    expect(completedRaces(races).map((race) => race.round)).toEqual(Array.from({ length: 20 }, (_, i) => i + 1));
  });

  it("opens on the latest completed race, and on none before any has run", () => {
    expect(resolveDefaultDebriefRace(races)?.round).toBe(20);
    expect(resolveDefaultDebriefRace([])).toBeNull();
    expect(resolveDefaultDebriefRace(races.map((race) => ({ ...race, status: "upcoming" })))).toBeNull();
  });

  it("takes the requested round when it is completed and the latest otherwise", () => {
    expect(resolveDebriefRound(races, 19)).toBe(19);
    expect(resolveDebriefRound(races, 21)).toBe(20);
    expect(resolveDebriefRound(races, 99)).toBe(20);
    expect(resolveDebriefRound(races, null)).toBe(20);
    expect(resolveDebriefRound([], 3)).toBeNull();
  });
});

describe("names", () => {
  it("prints a surname from the directory, and the full name without one", () => {
    expect(lastOf(ROWS[0], DIRECTORY_2026)).toBe("Verstappen");
    expect(lastOf(ROWS[0])).toBe("Max Verstappen");
  });

  it("finds the podium by place", () => {
    expect(podiumOf(R19).map((entry) => entry?.driver_code)).toEqual(["VER", "HAM", "ANT"]);
    expect(podiumOf(summary({ classification: [] }))).toEqual([undefined, undefined, undefined]);
  });
});

describe("debriefHeadline", () => {
  it("names the winner and the champion crowned", () => {
    expect(debriefHeadline(R19, DIRECTORY_2026)).toBe("Verstappen wins the Mexican Grand Prix; Antonelli is champion");
  });

  it("says no more than the win when no title was decided", () => {
    expect(debriefHeadline(summary({ titles: [] }), DIRECTORY_2026)).toBe("Verstappen wins the Mexican Grand Prix");
    const constructors = { ...R19.titles[0], table: "constructors" as const };
    expect(debriefHeadline(summary({ titles: [constructors] }), DIRECTORY_2026)).toBe(
      "Verstappen wins the Mexican Grand Prix",
    );
  });

  it("joins the title to the win when the winner took it", () => {
    const winner = { ...R19.titles[0], name: "Max Verstappen" };
    expect(debriefHeadline(summary({ titles: [winner] }), DIRECTORY_2026)).toBe(
      "Verstappen wins the Mexican Grand Prix and the title",
    );
  });

  it("is the race's name before there is a classification", () => {
    expect(debriefHeadline(summary({ classification: [], available: false }))).toBe("Mexican Grand Prix");
  });
});

describe("debriefMeta", () => {
  it("tells how the race was won and who completed the podium", () => {
    expect(debriefMeta(R19)).toBe(
      "Max Verstappen won from P5 and beat Lewis Hamilton by 0.799 seconds. Kimi Antonelli completed the podium.",
    );
  });

  it("says pole, and the pit lane", () => {
    expect(debriefMeta(podium({ grid: 1 }))).toContain("won from pole and");
    expect(debriefMeta(podium({ grid: null, pit_lane: true }))).toContain("won from the pit lane and");
  });

  it("drops the start when no grid is known", () => {
    expect(debriefMeta(podium({ grid: null }))).toContain("Max Verstappen won and beat");
  });

  it("states a lapped second place in laps, and no margin when there is none", () => {
    expect(debriefMeta(podium({}, { laps_down: 1, gap: "+1 lap" }))).toContain("by 1 lap.");
    expect(debriefMeta(podium({}, { gap: null }))).toContain("beat Lewis Hamilton.");
  });

  it("copes with a race of one or two classified cars", () => {
    const one = summary({ classification: [ROWS[0]] });
    expect(debriefMeta(one)).toBe("Max Verstappen won the race.");
    const two = summary({ classification: ROWS.slice(0, 2) });
    expect(debriefMeta(two)).toBe("Max Verstappen won from P5 and beat Lewis Hamilton by 0.799 seconds.");
  });

  it("gives the reason when the race is not classified", () => {
    expect(
      debriefMeta(summary({ available: false, reason: "The race hasn't been classified yet.", classification: [] })),
    ).toBe("The race hasn't been classified yet.");
    expect(debriefMeta(summary({ available: true, reason: null, classification: [] }))).toBe("");
  });
});

describe("starts", () => {
  it("places a pit-lane start behind every car with a slot or a pit-lane start", () => {
    const lawson = ROWS.find((entry) => entry.driver_code === "LAW")!;
    expect(startSlot(lawson, ROWS)).toBe(22);
    expect(startSlot(ROWS[0], ROWS)).toBe(5);
    expect(startSlot(row({ grid: null, pit_lane: false }), ROWS)).toBeNull();
  });

  it("phrases them", () => {
    expect(startPhrase(row({ grid: 1 }))).toBe("pole");
    expect(startPhrase(row({ grid: 5 }))).toBe("P5");
    expect(startPhrase(row({ grid: null, pit_lane: true }))).toBe("pit lane");
    expect(startPhrase(row({ grid: null }))).toBeNull();
  });
});

describe("winningMargin", () => {
  it("is the gap in seconds, without its plus", () => {
    expect(winningMargin(R19)).toEqual({ value: "0.799", unit: "s" });
  });

  it("is laps when second was lapped", () => {
    expect(winningMargin(podium({}, { laps_down: 1 }))).toEqual({ value: "1", unit: "lap" });
    expect(winningMargin(podium({}, { laps_down: 2 }))).toEqual({ value: "2", unit: "laps" });
  });

  it("is none without a second place or a gap", () => {
    expect(winningMargin(summary({ classification: [ROWS[0]] }))).toBeNull();
    expect(winningMargin(podium({}, { gap: null }))).toBeNull();
  });
});

describe("biggestClimb", () => {
  it("is Lawson from the pit lane at Mexico City", () => {
    const climb = biggestClimb(R19);
    expect([climb?.row.driver_code, climb?.from, climb?.gained]).toEqual(["LAW", 22, 15]);
  });

  it("gives a tie to the better finish", () => {
    const tied = summary({
      classification: [
        row({ driver_code: "AAA", position: 1, grid: 3 }),
        row({ driver_code: "BBB", position: 2, grid: 4 }),
      ],
    });
    expect(biggestClimb(tied)?.row.driver_code).toBe("AAA");
  });

  it("is none when nobody gained, or no start is known", () => {
    expect(biggestClimb(summary({ classification: [row({ position: 1, grid: 1 })] }))).toBeNull();
    expect(biggestClimb(summary({ classification: [row({ position: 1, grid: null })] }))).toBeNull();
    expect(biggestClimb(summary({ classification: [row({ position: null, status: "DNF", grid: 9 })] }))).toBeNull();
  });
});

describe("retirements", () => {
  it("counts the cars out and groups those who stopped on the same lap", () => {
    expect(retirementCount(R19)).toBe(5);
    expect(retirementGroups(R19, DIRECTORY_2026).join(", ")).toBe(
      "Lindblad L58, Bearman L47, Bottas L42, Stroll & Alonso L5",
    );
  });

  it("leaves the lap off when it is not known", () => {
    expect(retirementGroups(summary({ classification: [row({ status: "DNF", laps: null })] }), DIRECTORY_2026)).toEqual(
      ["Verstappen"],
    );
  });
});

describe("slopeItems", () => {
  const items = slopeItems(R19);
  const byId = (id: string) => items.find((item) => item.id === id);

  it("draws a finisher from its grid slot to its place", () => {
    expect(byId("VER")).toMatchObject({ label: "VER", name: "Max Verstappen", start: 5, end: 1 });
    expect(byId("VER")?.incomplete).toBeUndefined();
  });

  it("starts a pit-lane car behind the field and says so", () => {
    expect(byId("LAW")).toMatchObject({ start: 22, end: 7, startText: "PL" });
  });

  it("draws a retirement dashed, in its slot in the classification, with its lap", () => {
    expect(byId("LIN")).toMatchObject({ start: 8, end: 18, endText: "DNF L58", incomplete: true });
  });

  it("labels a car not classified or disqualified, and leaves out one that did not start or has no start", () => {
    const special = slopeItems(
      summary({
        classification: [
          row({ driver_code: "AAA", position: null, status: "NC", grid: 3 }),
          row({ driver_code: "BBB", position: null, status: "DSQ", grid: 4 }),
          row({ driver_code: "CCC", position: null, status: "DNS", grid: 5 }),
          row({ driver_code: "DDD", position: null, status: "DNF", laps: null, grid: 6 }),
          row({ driver_code: "EEE", position: 1, grid: null }),
        ],
      }),
    );
    expect(special.map((item) => [item.id, item.endText])).toEqual([
      ["AAA", "NC"],
      ["BBB", "DSQ"],
      ["DDD", "DNF"],
    ]);
  });
});

describe("gridTitle", () => {
  it("names the biggest climber", () => {
    expect(gridTitle(R19, DIRECTORY_2026)).toBe("Lawson came from the pit lane to P7");
    expect(
      gridTitle(summary({ classification: [row({ position: 1, grid: 4, pit_lane: false })] }), DIRECTORY_2026),
    ).toBe("Verstappen came from P4 to P1");
  });

  it("says when nobody gained", () => {
    expect(gridTitle(summary({ classification: [] }))).toBe("Nobody gained places from the grid");
  });
});

describe("sourceNote", () => {
  it("names f1db's version and the FIA's final grid", () => {
    expect(sourceNote(R19)).toBe(
      "Classification: f1db v2026.20.0 · laps, race control and position changes: OpenF1 · grid: FIA final starting grid (doc 67)",
    );
  });

  it("names the FIA classification, f1db's grid and a grid not yet published", () => {
    const fia = summary({
      sources: [{ source: "fia-final-classification", role: "classification", document: 86 }],
      grid: { available: true, fia_document: null },
    });
    expect(sourceNote(fia)).toContain("Classification: FIA final classification (doc 86)");
    expect(sourceNote(fia)).toContain("grid: f1db");
    const early = summary({
      sources: [{ source: "openf1-session-result", role: "classification" }],
      grid: { available: false, fia_document: null },
    });
    expect(sourceNote(early)).toContain("Classification: OpenF1, provisional");
    expect(sourceNote(early)).toContain("grid: not published yet");
  });

  it("copes with no version and no source", () => {
    expect(sourceNote(summary({ sources: [{ source: "f1db", role: "classification" }] }))).toContain(
      "Classification: f1db ·",
    );
    expect(sourceNote(summary({ sources: [] }))).toContain("Classification: OpenF1, provisional");
  });
});
