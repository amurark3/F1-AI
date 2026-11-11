import { describe, expect, it } from "vitest";

import {
  MORE_NAV,
  PRIMARY_NAV,
  ariaCurrent,
  currentState,
  isMoreCurrent,
  layoutFor,
  showsRaceStatus,
  type NavLink,
} from "./navConfig";

const link = (label: string): NavLink => {
  const found = [...PRIMARY_NAV, ...MORE_NAV].find((entry) => entry.label === label);
  if (!found) throw new Error(`no nav link "${label}"`);
  return found;
};

describe("the nav lists", () => {
  it("puts seven sections in the top bar, in the mockups' order", () => {
    expect(PRIMARY_NAV.map(({ label }) => label)).toEqual([
      "Race Control",
      "Grand Prix",
      "Telemetry",
      "Standings",
      "Teams",
      "Power Units",
      "AI Engineer",
    ]);
  });

  it("puts Champions, Debriefs and Rulebook under More, each with one line on what it holds", () => {
    expect(MORE_NAV.map(({ label }) => label)).toEqual(["Champions", "Debriefs", "Rulebook"]);
    for (const entry of MORE_NAV) expect(entry.description).toMatch(/\S/);
  });

  it("reaches every Race Control screen once", () => {
    const hrefs = [...PRIMARY_NAV, ...MORE_NAV].map(({ href }) => href);
    expect(new Set(hrefs).size).toBe(hrefs.length);
    expect(hrefs).toEqual([
      "/race-control",
      "/race-control/grand-prix",
      "/race-control/telemetry",
      "/race-control/teams",
      "/race-control/constructors",
      "/race-control/power-units",
      "/race-control/engineer",
      "/race-control/champions",
      "/race-control/debriefs",
      "/race-control/rulebook",
    ]);
  });
});

describe("currentState", () => {
  it("is the page on the link's own path", () => {
    expect(currentState(link("Telemetry"), "/race-control/telemetry")).toBe("page");
    expect(currentState(link("Race Control"), "/race-control")).toBe("page");
  });

  it("is the section on a page below the link's path", () => {
    expect(currentState(link("Power Units"), "/race-control/power-units/ferrari-16")).toBe("section");
    expect(currentState(link("Champions"), "/race-control/champions/1988")).toBe("section");
  });

  it("counts the paths a link also owns: a driver page sits under Teams", () => {
    expect(currentState(link("Teams"), "/race-control/drivers/lewis-hamilton")).toBe("section");
    expect(currentState(link("Teams"), "/race-control/constructors/mercedes")).toBe("section");
  });

  it("never lights the Command Center for the screens under it", () => {
    expect(currentState(link("Race Control"), "/race-control/telemetry")).toBeNull();
  });

  it("matches whole path segments, not prefixes of a name", () => {
    expect(currentState(link("Standings"), "/race-control/teamsheet")).toBeNull();
    expect(currentState(link("Telemetry"), "/")).toBeNull();
  });
});

describe("ariaCurrent", () => {
  it("marks the link to this very page as the page, and a section link as current", () => {
    expect(ariaCurrent(link("Grand Prix"), "/race-control/grand-prix")).toBe("page");
    expect(ariaCurrent(link("Teams"), "/race-control/drivers/lewis-hamilton")).toBe("true");
    expect(ariaCurrent(link("Grand Prix"), "/race-control/telemetry")).toBeUndefined();
  });
});

describe("isMoreCurrent", () => {
  it("is true on a screen kept under More, and below it", () => {
    expect(isMoreCurrent("/race-control/rulebook")).toBe(true);
    expect(isMoreCurrent("/race-control/champions/2026")).toBe(true);
  });

  it("is false elsewhere", () => {
    expect(isMoreCurrent("/race-control/grand-prix")).toBe(false);
    expect(isMoreCurrent("/")).toBe(false);
  });
});

describe("layoutFor", () => {
  it("leaves the homepage bare: it draws its own full-bleed hero", () => {
    expect(layoutFor("/")).toBe("bare");
  });

  it("gives the AI Engineer the whole viewport under the bar", () => {
    expect(layoutFor("/race-control/engineer")).toBe("workspace");
  });

  it("frames every other screen in the page wrap, unknown paths included", () => {
    expect(layoutFor("/race-control")).toBe("page");
    expect(layoutFor("/race-control/drivers/max-verstappen")).toBe("page");
    expect(layoutFor("/no-such-page")).toBe("page");
  });
});

describe("showsRaceStatus", () => {
  it("is off on the static homepage, which fetches nothing", () => {
    expect(showsRaceStatus("/")).toBe(false);
  });

  it("is on for every data route", () => {
    expect(showsRaceStatus("/race-control")).toBe(true);
    expect(showsRaceStatus("/race-control/engineer")).toBe(true);
  });
});
