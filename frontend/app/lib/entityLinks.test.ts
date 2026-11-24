import { describe, expect, it } from "vitest";

import { debriefHref, driverHref, grandPrixHref, teamHref } from "./entityLinks";

describe("entity links", () => {
  it("escape ids into driver and team paths", () => {
    expect(driverHref("max-verstappen")).toBe("/race-control/drivers/max-verstappen");
    expect(teamHref("a/b")).toBe("/race-control/constructors/a%2Fb");
  });

  it("open a debrief on the latest race, a round, or a round of a year", () => {
    expect(debriefHref(null)).toBe("/race-control/debriefs");
    expect(debriefHref(5)).toBe("/race-control/debriefs?round=5");
    expect(debriefHref(5, 2025)).toBe("/race-control/debriefs?round=5&year=2025");
    expect(debriefHref(null, 2025)).toBe("/race-control/debriefs?year=2025");
  });

  it("open a Grand Prix round on a tab and a year when given", () => {
    expect(grandPrixHref(5)).toBe("/race-control/grand-prix?round=5");
    expect(grandPrixHref(5, "grid", 2025)).toBe("/race-control/grand-prix?round=5&tab=grid&year=2025");
  });
});
