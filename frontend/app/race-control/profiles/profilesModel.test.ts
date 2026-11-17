import { describe, expect, it } from "vitest";

import { DIRECTORY_2026, PROFILE_PAGES_2026, TEAMS_2026 } from "@/test/fixtures";

import {
  formatPoints,
  isDriverProfile,
  isTeamProfile,
  ordinalPosition,
  profilesUrl,
  resolveDriverId,
  resolveTeamId,
  type DriverProfileResponse,
} from "./profilesModel";

const { mercedes, hamilton, unknown_team: unknownTeam } = PROFILE_PAGES_2026;
const unknownDriver: DriverProfileResponse = { year: 2026, status: "not_found" };

describe("profilesUrl", () => {
  it("builds a season's profiles route", () => {
    expect(profilesUrl("http://localhost:8000", 2026, "directory")).toBe(
      "http://localhost:8000/api/profiles/2026/directory",
    );
  });
});

describe("profile guards", () => {
  it("accept an ok answer and refuse a not-found or missing one", () => {
    expect(isTeamProfile(mercedes)).toBe(true);
    expect(isTeamProfile(unknownTeam)).toBe(false);
    expect(isTeamProfile(undefined)).toBe(false);
    expect(isDriverProfile(hamilton)).toBe(true);
    expect(isDriverProfile(unknownDriver)).toBe(false);
    expect(isDriverProfile(null)).toBe(false);
  });
});

describe("points and positions", () => {
  it("prints whole points plainly and half points to one place", () => {
    expect(formatPoints(mercedes.team.points)).toBe("652");
    // A literal probe: half points, as a shortened race awards them.
    expect(formatPoints(12.5)).toBe("12.5");
  });

  it("prints a championship place, or a dash for none", () => {
    expect(ordinalPosition(hamilton.standing.position)).toBe("P4");
    expect(ordinalPosition(null)).toBe("—");
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
    const haas = DIRECTORY_2026.teams.find((team) => team.id === "haas");
    expect(resolveTeamId(DIRECTORY_2026, { id: "haas" })).toBe("haas");
    expect(resolveTeamId(DIRECTORY_2026, { name: haas?.full_name })).toBe("haas");
    expect(resolveTeamId(DIRECTORY_2026, { name: "RB F1 Team" })).toBe("racing-bulls");
    expect(resolveTeamId(DIRECTORY_2026, { name: "Haas F1" })).toBeNull();
    expect(resolveTeamId(undefined, { name: "Haas" })).toBeNull();
  });
});
