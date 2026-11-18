import { describe, expect, it } from "vitest";

import { DIRECTORY_2026, STANDINGS_PROGRESSION_2026 } from "@/test/fixtures";

import { chartGeometry, linePath, titleRaceSub, titleRaceTitle, xTicks, yScale } from "./titleRaceModel";

const { rounds, drivers } = STANDINGS_PROGRESSION_2026;
const [leader] = drivers.entrants;

describe("yScale", () => {
  it("steps by 25, 50 or 100 and rounds the top up", () => {
    expect(yScale(380)).toEqual({ top: 400, ticks: [0, 100, 200, 300, 400] });
    expect(yScale(90)).toEqual({ top: 100, ticks: [0, 25, 50, 75, 100] });
    expect(yScale(0).top).toBe(25);
    expect(yScale(150)).toEqual({ top: 150, ticks: [0, 50, 100, 150] });
  });
});

describe("xTicks", () => {
  it("picks four evenly spread rounds without repeats", () => {
    expect(xTicks(19)).toEqual([0, 6, 12, 18]);
    expect(xTicks(2)).toEqual([0, 1]);
    expect(xTicks(1)).toEqual([0]);
  });
});

describe("linePath", () => {
  it("restarts after a gap", () => {
    expect(
      linePath(
        [null, 1, 2, null, 3],
        (i) => i * 10,
        (v) => v * 10,
      ),
    ).toBe("M10 10 L20 20 M40 30 L40 30");
  });
  it("draws a single point as a dot", () => {
    expect(
      linePath(
        [5],
        () => 7,
        (v) => v,
      ),
    ).toBe("M7 5 L7 5");
  });
});

describe("chartGeometry", () => {
  const geometry = chartGeometry(rounds, drivers.entrants, drivers.clinched);

  it("draws the top five with the leader last and in its team colour", () => {
    expect(geometry.lines).toHaveLength(5);
    expect(geometry.lines.at(-1)).toMatchObject({ key: "ANT", color: "#27F4D2", width: 3, label: "ANT 380" });
    expect(geometry.lines[0]).toMatchObject({ width: 1.5, quiet: true });
    expect(geometry.ticks.x.map((t) => t.label)).toEqual(["R1", "R7", "R13", "R19"]);
    expect(geometry.ticks.y.map((t) => t.label)).toEqual(["0", "100", "200", "300", "400"]);
  });

  it("keeps the end labels at least 12 apart", () => {
    const ys = geometry.lines.map((l) => l.labelY).sort((a, b) => a - b);
    ys.slice(1).forEach((y, i) => expect(y - ys[i]).toBeGreaterThanOrEqual(12));
  });

  it("puts the clinch marker on the leader's line, its label anchored to the end past the middle", () => {
    expect(geometry.marker).toMatchObject({ label: "Clinched · R19 Mexico City", anchor: "end" });
    expect(geometry.marker?.cx).toBe(426);
  });

  it("anchors an early marker to the start and has none for an unknown round or an open title", () => {
    const at = (round: number) => chartGeometry(rounds, drivers.entrants, { round, races_left: 5, sprints_left: 0 });
    expect(at(2).marker?.anchor).toBe("start");
    expect(at(99).marker).toBeNull();
    expect(chartGeometry(rounds, drivers.entrants, null).marker).toBeNull();
  });

  it("draws one round as a dot at the left edge", () => {
    const one = chartGeometry(rounds.slice(0, 1), [{ ...leader, points: [0], positions: [1] }], null);
    expect(one.lines[0]).toMatchObject({ label: "ANT 0", d: "M30 278 L30 278" });
  });

  it("has no marker, and labels zero, when the leader had no points at all", () => {
    const gap = { ...leader, points: leader.points.map(() => null) };
    const empty = chartGeometry(rounds, [gap], drivers.clinched);
    expect(empty.marker).toBeNull();
    expect(empty.lines[0].label).toBe("ANT 0");
  });
});

describe("titleRaceTitle", () => {
  it("names where the leader took the lead for good", () => {
    expect(titleRaceTitle(leader, rounds, true, DIRECTORY_2026)).toBe(
      "Antonelli led from Suzuka and never gave it back",
    );
    expect(titleRaceTitle(leader, rounds, false, DIRECTORY_2026)).toBe("Antonelli has led since Suzuka");
  });
  it("has the first-round forms", () => {
    const first = { ...leader, positions: leader.positions.map(() => 1) };
    expect(titleRaceTitle(first, rounds, true, DIRECTORY_2026)).toBe(
      "Antonelli led from the first round and never gave it back",
    );
    expect(titleRaceTitle(first, rounds, false, DIRECTORY_2026)).toBe("Antonelli has led since the first round");
  });
  it("falls back to the round number when the calendar has no location", () => {
    const bare = rounds.map((r) => ({ ...r, location: null }));
    expect(titleRaceTitle(leader, bare, false, DIRECTORY_2026)).toBe("Antonelli has led since round 3");
  });
});

describe("titleRaceSub", () => {
  it("counts the lines and flags a provisional last round", () => {
    expect(titleRaceSub(rounds, 5)).toBe("Cumulative points by round · top 5");
    const provisional = rounds.map((r, i) => ({ ...r, provisional: i === rounds.length - 1 }));
    expect(titleRaceSub(provisional, 5)).toBe("Cumulative points by round · top 5 · round 19 provisional");
  });
});
