/**
 * The "Power units" card on the Team and Driver pages, as pure functions of the
 * power-units payload: which cars a page shows, the computed title and sub,
 * how many pips an element draws, and the footer link.
 *
 * The allocation belongs to the car and cars are shared, so every sentence is
 * in car terms ("Car #12 …"), never "{driver} has used …".
 */
import {
  carHref,
  elementsOver,
  totalOverBy,
  type DocumentRef,
  type ElementUsage,
  type PenaltyTotals,
  type PowerUnitCar,
} from "../power-units/powerUnitsModel";

export type CarScope = { kind: "team"; teamId: string } | { kind: "driver"; driverId: string; lastName: string };

const POWER_UNITS_HREF = "/race-control/power-units";

/** The cars the page is about, by car number: a team's, or every car the driver raced. */
export function pickCars(cars: readonly PowerUnitCar[], scope: CarScope): PowerUnitCar[] {
  const mine =
    scope.kind === "team"
      ? cars.filter((car) => car.team_id === scope.teamId)
      : cars.filter((car) => car.drivers.some((stint) => stint.id === scope.driverId));
  return [...mine].sort((a, b) => a.car_number - b.car_number);
}

function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

function lostSuffix(cars: readonly PowerUnitCar[]): string {
  const places = cars.reduce((sum, car) => sum + car.penalties.grid_places, 0);
  return places > 0 ? `: ${plural(places, "grid place")} lost` : "";
}

type Limited = ElementUsage & { allowance: number };

function usedFullAllocation(car: PowerUnitCar): boolean {
  const limited = car.elements.filter((element): element is Limited => element.allowance !== null);
  return limited.length > 0 && limited.every((element) => element.used >= element.allowance);
}

function soleCarTitle(car: PowerUnitCar): string {
  if (totalOverBy(car) > 0)
    return `Car #${car.car_number} is past the allocation on ${plural(elementsOver(car), "element")}`;
  if (usedFullAllocation(car)) return `Car #${car.car_number} has used its full allocation of every element`;
  return `Car #${car.car_number} is within the allocation on every element`;
}

function soleCar(cars: readonly PowerUnitCar[]): PowerUnitCar | undefined {
  return cars.length === 1 ? cars[0] : undefined;
}

function fleetTitle(cars: readonly PowerUnitCar[]): string {
  const count = cars.length;
  const over = cars.filter((car) => totalOverBy(car) > 0).length;
  const all = count === 2 ? "Both cars" : `All ${count} cars`;
  if (over === count) return `${all} are past the allocation`;
  if (over > 0) return `${over} of ${count} cars are past the allocation`;
  return `${all} are within the allocation`;
}

/** The card's finding, computed from the cars it lists (at least one). */
export function carAllocationsTitle(cars: readonly PowerUnitCar[]): string {
  const sole = soleCar(cars);
  return `${sole ? soleCarTitle(sole) : fleetTitle(cars)}${lostSuffix(cars)}`;
}

function hasPenalties(car: PowerUnitCar): boolean {
  const { grid_places, pit_lane_starts, back_of_grid } = car.penalties;
  return grid_places > 0 || pit_lane_starts > 0 || back_of_grid > 0;
}

/** What the figures count, and how far the documents reach. */
export function carAllocationsSub(
  cars: readonly PowerUnitCar[],
  asOf: (DocumentRef & { round: number }) | null | undefined,
): string {
  const counted = `Counted from the FIA's documents${asOf ? ` through round ${asOf.round}` : ""}`;
  return cars.some(hasPenalties) ? counted : `No grid penalties · ${counted}`;
}

export interface Pips {
  /** Filled pips within the allocation. */
  used: number;
  /** Empty pips: the allocation still to use. */
  empty: number;
  /** Filled red pips past the allocation. */
  beyond: number;
  label: string;
  over: boolean;
}

/** One element's pips and the sentence that stands for them. */
export function pipsFor(element: ElementUsage): Pips {
  if (element.allowance === null) {
    return { used: element.used, empty: 0, beyond: 0, label: `${element.used} used`, over: false };
  }
  const beyond = element.over_by;
  const label = `${element.used} of ${element.allowance} used${beyond > 0 ? `, ${beyond} beyond the allocation` : ""}`;
  return {
    used: Math.min(element.used, element.allowance),
    empty: Math.max(element.allowance - element.used, 0),
    beyond,
    label,
    over: beyond > 0,
  };
}

/** The grid-places cell: the places lost (null for none) and any pit-lane or back-of-grid starts. */
export function gridPlacesCell(totals: PenaltyTotals): { places: number | null; extras: string[] } {
  const extras = [
    totals.pit_lane_starts > 0 ? `+ ${totals.pit_lane_starts} pit lane` : null,
    totals.back_of_grid > 0 ? `+ ${totals.back_of_grid} back of grid` : null,
  ].filter((text) => text !== null);
  return { places: totals.grid_places > 0 ? totals.grid_places : null, extras };
}

/** The link under the table: a driver's one car in full, or every car on the Power Units page. */
export function carFooterLink(
  cars: readonly PowerUnitCar[],
  allCars: number,
  scope: CarScope,
): { href: string; label: string } {
  const sole = scope.kind === "driver" ? soleCar(cars) : undefined;
  if (sole) return { href: carHref(sole), label: `Car #${sole.car_number} in full: every part and FIA document →` };
  return { href: POWER_UNITS_HREF, label: `All ${allCars} cars and every FIA document →` };
}
