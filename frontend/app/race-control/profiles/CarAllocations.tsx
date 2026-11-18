"use client";

import Link from "next/link";

import { API_BASE } from "@/app/constants/api";
import { getTeamColor } from "@/app/lib/teamColors";
import { Legend } from "@/app/ui/Legend";
import { DriverName } from "@/app/ui/names/DriverName";
import { TeamName } from "@/app/ui/names/TeamName";
import { PanelHeading } from "@/app/ui/PanelHeading";
import { Section } from "@/app/ui/section/Section";
import { useSection } from "@/app/ui/section/useSection";
import { SectionHead } from "@/app/ui/SectionHead";
import { f1, rc } from "@/app/ui/tokens";

import {
  carHref,
  powerUnitsUrl,
  roundRuns,
  type ElementInfo,
  type ElementUsage,
  type PowerUnitCar,
  type PowerUnitsResponse,
} from "../power-units/powerUnitsModel";

import {
  carAllocationsSub,
  carAllocationsTitle,
  carFooterLink,
  gridPlacesCell,
  pickCars,
  pipsFor,
  type CarScope,
} from "./carAllocationsModel";

import type { ReactNode } from "react";

const REFRESH = { revalidateOnFocus: false, dedupingInterval: 120_000 };

const PIP = "inline-block h-4 w-2 rounded-[1px] border";
const PIP_STYLE = {
  used: `${PIP} border-rc-ink-2 bg-rc-ink-2`,
  empty: `${PIP} border-rc-ink-3/55`,
  beyond: `${PIP} border-f1-red bg-f1-red`,
} as const;

const HEAD = "pb-2.5 text-left font-mono text-[11px] font-semibold uppercase tracking-[0.12em] text-rc-ink-3";
const STICKY = "max-sm:sticky max-sm:left-0 max-sm:z-10 max-sm:bg-(--surface) max-sm:pr-3";

const LEGEND = [
  { label: "Used", color: rc.ink2 },
  { label: "Unused", color: rc.ink3, mark: "outline" },
  { label: "Beyond the allocation", color: f1.red },
] as const;

function Pips({ usage }: { usage: ElementUsage }) {
  const pips = pipsFor(usage);
  const pip = (kind: keyof typeof PIP_STYLE, count: number, first = false) =>
    Array.from({ length: count }, (_, index) => (
      <i
        key={`${kind}${index}`}
        data-pip={kind}
        className={`${PIP_STYLE[kind]} ${first && index === 0 ? "ml-[3px]" : ""}`}
      />
    ));
  return (
    <>
      <span role="img" aria-label={pips.label} className="inline-flex gap-[3px] align-middle">
        {pip("used", pips.used)}
        {pip("empty", pips.empty)}
        {pip("beyond", pips.beyond, pips.used > 0)}
      </span>
      <span
        aria-hidden="true"
        className={`ml-2 align-middle font-mono text-[11px] font-medium leading-none ${pips.over ? "text-rc-red-text" : "text-rc-ink-3"}`}
      >
        {usage.used}
      </span>
    </>
  );
}

function CarNames({ car, scope, year }: { car: PowerUnitCar; scope: CarScope; year: number }) {
  if (scope.kind === "driver") {
    const rounds = car.drivers.filter((stint) => stint.id === scope.driverId).flatMap((stint) => stint.rounds);
    return (
      <>
        <TeamName name={car.team} id={car.team_id} year={year} />
        <span className="ml-2 font-mono text-[11px] font-medium text-rc-ink-3">{roundRuns(rounds)}</span>
      </>
    );
  }
  return car.drivers.map((stint, index) => (
    <span key={stint.id}>
      {index > 0 && " / "}
      <DriverName variant="last" name={stint.name} code={stint.code} id={stint.id} year={year} />
    </span>
  ));
}

function CarRow({ car, elements, name }: { car: PowerUnitCar; elements: ElementInfo[]; name: ReactNode }) {
  const grid = gridPlacesCell(car.penalties);
  return (
    <tr className="border-b border-rc-line-soft">
      <th scope="row" className={`py-2.5 pr-3.5 text-left font-semibold whitespace-nowrap ${STICKY}`}>
        <Link href={carHref(car)} className="inline-flex items-center gap-2 text-rc-ink hover:underline">
          <i
            aria-hidden="true"
            className="h-4 w-[3px] rounded-[1px]"
            style={{ backgroundColor: getTeamColor(car.team) }}
          />
          <span className="font-display text-lg font-extrabold">#{car.car_number}</span>
          {name}
        </Link>
      </th>
      {elements.map((element) => {
        const usage = car.elements.find((item) => item.code === element.code);
        return (
          <td key={element.code} className="py-2.5 pr-3.5 whitespace-nowrap">
            {usage && <Pips usage={usage} />}
          </td>
        );
      })}
      <td className="py-2.5 pr-3.5 text-right font-mono whitespace-nowrap">
        {grid.places === null ? (
          <span className="text-rc-ink-3">—</span>
        ) : (
          <span className="text-rc-red-text">{grid.places}</span>
        )}
        {grid.extras.map((extra) => (
          <span key={extra} className="ml-2 text-[11px] text-rc-ink-3">
            {extra}
          </span>
        ))}
      </td>
      <td aria-hidden="true" className="w-5 py-2.5 text-right font-mono text-rc-ink-3">
        →
      </td>
    </tr>
  );
}

/** The pip table, shared by the Team and Driver cards and the Power Units page. */
export function AllocationTable({
  cars,
  elements,
  caption,
  nameFor,
}: {
  cars: readonly PowerUnitCar[];
  elements: ElementInfo[];
  caption: string;
  nameFor: (car: PowerUnitCar) => ReactNode;
}) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[780px] border-collapse text-sm">
        <caption className="sr-only">{caption}</caption>
        <thead>
          <tr className="border-b border-rc-line">
            <th scope="col" className={`${HEAD} ${STICKY}`}>
              Car
            </th>
            {elements.map((element) => (
              <th key={element.code} scope="col" className={HEAD}>
                {element.code}
                {element.allowance !== null && <span className="ml-1 font-medium">/{element.allowance}</span>}
              </th>
            ))}
            <th scope="col" className={`${HEAD} text-right`}>
              Grid places
            </th>
            <th scope="col" aria-hidden="true" className={HEAD} />
          </tr>
        </thead>
        <tbody>
          {cars.map((car) => (
            <CarRow key={car.seat_id} car={car} elements={elements} name={nameFor(car)} />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function AllocationCard({
  data,
  cars,
  scope,
  year,
}: {
  data: PowerUnitsResponse;
  cars: PowerUnitCar[];
  scope: CarScope;
  year: number;
}) {
  const title = carAllocationsTitle(cars);
  const elements = data.elements ?? [];
  const link = carFooterLink(cars, data.cars.length, scope);
  return (
    <figure className="rounded-md border border-rc-line bg-(--surface) p-6">
      <PanelHeading eyebrow="Allocation by car" title={title} sub={carAllocationsSub(cars, data.as_of)} />
      <AllocationTable
        cars={cars}
        elements={elements}
        caption={title}
        nameFor={(car) => <CarNames car={car} scope={scope} year={year} />}
      />
      <div className="mt-4 flex flex-wrap items-center justify-between gap-x-6 gap-y-3.5">
        <Legend items={LEGEND} label="Legend" />
        <Link
          href={link.href}
          className="font-mono text-[11px] font-medium uppercase tracking-[0.08em] text-rc-ink-2 hover:text-rc-ink"
        >
          {link.label}
        </Link>
      </div>
    </figure>
  );
}

function Note({ children }: { children: ReactNode }) {
  return <p className="text-sm text-rc-ink-3">{children}</p>;
}

function CardBody({ data, scope, year }: { data: PowerUnitsResponse; scope: CarScope; year: number }) {
  if (!data.available) {
    return <Note>{`Power-unit usage isn't available${data.reason ? `: ${data.reason}` : "."}`}</Note>;
  }
  const cars = pickCars(data.cars, scope);
  if (cars.length === 0) {
    return <Note>No power-unit records for this {scope.kind} this season.</Note>;
  }
  return <AllocationCard data={data} cars={cars} scope={scope} year={year} />;
}

interface CarAllocationsProps {
  year: number;
  scope: CarScope;
}

/**
 * The "Power units" section of a Team or Driver page: each car's elements
 * against the season's allocation. It fetches its own endpoint, with no server
 * seed (it sits below the fold and the power-unit read is the slowest), so its
 * failure never blanks the page around it.
 */
export function CarAllocations({ year, scope }: CarAllocationsProps) {
  const state = useSection<PowerUnitsResponse>(powerUnitsUrl(API_BASE, year), { config: REFRESH });
  return (
    <section className="pt-16">
      <SectionHead
        index={scope.kind === "team" ? 3 : 2}
        title={scope.kind === "team" ? "Power units" : "Power unit"}
        aside="Elements used against the season's allocation"
      />
      <Section state={state} label="Power units" skeletonClassName="h-[220px]">
        {state.data && <CardBody data={state.data} scope={scope} year={year} />}
      </Section>
    </section>
  );
}
