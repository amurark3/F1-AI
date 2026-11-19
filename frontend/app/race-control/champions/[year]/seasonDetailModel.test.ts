import { describe, expect, it } from "vitest";

import type { SeasonDetail } from "@/app/lib/server/champions";
import { CHAMPIONS } from "@/test/fixtures/champions";

import {
  dayMonth,
  ribbonLegend,
  ribbonTitle,
  roundsAside,
  roundTicks,
  seasonEyebrow,
  seasonMeta,
  seasonSource,
  seasonTiles,
  toRunRow,
  winnerRows,
} from "./seasonDetailModel";

const clinched = CHAMPIONS.season2026;
const fangio = CHAMPIONS.season1957;
const driver = clinched.driver_champion!;

// Derived from season2026 with f1db's standings after R18 (title not yet decided).
const open: SeasonDetail = {
  ...clinched,
  rounds_completed: 18,
  decided_at: null,
  race_winners: clinched.race_winners!.filter((w) => w.round <= 18),
  driver_champion: { ...driver, points: 365, wins: 9, title_decided: false },
  runner_up: { name: "George Russell", last_name: "Russell", points: 242 },
  constructor_champion: { name: "Mercedes", points: 607, title_decided: false },
};
// Derived from season2026: every round run, the title decided in round 19 of 20 / 20 of 20.
const final: SeasonDetail = { ...clinched, round_count: 20 };
const lastRound: SeasonDetail = { ...final, decided_at: { round: 20, date: "2026-11-08", place: "Sao Paulo" } };
// Derived from season2026: nothing recorded.
const none: SeasonDetail = {
  ...clinched,
  driver_champion: null,
  runner_up: null,
  constructor_champion: null,
  race_winners: [],
  rounds_completed: 0,
  decided_at: null,
};

describe("season hero copy", () => {
  it("labels every title state", () => {
    expect(seasonEyebrow(clinched)).toBe("2026 World Champion · clinched");
    expect(seasonEyebrow(final)).toBe("2026 World Champion");
    expect(seasonEyebrow(open)).toBe("2026 championship leader");
    expect(seasonEyebrow(none)).toBe("2026 season");
  });

  it("writes the meta line", () => {
    expect(seasonMeta(clinched)).toBe("Mercedes · Title decided in round 19, Mexico City. 3 rounds still to run.");
    expect(seasonMeta(fangio)).toBe("Maserati · Title decided in round 6, Nürburg.");
    expect(seasonMeta(open)).toBe("Mercedes · Leads after round 18 of 23; the title is still open.");
    expect(seasonMeta({ ...clinched, decided_at: { round: 19, date: "2026-11-01", place: null } })).toContain(
      "in round 19.",
    );
    expect(seasonMeta({ ...final, decided_at: null })).toBe("Mercedes");
    expect(seasonMeta({ ...final, decided_at: null, driver_champion: { ...driver, team: null } })).toBeUndefined();
    expect(seasonMeta(none)).toBeUndefined();
  });

  it("builds the tiles for a clinched title", () => {
    expect(seasonTiles(clinched)).toEqual([
      { label: "Points", value: "390", unit: "pts", sub: "after round 20 of 23", lead: true },
      { label: "Wins", value: "9", unit: "of 20" },
      { label: "Margin", value: "111", unit: "pts", sub: "over Max Verstappen · 279 pts" },
      { label: "Constructors' champion", value: "Mercedes", sub: "652 pts after round 20 of 23" },
    ]);
  });

  it("builds the tiles for a past title, with no constructors' title before 1958", () => {
    expect(seasonTiles(fangio).map((t) => [t.label, t.value, t.sub])).toEqual([
      ["Points", "40", "final total"],
      ["Wins", "4", undefined],
      ["Margin", "15", "over Stirling Moss · 25 pts"],
      ["Constructors' champion", "—", "title awarded from 1958"],
    ]);
  });

  it("builds the tiles for an open title and a final one", () => {
    expect(seasonTiles(open).map((t) => [t.label, t.value, t.sub])).toEqual([
      ["Points", "365", "after round 18 of 23"],
      ["Wins", "9", undefined],
      ["Lead", "123", "over George Russell · 242 pts"],
      ["Constructors' leader", "Mercedes", "607 pts after round 18 of 23"],
    ]);
    expect(seasonTiles(final).map((t) => t.sub)).toContain("652 pts");
  });

  it("drops the tiles it has no data for", () => {
    expect(seasonTiles({ ...clinched, runner_up: null })).toHaveLength(3);
    expect(seasonTiles({ ...clinched, constructor_champion: null })).toHaveLength(3);
    expect(seasonTiles(none)).toEqual([]);
    expect(seasonTiles({ ...none, constructor_champion: clinched.constructor_champion })).toHaveLength(1);
    expect(seasonTiles({ ...clinched, driver_champion: { ...driver, points: 390.5 } })[0].value).toBe("390.5");
  });
});

describe("round by round", () => {
  it("computes the card's finding", () => {
    expect(ribbonTitle(clinched, driver)).toBe("9 wins for Antonelli, decided with 4 rounds to spare");
    expect(ribbonTitle(fangio, fangio.driver_champion!)).toBe("4 wins for Fangio, decided with 2 rounds to spare");
    expect(ribbonTitle(open, open.driver_champion!)).toBe("9 wins for Antonelli, title still open after round 18");
    expect(ribbonTitle(final, driver)).toBe("9 wins for Antonelli, decided with 1 round to spare");
    expect(ribbonTitle(lastRound, driver)).toBe("9 wins for Antonelli, decided at the last round");
    expect(ribbonTitle({ ...final, decided_at: null }, driver)).toBe("9 wins for Antonelli");
    expect(ribbonTitle({ ...final, decided_at: null }, { ...driver, wins: 1 })).toBe("1 win for Antonelli");
  });

  it("draws one tick per round", () => {
    const ticks = roundTicks(clinched);
    expect(ticks).toHaveLength(23);
    expect(ticks.filter((t) => t.championWon).map((t) => t.round)).toEqual([2, 3, 4, 5, 6, 10, 13, 14, 18]);
    expect(ticks.filter((t) => !t.run).map((t) => t.round)).toEqual([21, 22, 23]);
    expect(ticks.filter((t) => t.keep).map((t) => t.round)).toEqual([1, 19, 23]);
    expect(ticks[0].tip).toBe("R1 · George Russell · Mercedes");
    expect(ticks[20].tip).toBe("R21 · still to run");
    expect(ticks[18].flag).toEqual({ text: "Title decided · Mexico City", side: "end" });
    expect(ticks.filter((t) => t.decider)).toHaveLength(1);
  });

  it("folds a shared drive into one tick", () => {
    const tick = roundTicks(fangio)[4];
    expect(tick.tip).toBe("R5 · Tony Brooks / Stirling Moss · Vanwall · shared drive");
    expect(roundTicks(fangio)[5].flag).toEqual({ text: "Title decided · Nürburg", side: "end" });
  });

  it("opens the flag rightwards early in the season, and says less without a place", () => {
    const early = roundTicks({ ...clinched, decided_at: { round: 5, date: "2026-05-01", place: null } })[4];
    expect(early.flag).toEqual({ text: "Title decided", side: "start" });
    expect(roundTicks(none).every((t) => !t.run && !t.championWon && !t.decider)).toBe(true);
  });

  it("copes with a payload that has no winners list", () => {
    const bare = { ...none, race_winners: undefined };
    expect(roundTicks(bare)).toHaveLength(23);
    expect(winnerRows(bare)).toEqual([]);
  });

  it("lists a tick's team only when the feed has one", () => {
    const [first] = clinched.race_winners!;
    const tick = roundTicks({ ...clinched, race_winners: [{ ...first, team: null }] })[0];
    expect(tick.tip).toBe("R1 · George Russell");
    expect(tick.team).toBeNull();
  });

  it("keys the legend to the state", () => {
    expect(ribbonLegend(clinched, driver).map((i) => i.label)).toEqual([
      "Antonelli's win",
      "Title decided",
      "Still to run",
      "Bar = the winning car's team",
    ]);
    expect(ribbonLegend(open, open.driver_champion!).map((i) => i.label)).toEqual([
      "Antonelli's win",
      "Still to run",
      "Bar = the winning car's team",
    ]);
    expect(ribbonLegend(fangio, fangio.driver_champion!).map((i) => i.label)).not.toContain("Still to run");
  });
});

describe("winner rows", () => {
  it("lists every round, a shared drive folded", () => {
    const rows = winnerRows(clinched);
    expect(rows).toHaveLength(20);
    expect(rows[0]).toMatchObject({ round: 1, date: "8 Mar", decider: false, shared: false, team: "Mercedes" });
    expect(rows[18].decider).toBe(true);
    const shared = winnerRows(fangio)[4];
    expect(shared.shared).toBe(true);
    expect(shared.winners.map((w) => w.winner)).toEqual(["Tony Brooks", "Stirling Moss"]);
    expect(winnerRows(none)).toEqual([]);
  });

  it("leaves the team id null when the feed has none", () => {
    const [first] = clinched.race_winners!;
    expect(winnerRows({ ...clinched, race_winners: [{ ...first, team_id: undefined }] })[0].teamId).toBeNull();
  });

  it("closes with the rounds still to run", () => {
    expect(toRunRow(clinched)).toEqual({ span: "R21–R23", text: "3 rounds still to run" });
    expect(toRunRow({ ...clinched, round_count: 21 })).toEqual({ span: "R21", text: "1 round still to run" });
    expect(toRunRow(none)).toEqual({ span: "R1–R23", text: "23 rounds still to run" });
    expect(toRunRow(final)).toBeNull();
  });

  it("writes the aside, the source note and the dates", () => {
    expect(roundsAside(clinched)).toBe("20 of 23 rounds");
    expect(seasonSource(clinched)).toBe("Source: f1db · 2026 after round 20 of 23");
    expect(seasonSource(fangio)).toBe("Source: f1db");
    expect(seasonSource(none)).toBe("Source: f1db");
    expect(dayMonth("2026-03-08")).toBe("8 Mar");
    expect(dayMonth(null)).toBe("");
  });
});
