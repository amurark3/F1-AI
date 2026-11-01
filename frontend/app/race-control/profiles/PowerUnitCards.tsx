/**
 * Power-unit usage for the cars on a team or driver page.
 *
 * Usage belongs to the car (FIA B8.2.7), so a driver page shows the whole car
 * and then narrows to the driver: the parts that arrived in the rounds they
 * raced it, and the decisions those rounds drew. Every decision links to the
 * FIA document it came from.
 *
 * Server-safe: no state, no effects.
 */
import { Cpu, ExternalLink } from "lucide-react";
import Link from "next/link";

import { ConsoleHeader, ConsolePanel } from "../grand-prix/predictionConsole";
import { ElementPips, UsageCount } from "../power-units/ElementPips";
import {
  carHref,
  outcomeLabel,
  type Decision,
  type ElementInfo,
  type Part,
  type PowerUnitCar,
} from "../power-units/powerUnitsModel";

import type { CarShare, ProfilePowerUnits } from "./profilesModel";

/** What narrows a car to one driver: the rounds they raced it, and who else did. */
export interface DriverFocus {
  driverName: string;
  rounds: number[];
  sharedWith: CarShare[];
}

interface CarCardProps {
  car: PowerUnitCar;
  color: string;
  elements: ElementInfo[];
  focus?: DriverFocus;
}

function penaltyLine(car: PowerUnitCar): string {
  const { grid_places, pit_lane_starts, back_of_grid, pending } = car.penalties;
  const parts = [
    grid_places ? `−${grid_places} grid places` : null,
    pit_lane_starts ? `${pit_lane_starts} pit-lane start${pit_lane_starts === 1 ? "" : "s"}` : null,
    back_of_grid ? `${back_of_grid} back-of-grid start${back_of_grid === 1 ? "" : "s"}` : null,
    pending ? `${pending} decision${pending === 1 ? "" : "s"} pending` : null,
  ].filter((item): item is string => item !== null);
  return parts.length ? parts.join(" · ") : "No power-unit penalties";
}

function driversLine(car: PowerUnitCar, focus?: DriverFocus): string {
  if (!focus) {
    return car.drivers.map((driver) => driver.name).join(", ");
  }
  const shared = focus.sharedWith.map((other) => `${other.name} (${other.rounds_label})`).join(", ");
  return shared ? `Shared with ${shared}` : `Raced only by ${focus.driverName}`;
}

function partsInRounds(car: PowerUnitCar, rounds: number[]): Part[] {
  const wanted = new Set(rounds);
  return car.elements.flatMap((element) =>
    element.parts.filter((part) => part.round !== null && wanted.has(part.round)),
  );
}

function decisionsInRounds(car: PowerUnitCar, rounds: number[]): Array<Decision & { round: number }> {
  const wanted = new Set(rounds);
  return car.events
    .filter((event) => wanted.has(event.round))
    .flatMap((event) => event.decisions.map((decision) => ({ ...decision, round: event.round })));
}

function ElementRows({ car, color, elements }: { car: PowerUnitCar; color: string; elements: ElementInfo[] }) {
  const names = new Map(elements.map((element) => [element.code, element.name]));
  return (
    <dl className="divide-y divide-[#1E2633]">
      {car.elements.map((usage) => (
        <div key={usage.code} className="flex items-center justify-between gap-3 py-2">
          <dt className="min-w-0 text-xs text-[#8E96A8]" title={names.get(usage.code) ?? usage.code}>
            <span className="font-mono font-bold text-white">{usage.code}</span>
          </dt>
          <dd className="flex items-center gap-3">
            <ElementPips usage={usage} teamColor={color} />
            <UsageCount usage={usage} />
          </dd>
        </div>
      ))}
    </dl>
  );
}

function FocusDetail({ car, focus }: { car: PowerUnitCar; focus: DriverFocus }) {
  const parts = partsInRounds(car, focus.rounds);
  const decisions = decisionsInRounds(car, focus.rounds);
  return (
    <div className="mt-4 space-y-3 border-t border-[#1E2633] pt-3 text-sm">
      <p className="text-[#8E96A8]">
        <span className="font-bold text-white">{parts.length}</span> new part{parts.length === 1 ? "" : "s"} in{" "}
        {focus.driverName}&apos;s rounds
        {parts.length > 0 && (
          <span className="ml-1 font-mono text-xs text-[#B7BDCA]">
            ({parts.map((part) => `${part.code} #${part.number} R${part.round}`).join(", ")})
          </span>
        )}
      </p>
      {decisions.map((decision) => (
        <a
          key={`${decision.round}-${decision.url}`}
          href={decision.url}
          target="_blank"
          rel="noreferrer"
          className="flex items-start gap-2 rounded border border-[#E10600]/25 bg-[#E10600]/[0.06] p-2 text-xs text-neutral-300 hover:border-[#E10600]/50"
        >
          <ExternalLink className="mt-0.5 h-3.5 w-3.5 shrink-0 text-[#FF8A85]" aria-hidden="true" />
          <span>
            <span className="font-bold text-white">
              R{decision.round} · {outcomeLabel(decision)}
            </span>{" "}
            — {decision.title}
          </span>
        </a>
      ))}
    </div>
  );
}

export function PowerUnitCarCard({ car, color, elements, focus }: CarCardProps) {
  return (
    <ConsolePanel>
      <ConsoleHeader
        label={`Car #${car.car_number}`}
        right={
          <Link href={carHref(car)} className="text-xs font-bold text-[#9EC5FF] hover:text-white">
            Full ledger →
          </Link>
        }
      />
      <div className="p-4">
        <p className="text-sm text-[#B7BDCA]">{driversLine(car, focus)}</p>
        <p className="mb-3 mt-1 text-xs text-[#6F7789]">{penaltyLine(car)}</p>
        <ElementRows car={car} color={color} elements={elements} />
        {focus && <FocusDetail car={car} focus={focus} />}
      </div>
    </ConsolePanel>
  );
}

/** The section wrapper: a reason when there is no data, otherwise one card per car. */
export function PowerUnitsSection<C extends PowerUnitCar>({
  section,
  color,
  renderFocus,
}: {
  section: ProfilePowerUnits<C>;
  color: string;
  renderFocus?: (car: C) => DriverFocus;
}) {
  return (
    <section aria-labelledby="power-units-heading" className="mb-5">
      <h2 id="power-units-heading" className="mb-3 flex items-center gap-2 text-lg font-black text-white">
        <Cpu className="h-4 w-4" style={{ color }} aria-hidden="true" />
        Power units
      </h2>
      {!section.available || section.cars.length === 0 ? (
        <p className="rounded-md border border-[#1E2633] bg-[#0D111B] p-4 text-sm text-[#8E96A8]">
          {section.reason ?? "No power-unit usage has been read for this car yet."}
        </p>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {section.cars.map((car) => (
            <PowerUnitCarCard
              key={car.seat_id}
              car={car}
              color={color}
              elements={section.elements}
              focus={renderFocus?.(car)}
            />
          ))}
        </div>
      )}
      {section.as_of && (
        <p className="mt-2 text-xs text-[#6F7789]">
          Read from FIA documents through round {section.as_of.round} ({section.as_of.title}).
        </p>
      )}
    </section>
  );
}
