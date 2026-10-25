/**
 * Shapes of `GET /api/race-control/power-units/{year}`, and the pure helpers the
 * power-unit screens share.
 *
 * Everything here is a function of the payload — no fetching, no React — so
 * both server and client components can use it.
 *
 * Usage is keyed by car, not by driver, because that is how the FIA counts it
 * (Article B8.2.7): a stand-in uses the allocation of the car they drive. Each
 * car still carries the drivers who raced it, so the driver sits beside the
 * number everywhere the number appears.
 */

export type PartSource = "report" | "derived";
export type PenaltyStatus = "none" | "decided" | "pending" | "not_found";
export type GridStatus = "official" | "pending" | "not_listed";
export type Outcome = "grid_drop" | "pit_lane" | "back_of_grid" | "other";

export interface DocumentRef {
  title: string;
  url: string;
  published: string;
  number: number | null;
}

export interface Part {
  code: string;
  number: number;
  /** The round the unit was introduced at, when the documents pin it down. */
  round: number | null;
  /** The first and last round it could have arrived at, when they do not. */
  window: [number, number] | null;
  source: PartSource;
  beyond_allowance: boolean;
  /** The round whose FIA usage report stopped counting this unit, if one did. */
  not_counted_from: number | null;
}

export interface ElementUsage {
  code: string;
  allowance: number | null;
  used: number;
  over_by: number;
  parts: Part[];
}

export interface DriverRef {
  id: string;
  name: string;
  code: string;
  car_number: number;
}

export interface DriverStint extends DriverRef {
  rounds: number[];
}

export interface Decision extends DocumentRef {
  session: string | null;
  outcome: Outcome;
  places: number | null;
  /** Places the elements would have cost, when a pit-lane start superseded them. */
  nominal_places: number | null;
  summary: string;
  elements: Array<{ code: string; number: number }>;
}

export interface GridOutcome {
  status: GridStatus;
  qualified?: number | null;
  started?: number | null;
  pit_lane?: boolean;
  back_of_grid?: boolean;
  penalty_positions?: number | null;
}

export interface CarEvent {
  round: number;
  /** `null` only for a round f1db had not published when the car was seated. */
  driver: DriverRef | null;
  stand_in: boolean;
  new_parts: Part[];
  decisions: Decision[];
  penalty_status: PenaltyStatus;
  grid: GridOutcome;
  sources: DocumentRef[];
}

export interface PenaltyTotals {
  grid_places: number;
  pit_lane_starts: number;
  back_of_grid: number;
  decisions: number;
  pending: number;
  not_found: number;
}

export interface PowerUnitCar {
  seat_id: string;
  car_number: number;
  team: string;
  team_id: string;
  driver: DriverRef;
  drivers: DriverStint[];
  elements: ElementUsage[];
  events: CarEvent[];
  penalties: PenaltyTotals;
  warnings: string[];
}

/** Where an allowance came from: the FIA report that stated it, or a hand-pinned value. */
export interface AllowanceSource {
  kind: "fia_report" | "manual";
  title: string | null;
  url: string | null;
  stated_on: string | null;
  updated_at: string;
  note: string | null;
}

export interface ElementInfo {
  code: string;
  name: string;
  allowance: number | null;
  allowance_source: AllowanceSource | null;
}

/** When the collection job last read fia.com, and how it went. */
export interface Freshness {
  checked_at: string | null;
  changed_at: string | null;
  outcome: string | null;
  error: string | null;
  stale: boolean;
}

/** A document the FIA withdrew, rescinded or replaced — kept, but not counted. */
export interface WithdrawnDocument {
  title: string;
  url: string;
  reason: string;
}

export interface RoundInfo {
  round: number;
  name: string;
  code: string;
  date: string;
  has_documents: boolean;
}

export interface UnreadDocument {
  title: string;
  url: string;
  event: string;
  reason: string;
}

export interface PowerUnitsResponse {
  year: number;
  available: boolean;
  reason?: string | null;
  as_of?: (DocumentRef & { round: number }) | null;
  freshness?: Freshness | null;
  elements?: ElementInfo[];
  rounds?: RoundInfo[];
  cars: PowerUnitCar[];
  unread: UnreadDocument[];
  withdrawn?: WithdrawnDocument[];
  warnings: string[];
  notes?: string[];
  error?: string;
  error_id?: string;
}

/** F1 red for anything beyond the allowance — the one colour that means "penalty". */
export const OVER_COLOR = "#E10600";
/** Amber for what is not known yet: a ruling still to come, or one not found. */
export const PENDING_COLOR = "#F5C542";
/** Muted ink for units within the allowance on a neutral surface. */
export const NEUTRAL_INK = "#7F8797";

const UTC_STAMP = new Intl.DateTimeFormat("en-GB", {
  timeZone: "UTC",
  day: "2-digit",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
});

/**
 * "24 Oct 2026, 08:17 UTC". Always UTC, so the server render and the browser
 * agree on the text and hydration never sees two different times.
 */
export function formatUtc(iso: string | null | undefined): string {
  if (!iso) return "never";
  const moment = new Date(iso);
  return Number.isNaN(moment.getTime()) ? iso : `${UTC_STAMP.format(moment)} UTC`;
}

export function powerUnitsUrl(apiBase: string, year: number): string {
  return `${apiBase}/api/race-control/power-units/${year}`;
}

export function roundsByNumber(rounds: RoundInfo[] | undefined): Map<number, RoundInfo> {
  return new Map((rounds ?? []).map((item) => [item.round, item]));
}

/** Short label for where a unit arrived: "BEL", "R1–16", or "?". */
export function partShortWhere(part: Part, rounds: Map<number, RoundInfo>): string {
  if (part.round !== null) {
    return rounds.get(part.round)?.code ?? `R${part.round}`;
  }
  if (part.window) {
    return `R${part.window[0]}–${part.window[1]}`;
  }
  return "?";
}

/** Sentence-length version of {@link partShortWhere}, for tooltips. */
export function partWhere(part: Part, rounds: Map<number, RoundInfo>): string {
  if (part.round !== null) {
    const name = rounds.get(part.round)?.name ?? `round ${part.round}`;
    const how = part.source === "report" ? "named in an FIA document" : "the only round between two FIA usage reports";
    return `Introduced at the ${name} (${how})`;
  }
  if (part.window) {
    return `Introduced between round ${part.window[0]} and round ${part.window[1]} — the FIA documents collected do not pin the round down`;
  }
  return "The FIA documents collected do not show where this unit was introduced";
}

export function totalOverBy(car: PowerUnitCar): number {
  return car.elements.reduce((sum, item) => sum + item.over_by, 0);
}

export function elementsOver(car: PowerUnitCar): number {
  return car.elements.filter((item) => item.over_by > 0).length;
}

/** The car a URL segment names: its current number, or any number it raced under. */
export function findCar(cars: PowerUnitCar[], segment: string): PowerUnitCar | undefined {
  const wanted = Number.parseInt(segment, 10);
  if (Number.isNaN(wanted)) {
    return cars.find((car) => car.seat_id === segment);
  }
  return (
    cars.find((car) => car.car_number === wanted) ??
    cars.find((car) => car.drivers.some((d) => d.car_number === wanted))
  );
}

export function carHref(car: PowerUnitCar): string {
  return `/race-control/power-units/${car.car_number}`;
}

export function outcomeLabel(decision: Decision): string {
  switch (decision.outcome) {
    case "grid_drop":
      return `−${decision.places ?? 0} grid places`;
    case "pit_lane":
      return "Pit-lane start";
    case "back_of_grid":
      return "Back of the grid";
    default:
      return decision.summary;
  }
}

/** The grid outcome in one line, saying plainly when it is not known yet. */
export function gridLabel(grid: GridOutcome): string {
  if (grid.status === "pending") {
    return "Grid sheet not published yet";
  }
  if (grid.status === "not_listed") {
    return "Not on the published grid sheet";
  }
  const start = grid.pit_lane ? "started from the pit lane" : `started P${grid.started ?? "—"}`;
  // A pit-lane starter can have no qualifying position on the sheet.
  return grid.qualified
    ? `Qualified P${grid.qualified} → ${start}`
    : `${start.charAt(0).toUpperCase()}${start.slice(1)}`;
}

const SHORT_DAY = new Intl.DateTimeFormat("en-GB", { timeZone: "UTC", day: "numeric", month: "short" });

/** "25 Oct" for an ISO date, UTC so server and browser agree. */
export function shortDay(isoDate: string | null | undefined): string {
  if (!isoDate) return "";
  const moment = new Date(`${isoDate}T00:00:00Z`);
  return Number.isNaN(moment.getTime()) ? isoDate : SHORT_DAY.format(moment);
}

export const STATUS_LABELS: Record<PenaltyStatus, string> = {
  none: "Within allowance",
  decided: "Stewards decided",
  pending: "Decision pending",
  not_found: "No decision found",
};

export function statusColor(status: PenaltyStatus): string {
  if (status === "decided") return OVER_COLOR;
  if (status === "pending" || status === "not_found") return PENDING_COLOR;
  return "#00FF78";
}

export interface LogEntry {
  car: PowerUnitCar;
  event: CarEvent;
  decision: Decision;
}

/** Every stewards' decision of the season, newest first. */
export function penaltyLog(cars: PowerUnitCar[]): LogEntry[] {
  const entries = cars.flatMap((car) =>
    car.events.flatMap((event) => event.decisions.map((decision) => ({ car, event, decision }))),
  );
  return entries.sort((a, b) => b.event.round - a.event.round || (b.decision.number ?? 0) - (a.decision.number ?? 0));
}

export interface SeasonTotals {
  carsOver: number;
  gridPlaces: number;
  pitLaneStarts: number;
  pending: number;
}

export function seasonTotals(cars: PowerUnitCar[]): SeasonTotals {
  return {
    carsOver: cars.filter((car) => totalOverBy(car) > 0).length,
    gridPlaces: cars.reduce((sum, car) => sum + car.penalties.grid_places, 0),
    pitLaneStarts: cars.reduce((sum, car) => sum + car.penalties.pit_lane_starts, 0),
    pending: cars.reduce((sum, car) => sum + car.penalties.pending, 0),
  };
}

/** "R12–R14" style list of the rounds someone raced a car, collapsing runs. */
export function roundRuns(rounds: number[]): string {
  const sorted = [...rounds].sort((a, b) => a - b);
  const runs: Array<[number, number]> = [];
  for (const round of sorted) {
    const last = runs.at(-1);
    if (last && round === last[1] + 1) {
      last[1] = round;
    } else {
      runs.push([round, round]);
    }
  }
  return runs.map(([start, end]) => (start === end ? `R${start}` : `R${start}–R${end}`)).join(", ");
}
