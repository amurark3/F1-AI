import { describe, expect, it } from "vitest";

import { POWER_UNITS_2026 } from "@/test/fixtures";

import {
  carHref,
  elementsOver,
  findCar,
  formatUtc,
  gridLabel,
  outcomeLabel,
  partShortWhere,
  partWhere,
  penaltyLog,
  powerUnitsUrl,
  regularStint,
  roundRuns,
  roundsByNumber,
  seasonTotals,
  shortDay,
  totalOverBy,
  type Part,
} from "./powerUnitsModel";

const CARS = POWER_UNITS_2026.cars;
const ROUNDS = roundsByNumber(POWER_UNITS_2026.rounds);
const car = (number: number) => CARS.find((item) => item.car_number === number)!;

const PART: Part = {
  code: "ICE",
  number: 2,
  round: 2,
  window: null,
  source: "report",
  beyond_allowance: false,
  not_counted_from: null,
};

describe("formatUtc", () => {
  it("prints UTC, 'never' for none, and the input back when it is not a date", () => {
    expect(formatUtc("2026-11-18T14:36:00Z")).toBe("18 Nov 2026, 14:36 UTC");
    expect(formatUtc(null)).toBe("never");
    expect(formatUtc("not a date")).toBe("not a date");
  });
});

describe("urls and lookups", () => {
  it("builds the endpoint", () => {
    expect(powerUnitsUrl("https://api", 2026)).toBe("https://api/api/race-control/power-units/2026");
  });

  it("indexes rounds, even when there are none", () => {
    expect(ROUNDS.get(17)?.name).toBe("Singapore GP");
    expect(roundsByNumber(undefined).size).toBe(0);
  });

  it("finds a car by its number, a number it raced under, or its seat id", () => {
    expect(findCar(CARS, "6")?.car_number).toBe(6);
    expect(findCar(CARS, "22")?.car_number).toBe(30);
    expect(findCar(CARS, car(6).seat_id)?.car_number).toBe(6);
    expect(findCar(CARS, "99")).toBeUndefined();
    expect(carHref(car(6))).toBe("/race-control/power-units/6");
  });
});

describe("where a unit arrived", () => {
  it("is short and long for a named round, a window and neither", () => {
    expect(partShortWhere(PART, ROUNDS)).toBe("CHN");
    expect(partShortWhere({ ...PART, round: 99 }, ROUNDS)).toBe("R99");
    expect(partShortWhere({ ...PART, round: null, window: [3, 5] }, ROUNDS)).toBe("R3–5");
    expect(partShortWhere({ ...PART, round: null }, ROUNDS)).toBe("?");

    expect(partWhere(PART, ROUNDS)).toBe("Introduced at the Chinese GP (named in an FIA document)");
    expect(partWhere({ ...PART, source: "derived" }, ROUNDS)).toBe(
      "Introduced at the Chinese GP (the only round between two FIA usage reports)",
    );
    expect(partWhere({ ...PART, round: 99 }, ROUNDS)).toContain("round 99");
    expect(partWhere({ ...PART, round: null, window: [3, 5] }, ROUNDS)).toBe(
      "Introduced between round 3 and round 5 — the FIA documents collected do not pin the round down",
    );
    expect(partWhere({ ...PART, round: null }, ROUNDS)).toBe(
      "The FIA documents collected do not show where this unit was introduced",
    );
  });
});

describe("outcomeLabel and gridLabel", () => {
  const decision = car(6).events.find((event) => event.round === 17)!.decisions[0];

  it("names each outcome", () => {
    expect(outcomeLabel({ ...decision, outcome: "grid_drop", places: 30 })).toBe("−30 grid places");
    expect(outcomeLabel({ ...decision, outcome: "grid_drop", places: null })).toBe("−0 grid places");
    expect(outcomeLabel(decision)).toBe("Pit-lane start");
    expect(outcomeLabel({ ...decision, outcome: "back_of_grid" })).toBe("Back of the grid");
    expect(outcomeLabel({ ...decision, outcome: "other", summary: "Reprimand" })).toBe("Reprimand");
  });

  it("says the grid plainly, including when it is not known", () => {
    expect(gridLabel({ status: "pending" })).toBe("Grid sheet not published yet");
    expect(gridLabel({ status: "not_listed" })).toBe("Not on the published grid sheet");
    expect(gridLabel({ status: "official", qualified: 10, started: 21 })).toBe("Qualified P10 → started P21");
    expect(gridLabel({ status: "official", qualified: 14, pit_lane: true })).toBe(
      "Qualified P14 → started from the pit lane",
    );
    expect(gridLabel({ status: "official", pit_lane: true })).toBe("Started from the pit lane");
    expect(gridLabel({ status: "official", qualified: 5 })).toBe("Qualified P5 → started P—");
  });
});

describe("shortDay", () => {
  it("prints day and month in UTC, and degrades", () => {
    expect(shortDay("2026-10-11")).toBe("11 Oct");
    expect(shortDay(null)).toBe("");
    expect(shortDay("soon")).toBe("soon");
  });
});

describe("season figures", () => {
  it("sorts the stewards' decisions newest first", () => {
    const log = penaltyLog(CARS);
    expect(log[0].event.round).toBeGreaterThanOrEqual(log.at(-1)!.event.round);
  });

  it("totals the season", () => {
    expect(seasonTotals(CARS)).toMatchObject({ gridPlaces: 685, pitLaneStarts: 7 });
  });

  it("counts a car's elements over and units beyond", () => {
    expect(elementsOver(car(6))).toBe(7);
    expect(totalOverBy(car(6))).toBe(15);
    expect(totalOverBy(car(51))).toBe(0);
  });

  it("collapses a driver's rounds into runs", () => {
    expect(roundRuns([15, 1, 2, 3, 20, 16])).toBe("R1–R3, R15–R16, R20");
    expect(roundRuns([4])).toBe("R4");
  });

  it("names the driver who raced most, the first on a tie", () => {
    expect(regularStint(car(6)).code).toBe("HAD");
    const tied = structuredClone(car(6));
    tied.drivers[0].rounds = [1];
    tied.drivers[1].rounds = [2];
    expect(regularStint(tied).code).toBe(tied.drivers[0].code);
  });
});
