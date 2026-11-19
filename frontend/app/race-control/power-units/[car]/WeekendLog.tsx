"use client";

import { DriverName } from "@/app/ui/names/DriverName";
import { Section } from "@/app/ui/section/Section";
import { SectionHead } from "@/app/ui/SectionHead";

import { StateTag } from "../../grand-prix/StateTag";
import {
  gridLabel,
  outcomeLabel,
  regularStint,
  roundsByNumber,
  shortDay,
  type CarEvent,
  type Decision,
  type DocumentRef,
  type Part,
  type PowerUnitCar,
  type RoundInfo,
} from "../powerUnitsModel";

import { decisionLine, docLabel, gapNote, isStandIn, nominalNote, STATUS_TAGS, weekendsAside } from "./carModel";
import { useCar, type CarSectionProps } from "./useCar";

const DOC_LINK =
  "inline-block font-mono text-[11px] font-medium leading-normal text-rc-ink-2 underline decoration-rc-line underline-offset-[3px] hover:text-rc-ink hover:decoration-rc-ink-3";

function DocLink({ doc, label, className = "" }: { doc: Pick<DocumentRef, "url">; label: string; className?: string }) {
  return (
    <a href={doc.url} target="_blank" rel="noopener noreferrer" className={`${DOC_LINK} ${className}`}>
      {label} ↗<span className="sr-only">(opens the FIA document)</span>
    </a>
  );
}

function Chips({ label, parts }: { label: string; parts: Part[] }) {
  if (parts.length === 0) return null;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="min-w-0 font-mono text-[10px] font-medium uppercase leading-none tracking-[0.14em] text-rc-ink-3 sm:min-w-[176px]">
        {label}
      </span>
      {parts.map((part) => (
        <span
          key={`${part.code}-${part.number}`}
          className={`rounded-[3px] border px-[7px] py-[5px] font-mono text-[11px] font-semibold leading-none ${
            part.beyond_allowance ? "border-f1-red bg-f1-red/16" : "border-rc-line bg-rc-raised"
          } ${part.not_counted_from === null ? "text-rc-ink" : "text-rc-ink-3 line-through"}`}
        >
          {part.code} #{part.number}
        </span>
      ))}
    </div>
  );
}

function StandInNote({ car, event, year }: { car: PowerUnitCar; event: CarEvent; year: number }) {
  const { driver } = event;
  const regular = regularStint(car);
  if (!driver || !isStandIn(car, driver)) return null;
  return (
    <p className="max-w-[76ch] border-l-2 border-rc-blue py-0.5 pl-3 text-[13px] text-rc-ink-2">
      <StateTag tone="blue">Stand-in</StateTag>{" "}
      <DriverName name={driver.name} code={driver.code} id={driver.id} year={year} /> drove car {car.car_number} this
      weekend
      {driver.car_number === car.car_number ? "" : ` under his own number, #${driver.car_number}`}. Units fitted to this
      car count against its allocation, the one{" "}
      <DriverName variant="last" name={regular.name} code={regular.code} id={regular.id} year={year} /> races with,
      whoever drives it (Article B8.2.7).
    </p>
  );
}

function DecisionBlock({ decision }: { decision: Decision }) {
  const nominal = nominalNote(decision);
  return (
    <div className="border-l-[3px] border-f1-red py-0.5 pl-4">
      <b className="font-display text-[26px] font-extrabold uppercase leading-none text-rc-red-text">
        {outcomeLabel(decision)}
      </b>
      <p className="mt-2 font-mono text-[11px] font-medium leading-normal tracking-[0.04em] text-rc-ink-2">
        {decisionLine(decision)}
      </p>
      {nominal !== null && <p className="mt-1.5 text-[13px] text-rc-ink-2">{nominal}</p>}
      <p className="mt-1.5 max-w-[76ch] text-[13px] text-rc-ink-3">{decision.summary}</p>
      <DocLink doc={decision} label={`Stewards · ${docLabel(decision.title)}`} className="mt-2" />
    </div>
  );
}

function Weekend({
  car,
  event,
  round,
  year,
}: {
  car: PowerUnitCar;
  event: CarEvent;
  round: RoundInfo | undefined;
  year: number;
}) {
  const tag = STATUS_TAGS[event.penalty_status];
  const gap = gapNote(event.penalty_status);
  return (
    <article
      id={`round-${event.round}`}
      className="grid scroll-mt-[84px] gap-x-8 gap-y-3.5 border-t border-rc-line py-[26px] last:border-b md:grid-cols-[180px_minmax(0,1fr)] lg:grid-cols-[200px_minmax(0,1fr)_260px]"
    >
      <header>
        <p className="font-display text-[40px] font-extrabold leading-none text-rc-ink">
          R{event.round}
          <span className="ml-2 align-[0.4em] font-mono text-[11px] font-semibold tracking-[0.12em] text-rc-ink-3">
            {round?.code}
          </span>
        </p>
        <h3 className="mt-2.5 text-[15px] font-semibold leading-snug text-rc-ink">
          {round?.name ?? `Round ${event.round}`}
        </h3>
        <p className="mb-3 mt-1.5 font-mono text-[11px] font-medium uppercase leading-none tracking-[0.08em] text-rc-ink-3">
          {shortDay(round?.date)}
        </p>
        <StateTag tone={tag.tone}>{tag.label}</StateTag>
      </header>
      <div className="grid min-w-0 content-start gap-3.5">
        <StandInNote car={car} event={event} year={year} />
        <Chips label="Beyond the allocation" parts={event.new_parts.filter((part) => part.beyond_allowance)} />
        <Chips label="Within" parts={event.new_parts.filter((part) => !part.beyond_allowance)} />
        {event.decisions.map((decision) => (
          <DecisionBlock key={decision.url} decision={decision} />
        ))}
        {gap !== null && (
          <p className="max-w-[76ch] border-l-2 border-rc-ink-3 py-0.5 pl-3 text-[13px] text-rc-ink-2">{gap}</p>
        )}
      </div>
      <dl className="grid content-start gap-1.5 md:col-start-2 lg:col-start-auto">
        <dt className="font-mono text-[10px] font-semibold uppercase leading-none tracking-[0.16em] text-rc-ink-3">
          Grid
        </dt>
        <dd className="mb-3 text-[13px] text-rc-ink-2">{gridLabel(event.grid)}</dd>
        {event.sources.length > 0 && (
          <>
            <dt className="font-mono text-[10px] font-semibold uppercase leading-none tracking-[0.16em] text-rc-ink-3">
              FIA reports
            </dt>
            <dd className="grid justify-items-start text-[13px]">
              {event.sources.map((ref) => (
                <DocLink key={ref.url} doc={ref} label={`TD report${ref.number ? ` · Doc ${ref.number}` : ""}`} />
              ))}
            </dd>
          </>
        )}
      </dl>
    </article>
  );
}

/** 03: an open log of the weekends that fitted new units, newest first. */
export function WeekendLog(props: CarSectionProps) {
  const { state, data, car, absent } = useCar(props);
  if (absent) return null;
  const rounds = roundsByNumber(data?.rounds);
  const events = [...(car?.events ?? [])].sort((a, b) => b.round - a.round);
  return (
    <section aria-labelledby="pu-car-weekends">
      <SectionHead
        index={3}
        id="pu-car-weekends"
        title="Weekend by weekend"
        aside={car ? weekendsAside(car) : undefined}
      />
      <Section state={state} label="Weekend log" skeletonClassName="h-[1200px]">
        {car &&
          (events.length === 0 ? (
            <p className="text-sm text-rc-ink-3">No new units recorded for this car yet.</p>
          ) : (
            <div>
              {events.map((event) => (
                <Weekend key={event.round} car={car} event={event} round={rounds.get(event.round)} year={props.year} />
              ))}
            </div>
          ))}
      </Section>
    </section>
  );
}
