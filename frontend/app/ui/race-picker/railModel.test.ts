import { describe, expect, it } from "vitest";

import { SEASON_2026 } from "@/test/fixtures";

import { raceDay, seasonRail, tipAlign } from "./railModel";

const { schedule, winners, winnersThroughRound19 } = SEASON_2026;
/** Days from 1 March 2026 to 1 January 2027: the opening race's month to the end of the finale's. */
const SPAN_DAYS = 306;

function at(day: number): number {
  return (day / SPAN_DAYS) * 100;
}

describe("seasonRail", () => {
  const rail = seasonRail(schedule, winners.race_winners);

  it("places every round by its race day, across the whole months from the first race to the last", () => {
    expect(rail.ticks.map((tick) => tick.race.round)).toEqual(schedule.map((race) => race.round));
    expect(rail.ticks[0]?.left).toBeCloseTo(at(7)); // Melbourne, 8 March
    expect(rail.ticks[3]?.left).toBeCloseTo(at(63)); // Miami, 3 May: no race in April
    expect(rail.ticks.at(-1)?.left).toBeCloseTo(at(280)); // Abu Dhabi, 6 December
  });

  it("marks the start of each month the rail spans", () => {
    expect(rail.months.map((month) => month.label)).toEqual([
      "MAR",
      "APR",
      "MAY",
      "JUN",
      "JUL",
      "AUG",
      "SEP",
      "OCT",
      "NOV",
      "DEC",
    ]);
    expect(rail.months[0]?.left).toBe(0);
    expect(rail.months[1]?.left).toBeCloseTo(at(31));
  });

  it("colours a run round by its winner's team, and leaves the rounds to come uncoloured", () => {
    const colours = Object.fromEntries(rail.ticks.map((tick) => [tick.race.round, tick.color]));
    expect(colours).toMatchObject({ 1: "#27F4D2", 7: "#E8002D", 11: "#FF8000", 19: "#3671C6", 20: "#FF8000" });
    expect(rail.ticks.filter((tick) => tick.state === "won")).toHaveLength(20);
    expect(rail.ticks.slice(20).map((tick) => [tick.state, tick.color])).toEqual([
      ["upcoming", null],
      ["upcoming", null],
      ["upcoming", null],
    ]);
  });

  it("titles each round and says who won it, with the team the colour stands for", () => {
    expect(rail.ticks[18]).toMatchObject({ title: "R19 · Mexico City GP", detail: "Max Verstappen won · Red Bull" });
    expect(rail.ticks[19]).toMatchObject({ title: "R20 · São Paulo GP", detail: "Lando Norris won · McLaren" });
    expect(rail.ticks[20]).toMatchObject({ title: "R21 · Las Vegas GP", detail: "Race day 21 Nov" });
  });

  it("names a winner f1db joined no team to, in the neutral colour", () => {
    // `race_winners` LEFT JOINs the constructor, so `team` may be null.
    const teamless = winners.race_winners.map((winner) => (winner.round === 1 ? { ...winner, team: null } : winner));

    expect(seasonRail(schedule, teamless).ticks[0]).toMatchObject({
      state: "won",
      color: "#6B7280",
      detail: "George Russell won",
    });
  });

  it("leaves a run round neutral until its winner is published", () => {
    const beforeF1db = seasonRail(schedule, winnersThroughRound19.race_winners);

    expect(beforeF1db.ticks[19]).toMatchObject({ state: "awaiting", color: null, detail: "Winner not published yet" });
    expect(beforeF1db.ticks[18]).toMatchObject({ state: "won", color: "#3671C6" });
  });

  it("claims nothing about a winner while the winners have not loaded", () => {
    const unknown = seasonRail(schedule, undefined);

    expect(unknown.ticks[0]).toMatchObject({ state: "awaiting", color: null, detail: "Completed" });
    expect(unknown.ticks[20]).toMatchObject({ state: "upcoming", detail: "Race day 21 Nov" });
  });

  it("says a weekend is under way while it runs", () => {
    // The backend marks a weekend `in_progress` from its first session to three hours after its last.
    const running = schedule.map((race) => (race.round === 21 ? { ...race, status: "in_progress" } : race));

    expect(seasonRail(running, winners.race_winners).ticks[20]).toMatchObject({
      state: "awaiting",
      color: null,
      detail: "Race weekend under way",
    });
  });

  it("spaces the rounds evenly when a round has no date to place it by", () => {
    const undated = schedule.slice(0, 4).map((race, index) => (index === 2 ? { ...race, date: undefined } : race));
    const even = seasonRail(undated, winners.race_winners);

    expect(even.ticks.map((tick) => tick.left)).toEqual([12.5, 37.5, 62.5, 87.5]);
    expect(even.months).toEqual([]);
  });

  it("is empty for an empty calendar", () => {
    expect(seasonRail([], winners.race_winners)).toEqual({ ticks: [], months: [] });
  });
});

describe("raceDay", () => {
  it("reads the race day in UTC, the circuit's own date", () => {
    expect(raceDay(schedule[19])).toBe("8 Nov");
    expect(raceDay(schedule[13])).toBe("13 Sep");
    expect(raceDay({ ...schedule[19], date: undefined })).toBe("date TBC");
  });
});

describe("tipAlign", () => {
  it("keeps a tip inside the rail at either end", () => {
    expect(tipAlign(2.3)).toBe("start");
    expect(tipAlign(50)).toBe("center");
    expect(tipAlign(85.6)).toBe("end");
  });
});
