/**
 * The Power Units season page as pure functions of the power-units payload
 * and the championship table: the hero, the KPI row, the car order, the
 * grid-place ranking, the shared-seat story and the source note.
 */
import {
  formatUtc,
  outcomeLabel,
  penaltyLog,
  regularStint,
  roundRuns,
  roundsByNumber,
  seasonTotals,
  type DriverRef,
  type DriverStint,
  type PowerUnitCar,
  type PowerUnitsResponse,
} from "./powerUnitsModel";

import type { TeamsResponse } from "../standings/teamsModel";

const ENGINE = "ICE";

export function plural(count: number): string {
  return count === 1 ? "" : "s";
}

function sum(cars: readonly PowerUnitCar[], pick: (car: PowerUnitCar) => number): number {
  return cars.reduce((total, car) => total + pick(car), 0);
}

function carsOverOnEngines(data: PowerUnitsResponse): number {
  return data.cars.filter((car) => car.elements.some((item) => item.code === ENGINE && item.over_by > 0)).length;
}

export interface HeroModel {
  eyebrow: string;
  title: string;
}

/** The eyebrow says how far the FIA documents reach; the title says whether any engine is over. */
export function heroModel(data: PowerUnitsResponse): HeroModel {
  const asOf = data.as_of;
  let eyebrow = `Power units · ${data.year}`;
  if (asOf) {
    const round = roundsByNumber(data.rounds).get(asOf.round)?.name ?? `round ${asOf.round}`;
    eyebrow += ` · after round ${asOf.round} · latest FIA document: ${round}${asOf.number ? ` doc ${asOf.number}` : ""}`;
  }
  return {
    eyebrow,
    title: carsOverOnEngines(data) > 0 ? "Engines over the limit" : "Every engine within the allocation",
  };
}

export interface Kpi {
  label: string;
  value: string;
  unit?: string;
  sub: string;
}

/** What the lead tile adds when a weekend's ruling is still to come, or was not found. */
export function rulingSuffix(pending: number, notFound: number): string {
  let suffix = "";
  if (pending > 0) suffix += ` · ${pending} weekend${pending === 1 ? "'s ruling" : "s' rulings"} still pending`;
  if (notFound > 0) suffix += ` · ${notFound} weekend${plural(notFound)} past the allocation with no ruling found`;
  return suffix;
}

function gridPlacesSub(pending: number, notFound: number): string {
  return `by power-unit penalties this season${rulingSuffix(pending, notFound)}`;
}

/** The three season figures: places imposed, cars over on engines, pit-lane starts. */
export function kpis(data: PowerUnitsResponse): [Kpi, Kpi, Kpi] {
  const totals = seasonTotals(data.cars);
  const backOfGrid = sum(data.cars, (car) => car.penalties.back_of_grid);
  const allowance = (data.elements ?? []).find((item) => item.code === ENGINE)?.allowance ?? null;
  return [
    {
      label: "Grid places imposed",
      value: String(totals.gridPlaces),
      sub: gridPlacesSub(
        totals.pending,
        sum(data.cars, (car) => car.penalties.not_found),
      ),
    },
    {
      label: "Over on engines",
      value: String(carsOverOnEngines(data)),
      unit: `of ${data.cars.length}`,
      sub: allowance === null ? "cars past the engine allocation" : `cars past the ${allowance}-engine allocation`,
    },
    {
      label: "Pit-lane starts",
      value: String(totals.pitLaneStarts),
      sub: `from power-unit changes${backOfGrid > 0 ? ` · plus ${backOfGrid} from the back of the grid` : ""}`,
    },
  ];
}

export interface LatestPenalty {
  value: string;
  driver: DriverRef;
  detail: string;
}

/** The newest stewards' decision of the season, or null when there is none. */
export function latestPenalty(data: PowerUnitsResponse): LatestPenalty | null {
  const entry = penaltyLog(data.cars)[0];
  if (!entry) return null;
  const { car, event, decision } = entry;
  const round = roundsByNumber(data.rounds).get(event.round)?.name ?? `round ${event.round}`;
  const codes = decision.elements.map((element) => element.code).join(", ");
  return {
    value: decision.outcome === "grid_drop" ? `−${decision.places ?? 0}` : outcomeLabel(decision),
    driver: event.driver ?? car.driver,
    detail: `${round} · ${codes}${decision.number ? ` (FIA doc ${decision.number})` : ""}`,
  };
}

function bestPosition(car: PowerUnitCar, teams: TeamsResponse): number {
  const codes = new Set(car.drivers.map((stint) => stint.code));
  const positions = teams.teams
    .flatMap((team) => team.drivers)
    .filter((driver) => driver.code !== undefined && codes.has(driver.code))
    .map((driver) => driver.position);
  return positions.length > 0 ? Math.min(...positions) : Number.MAX_SAFE_INTEGER;
}

function teamPosition(car: PowerUnitCar, teams: TeamsResponse): number {
  return teams.teams.find((team) => team.slug === car.team_id)?.position ?? Number.MAX_SAFE_INTEGER;
}

/** The cars in constructors' championship order, or by car number when the table is missing. */
export function standingsOrder(
  cars: readonly PowerUnitCar[],
  teams: TeamsResponse | undefined,
): { cars: PowerUnitCar[]; byStandings: boolean } {
  if (!teams || teams.teams.length === 0) {
    return { cars: [...cars].sort((a, b) => a.car_number - b.car_number), byStandings: false };
  }
  const ordered = [...cars].sort(
    (a, b) =>
      teamPosition(a, teams) - teamPosition(b, teams) ||
      bestPosition(a, teams) - bestPosition(b, teams) ||
      a.car_number - b.car_number,
  );
  return { cars: ordered, byStandings: true };
}

/** Cars that lost grid places, most first; ties by car number. */
export function gridPlaceRanking(cars: readonly PowerUnitCar[]): PowerUnitCar[] {
  return cars
    .filter((car) => car.penalties.grid_places > 0)
    .sort((a, b) => b.penalties.grid_places - a.penalties.grid_places || a.car_number - b.car_number);
}

/** ", " between items and " and " before the last. */
export function listSeparator(index: number, count: number): string {
  if (index === 0) return "";
  return index === count - 1 ? " and " : ", ";
}

/** The ranking's finding, never naming one car for a tie. `ranked` is non-empty and ordered. */
export function rankingTitle(ranked: readonly PowerUnitCar[]): string {
  const top = ranked.filter((car) => car.penalties.grid_places === ranked[0].penalties.grid_places);
  const names = top.map((car, index) => `${listSeparator(index, top.length)}#${car.car_number}`).join("");
  return top.length === 1
    ? `Car ${names} has the most grid-place penalties`
    : `Cars ${names} share the most grid-place penalties`;
}

export interface SharedSeatStory {
  car: PowerUnitCar;
  regular: DriverStint;
  others: DriverStint[];
  except: string;
}

/** The shared car with the most grid places imposed: who raced it, and in which rounds the others did. */
export function sharedSeatStory(cars: readonly PowerUnitCar[]): SharedSeatStory | null {
  const [car] = cars
    .filter((candidate) => candidate.drivers.length > 1)
    .sort((a, b) => b.penalties.grid_places - a.penalties.grid_places || a.car_number - b.car_number);
  if (!car) return null;
  const regular = regularStint(car);
  const others = car.drivers.filter((stint) => stint !== regular);
  return { car, regular, others, except: roundRuns(others.flatMap((other) => other.rounds)) };
}

export interface SourceNote {
  text: string;
  url?: string;
}

function collectionLabel(data: PowerUnitsResponse): string | null {
  const freshness = data.freshness;
  if (!freshness) return null;
  if (!freshness.checked_at) return "Not checked yet";
  if (freshness.outcome === "aborted") return "Last check failed";
  if (freshness.outcome === "write_failed") return "Last check not saved";
  if (freshness.stale) return "Collection overdue";
  if (freshness.outcome === "document_failures") return "Some documents unread";
  return null;
}

/** What the reader should know before trusting the figures; empty when nothing is amiss. */
export function sourceNotes(data: PowerUnitsResponse): SourceNote[] {
  const label = collectionLabel(data);
  const checkedAt = data.freshness?.checked_at;
  const error = data.freshness?.error ? ` · ${data.freshness.error}` : "";
  const collection = label
    ? [{ text: `${checkedAt ? `${label} · last checked ${formatUtc(checkedAt)}` : label}${error}` }]
    : [];
  const unread = data.unread.map((item) => ({
    text: `${item.event}: ${item.title} could not be read (${item.reason}); counts that depend on it may be incomplete`,
    url: item.url,
  }));
  const withdrawn = (data.withdrawn ?? []).map((item) => ({
    text: `${item.title}: withdrawn or replaced by the FIA, not counted (${item.reason})`,
    url: item.url,
  }));
  const warnings = data.warnings.map((text) => ({ text }));
  const allowances = (data.elements ?? []).flatMap((item): SourceNote[] => {
    if (item.allowance_source === null) return [{ text: `${item.code}: allowance not stated by the FIA yet` }];
    if (item.allowance_source.kind !== "manual") return [];
    const note = item.allowance_source.note;
    return [{ text: `${item.code}: allowance pinned by hand${note ? ` (${note})` : ""}` }];
  });
  return [...collection, ...unread, ...withdrawn, ...warnings, ...allowances];
}
