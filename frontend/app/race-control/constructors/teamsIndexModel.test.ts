import { describe, expect, it } from "vitest";

import { PROFILE_PAGES_2026 } from "@/test/fixtures";

import { gapLabel, shareLabel, shareNote, shareSegments, showRounds, teamsTitle } from "./teamsIndexModel";

import type { TeamsIndexTeam } from "../profiles/profilesModel";

const { teams } = PROFILE_PAGES_2026.teams_index;
const leader = teams[0];

function team(id: string): TeamsIndexTeam {
  const found = teams.find((item) => item.id === id);
  if (!found) throw new Error(`no ${id} in the fixture`);
  return found;
}

describe("teamsTitle", () => {
  it("spells small counts and counts large ones", () => {
    expect(teamsTitle(teams.length)).toBe("Eleven teams");
    expect(teamsTitle(1)).toBe("One team");
    expect(teamsTitle(20)).toBe("Twenty teams");
    expect(teamsTitle(25)).toBe("25 teams");
  });
});

describe("gapLabel", () => {
  it("names the leader, then the gap to them with a true minus", () => {
    expect(gapLabel(leader, leader)).toBe("Leader");
    expect(gapLabel(team("ferrari"), leader)).toBe("−142");
    expect(gapLabel(team("red-bull"), leader)).toBe("−237");
  });

  it("says Unranked for a team the table does not place", () => {
    expect(gapLabel({ ...team("ferrari"), position: null }, leader)).toBe("Unranked");
  });
});

describe("shareSegments", () => {
  it("splits Red Bull's points by what each driver scored for it", () => {
    const segments = shareSegments(team("red-bull"));

    expect(segments.map((item) => [item.driver.code, item.points])).toEqual([
      ["VER", 279],
      ["HAD", 122],
      ["LAW", 14],
    ]);
    expect(segments.map((item) => item.opacity)).toEqual([1, 0.45, 0.45]);
    expect(segments.reduce((sum, item) => sum + item.percent, 0)).toBeCloseTo(100);
  });

  it("leaves a driver with no points out of the bar", () => {
    expect(shareSegments(team("haas")).map((item) => item.driver.code)).toEqual(["BEA", "OCO", "HIR"]);
    expect(shareSegments(team("cadillac"))).toEqual([]);
  });
});

describe("shareNote", () => {
  it.each([
    ["mercedes", "Antonelli scored 60% of the points"],
    ["ferrari", "Hamilton scored 51% of the points"],
    ["red-bull", "Verstappen scored 67% of the points"],
    ["haas", "Bearman scored 74% of the points"],
    ["audi", "Bortoleto and Hülkenberg level on 14"],
    ["aston-martin", "Alonso scored all 7 points"],
    ["cadillac", "No points yet"],
  ])("%s: %s", (id, note) => {
    expect(shareNote(team(id), 2026)).toBe(note);
  });
});

describe("shareLabel", () => {
  it("names each scorer's points for the share bar", () => {
    expect(shareLabel(team("red-bull"), 2026)).toBe("Points split: Verstappen 279, Hadjar 122, Lawson 14");
  });
});

describe("showRounds", () => {
  it("shows a driver's rounds only when they missed some of the season", () => {
    const redBull = team("red-bull");

    expect(showRounds(redBull.drivers[0], 20)).toBe(false);
    expect(showRounds(redBull.drivers[2], 20)).toBe(true);
    expect(showRounds({ ...redBull.drivers[2], rounds_label: "" }, 20)).toBe(false);
  });
});
