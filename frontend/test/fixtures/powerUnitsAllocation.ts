import type {
  DriverStint,
  ElementInfo,
  PenaltyTotals,
  PowerUnitCar,
  PowerUnitsResponse,
} from "@/app/race-control/power-units/powerUnitsModel";

/**
 * HAND-BUILT, not captured: a typed `PowerUnitsResponse` that mirrors the
 * rows of the team and driver pages' "Power units" section: Mercedes #12 and #63 past the allocation with 30 and 60
 * grid places imposed, Ferrari #44 at its full allocation of every element.
 * It stands in for the endpoint in unit and e2e tests; nothing here is f1db or
 * FIA data.
 */

const ALLOWANCES: ReadonlyArray<readonly [string, number]> = [
  ["ICE", 4],
  ["TC", 4],
  ["EXH", 4],
  ["MGU-K", 3],
  ["ES", 3],
  ["PU-CE", 3],
  ["PU-ANC", 6],
];

const ELEMENTS: ElementInfo[] = ALLOWANCES.map(([code, allowance]) => ({
  code,
  name: code,
  allowance,
  allowance_source: null,
}));

const NO_PENALTIES: PenaltyTotals = {
  grid_places: 0,
  pit_lane_starts: 0,
  back_of_grid: 0,
  decisions: 0,
  pending: 0,
  not_found: 0,
};

interface CarSpec {
  number: number;
  team: string;
  teamId: string;
  driver: { id: string; name: string; code: string };
  /** Elements used, in the order of `ALLOWANCES`. */
  used: number[];
  gridPlaces?: number;
}

function car({ number, team, teamId, driver, used, gridPlaces = 0 }: CarSpec): PowerUnitCar {
  const rounds = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10];
  const stint: DriverStint = { ...driver, car_number: number, rounds };
  return {
    seat_id: `${teamId}-${number}`,
    car_number: number,
    team,
    team_id: teamId,
    driver: { ...driver, car_number: number },
    drivers: [stint],
    elements: ALLOWANCES.map(([code, allowance], index) => {
      const count = used[index] ?? 0;
      return { code, allowance, used: count, over_by: Math.max(count - allowance, 0), parts: [] };
    }),
    events: [],
    penalties: { ...NO_PENALTIES, grid_places: gridPlaces },
    warnings: [],
  };
}

export const ALLOCATION_ANTONELLI = car({
  number: 12,
  team: "Mercedes",
  teamId: "mercedes",
  driver: { id: "kimi-antonelli", name: "Kimi Antonelli", code: "ANT" },
  used: [5, 3, 3, 2, 4, 4, 6],
  gridPlaces: 30,
});

export const ALLOCATION_RUSSELL = car({
  number: 63,
  team: "Mercedes",
  teamId: "mercedes",
  driver: { id: "george-russell", name: "George Russell", code: "RUS" },
  used: [5, 5, 5, 4, 4, 4, 5],
  gridPlaces: 60,
});

export const ALLOCATION_HAMILTON = car({
  number: 44,
  team: "Ferrari",
  teamId: "ferrari",
  driver: { id: "lewis-hamilton", name: "Lewis Hamilton", code: "HAM" },
  used: [4, 4, 4, 3, 3, 3, 6],
});

export const ALLOCATION_RESPONSE: PowerUnitsResponse = {
  year: 2026,
  available: true,
  reason: null,
  as_of: {
    round: 19,
    title: "Doc 99",
    url: "https://example.test/doc-99",
    published: "2026-11-01T12:00:00Z",
    number: 99,
  },
  elements: ELEMENTS,
  cars: [ALLOCATION_ANTONELLI, ALLOCATION_RUSSELL, ALLOCATION_HAMILTON],
  unread: [],
  warnings: [],
};
