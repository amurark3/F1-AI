import { describe, expect, it } from "vitest";

import { GRIDS_2026 } from "@/test/fixtures";

import {
  buildGridLayout,
  gridNote,
  gridSourceLabel,
  gridTitle,
  hasGrid,
  lastSlot,
  penaltyNote,
  promotedNote,
  qualifiedNote,
} from "./gridHelpers";

import type { GridSlot } from "./gridModel";

const mexico = GRIDS_2026.mexicoCityOfficial;
const slot = (code: string): GridSlot => mexico.grid.find((s) => s.driver_code === code)!;
const last = lastSlot(mexico.grid);

describe("grid labels on Mexico City 2026", () => {
  it("lays the numbered slots out in staggered rows and keeps the pit lane apart", () => {
    const layout = buildGridLayout(mexico.grid);

    expect(layout.rows).toHaveLength(11);
    expect(layout.rows[0]?.leading?.driver_code).toBe("HAM");
    expect(layout.rows[0]?.trailing?.driver_code).toBe("RUS");
    expect(layout.pitLane.map((s) => s.driver_code)).toEqual(["LAW"]);
    expect(last).toBe(21);
  });

  it("leaves out cars that are in neither a slot nor the pit lane", () => {
    const orphan: GridSlot = { ...slot("HAM"), position: null, pit_lane: false };

    expect(buildGridLayout([orphan])).toEqual({ rows: [], pitLane: [] });
  });

  it("says where a car qualified only when that is news", () => {
    const none = new Set<string>();

    expect(qualifiedNote(slot("HAM"), none)).toBeNull();
    expect(qualifiedNote(slot("ANT"), none)).toBe("Qualified P5");
    expect(qualifiedNote(slot("VER"), none)).toBe("Qualified P4");
    expect(qualifiedNote(slot("LAW"), none)).toBeNull();
    expect(qualifiedNote(slot("LAW"), new Set(["LAW"]))).toBe("DSQ");
  });

  it("words each sanction, and marks a penalty that cost nothing", () => {
    expect(penaltyNote(slot("VER"), last)).toBe("−1 place");
    expect(penaltyNote(slot("LAW"), last)).toBe("Pit lane");
    expect(penaltyNote(slot("BOT"), last)).toBe("−50 places · cost nothing, already at the back");
    expect(penaltyNote(slot("HAM"), last)).toBeNull();
    expect(penaltyNote({ ...slot("HAM"), start_from_back: true }, last)).toBe("Back of grid");
    // Held its slot but not at the back: the cost-nothing mark does not claim the back.
    expect(penaltyNote({ ...slot("BOT"), position: 18 }, last)).toBe("−50 places · cost nothing");
  });

  it("credits a promotion to the penalised car that qualified ahead and started behind", () => {
    expect(promotedNote(slot("ANT"), mexico.grid)).toEqual({ places: 1, by: ["VER"] });
    expect(promotedNote(slot("HAM"), mexico.grid)).toBeNull();
    expect(promotedNote(slot("VER"), mexico.grid)).toBeNull();
    // No qualifying slot to compare: the gain is stated without a cause.
    expect(promotedNote({ ...slot("ANT"), qualifying_position: null }, mexico.grid)).toEqual({ places: 1, by: [] });
    expect(promotedNote({ ...slot("ANT"), position: null }, mexico.grid)?.by).toEqual(["VER"]);
  });

  it("computes the headline from the penalties on the sheet", () => {
    expect(gridTitle(mexico)).toBe("3 penalties on the grid");
    expect(gridTitle({ ...mexico, penalties: mexico.penalties.slice(0, 1) })).toBe("1 penalty on the grid");
    expect(gridTitle({ ...mexico, penalties: [] })).toBe("Every car starts where it qualified");
    expect(gridTitle(GRIDS_2026.saoPauloJolpicaProvisional)).toBe("Qualifying order, before any penalty");
    expect(gridTitle(GRIDS_2026.lasVegasNone)).toBeUndefined();
    expect(gridTitle(undefined)).toBeUndefined();
  });

  it("knows whether a payload holds a grid worth drawing", () => {
    expect(hasGrid(mexico)).toBe(true);
    expect(hasGrid(GRIDS_2026.lasVegasNone)).toBe(false);
    expect(hasGrid(undefined)).toBe(false);
    expect(hasGrid({ ...mexico, grid: [] })).toBe(false);
  });

  it("names the source and says whether it is final", () => {
    expect(gridNote(mexico)).toMatch(/FIA final starting grid/);
    expect(gridNote(GRIDS_2026.saoPauloJolpicaProvisional)).toMatch(/jolpica-qualifying\), provisional/);
    expect(gridNote(GRIDS_2026.saoPauloQualifyingDay)).toMatch(/\(qualifying\), provisional/);
    expect(gridNote(GRIDS_2026.lasVegasNone)).toBe("No grid is published for this round yet.");
    expect(gridNote(undefined)).toBe("No grid is published for this round yet.");
    expect(gridSourceLabel("official_grid")).toBe("official grid sheet");
    expect(gridSourceLabel("qualifying_classification")).toBe("qualifying order - provisional");
    expect(gridSourceLabel("unavailable")).toBe("not published");
  });
});
