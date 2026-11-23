import { describe, expect, it } from "vitest";

import { REWIND_R19 as r19 } from "@/test/fixtures/rewind";
import { change, driver, finalOf, lap, race } from "@/test/fixtures/rewindHandBuilt";

import {
  changeDetail,
  changeLabel,
  changesAt,
  defaultStep,
  driverOf,
  initialStep,
  lapAt,
  leaders,
  maxStep,
  stepKind,
  stepLabel,
  towerRows,
} from "./rewindModel";

const codes = (rows: ReadonlyArray<{ code: string }>) => rows.map((row) => row.code).join(" ");
const name = (code: string | null) => (code === null ? "" : `<${code}>`);

describe("steps", () => {
  it("runs from the grid through every lap to the final classification", () => {
    expect(maxStep(r19)).toBe(72);
    expect(maxStep(race({ final: null }))).toBe(3);
    expect(stepKind(0, r19)).toEqual({ kind: "grid" });
    expect(stepKind(44, r19)).toEqual({ kind: "lap", lap: 44 });
    expect(stepKind(72, r19)).toEqual({ kind: "final" });
  });

  it("labels each step for the range", () => {
    expect(stepLabel(0, r19)).toBe("Grid");
    expect(stepLabel(44, r19)).toBe("After lap 44 of 71");
    expect(stepLabel(72, r19)).toBe("Final classification");
  });

  it("opens on the first lap of the last lead run, or lap 1 when one car led every lap", () => {
    expect(defaultStep(r19)).toBe(44);
    expect(defaultStep(race())).toBe(1);
    expect(defaultStep(race({ laps: [] }))).toBe(1);
    expect(leaders(race({ laps: [lap(1, [])] }))).toEqual([null]);
  });

  it("takes the step the URL asks for when this race has it", () => {
    expect(initialStep(28, r19)).toBe(28);
    expect(initialStep(0, r19)).toBe(0);
    expect(initialStep("final", r19)).toBe(72);
    expect(initialStep("final", race({ final: null }))).toBe(1);
    expect(initialStep(99, r19)).toBe(44);
    expect(initialStep(72, r19)).toBe(44);
    expect(initialStep(null, r19)).toBe(44);
  });

  it("finds the lap a step shows", () => {
    expect(lapAt(r19, 44)?.track).toBe("sc");
    expect(lapAt(r19, 0)).toBeNull();
    expect(lapAt(r19, 72)).toBeNull();
  });
});

describe("the tower on R19", () => {
  it("shows the order at the line after lap 44, the pit stops and the cars that are out", () => {
    const rows = towerRows(r19, 44);

    expect(codes(rows)).toBe("VER LEC HAM ANT NOR RUS PIA LIN COL GAS HUL BEA BOR HAD LAW SAI HIR ALB PER BOT ALO STR");
    expect(
      rows
        .filter((row) => row.tag === "PIT")
        .map((row) => row.code)
        .sort(),
    ).toEqual(["ANT", "GAS", "HAM", "HIR", "PER", "PIA", "RUS"]);
    const out = rows.filter((row) => row.out);
    expect(out.map((row) => [row.code, row.tag, row.place])).toEqual([
      ["BOT", "DNF L42", null],
      ["ALO", "DNF L5", null],
      ["STR", "DNF L5", null],
    ]);
    expect(rows[0]).toMatchObject({ place: 1, code: "VER", delta: 1, name: "Max Verstappen" });
    expect(rows.find((row) => row.code === "ANT")?.delta).toBe(-3);
  });

  it("shows the grid with the pit-lane starter unplaced", () => {
    const rows = towerRows(r19, 0);

    expect(rows[0]).toMatchObject({ code: "HAM", place: 1, delta: null, tag: null });
    expect(rows.at(-1)).toMatchObject({ code: "LAW", place: null, tag: "Pit lane" });
    expect(rows.at(-2)?.place).toBe(21);
  });

  it("shows the FIA order at the final step, then the retirements", () => {
    const rows = towerRows(r19, 72);

    expect(codes(rows)).toBe("VER HAM ANT LEC NOR RUS LAW BOR HAD HIR ALB SAI PIA HUL COL PER GAS LIN BEA BOT STR ALO");
    expect(rows.find((row) => row.code === "PIA")).toMatchObject({ place: 13, delta: -6 });
    expect(rows.find((row) => row.code === "LAW")).toMatchObject({ place: 7, delta: 2 });
    expect(rows.find((row) => row.code === "LIN")).toMatchObject({
      place: null,
      tag: "DNF L58",
      out: true,
      delta: null,
    });
  });

  it("puts lap 71 in the road order", () => {
    expect(codes(towerRows(r19, 71).filter((row) => !row.out))).toBe(
      "VER HAM ANT LEC NOR RUS PIA COL LAW GAS BOR HAD HIR ALB SAI HUL PER",
    );
  });
});

describe("the tower on hand-built races", () => {
  it("tags a DNS before the grid, and a DSQ, DNS and NC at the final step", () => {
    const final = finalOf({
      rows: [
        { driver_code: "AAA", position: 1, status: "finished", laps: 3, road_position: null, penalties: [] },
        { driver_code: "BBB", position: null, status: "dsq", laps: 3, road_position: 2, penalties: [] },
        { driver_code: "CCC", position: null, status: "dns", laps: null, road_position: null, penalties: [] },
        { driver_code: "ZZZ", position: null, status: "not_classified", laps: 1, road_position: null, penalties: [] },
      ],
    });
    const rows = towerRows(race({ final }), 4);

    expect(rows.map((row) => [row.code, row.tag, row.out, row.delta])).toEqual([
      ["AAA", null, false, null],
      ["BBB", "DSQ", true, null],
      ["CCC", "DNS", false, null],
      ["ZZZ", "NC", false, null],
    ]);
    expect(rows[3]).toMatchObject({ name: "ZZZ", team: "" });
  });

  it("has no rows at the final step without a classification", () => {
    expect(towerRows(race({ final: null }), 4)).toEqual([]);
  });

  it("lists the cars that never started among the cars out", () => {
    const drivers = [
      driver("AAA"),
      driver("BBB"),
      driver("CCC", { status: "dns", laps: null }),
      driver("DDD", { status: "dns", laps: null }),
    ];
    const rows = towerRows(race({ drivers }), 2);

    expect(rows.slice(-2)).toMatchObject([
      { code: "CCC", tag: "DNS", out: true },
      { code: "DDD", tag: "DNS", out: true },
    ]);
  });

  it("gives a car new to the order no delta", () => {
    const rows = towerRows(race({ grid: { order: ["AAA"], pit_lane: [], source: "f1db", document: null } }), 1);

    expect(rows.map((row) => row.delta)).toEqual([0, null, null]);
  });

  it("finds a driver by code, or builds a stand-in", () => {
    expect(driverOf(race(), "BBB").driver_name).toBe("Bravo Bell");
    expect(driverOf(race(), "QQQ")).toMatchObject({ driver_name: "QQQ", team: "" });
  });

  it("orders the cars out by laps and then code", () => {
    const drivers = [
      driver("AAA"),
      driver("DDD", { status: "dnf", laps: 1 }),
      driver("CCC", { status: "dnf", laps: 1 }),
      driver("BBB", { status: "dnf", laps: 2 }),
    ];
    const rows = towerRows(race({ drivers, laps: [lap(1, ["AAA"]), lap(2, ["AAA"]), lap(3, ["AAA"])] }), 3);

    expect(codes(rows)).toBe("AAA BBB CCC DDD");
    expect(rows[1].tag).toBe("DNF L2");
  });
});

describe("the changes", () => {
  it("returns a lap's changes, and none for the grid or the final step", () => {
    expect(changesAt(r19, 44)).toHaveLength(6);
    expect(changesAt(r19, 0)).toEqual([]);
    expect(changesAt(r19, 72)).toEqual([]);
  });

  it("labels each kind, and a neutralised change by the lap's track", () => {
    const base = change("AAA", 2, 1);
    expect(changeLabel({ ...base, kind: "own_stop" }, null)).toBe("Own stop");
    expect(changeLabel({ ...base, kind: "rival_stop" }, null)).toBe("A rival's stop");
    expect(changeLabel({ ...base, kind: "retirement" }, null)).toBe("Retirement ahead");
    expect(changeLabel({ ...base, kind: "pass" }, null)).toBe("Pass");
    expect(changeLabel(base, null)).toBe("Position change");
    expect(changeLabel({ ...base, kind: "neutralised" }, "sc")).toBe("Under Safety Car");
    expect(changeLabel({ ...base, kind: "neutralised" }, "vsc")).toBe("Under VSC");
    expect(changeLabel({ ...base, kind: "neutralised" }, "red")).toBe("Under red flag");
    expect(changeLabel({ ...base, kind: "neutralised" }, null)).toBe("Neutralised");
  });

  it("details each kind", () => {
    const base = change("AAA", 2, 1, { rival: "BBB", stop_lap: 43 });
    expect(changeDetail({ ...base, kind: "own_stop" }, name)).toBe("stopped lap 43");
    expect(changeDetail({ ...base, kind: "rival_stop" }, name)).toBe("<BBB> stopped lap 43");
    expect(changeDetail({ ...base, kind: "retirement" }, name)).toBe("<BBB> retired");
    expect(changeDetail({ ...base, kind: "neutralised" }, name)).toBe("not counted as a pass");
    expect(changeDetail({ ...base, kind: "pass" }, name)).toBe("passed <BBB>");
    expect(changeDetail({ ...base, from: 1, to: 2, kind: "pass" }, name)).toBe("passed by <BBB>");
    expect(changeDetail({ ...base, kind: "change" }, name)).toBe("");
  });
});
