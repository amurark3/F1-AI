import { describe, expect, it } from "vitest";

import { DIRECTORY_2026, PROFILES_2026, TEAMS_2026 } from "@/test/fixtures";

import {
  championshipPoints,
  formatPoints,
  freshnessLine,
  isDriverProfile,
  isTeamProfile,
  ordinalPosition,
  profilesUrl,
  resolveDriverId,
  resolveTeamId,
} from "./profilesModel";

const { haas, hulkenberg, unknownTeam, hirakawa } = PROFILES_2026;

describe("profilesUrl", () => {
  it("builds a season's profiles route", () => {
    expect(profilesUrl("http://localhost:8000", 2026, "directory")).toBe(
      "http://localhost:8000/api/profiles/2026/directory",
    );
  });
});

describe("profile guards", () => {
  it("accept an ok answer and refuse a not-found or missing one", () => {
    expect(isTeamProfile(haas)).toBe(true);
    expect(isTeamProfile(unknownTeam)).toBe(false);
    expect(isTeamProfile(undefined)).toBe(false);
    expect(isDriverProfile(hulkenberg)).toBe(true);
    expect(isDriverProfile(hirakawa)).toBe(false);
    expect(isDriverProfile(null)).toBe(false);
  });
});

describe("points and positions", () => {
  it("prints whole points plainly and half points to one place", () => {
    expect(formatPoints(haas.team.points)).toBe("31");
    // A literal probe: half points, as a shortened race awards them.
    expect(formatPoints(12.5)).toBe("12.5");
  });

  it("prints a championship place, or a dash for none", () => {
    expect(ordinalPosition(hulkenberg.standing.position)).toBe("P15");
    expect(ordinalPosition(null)).toBe("—");
  });

  it("says how fresh the championship points are when the payload does", () => {
    expect(championshipPoints(haas.team.points, haas)).toBe("31 pts · after round 19 · confirmed");
    expect(championshipPoints(hulkenberg.standing.points, {})).toBe("13 pts");
  });

  it("names the last round with results, or says there are none yet", () => {
    expect(freshnessLine(hulkenberg.results_through, hulkenberg.year)).toBe("Results through R19 Mexican Grand Prix");
    expect(freshnessLine(null, 2027)).toBe("No 2027 results published yet");
  });
});

describe("resolving feed names to this season's pages", () => {
  it("finds a driver by f1db id, code or folded name, and nobody for a guess", () => {
    const sainz = TEAMS_2026.drivers?.find((driver) => driver.code === "SAI");
    expect(resolveDriverId(DIRECTORY_2026, { id: "nico-hulkenberg" })).toBe("nico-hulkenberg");
    expect(resolveDriverId(DIRECTORY_2026, { code: sainz?.code })).toBe("carlos-sainz-jr");
    expect(resolveDriverId(DIRECTORY_2026, { name: "Nico HULKENBERG" })).toBe("nico-hulkenberg");
    expect(resolveDriverId(DIRECTORY_2026, { name: "Sainz" })).toBeNull();
    expect(resolveDriverId(undefined, { code: "SAI" })).toBeNull();
  });

  it("finds a team by id, name or alias, and nobody for a substring", () => {
    expect(resolveTeamId(DIRECTORY_2026, { id: haas.team.id })).toBe("haas");
    expect(resolveTeamId(DIRECTORY_2026, { name: haas.team.full_name })).toBe("haas");
    expect(resolveTeamId(DIRECTORY_2026, { name: "RB F1 Team" })).toBe("racing-bulls");
    expect(resolveTeamId(DIRECTORY_2026, { name: "Haas F1" })).toBeNull();
    expect(resolveTeamId(undefined, { name: "Haas" })).toBeNull();
  });
});
