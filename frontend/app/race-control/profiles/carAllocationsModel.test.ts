import { describe, expect, it } from "vitest";

import {
  ALLOCATION_ANTONELLI,
  ALLOCATION_HAMILTON,
  ALLOCATION_RESPONSE,
  ALLOCATION_RUSSELL,
} from "@/test/fixtures/powerUnitsAllocation";

import {
  carAllocationsTitle,
  carFooterLink,
  carAllocationsSub,
  gridPlacesCell,
  pickCars,
  pipsFor,
  type CarScope,
} from "./carAllocationsModel";

import type { ElementUsage, PowerUnitCar } from "../power-units/powerUnitsModel";

const MERCEDES: CarScope = { kind: "team", teamId: "mercedes" };

function withUsed(car: PowerUnitCar, used: number[], gridPlaces = 0): PowerUnitCar {
  return {
    ...car,
    elements: car.elements.map((element, index) => ({
      ...element,
      used: used[index] ?? 0,
      over_by: Math.max((used[index] ?? 0) - (element.allowance ?? 0), 0),
    })),
    penalties: { ...car.penalties, grid_places: gridPlaces },
  };
}

describe("pickCars", () => {
  const cars = [ALLOCATION_HAMILTON, ALLOCATION_RUSSELL, ALLOCATION_ANTONELLI];

  it("takes a team's cars in number order", () => {
    expect(pickCars(cars, MERCEDES).map((car) => car.car_number)).toEqual([12, 63]);
  });

  it("takes the cars a driver raced, each stint counted", () => {
    expect(pickCars(cars, { kind: "driver", driverId: "lewis-hamilton", lastName: "Hamilton" })).toEqual([
      ALLOCATION_HAMILTON,
    ]);
  });

  it("gives a driver two rows when they raced two cars, and none when they raced none", () => {
    const shared = {
      ...ALLOCATION_RUSSELL,
      drivers: [
        ...ALLOCATION_RUSSELL.drivers,
        { id: "lewis-hamilton", name: "Lewis Hamilton", code: "HAM", car_number: 63, rounds: [3] },
      ],
    };
    const scope: CarScope = { kind: "driver", driverId: "lewis-hamilton", lastName: "Hamilton" };
    expect(pickCars([ALLOCATION_HAMILTON, shared], scope).map((car) => car.car_number)).toEqual([44, 63]);
    expect(pickCars(cars, { kind: "driver", driverId: "nobody", lastName: "Nobody" })).toEqual([]);
  });
});

describe("carAllocationsTitle", () => {
  it("names two cars past the allocation and the grid places lost", () => {
    expect(carAllocationsTitle([ALLOCATION_ANTONELLI, ALLOCATION_RUSSELL])).toBe(
      "Both cars are past the allocation: 90 grid places lost",
    );
  });

  it("says one place in the singular", () => {
    const one = withUsed(ALLOCATION_ANTONELLI, [5, 3, 3, 2, 3, 3, 6], 1);
    expect(carAllocationsTitle([one, ALLOCATION_HAMILTON])).toBe(
      "1 of 2 cars are past the allocation: 1 grid place lost",
    );
  });

  it("counts the cars past it when only some are, and says All above two", () => {
    expect(carAllocationsTitle([ALLOCATION_ANTONELLI, ALLOCATION_HAMILTON])).toBe(
      "1 of 2 cars are past the allocation: 30 grid places lost",
    );
    expect(
      carAllocationsTitle([
        ALLOCATION_ANTONELLI,
        ALLOCATION_RUSSELL,
        withUsed(ALLOCATION_RUSSELL, [6, 6, 6, 6, 6, 6, 9]),
      ]),
    ).toBe("All 3 cars are past the allocation: 90 grid places lost");
  });

  it("says both cars are within it when none is past", () => {
    const within = withUsed(ALLOCATION_HAMILTON, [1, 1, 1, 1, 1, 1, 1]);
    expect(carAllocationsTitle([within, within])).toBe("Both cars are within the allocation");
    expect(carAllocationsTitle([within, within, within])).toBe("All 3 cars are within the allocation");
  });

  it("speaks of the one car by its number", () => {
    expect(carAllocationsTitle([ALLOCATION_ANTONELLI])).toBe(
      "Car #12 is past the allocation on 3 elements: 30 grid places lost",
    );
    expect(carAllocationsTitle([withUsed(ALLOCATION_ANTONELLI, [5, 3, 3, 2, 3, 3, 6])])).toBe(
      "Car #12 is past the allocation on 1 element",
    );
    expect(carAllocationsTitle([ALLOCATION_HAMILTON])).toBe("Car #44 has used its full allocation of every element");
    expect(carAllocationsTitle([withUsed(ALLOCATION_HAMILTON, [2, 2, 2, 2, 2, 2, 2])])).toBe(
      "Car #44 is within the allocation on every element",
    );
  });

  it("does not call a car with no allowances at all fully used", () => {
    const open = {
      ...ALLOCATION_HAMILTON,
      elements: ALLOCATION_HAMILTON.elements.map((element) => ({ ...element, allowance: null })),
    };
    expect(carAllocationsTitle([open])).toBe("Car #44 is within the allocation on every element");
  });
});

describe("carAllocationsSub", () => {
  it("says what the figures count and through which round", () => {
    expect(carAllocationsSub([ALLOCATION_ANTONELLI], ALLOCATION_RESPONSE.as_of)).toBe(
      "Counted from the FIA's documents through round 19",
    );
  });

  it("says there are no grid penalties first, and leaves the round out when there is none", () => {
    expect(carAllocationsSub([ALLOCATION_HAMILTON], ALLOCATION_RESPONSE.as_of)).toBe(
      "No grid penalties · Counted from the FIA's documents through round 19",
    );
    expect(carAllocationsSub([ALLOCATION_HAMILTON], null)).toBe("No grid penalties · Counted from the FIA's documents");
    expect(carAllocationsSub([ALLOCATION_ANTONELLI], undefined)).toBe("Counted from the FIA's documents");
  });

  it("does not claim no penalties when a car starts from the pit lane or the back", () => {
    const pit = { ...ALLOCATION_HAMILTON, penalties: { ...ALLOCATION_HAMILTON.penalties, pit_lane_starts: 1 } };
    const back = { ...ALLOCATION_HAMILTON, penalties: { ...ALLOCATION_HAMILTON.penalties, back_of_grid: 1 } };
    expect(carAllocationsSub([pit], null)).toBe("Counted from the FIA's documents");
    expect(carAllocationsSub([back], null)).toBe("Counted from the FIA's documents");
  });
});

describe("pipsFor", () => {
  const element = (over: Partial<ElementUsage>): ElementUsage => ({
    code: "ICE",
    allowance: 4,
    used: 3,
    over_by: 0,
    parts: [],
    ...over,
  });

  it("fills what was used and leaves the rest empty", () => {
    expect(pipsFor(element({}))).toEqual({ used: 3, empty: 1, beyond: 0, label: "3 of 4 used", over: false });
  });

  it("puts what is past the allocation after the used ones", () => {
    expect(pipsFor(element({ used: 5, over_by: 1 }))).toEqual({
      used: 4,
      empty: 0,
      beyond: 1,
      label: "5 of 4 used, 1 beyond the allocation",
      over: true,
    });
  });

  it("shows only used pips when there is no allowance", () => {
    expect(pipsFor(element({ allowance: null, used: 2 }))).toEqual({
      used: 2,
      empty: 0,
      beyond: 0,
      label: "2 used",
      over: false,
    });
  });
});

describe("gridPlacesCell", () => {
  const totals = ALLOCATION_ANTONELLI.penalties;

  it("gives the places lost", () => {
    expect(gridPlacesCell(totals)).toEqual({ places: 30, extras: [] });
  });

  it("gives no places as null, and adds pit-lane and back-of-grid starts", () => {
    expect(gridPlacesCell({ ...totals, grid_places: 0 })).toEqual({ places: null, extras: [] });
    expect(gridPlacesCell({ ...totals, pit_lane_starts: 2, back_of_grid: 1 })).toEqual({
      places: 30,
      extras: ["+ 2 pit lane", "+ 1 back of grid"],
    });
  });

  it("labels a ruling still to come, and a past-allocation weekend with none found", () => {
    expect(gridPlacesCell({ ...totals, pending: 1, not_found: 1 }).extras).toEqual([
      "ruling pending",
      "no ruling found",
    ]);
    expect(gridPlacesCell({ ...totals, pending: 2, not_found: 2 }).extras).toEqual([
      "2 rulings pending",
      "2× no ruling found",
    ]);
  });
});

describe("carFooterLink", () => {
  it("links a team to every car on the Power Units page", () => {
    expect(carFooterLink([ALLOCATION_ANTONELLI], 22, MERCEDES)).toEqual({
      href: "/race-control/power-units",
      label: "All 22 cars and every FIA document →",
    });
  });

  it("links a driver's one car to its own page, and several to the whole page", () => {
    const scope: CarScope = { kind: "driver", driverId: "lewis-hamilton", lastName: "Hamilton" };
    expect(carFooterLink([ALLOCATION_HAMILTON], 22, scope)).toEqual({
      href: "/race-control/power-units/44",
      label: "Car #44 in full: every part and FIA document →",
    });
    expect(carFooterLink([ALLOCATION_HAMILTON, ALLOCATION_RUSSELL], 22, scope).label).toBe(
      "All 22 cars and every FIA document →",
    );
  });
});
