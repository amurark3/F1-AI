import { describe, expect, it } from "vitest";

import {
  NAV_GROUPS,
  NAV_LINKS,
  ariaCurrent,
  currentState,
  layoutFor,
  showsRaceStatus,
  type NavLink,
} from "./navConfig";

const link = (label: string): NavLink => {
  const found = NAV_LINKS.find((entry) => entry.label === label);
  if (!found) throw new Error(`no nav link "${label}"`);
  return found;
};

describe("the nav lists", () => {
  it("groups screens by job, each with a description", () => {
    expect(NAV_GROUPS.map(({ label, links }) => [label, links.map((link) => link.label)])).toEqual([
      ["Races", ["Grand Prix", "Telemetry", "Debrief", "Race Rewind"]],
      ["Season", ["Standings", "Teams & drivers", "Power Units"]],
      ["Reference", ["Champions", "Rulebook"]],
    ]);
    for (const group of NAV_GROUPS) {
      for (const entry of group.links) expect(entry.description).toMatch(/\S/);
    }
  });

  it("reaches every Race Control screen once", () => {
    const hrefs = NAV_LINKS.map(({ href }) => href);
    expect(new Set(hrefs).size).toBe(hrefs.length);
    expect(hrefs).toEqual([
      "/race-control",
      "/race-control/grand-prix",
      "/race-control/telemetry",
      "/race-control/debriefs",
      "/race-control/rewind",
      "/race-control/standings",
      "/race-control/constructors",
      "/race-control/power-units",
      "/race-control/champions",
      "/race-control/rulebook",
      "/race-control/engineer",
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
    expect(currentState(link("Teams & drivers"), "/race-control/drivers/lewis-hamilton")).toBe("section");
    expect(currentState(link("Teams & drivers"), "/race-control/constructors/mercedes")).toBe("section");
  });

  it("never lights the Command Center for the screens under it", () => {
    expect(currentState(link("Race Control"), "/race-control/telemetry")).toBeNull();
  });

  it("matches whole path segments, not prefixes of a name", () => {
    expect(currentState(link("Standings"), "/race-control/standingsheet")).toBeNull();
    expect(currentState(link("Telemetry"), "/")).toBeNull();
  });
});

describe("ariaCurrent", () => {
  it("marks the link to this very page as the page, and a section link as current", () => {
    expect(ariaCurrent(link("Grand Prix"), "/race-control/grand-prix")).toBe("page");
    expect(ariaCurrent(link("Teams & drivers"), "/race-control/drivers/lewis-hamilton")).toBe("true");
    expect(ariaCurrent(link("Grand Prix"), "/race-control/telemetry")).toBeUndefined();
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
