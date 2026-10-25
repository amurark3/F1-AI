/**
 * One Grand Prix in the life of a car's power unit: who drove it, which new
 * units it fitted, what the stewards decided, and where it started.
 *
 * Server-safe: no state, no effects.
 */
import { UserRoundCog } from "lucide-react";

import { StatusPill } from "../../components/RaceControlPrimitives";
import {
  OVER_COLOR,
  STATUS_LABELS,
  gridLabel,
  outcomeLabel,
  statusColor,
  type CarEvent,
  type Decision,
  type PowerUnitCar,
  type RoundInfo,
} from "../powerUnitsModel";
import { FiaLink } from "../SeasonPanels";

function DecisionBlock({ decision }: { decision: Decision }) {
  return (
    <div className="rounded border border-[#E10600]/40 bg-[#E10600]/10 px-3 py-2.5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="font-mono text-base font-black text-white">{outcomeLabel(decision)}</span>
        <FiaLink href={decision.url} label={decision.number ? `Stewards · Doc ${decision.number}` : "Stewards"} />
      </div>
      <p className="mt-1 text-xs text-[#FFB4B1]">
        {decision.elements.map((item) => `${item.code} #${item.number}`).join(" · ")}
        {decision.session && <span className="text-[#C9CED8]"> — first used in {decision.session}</span>}
      </p>
      {decision.outcome === "pit_lane" && decision.nominal_places !== null && (
        <p className="mt-1 text-xs text-[#C9CED8]">
          The units alone carried {decision.nominal_places} grid places; the pit-lane start made that drop redundant.
        </p>
      )}
      <p className="mt-1 text-xs leading-relaxed text-[#8E96A8]">{decision.summary}</p>
    </div>
  );
}

function PendingNote({ status }: { status: CarEvent["penalty_status"] }) {
  if (status === "pending") {
    return (
      <p className="rounded border border-[#F5C542]/40 bg-[#F5C542]/10 px-3 py-2 text-xs text-[#FFF6A3]">
        Units beyond the allowance were fitted, and the stewards have not published a decision yet.
      </p>
    );
  }
  if (status === "not_found") {
    return (
      <p className="rounded border border-[#F5C542]/40 bg-[#F5C542]/10 px-3 py-2 text-xs text-[#FFF6A3]">
        Units beyond the allowance were fitted, but no stewards&apos; decision naming them was found in the collected
        documents.
      </p>
    );
  }
  return null;
}

export function WeekendCard({
  event,
  round,
  car,
  teamColor,
}: {
  event: CarEvent;
  round: RoundInfo | undefined;
  car: PowerUnitCar;
  teamColor: string;
}) {
  return (
    <article id={`round-${event.round}`} className="scroll-mt-24 rounded-md border border-[#1E2633] bg-[#0D111B]">
      <header className="flex flex-wrap items-center justify-between gap-3 border-b border-[#1E2633] px-4 py-3">
        <div className="flex min-w-0 items-center gap-3">
          <span className="rounded bg-[#101520] px-2 py-1 font-mono text-[11px] font-black tracking-[0.12em] text-white">
            R{event.round} {round?.code}
          </span>
          <div className="min-w-0">
            <p className="truncate text-sm font-bold text-white">{round?.name ?? `Round ${event.round}`}</p>
            <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-[#6F7789]">{round?.date}</p>
          </div>
        </div>
        <StatusPill color={statusColor(event.penalty_status)}>{STATUS_LABELS[event.penalty_status]}</StatusPill>
      </header>

      <div className="flex flex-col gap-3 px-4 py-3">
        {event.stand_in && event.driver && (
          <p className="flex items-start gap-2 rounded border border-[#3671C6]/40 bg-[#3671C6]/10 px-3 py-2 text-xs text-[#9EC5FF]">
            <UserRoundCog className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            <span>
              Driven by {event.driver.name} (#{event.driver.car_number}) this weekend. Under Article B8.2.7, units
              fitted to this car count against its allocation — the one {car.driver.name} races with — whoever drives
              it.
            </span>
          </p>
        )}

        {event.new_parts.length > 0 && (
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="mr-1 font-mono text-[10px] uppercase tracking-[0.16em] text-[#6F7789]">New units</span>
            {event.new_parts.map((part) => (
              <span
                key={`${part.code}-${part.number}`}
                className={`rounded border px-1.5 py-0.5 font-mono text-[11px] font-bold text-white ${
                  part.not_counted_from === null ? "" : "line-through opacity-60"
                }`}
                style={
                  part.beyond_allowance
                    ? { borderColor: OVER_COLOR, background: `${OVER_COLOR}2E` }
                    : { borderColor: `${teamColor}80`, background: `${teamColor}1F` }
                }
              >
                {part.code} #{part.number}
              </span>
            ))}
          </div>
        )}

        {event.decisions.map((decision) => (
          <DecisionBlock key={decision.url} decision={decision} />
        ))}
        <PendingNote status={event.penalty_status} />

        <div className="flex flex-wrap items-center justify-between gap-2 border-t border-[#1E2633] pt-3">
          <span className="font-mono text-xs text-[#C9CED8]">{gridLabel(event.grid)}</span>
          <span className="flex flex-wrap gap-3">
            {event.sources.map((ref) => (
              <FiaLink
                key={ref.url}
                href={ref.url}
                label={ref.number ? `TD report · Doc ${ref.number}` : "TD report"}
              />
            ))}
          </span>
        </div>
      </div>
    </article>
  );
}
