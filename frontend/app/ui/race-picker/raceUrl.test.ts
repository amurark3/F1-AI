import { describe, expect, it } from "vitest";

import { raceQuery, readRaceYear } from "./raceUrl";

describe("race URLs", () => {
  it("accepts a year in the supported range and rejects malformed or future years", () => {
    for (const year of [2023, 2025, 2026]) {
      expect(readRaceYear(new URLSearchParams({ year: String(year) }), 2026)).toBe(year);
    }
    for (const query of ["", "year=2022", "year=2027", "year=2025.5", "year=2025x", "year=0025"]) {
      expect(readRaceYear(new URLSearchParams(query), 2026)).toBeNull();
    }
  });

  it("serializes the round and an explicitly selected year", () => {
    expect(raceQuery(19, 2025).toString()).toBe("round=19&year=2025");
    expect(raceQuery(19, null).toString()).toBe("round=19");
    expect(raceQuery(null, 2025).toString()).toBe("year=2025");
    expect(raceQuery(null, null).toString()).toBe("");
  });
});
