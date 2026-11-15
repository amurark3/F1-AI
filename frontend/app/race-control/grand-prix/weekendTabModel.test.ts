import { describe, expect, it } from "vitest";

import { CIRCUIT_RECORDS, MEXICO_CITY_2026, RACE_RESULTS_2026, SEASON_2026 } from "@/test/fixtures";

import { circuitFacts, raceWinner, scheduleNodes } from "./weekendTabModel";

const MEXICO = SEASON_2026.schedule.find((race) => race.round === 19)!;
const SESSIONS = MEXICO.sessions ?? {};
const FIRST = Object.values(SESSIONS).sort()[0];

describe("scheduleNodes", () => {
  it("lists the sessions in start order, all later with no clock", () => {
    const nodes = scheduleNodes(SESSIONS, null);
    expect(nodes.map((node) => node.startsAt)).toEqual(Object.values(SESSIONS).sort());
    expect(new Set(nodes.map((node) => node.state))).toEqual(new Set(["later"]));
  });

  it("marks done, live, next and later against the clock", () => {
    const start = new Date(FIRST).getTime();
    expect(scheduleNodes(SESSIONS, start - 60_000).map((node) => node.state)).toEqual([
      "next",
      "later",
      "later",
      "later",
      "later",
    ]);
    const states = scheduleNodes(SESSIONS, start + 30 * 60_000).map((node) => node.state);
    expect(states[0]).toBe("live");
    expect(states[1]).toBe("later");
    const over = scheduleNodes(SESSIONS, start + 90 * 60_000).map((node) => node.state);
    expect(over.slice(0, 2)).toEqual(["done", "next"]);
  });

  it("leaves a session with no readable time out", () => {
    expect(scheduleNodes({ Race: "soon" }, 0)).toEqual([]);
  });
});

describe("raceWinner", () => {
  it("is the classification's first place, and none before one is published", () => {
    expect(raceWinner(RACE_RESULTS_2026.mexicoCity)?.driver_code).toBe("VER");
    expect(raceWinner(undefined)).toBeNull();
    expect(raceWinner({ ...RACE_RESULTS_2026.mexicoCity, race: null })).toBeNull();
  });
});

describe("circuitFacts", () => {
  it("reads the strip from f1db's record", () => {
    expect(circuitFacts(MEXICO_CITY_2026.circuit.record)).toEqual({
      lap: "4.304",
      laps: "71",
      distance: "305.4",
      corners: "17",
      direction: "Clockwise",
    });
    expect(circuitFacts({ ...CIRCUIT_RECORDS.imola2020, direction: "anti-clockwise" }).direction).toBe("Anticlockwise");
  });

  it("prints a dash, never a zero, for a fact f1db does not hold", () => {
    expect(circuitFacts(null)).toEqual({ lap: "-", laps: "-", distance: "-", corners: "-", direction: null });
    expect(circuitFacts({ ...CIRCUIT_RECORDS.madring2026.record, length_km: null }).lap).toBe("-");
  });
});
