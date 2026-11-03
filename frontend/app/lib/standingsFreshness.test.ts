import { describe, expect, it } from "vitest";

import { TEAMS_2026 } from "@/test/fixtures";

import { hasDisagreement, sourceLine, standingsLabel, type StandingsSource } from "./standingsFreshness";

describe("standingsLabel", () => {
  it("labels the captured R19 table as confirmed once f1db publishes the round", () => {
    expect(standingsLabel(TEAMS_2026)).toBe("after round 19 · confirmed");
  });

  it("labels a table that holds an unpublished round as provisional", () => {
    expect(standingsLabel({ ...TEAMS_2026, provisional: true })).toBe("after round 19 · provisional");
  });

  it("reads a payload without the provisional flag as confirmed", () => {
    expect(standingsLabel({ as_of_round: 3 })).toBe("after round 3 · confirmed");
  });

  it.each([
    ["no payload", null],
    ["an undefined payload", undefined],
    ["a payload without freshness fields", {}],
    ["a table before any round has points", { as_of_round: null, provisional: false }],
    ["round zero", { as_of_round: 0, provisional: true }],
  ])("gives no label for %s", (_case, freshness) => {
    expect(standingsLabel(freshness)).toBeNull();
  });
});

/**
 * The provisional table the backend serves the morning after a race, shaped
 * like `current_standings._sources`: f1db's base, OpenF1's points for the
 * round f1db lacks, and the feeds it was checked against.
 */
const PROVISIONAL_SOURCES: StandingsSource[] = [
  { source: "f1db", role: "base", through_round: 18, version: "v2026.18.0" },
  { source: "openf1-session-result", role: "points", round: 19, sessions: ["R"] },
  { source: "openf1-championship", role: "cross_check", round: 19, status: "agrees" },
  { source: "jolpica-standings", role: "cross_check", round: 19, status: "disagrees" },
];

describe("sourceLine", () => {
  it("names the base release and the rounds it covers", () => {
    const [base] = TEAMS_2026.sources;
    expect(sourceLine(base)).toBe("Base: f1db v2026.19.0, through round 19");
  });

  it("names each feed in words and spells out session codes", () => {
    expect(PROVISIONAL_SOURCES.map(sourceLine)).toEqual([
      "Base: f1db v2026.18.0, through round 18",
      "Points: OpenF1 session results, round 19 (race)",
      "Cross-check: OpenF1 championship table, round 19 — agrees",
      "Cross-check: Jolpica standings, round 19 — disagrees",
    ]);
  });

  it("lists a sprint weekend's sessions in the order sent", () => {
    const line = sourceLine({ source: "openf1-session-result", role: "points", round: 20, sessions: ["S", "R"] });
    expect(line).toBe("Points: OpenF1 session results, round 20 (sprint, race)");
  });

  it("shows an unknown feed, session code or missing detail as sent", () => {
    expect(sourceLine({ source: "fia-docs", role: "points", round: 21, sessions: ["SQ"] })).toBe(
      "Points: fia-docs, round 21 (SQ)",
    );
    expect(sourceLine({ source: "f1db", role: "base", version: null })).toBe("Base: f1db");
    expect(sourceLine({ source: "jolpica-standings", role: "cross_check", sessions: [], status: "unavailable" })).toBe(
      "Cross-check: Jolpica standings — unavailable",
    );
  });
});

describe("hasDisagreement", () => {
  it("is true when any cross-check disagrees with the served table", () => {
    expect(hasDisagreement({ sources: PROVISIONAL_SOURCES })).toBe(true);
  });

  it.each([
    ["no payload", null],
    ["a payload without sources", {}],
    [
      "checks that agree or were unavailable",
      { sources: [{ ...PROVISIONAL_SOURCES[2], status: "unavailable" as const }] },
    ],
    ["the captured confirmed table", TEAMS_2026],
  ])("is false for %s", (_case, freshness) => {
    expect(hasDisagreement(freshness)).toBe(false);
  });
});
