import { describe, expect, it } from "vitest";

import { PROFILE_PAGES_2026 } from "@/test/fixtures";

import { driverRecord, heatCell, standingLine, teamKpis, weekendTitle } from "./teamModel";

import type { Finish, TeamProfile, TeamRound } from "../../profiles/profilesModel";

const { mercedes, red_bull: redBull } = PROFILE_PAGES_2026;

function finish(over: Partial<Finish> = {}): Finish {
  return {
    number: 1,
    position: 8,
    position_text: "8",
    grid: 8,
    points: 0,
    positions_gained: 0,
    reason_retired: null,
    fastest_lap: false,
    pole: false,
    status: "finished",
    pit_lane: false,
    ...over,
  };
}

function round(over: Partial<TeamRound> = {}): TeamRound {
  return {
    round: 1,
    name: "Australian Grand Prix",
    short_name: "Australian GP",
    date: "2026-03-08",
    status: "complete",
    results: [],
    points: 0,
    cumulative_points: null,
    ...over,
  };
}

function profile(over: Partial<TeamProfile>): TeamProfile {
  return { ...mercedes, ...over };
}

describe("standingLine", () => {
  it("says how far clear the leader is and how many rounds are left", () => {
    expect(standingLine(mercedes)).toBe("652 points, 142 clear of Ferrari with 3 rounds to run.");
  });

  it("drops the rounds clause once none are left, and says one round in the singular", () => {
    const done = profile({ rounds: mercedes.rounds.map((item) => ({ ...item, status: "complete" as const })) });
    expect(standingLine(done)).toBe("652 points, 142 clear of Ferrari.");
    const last = profile({
      rounds: mercedes.rounds.map((item, index) => ({ ...item, status: index === 0 ? "pending" : "complete" })),
    });
    expect(standingLine(last)).toBe("652 points, 142 clear of Ferrari with 1 round to run.");
  });

  it("says how far behind the team ahead a chaser is, with no rounds clause", () => {
    expect(standingLine(redBull)).toBe("415 points, 95 behind Ferrari.");
  });

  it("says level when the gap is nil", () => {
    const level = profile({
      team: { ...redBull.team, position: 3, points: 510 },
      rivals: redBull.rivals,
      rounds: redBull.rounds,
    });
    expect(standingLine(level)).toBe("510 points, level with Ferrari.");
  });

  it("says level when the leader's lead is nil", () => {
    const level = profile({ rivals: { ahead: null, behind: { ...mercedes.rivals.behind!, points: 652 } } });
    expect(standingLine(level)).toBe("652 points, level with Ferrari.");
  });

  it("states only the points for an unranked team or a leader with nobody behind", () => {
    expect(standingLine(profile({ team: { ...mercedes.team, position: null } }))).toBe("652 points.");
    expect(standingLine(profile({ rivals: { ahead: null, behind: null } }))).toBe("652 points.");
    expect(
      standingLine(profile({ team: { ...redBull.team, position: 3 }, rivals: { ahead: null, behind: null } })),
    ).toBe("415 points.");
  });
});

describe("teamKpis", () => {
  it("counts Mercedes' wins, podiums, poles and retirements by driver", () => {
    expect(teamKpis(mercedes)).toEqual({
      wins: { value: 12, unit: "of 20", sub: "Antonelli 9 · Russell 3" },
      podiums: { value: 24, sub: "of 40 starts" },
      poles: { value: 12, sub: "Antonelli 7 · Russell 5" },
      retirements: { value: 4, sub: "Antonelli R7 · Russell R5, R10, R16" },
    });
  });

  it("says None and gives no names when nobody did", () => {
    const quiet = profile({
      rounds: [round({ results: [{ driver_id: "kimi-antonelli", race: finish(), sprint: null }] })],
    });
    expect(teamKpis(quiet)).toEqual({
      wins: { value: 0, unit: "of 1", sub: "None" },
      podiums: { value: 0, sub: "of 1 starts" },
      poles: { value: 0, sub: "None" },
      retirements: { value: 0, sub: "None" },
    });
  });

  it("does not count rounds still to run, and counts a non-start out of the starts", () => {
    const mixed = profile({
      rounds: [
        round({
          results: [
            {
              driver_id: "kimi-antonelli",
              race: finish({ status: "dns", position: null, position_text: "DNS" }),
              sprint: null,
            },
            { driver_id: "george-russell", race: finish({ position: 1 }), sprint: null },
          ],
        }),
        round({ round: 2, status: "pending", results: [] }),
      ],
    });
    const kpis = teamKpis(mixed);
    expect(kpis.wins).toEqual({ value: 1, unit: "of 1", sub: "Russell 1" });
    expect(kpis.podiums.sub).toBe("of 1 starts");
  });

  it("does not count a finish with no place as a podium", () => {
    const unplaced = profile({
      rounds: [round({ results: [{ driver_id: "kimi-antonelli", race: finish({ position: null }), sprint: null }] })],
    });
    expect(teamKpis(unplaced).podiums.value).toBe(0);
  });

  it("falls back to the driver id for a result whose driver the team does not list", () => {
    const odd = profile({
      rounds: [round({ results: [{ driver_id: "nobody", race: finish({ position: 1 }), sprint: null }] })],
    });
    expect(teamKpis(odd).wins.sub).toBe("nobody 1");
  });
});

describe("driverRecord", () => {
  it("counts a driver's wins and poles over completed rounds", () => {
    expect(driverRecord(mercedes, "kimi-antonelli")).toEqual({ wins: 9, poles: 7 });
    expect(driverRecord(mercedes, "nobody")).toEqual({ wins: 0, poles: 0 });
  });
});

describe("heatCell", () => {
  const rounds = redBull.rounds;
  const cell = (roundIndex: number, driverId: string) =>
    heatCell(
      rounds[roundIndex],
      rounds[roundIndex].results.find((item) => item.driver_id === driverId),
    );

  it("reads a retirement as out, never as its classified place (VER R9)", () => {
    const out = cell(8, "max-verstappen");
    expect(out.kind).toBe("out");
    expect(out.finish?.reason_retired).toBe("Spun off");
  });

  it("is future for a round still to run, and absent for a round the driver did not race for the team", () => {
    expect(cell(22, "max-verstappen").kind).toBe("future");
    expect(cell(0, "liam-lawson").kind).toBe("absent");
  });

  it("colours the top three, then points, then the rest", () => {
    const base = round();
    const at = (race: Finish) => heatCell(base, { driver_id: "x", race, sprint: null }).kind;
    expect(at(finish({ position: 1, points: 25 }))).toBe("p1");
    expect(at(finish({ position: 2, points: 18 }))).toBe("p2");
    expect(at(finish({ position: 3, points: 15 }))).toBe("p3");
    expect(at(finish({ position: 7, points: 6 }))).toBe("points");
    expect(at(finish({ position: 12 }))).toBe("plain");
  });

  it("treats a finish with no place as a plain one", () => {
    const base = round();
    expect(heatCell(base, { driver_id: "x", race: finish({ position: null }), sprint: null }).kind).toBe("plain");
  });

  it("treats a result with no race row as absent", () => {
    expect(heatCell(round(), { driver_id: "x", race: null, sprint: finish() }).kind).toBe("absent");
  });
});

describe("weekendTitle", () => {
  it("names the biggest haul when every round scored", () => {
    expect(weekendTitle(mercedes)).toBe("Scored in every round; the Chinese GP was the biggest haul");
  });

  it("counts the rounds that scored when not all did", () => {
    const some = profile({
      rounds: [
        round({ points: 10 }),
        round({ round: 2, short_name: "Chinese GP", points: 0 }),
        round({ round: 3, status: "pending", points: 0 }),
      ],
    });
    expect(weekendTitle(some)).toBe("Scored in 1 of 2 rounds; the Australian GP was the biggest haul");
  });

  it("says no points yet before any score, with no haul named", () => {
    expect(weekendTitle(profile({ rounds: [round()] }))).toBe("No points yet");
    expect(weekendTitle(profile({ rounds: [] }))).toBe("No points yet");
  });

  it("marks a tie for the best weekend", () => {
    const tied = profile({
      rounds: [round({ points: 10 }), round({ round: 2, short_name: "Chinese GP", points: 10 })],
    });
    expect(weekendTitle(tied)).toBe("Scored in every round; the Australian GP was the biggest haul (tied)");
  });
});
