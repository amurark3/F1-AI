import { describe, expect, it } from "vitest";

import { DIRECTORY_2026, OVERVIEW_SEGMENTS_2026, STANDINGS_PROGRESSION_2026, TEAMS_2026 } from "@/test/fixtures";

import { columnsOf, gapAside, heroModel, isDecided, venueOf } from "./standingsModel";

import type { TeamsResponse } from "./teamsModel";
import type { ChampionshipStakes } from "../weekend/weekendTypes";

const STAKES = OVERVIEW_SEGMENTS_2026.shell.stakes as ChampionshipStakes;
const DRIVER_STAKES = STAKES.drivers!;
const CTX = { year: 2026, stakes: STAKES, progression: STANDINGS_PROGRESSION_2026, directory: DIRECTORY_2026 };

function tile(model: ReturnType<typeof heroModel>, label: string) {
  return model?.tiles.find((t) => t.label === label);
}

describe("isDecided", () => {
  it("reads the stakes' decided flag or the progression's clinch round", () => {
    expect(isDecided("drivers", STAKES, undefined)).toBe(true);
    expect(isDecided("constructors", STAKES, undefined)).toBe(false);
    expect(isDecided("drivers", undefined, STANDINGS_PROGRESSION_2026)).toBe(true);
    expect(isDecided("constructors", undefined, STANDINGS_PROGRESSION_2026)).toBe(false);
    expect(isDecided("drivers")).toBe(false);
  });
});

describe("venueOf", () => {
  const rounds = STANDINGS_PROGRESSION_2026.rounds;
  it("names a round by its city", () => {
    expect(venueOf(rounds, 3)).toBe("Suzuka");
    expect(venueOf(rounds, 19)).toBe("Mexico City");
  });
  it("falls back to the round number without a round or a location", () => {
    expect(venueOf(rounds, 99)).toBe("round 99");
    expect(venueOf([{ ...rounds[2], location: null }], 3)).toBe("round 3");
  });
});

describe("columnsOf", () => {
  it("splits at the half, the first column taking the odd one", () => {
    expect(columnsOf([1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11])).toEqual([
      [1, 2, 3, 4, 5, 6],
      [7, 8, 9, 10, 11],
    ]);
    expect(columnsOf([1])).toEqual([[1], []]);
  });
});

describe("gapAside", () => {
  it("prints a dash for the leader and the true-minus gap for the rest", () => {
    expect(gapAside(380, 380, 0)).toBe("—");
    expect(gapAside(261, 380, 1)).toBe("−119");
    expect(gapAside(10.5, 12, 1)).toBe("−1.5");
  });
});

describe("heroModel: drivers", () => {
  const model = heroModel("drivers", TEAMS_2026, CTX);

  it("shows the champion with the plain lead line", () => {
    expect(model).toMatchObject({
      decided: true,
      eyebrow: "2026 World Champion",
      figure: "380",
      leader: { name: "Kimi Antonelli", code: "ANT" },
      swatch: "#27F4D2",
      meta: "Mercedes · 9 wins from 19 races",
      line: "119 points clear of Verstappen after round 19.",
    });
  });

  it("has the three tiles of the mockup", () => {
    expect(model?.tiles).toEqual([
      { label: "Fight for second", value: "16", unit: "pts", sub: "Verstappen, Hamilton, Russell, Leclerc" },
      { label: "Constructors", value: "126", unit: "pts", sub: "Mercedes over Ferrari · 172 left" },
      { label: "Races left", value: "4", sub: "no sprints" },
    ]);
  });

  it("is the leader's page while the title is open, with the rivals still in reach", () => {
    const stakes = {
      ...STAKES,
      drivers: {
        ...DRIVER_STAKES,
        decided: false,
        rivals_alive: 3,
        contenders: DRIVER_STAKES.contenders.map((c) => ({ ...c, alive: c.position <= 2 })),
      },
    };
    const open = heroModel("drivers", TEAMS_2026, { ...CTX, stakes, progression: undefined });
    expect(open).toMatchObject({ decided: false, eyebrow: "Championship leader" });
    expect(tile(open, "Rivals in reach")).toEqual({ label: "Rivals in reach", value: "3", sub: "Verstappen +2 more" });
    expect(tile(open, "Fight for second")).toBeUndefined();
  });
});

describe("heroModel: constructors", () => {
  const model = heroModel("constructors", TEAMS_2026, CTX);

  it("leads with Mercedes, whose title is still open", () => {
    expect(model).toMatchObject({
      decided: false,
      eyebrow: "Constructors' leader",
      figure: "630",
      leader: { name: "Mercedes" },
      swatch: null,
      meta: "12 wins from 19 races",
      line: "126 points clear of Ferrari after round 19.",
    });
  });

  it("counts the rivals in reach and shows the drivers' title as clinched", () => {
    expect(tile(model, "Rivals in reach")).toEqual({ label: "Rivals in reach", value: "1", sub: "Ferrari" });
    expect(tile(model, "Drivers")).toEqual({
      label: "Drivers",
      value: "119",
      unit: "pts",
      sub: "Antonelli clinched · 100 left",
    });
  });
});

describe("heroModel: states the data may be in", () => {
  it("leaves the stakes tiles out without stakes, and the champion needs the progression", () => {
    const model = heroModel("drivers", TEAMS_2026, { ...CTX, stakes: undefined });
    expect(model?.eyebrow).toBe("2026 World Champion");
    expect(model?.tiles.map((t) => t.label)).toEqual(["Fight for second", "Constructors"]);
    expect(tile(model, "Constructors")?.sub).toBe("Mercedes over Ferrari");

    const open = heroModel("drivers", TEAMS_2026, { ...CTX, stakes: undefined, progression: undefined });
    expect(open?.eyebrow).toBe("Championship leader");
    expect(open?.tiles.map((t) => t.label)).toEqual(["Constructors"]);
  });

  it("reads level points and one win and one race in the singular", () => {
    const teams: TeamsResponse = {
      ...TEAMS_2026,
      as_of_round: 1,
      drivers: [
        { ...TEAMS_2026.drivers![0], points: 25, wins: 1 },
        { ...TEAMS_2026.drivers![1], points: 25, wins: 0 },
      ],
    };
    const model = heroModel("drivers", teams, { ...CTX, stakes: undefined, progression: undefined });
    expect(model?.meta).toBe("Mercedes · 1 win from 1 race");
    expect(model?.line).toBe("Level on points with Verstappen, ahead on count-back.");
    expect(model?.tiles.map((t) => t.label)).toEqual(["Constructors"]);
  });

  it("describes the races left", () => {
    const left = (races_left: number, sprints_left: number) =>
      tile(heroModel("drivers", TEAMS_2026, { ...CTX, stakes: { ...STAKES, races_left, sprints_left } }), "Races left");
    expect(left(0, 0)).toEqual({ label: "Races left", value: "0", sub: "season complete" });
    expect(left(3, 1)?.sub).toBe("1 sprint");
    expect(left(3, 2)?.sub).toBe("2 sprints");
  });

  it("leaves out the fight for second with only two drivers, and the other table with only one team", () => {
    const small: TeamsResponse = {
      ...TEAMS_2026,
      drivers: TEAMS_2026.drivers!.slice(0, 2),
      teams: TEAMS_2026.teams.slice(0, 1),
    };
    const model = heroModel("drivers", small, CTX);
    expect(model?.decided).toBe(true);
    expect(model?.tiles.map((t) => t.label)).toEqual(["Races left"]);
  });

  it("names a decided constructors' title the Constructors' Champion", () => {
    const stakes = { ...STAKES, constructors: { ...STAKES.constructors!, decided: true } };
    const model = heroModel("constructors", TEAMS_2026, { ...CTX, stakes });
    expect(model?.eyebrow).toBe("2026 Constructors' Champion");
  });

  it("has no hero without two rows or without a round", () => {
    expect(heroModel("drivers", { ...TEAMS_2026, drivers: undefined }, CTX)).toBeNull();
    expect(heroModel("drivers", { ...TEAMS_2026, drivers: TEAMS_2026.drivers!.slice(0, 1) }, CTX)).toBeNull();
    expect(heroModel("drivers", { ...TEAMS_2026, as_of_round: null }, CTX)).toBeNull();
  });

  it("works without the profiles directory, falling back to full names", () => {
    const model = heroModel("drivers", TEAMS_2026, { ...CTX, directory: undefined });
    expect(model?.line).toBe("119 points clear of Max Verstappen after round 19.");
  });
});
