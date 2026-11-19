"use client";

import { Fragment, type CSSProperties } from "react";

import { DriverName } from "@/app/ui/names/DriverName";
import { PanelHeading } from "@/app/ui/PanelHeading";
import { Section } from "@/app/ui/section/Section";
import { SectionHead } from "@/app/ui/SectionHead";

import { timelineSub, timelineTitle, seasonCells, type CellKind, type SeasonCell } from "./carModel";
import { useCar, type CarSectionProps } from "./useCar";

const MARK: Record<CellKind, string> = {
  units: "bg-rc-raised text-rc-ink ring-1 ring-inset ring-rc-line",
  penalty: "bg-f1-red text-rc-ink",
  pending: "text-rc-blue ring-1 ring-inset ring-rc-blue",
  notFound: "text-rc-ink-2 ring-1 ring-inset ring-rc-ink-3",
  window: "border border-dashed border-rc-ink-3 text-rc-ink-2",
  nothing: "bg-rc-ink/3 text-rc-ink-3",
  future: "border border-dashed border-rc-line",
};

const MARK_BASE = "grid place-items-center rounded-[3px] font-mono font-semibold leading-none";

function Cell({ cell, linked, showDriver }: { cell: SeasonCell; linked: boolean; showDriver: boolean }) {
  const body = (
    <>
      <span
        className={`font-mono text-[10px] font-medium leading-none tracking-[0.04em] ${cell.latest ? "text-rc-ink" : "text-rc-ink-3"}`}
      >
        {cell.code}
      </span>
      <span
        aria-label={linked ? undefined : cell.label}
        className={`${MARK_BASE} h-10 text-[13px] ${MARK[cell.kind]} ${cell.latest ? "ring-1 ring-inset ring-rc-ink-3" : ""}`}
      >
        {cell.text}
      </span>
      {showDriver && (
        <span
          className={`min-h-2.5 font-mono text-[10px] font-medium leading-none ${cell.driver?.standIn ? "text-rc-blue" : "text-rc-ink-3"}`}
        >
          {cell.driver?.code}
        </span>
      )}
    </>
  );
  const className = "grid gap-[5px] text-center";
  return linked ? (
    <a
      href={`#round-${cell.round}`}
      aria-label={cell.label}
      title={cell.label}
      className={`${className} hover:opacity-80`}
    >
      {body}
    </a>
  ) : (
    <span title={cell.label} className={className}>
      {body}
    </span>
  );
}

function MiniMark({ kind, children }: { kind: CellKind; children?: string }) {
  return (
    <b aria-hidden="true" className={`${MARK_BASE} inline-grid h-[18px] w-[26px] text-[10px] ${MARK[kind]}`}>
      {children}
    </b>
  );
}

function TimelineLegend({ cells, standIn }: { cells: SeasonCell[]; standIn: string | null }) {
  const items: Array<[CellKind, string, string]> = [
    ["units", "7", "new units"],
    ["penalty", "−30", "grid places"],
    ["penalty", "PL", "pit-lane start"],
    ["pending", "?", "ruling pending"],
    ["notFound", "!", "no ruling found"],
    ["nothing", "·", "nothing new"],
    ["future", "", "no FIA documents yet"],
  ];
  return (
    <ul
      aria-label="Legend"
      className="mt-5 flex flex-wrap gap-x-[18px] gap-y-2 font-mono text-[11px] font-medium leading-none text-rc-ink-3"
    >
      {items.map(([kind, text, label]) => (
        <li key={label} className="inline-flex items-center gap-[7px]">
          <MiniMark kind={kind}>{text}</MiniMark>
          {label}
        </li>
      ))}
      {cells.some((cell) => cell.kind === "window") && (
        <li className="inline-flex items-center gap-[7px]">
          <MiniMark kind="window">3</MiniMark>round not pinned down
        </li>
      )}
      {standIn !== null && (
        <li className="inline-flex items-center gap-[7px]">
          <b aria-hidden="true" className="font-mono text-[10px] font-semibold text-rc-blue">
            {standIn}
          </b>
          stand-in driver
        </li>
      )}
    </ul>
  );
}

/** 02: one cell per Grand Prix, marked with what its power unit cost there. */
export function SeasonTimeline(props: CarSectionProps) {
  const { state, data, car, absent } = useCar(props);
  if (absent) return null;
  const latest = data?.as_of?.round ?? null;
  const cells = data && car ? seasonCells(data, car) : [];
  const sub = car ? timelineSub(car, latest) : null;
  const shared = (car?.drivers.length ?? 0) > 1;
  return (
    <section aria-labelledby="pu-car-season">
      <SectionHead
        index={2}
        id="pu-car-season"
        title="Season"
        aside="One cell per Grand Prix · select one for the weekend"
      />
      <Section state={state} label="Season" skeletonClassName="h-[260px]">
        {car && sub && (
          <figure className="rounded-md border border-rc-line bg-(--surface) p-[18px] sm:p-6">
            <PanelHeading
              eyebrow="What each weekend cost"
              title={timelineTitle(car, latest)}
              sub={
                <>
                  {sub.head}
                  {sub.standIns.map(({ stint, runs }) => (
                    <Fragment key={stint.id}>
                      {" · "}
                      <DriverName
                        variant="last"
                        name={stint.name}
                        code={stint.code}
                        id={stint.id}
                        year={props.year}
                      />{" "}
                      (#
                      {stint.car_number}) stood in at {runs}
                    </Fragment>
                  ))}
                  {sub.tail}
                </>
              }
            />
            <ol
              style={{ "--rounds": cells.length } as CSSProperties}
              className="grid grid-cols-8 gap-x-1 gap-y-3 sm:grid-cols-[repeat(var(--rounds),minmax(0,1fr))]"
            >
              {cells.map((cell) => (
                <li key={cell.round}>
                  <Cell
                    cell={cell}
                    linked={car.events.some((event) => event.round === cell.round)}
                    showDriver={shared}
                  />
                </li>
              ))}
            </ol>
            <TimelineLegend cells={cells} standIn={sub.standIns[0]?.stint.code ?? null} />
          </figure>
        )}
      </Section>
    </section>
  );
}
