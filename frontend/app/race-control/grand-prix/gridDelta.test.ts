import { describe, expect, it } from "vitest";

import { GRIDS_2026, PREDICTION_ORDERS_2026, type PredictionOrderRow } from "@/test/fixtures";

import { gridColumnNote, gridDelta, gridDeltaCell, type GridDelta } from "./gridDelta";

import type { GridSlot, StartingGridResponse } from "./gridModel";

const SAO_PAULO_POST = PREDICTION_ORDERS_2026.saoPauloPostQualifying;
const SAO_PAULO_PRE = PREDICTION_ORDERS_2026.saoPauloPreQualifying;
const MEXICO_POST = PREDICTION_ORDERS_2026.mexicoCityPostQualifying;

function predicted(order: PredictionOrderRow[], code: string): PredictionOrderRow {
  const row = order.find((prediction) => prediction.driver_code === code);
  if (!row) throw new Error(`${code} is not in this prediction`);
  return row;
}

function deltasFor(order: PredictionOrderRow[], grid: StartingGridResponse | undefined): Record<string, GridDelta> {
  return Object.fromEntries(order.map((prediction) => [prediction.driver_code, gridDelta(prediction, grid)]));
}

function places(start: number, finish: number): GridDelta {
  return { kind: "places", start, finish, places: start - finish };
}

function withSlot(grid: StartingGridResponse, code: string, change: Partial<GridSlot>): StartingGridResponse {
  return {
    ...grid,
    grid: grid.grid.map((slot) => (slot.driver_code === code ? { ...slot, ...change } : slot)),
  };
}

describe("gridDelta", () => {
  it("reads São Paulo's provisional grid, not the prediction's explanation text", () => {
    // 8 Nov audit: the column showed LEC +1, HAM +1, VER +2, PIA 0, GAS -1, STR -2,
    // PER -2 and BOR -5, parsed from "Trained model projects P<n>" and the like.
    const deltas = deltasFor(SAO_PAULO_POST, GRIDS_2026.saoPauloQualifyingDay);

    expect(deltas.LEC).toEqual(places(4, 4));
    expect(deltas.HAM).toEqual(places(11, 7));
    expect(deltas.VER).toEqual(places(16, 8));
    expect(deltas.PIA).toEqual(places(12, 10));
    expect(deltas.GAS).toEqual(places(18, 15));
    expect(deltas.STR).toEqual(places(19, 19));
    expect(deltas.PER).toEqual(places(21, 20));
    expect(deltas.BOR).toEqual(places(22, 22));
    expect([deltas.HAM, deltas.VER, deltas.BOR].map((delta) => delta.kind === "places" && delta.places)).toEqual([
      4, 8, 0,
    ]);
  });

  it("never matches anyone to a grid slot that carries no driver code", () => {
    // f1db v2026.19.0 did not know Câmara on qualifying day, so his P13 slot is uncoded.
    const grid = GRIDS_2026.saoPauloQualifyingDay;
    const deltas = deltasFor(SAO_PAULO_POST, grid);

    expect(deltas.CAM).toEqual({ kind: "unknown", reason: "slot_unidentified" });
    expect(Object.values(deltas).filter((delta) => delta.kind === "places")).toHaveLength(21);
    expect(gridDelta({ driver_code: "", position: 13 }, grid)).toEqual({
      kind: "unknown",
      reason: "slot_unidentified",
    });
  });

  it("does not match a slot flagged unresolved even when it carries a code", () => {
    const grid = withSlot(GRIDS_2026.saoPauloF1dbV202620, "CAM", { code_unresolved: true });

    expect(gridDelta(predicted(SAO_PAULO_POST, "CAM"), grid)).toEqual({
      kind: "unknown",
      reason: "slot_unidentified",
    });
  });

  it("reads Câmara from P13 once f1db codes him", () => {
    // His stored prediction (P18) was scored from "P23" before P0b.6.
    expect(gridDelta(predicted(SAO_PAULO_POST, "CAM"), GRIDS_2026.saoPauloF1dbV202620)).toEqual(places(13, 18));
  });

  it("means the same before qualifying: the predicted finish against where the car starts", () => {
    const deltas = deltasFor(SAO_PAULO_PRE, GRIDS_2026.saoPauloF1dbV202620);

    expect(deltas.ANT).toEqual(places(3, 1));
    expect(deltas.VER).toEqual(places(16, 2));
    expect(deltas.CAM).toEqual(places(13, 15));
  });

  it("reads the official grid sheet, penalties applied", () => {
    const deltas = deltasFor(MEXICO_POST, GRIDS_2026.mexicoCityOfficial);

    // Verstappen qualified P4 and dropped one place; Bottas's 50 places left him P21.
    expect(deltas.VER).toEqual(places(5, 1));
    expect(deltas.HAM).toEqual(places(1, 3));
    expect(deltas.BOT).toEqual(places(21, 21));
  });

  it("says pit lane, with no number, for a pit-lane start", () => {
    expect(gridDelta(predicted(MEXICO_POST, "LAW"), GRIDS_2026.mexicoCityOfficial)).toEqual({ kind: "pit_lane" });
  });

  it("says a driver is not on the grid rather than guessing", () => {
    // The Mexico snapshot coded Hirakawa "NAN"; the grid sheet has him as HIR.
    expect(gridDelta(predicted(MEXICO_POST, "NAN"), GRIDS_2026.mexicoCityOfficial)).toEqual({
      kind: "unknown",
      reason: "not_on_grid",
    });
  });

  it("gives no number for a slot published without a position", () => {
    const grid = withSlot(GRIDS_2026.mexicoCityOfficial, "VER", { position: null });

    expect(gridDelta(predicted(MEXICO_POST, "VER"), grid)).toEqual({ kind: "unknown", reason: "no_slot" });
  });

  it("gives no number before there is a grid", () => {
    const deltas = deltasFor(SAO_PAULO_PRE, GRIDS_2026.lasVegasNone);

    expect(new Set(Object.values(deltas).map((delta) => JSON.stringify(delta)))).toEqual(
      new Set([JSON.stringify({ kind: "unknown", reason: "no_grid" })]),
    );
  });

  it("gives no number while the grid has not loaded or failed to", () => {
    const failed: StartingGridResponse = { ...GRIDS_2026.lasVegasNone, error: "Could not load the grid." };
    const ver = predicted(SAO_PAULO_POST, "VER");

    expect(gridDelta(ver, undefined)).toEqual({ kind: "unknown", reason: "grid_not_loaded" });
    expect(gridDelta(ver, failed)).toEqual({ kind: "unknown", reason: "grid_not_loaded" });
  });
});

describe("gridDeltaCell", () => {
  it("signs and colours places gained, lost and held", () => {
    expect(gridDeltaCell(places(16, 8))).toEqual({
      text: "+8",
      className: "text-rc-gain",
      note: "Starts P16, predicted P8",
    });
    expect(gridDeltaCell(places(1, 3))).toEqual({
      text: "-2",
      className: "text-rc-red-text",
      note: "Starts P1, predicted P3",
    });
    expect(gridDeltaCell(places(22, 22))).toEqual({
      text: "0",
      className: "text-rc-ink-2",
      note: "Starts P22, predicted P22",
    });
  });

  it("writes a pit-lane start out", () => {
    expect(gridDeltaCell({ kind: "pit_lane" })).toEqual({
      text: "Pit lane",
      className: "text-rc-ink-2",
      note: "Starts from the pit lane",
    });
  });

  it("dashes every unknown and says why", () => {
    const notes = (["grid_not_loaded", "no_grid", "not_on_grid", "slot_unidentified", "no_slot"] as const).map(
      (reason) => gridDeltaCell({ kind: "unknown", reason }),
    );

    expect(new Set(notes.map(({ text, className }) => `${text} ${className}`))).toEqual(new Set(["— text-rc-ink-3"]));
    expect(notes.map(({ note }) => note)).toEqual([
      "The starting grid has not loaded",
      "No grid yet",
      "Not on the starting grid",
      "Not matched: a grid slot has no driver code",
      "No grid slot published",
    ]);
  });
});

describe("gridColumnNote", () => {
  it("names the grid the column reads", () => {
    expect(gridColumnNote(GRIDS_2026.saoPauloQualifyingDay, false)).toBe("vs grid: qualifying order - provisional");
    expect(gridColumnNote(GRIDS_2026.mexicoCityOfficial, false)).toBe("vs grid: official grid sheet");
  });

  it("says when there is no grid yet", () => {
    expect(gridColumnNote(GRIDS_2026.lasVegasNone, false)).toBe("vs grid: no grid yet");
  });

  it("tells loading apart from a failed load", () => {
    const failed: StartingGridResponse = { ...GRIDS_2026.lasVegasNone, error: "Could not load the grid." };

    expect(gridColumnNote(undefined, true)).toBe("vs grid: grid loading");
    expect(gridColumnNote(undefined, false)).toBe("vs grid: grid unavailable");
    expect(gridColumnNote(failed, false)).toBe("vs grid: grid unavailable");
  });
});
