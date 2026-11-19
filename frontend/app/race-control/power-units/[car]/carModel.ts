/**
 * The Power Units car page as pure functions of the power-units payload: the
 * hero, the KPI row, the ledger, the season cells and the weekend log. Every
 * title and sentence the page prints is built here, from the payload.
 */
import {
  formatUtc,
  outcomeLabel,
  partWhere,
  regularStint,
  roundRuns,
  shortDay,
  totalOverBy,
  elementsOver,
  type CarEvent,
  type Decision,
  type DriverRef,
  type DriverStint,
  type ElementInfo,
  type ElementUsage,
  type Freshness,
  type Part,
  type PenaltyStatus,
  type PowerUnitCar,
  type PowerUnitsResponse,
  type RoundInfo,
} from "../powerUnitsModel";
import { listSeparator, plural, rulingSuffix, sourceNotes, type Kpi, type SourceNote } from "../seasonModel";

import type { StateTone } from "../../grand-prix/StateTag";

const WORDS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"];

/** A count in words up to ten ("no", "one" … "ten"), digits above. */
export function countWord(count: number, capital = false): string {
  const word = WORDS[count] ?? String(count);
  return capital ? `${word.charAt(0).toUpperCase()}${word.slice(1)}` : word;
}

/** 1st, 2nd, 3rd, 4th … 11th, 12th, 13th, 21st. */
export function ordinal(count: number): string {
  const teen = count % 100;
  if (teen >= 11 && teen <= 13) return `${count}th`;
  const suffix = { 1: "st", 2: "nd", 3: "rd" }[count % 10] ?? "th";
  return `${count}${suffix}`;
}

/**
 * Whether a driver drove the car without being its regular or its current
 * driver. The payload's own `stand_in` flag is not used: it compares with the
 * car's current driver, so a car that changed hands flags its long-time driver.
 */
export function isStandIn(car: PowerUnitCar, driver: DriverRef | null): boolean {
  return driver !== null && driver.id !== regularStint(car).id && driver.id !== car.driver.id;
}

export function heroMeta(car: PowerUnitCar): string {
  const base = `Every power-unit element fitted to car ${car.car_number} this season, where it arrived and what it cost.`;
  return car.drivers.length > 1
    ? `${base} Elements belong to the car, so the penalties follow the car, never the driver.`
    : base;
}

const ENGINE = "ICE";

export interface EngineFigure {
  value: string;
  unit: string;
  line: string;
}

/** The engine count and what it was fitted against; null when the car has no engine row. */
export function engineFigure(car: PowerUnitCar, cars: readonly PowerUnitCar[]): EngineFigure | null {
  const ice = car.elements.find((item) => item.code === ENGINE);
  if (!ice) return null;
  const unit = ice.used === 1 ? "engine" : "engines";
  if (ice.allowance === null) {
    return { value: String(ice.used), unit, line: "fitted; the FIA has not stated the allocation yet." };
  }
  const others = cars
    .filter((other) => other.seat_id !== car.seat_id)
    .flatMap((other) => other.elements.filter((item) => item.code === ENGINE).map((item) => item.used));
  const most = others.every((used) => used < ice.used) ? ", the most of any car this season" : "";
  return { value: String(ice.used), unit, line: `fitted against an allocation of ${ice.allowance}${most}.` };
}

export interface SeatModel {
  stint: DriverStint;
  standIn: boolean;
  first: { bold: string; rest: string };
  rulings: string;
}

function gridPlaces(decisions: readonly Decision[]): number {
  return decisions.reduce((sum, item) => sum + (item.outcome === "grid_drop" ? (item.places ?? 0) : 0), 0);
}

function rulingsAt(car: PowerUnitCar, stint: DriverStint): string {
  const decisions = car.events.filter((event) => event.driver?.id === stint.id).flatMap((event) => event.decisions);
  const places = gridPlaces(decisions);
  const pitLane = decisions.filter((item) => item.outcome === "pit_lane").length;
  const back = decisions.filter((item) => item.outcome === "back_of_grid").length;
  const parts = [
    places > 0 ? `−${places} grid places` : null,
    pitLane > 0 ? `${pitLane} pit-lane start${plural(pitLane)}` : null,
    back > 0 ? `${back} back-of-grid start${plural(back)}` : null,
  ].filter((part) => part !== null);
  return parts.length > 0 ? parts.join(", ") : "no ruling";
}

/** One row per driver who raced the car: his rounds, and what the stewards ruled at them. */
export function lineup(car: PowerUnitCar): SeatModel[] {
  return car.drivers.map((stint) => {
    const standIn = isStandIn(car, stint);
    const runs = roundRuns(stint.rounds);
    const first = standIn
      ? { bold: runs, rest: stint.car_number === car.car_number ? "" : " · under his own number" }
      : { bold: `${stint.rounds.length} round${plural(stint.rounds.length)}`, rest: ` · ${runs}` };
    return { stint, standIn, first, rulings: rulingsAt(car, stint) };
  });
}

function sortedEvents(car: PowerUnitCar): CarEvent[] {
  return [...car.events].sort((a, b) => a.round - b.round);
}

function decisionsOf(car: PowerUnitCar, outcome: Decision["outcome"]): Array<{ round: number; decision: Decision }> {
  return sortedEvents(car).flatMap((event) =>
    event.decisions.filter((item) => item.outcome === outcome).map((decision) => ({ round: event.round, decision })),
  );
}

function roundTag(round: number, rounds: Map<number, RoundInfo>): string {
  const name = rounds.get(round)?.name;
  return name ? `R${round} ${name}` : `R${round}`;
}

/** The four tiles under the hero. */
export function carKpis(car: PowerUnitCar, rounds: Map<number, RoundInfo>): [Kpi, Kpi, Kpi, Kpi] {
  const { penalties } = car;
  const drops = decisionsOf(car, "grid_drop").map(({ round, decision }) => `R${round} −${gridPlaces([decision])}`);
  const pitLane = decisionsOf(car, "pit_lane").map(({ round }) => ` · ${roundTag(round, rounds)}`);
  const back = penalties.back_of_grid > 0 ? ` · plus ${penalties.back_of_grid} from the back of the grid` : "";
  const over = elementsOver(car);
  const total = car.elements.length;
  let overSub = "elements past their allocation";
  if (over === 0) overSub = "every element within its allocation";
  else if (over === total) overSub = "every element past its allocation";
  const extra = car.elements
    .filter((item) => item.over_by > 0)
    .sort((a, b) => b.over_by - a.over_by)
    .map((item) => ` · ${item.code} ${item.over_by}`);
  return [
    {
      label: "Grid places imposed",
      value: String(penalties.grid_places),
      sub: `${drops.length > 0 ? drops.join(" · ") : "no grid drop"}${rulingSuffix(penalties.pending, penalties.not_found)}`,
    },
    {
      label: "Pit-lane starts",
      value: String(penalties.pit_lane_starts),
      sub: `ordered by power-unit rulings${pitLane.join("")}${back}`,
    },
    { label: "Elements over", value: String(over), unit: `of ${total}`, sub: overSub },
    {
      label: "Extra units",
      value: String(totalOverBy(car)),
      sub: `beyond the allocation${extra.join("")}`,
    },
  ];
}

/** The ledger's finding. */
export function ledgerTitle(car: PowerUnitCar): string {
  const total = car.elements.length;
  const over = elementsOver(car);
  if (over === 0) return "Every element within the allocation";
  if (over === total) return `All ${countWord(total)} elements past the allocation`;
  return `${countWord(over, true)} of ${countWord(total)} elements past the allocation`;
}

export interface LedgerRow {
  usage: ElementUsage;
  name: string;
  within: Part[];
  spares: number;
  beyond: Part[];
  notCounted: Part[];
}

/** One row per element: counted units split by the backend's `beyond_allowance`, spares, and those no longer counted. */
export function ledgerRows(car: PowerUnitCar, elements: readonly ElementInfo[]): LedgerRow[] {
  return car.elements.map((usage) => {
    const counted = usage.parts.filter((part) => part.not_counted_from === null);
    const within = counted.filter((part) => !part.beyond_allowance);
    return {
      usage,
      name: elements.find((item) => item.code === usage.code)?.name ?? usage.code,
      within,
      spares: usage.allowance === null ? 0 : Math.max(0, usage.allowance - within.length),
      beyond: counted.filter((part) => part.beyond_allowance),
      notCounted: usage.parts.filter((part) => part.not_counted_from !== null),
    };
  });
}

export function tileLabel(part: Part, rounds: Map<number, RoundInfo>): string {
  const side = part.beyond_allowance ? "beyond" : "within";
  const counted = part.not_counted_from === null ? "" : ", not counted";
  return `${part.code} unit ${part.number}, ${side} the allocation${counted}: ${partWhere(part, rounds)}`;
}

export interface PartKey {
  code: string;
  number: number;
}

/** The newest unit, beyond the allocation first. */
export function defaultPart(car: PowerUnitCar): PartKey | null {
  const parts = car.elements.flatMap((item) => item.parts);
  const first = [...parts].sort(
    (a, b) => (b.round ?? 0) - (a.round ?? 0) || Number(b.beyond_allowance) - Number(a.beyond_allowance),
  )[0];
  return first ? { code: first.code, number: first.number } : null;
}

export function inspectorHead(part: Part, usage: ElementUsage): string {
  const head = `${part.code} #${part.number}`;
  if (part.not_counted_from !== null) return `${head} · not counted`;
  if (usage.allowance === null) return `${head} · allowance not stated`;
  const beyond = part.number - usage.allowance;
  return beyond > 0
    ? `${head} · ${ordinal(beyond)} beyond the ${usage.allowance} allowed`
    : `${head} · within the ${usage.allowance} allowed`;
}

export function rulingFor(part: Part, events: readonly CarEvent[]): string {
  if (part.not_counted_from !== null) {
    return `The FIA's usage reports stopped counting this unit from round ${part.not_counted_from}, so it is not in the total.`;
  }
  const event = events.find((item) => item.round === part.round);
  const decision = event?.decisions.find((item) =>
    item.elements.some((element) => element.code === part.code && element.number === part.number),
  );
  if (decision) {
    return `Stewards: ${outcomeLabel(decision)}${decision.session ? `, first used in ${decision.session}` : ""}.`;
  }
  if (!part.beyond_allowance) return "No penalty: within the season's allocation.";
  if (part.round === null) {
    return "No stewards' decision can be matched to this unit: the documents collected do not pin its round down.";
  }
  if (event?.penalty_status === "pending") return "The stewards' decision for this weekend has not been published yet.";
  return "No stewards' decision naming this unit was found in the collected documents.";
}

function rulingCounts(car: PowerUnitCar): { total: number; parts: string } {
  const all = car.events.flatMap((event) => event.decisions);
  const counts: Array<[number, string]> = [
    [all.filter((item) => item.outcome === "grid_drop").length, "grid drop"],
    [all.filter((item) => item.outcome === "pit_lane").length, "pit-lane start"],
    [all.filter((item) => item.outcome === "back_of_grid").length, "back-of-grid start"],
    [all.filter((item) => item.outcome === "other").length, "other ruling"],
  ];
  const present = counts.filter(([count]) => count > 0);
  const parts = present
    .map(([count, noun], index) => `${listSeparator(index, present.length)}${countWord(count)} ${noun}${plural(count)}`)
    .join("");
  return { total: all.length, parts };
}

function inRounds(latest: number | null): string {
  return latest === null ? "this season" : `in ${latest} round${plural(latest)}`;
}

/** The season panel's finding. `latest` is how many rounds the documents reach. */
export function timelineTitle(car: PowerUnitCar, latest: number | null): string {
  const { total, parts } = rulingCounts(car);
  if (total === 0) return `No power-unit ruling ${inRounds(latest)}`;
  return `${countWord(total, true)} ruling${plural(total)} ${inRounds(latest)}: ${parts}`;
}

export interface StandInRun {
  stint: DriverStint;
  runs: string;
}

export interface TimelineSub {
  head: string;
  /** Names are the component's: a surname needs the season directory. */
  standIns: StandInRun[];
  tail: string;
}

/** The [first, last] rounds of every unit the documents cannot pin to a round. */
function windows(car: PowerUnitCar): Array<[number, number]> {
  return car.elements
    .flatMap((item) => item.parts)
    .flatMap((part) => (part.round === null && part.window ? [part.window] : []));
}

export function timelineSub(car: PowerUnitCar, latest: number | null): TimelineSub {
  const groups = new Map<string, { count: number; first: number; last: number }>();
  for (const [first, last] of windows(car)) {
    const key = `${first}-${last}`;
    groups.set(key, { first, last, count: (groups.get(key)?.count ?? 0) + 1 });
  }
  const arrivals = [...groups.values()].map(
    ({ count, first, last }) =>
      ` · ${count} unit${plural(count)} arrived between R${first} and R${last}, round not pinned down`,
  );
  return {
    head: `New units fitted at ${car.events.length}${latest === null ? "" : ` of ${latest}`} Grand Prix weekends`,
    standIns: lineup(car)
      .filter((seat) => seat.standIn)
      .map(({ stint }) => ({ stint, runs: roundRuns(stint.rounds) })),
    tail: `${arrivals.join("")}${rulingSuffix(car.penalties.pending, car.penalties.not_found)}`,
  };
}

export type CellKind = "units" | "penalty" | "pending" | "notFound" | "window" | "nothing" | "future";

export interface SeasonCell {
  round: number;
  code: string;
  name: string;
  latest: boolean;
  kind: CellKind;
  text: string;
  label: string;
  driver: { code: string; standIn: boolean } | null;
}

function eventCell(event: CarEvent, name: string): Pick<SeasonCell, "kind" | "text" | "label"> {
  const places = gridPlaces(event.decisions);
  if (event.decisions.some((item) => item.outcome === "pit_lane")) {
    return { kind: "penalty", text: "PL", label: `${name}: pit-lane start` };
  }
  if (places > 0) return { kind: "penalty", text: `−${places}`, label: `${name}: ${places} grid places` };
  if (event.penalty_status === "pending") {
    return { kind: "pending", text: "?", label: `${name}: stewards' decision pending` };
  }
  if (event.penalty_status === "not_found") {
    return { kind: "notFound", text: "!", label: `${name}: no stewards' decision found` };
  }
  const units = event.new_parts.length;
  return { kind: "units", text: String(units), label: `${name}: ${units} new unit${plural(units)}` };
}

function quietCell(car: PowerUnitCar, round: RoundInfo): Pick<SeasonCell, "kind" | "text" | "label"> {
  const covering = windows(car).filter(([first, last]) => first <= round.round && round.round <= last);
  if (covering.length > 0) {
    const first = Math.min(...covering.map((span) => span[0]));
    const last = Math.max(...covering.map((span) => span[1]));
    const count = covering.length;
    return {
      kind: "window",
      text: String(count),
      label: `${round.name}: ${count} new unit${plural(count)} arrived at this round or another between R${first} and R${last} (round not pinned down)`,
    };
  }
  if (round.has_documents) return { kind: "nothing", text: "·", label: `${round.name}: nothing new` };
  return { kind: "future", text: "", label: `${round.name}: no FIA documents yet` };
}

/** One cell per Grand Prix of the season. */
export function seasonCells(data: PowerUnitsResponse, car: PowerUnitCar): SeasonCell[] {
  const byRound = new Map(car.events.map((event) => [event.round, event]));
  return (data.rounds ?? []).map((round) => {
    const event = byRound.get(round.round);
    const stint = car.drivers.find((item) => item.rounds.includes(round.round));
    return {
      round: round.round,
      code: round.code || `R${round.round}`,
      name: round.name,
      latest: data.as_of?.round === round.round,
      ...(event ? eventCell(event, round.name) : quietCell(car, round)),
      driver: stint ? { code: stint.code, standIn: isStandIn(car, stint) } : null,
    };
  });
}

export function weekendsAside(car: PowerUnitCar): string | undefined {
  const count = car.events.length;
  return count === 0 ? undefined : `${count} weekend${plural(count)} with new units · newest first`;
}

export const STATUS_TAGS: Record<PenaltyStatus, { label: string; tone: StateTone }> = {
  none: { label: "Within the allocation", tone: "neutral" },
  decided: { label: "Stewards decided", tone: "red" },
  pending: { label: "Ruling pending", tone: "blue" },
  not_found: { label: "No ruling found", tone: "neutral" },
};

export function decisionLine(decision: Decision): string {
  const names = decision.elements.map((item) => `${item.code} #${item.number}`).join(" · ");
  return `${names}${decision.session ? ` · first used in ${decision.session}` : ""}`;
}

export function nominalNote(decision: Decision): string | null {
  return decision.outcome === "pit_lane" && decision.nominal_places !== null
    ? `The units alone carried ${decision.nominal_places} grid places; the pit-lane start made that drop redundant.`
    : null;
}

export function gapNote(status: PenaltyStatus): string | null {
  if (status === "pending") {
    return "Units beyond the allocation were fitted, and the stewards have not published a decision yet.";
  }
  if (status === "not_found") {
    return "Units beyond the allocation were fitted, but no stewards' decision naming them was found in the collected documents.";
  }
  return null;
}

/** "Doc 83 - Infringement - Car 6" reads "Doc 83 · Infringement · Car 6". */
export function docLabel(title: string): string {
  return title.replaceAll(" - ", " · ");
}

const SOURCE_LINE =
  'Source: FIA technical-delegate reports "New PU elements for this competition" and the stewards\' power-unit decisions, checked hourly';

export function sourceLine(freshness: Freshness | null | undefined): string {
  const checked = freshness?.checked_at ? ` · last checked ${formatUtc(freshness.checked_at)}` : "";
  const changed = freshness?.changed_at ? ` · last change ${formatUtc(freshness.changed_at)}` : "";
  return `${SOURCE_LINE}${checked}${changed}`;
}

export interface AllocationGroup {
  codes: string;
  doc: string | null;
  url: string | null;
}

/** The allowances grouped by where the FIA (or a hand) stated them, in the order first seen. */
export function allocationGroups(elements: readonly ElementInfo[]): AllocationGroup[] {
  const groups = new Map<string, { codes: string[]; source: ElementInfo["allowance_source"] }>();
  for (const item of elements) {
    const source = item.allowance_source;
    const key = source ? `${source.kind}:${source.url ?? source.title ?? ""}` : "unstated";
    const code = `${item.code} ${item.allowance ?? "?"}`;
    groups.set(key, { source, codes: [...(groups.get(key)?.codes ?? []), code] });
  }
  return [...groups.values()].map(({ codes, source }) => {
    if (source?.kind !== "fia_report") return { codes: codes.join(" · "), doc: null, url: null };
    const head = (source.title ?? "document").split(" - ")[0].toLowerCase();
    const day = shortDay(source.stated_on);
    return { codes: codes.join(" · "), doc: `FIA ${head}${day ? `, ${day}` : ""}`, url: source.url };
  });
}

export function carNotes(data: PowerUnitsResponse, car: PowerUnitCar): SourceNote[] {
  return [...sourceNotes(data), ...car.warnings.map((text) => ({ text }))];
}
