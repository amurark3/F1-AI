"use client";

import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";

import { getTeamColor } from "@/app/lib/teamColors";

import { ConsoleHeader, ConsolePanel } from "../grand-prix/predictionConsole";

import { ElementPips, UsageCount } from "./ElementPips";
import {
  OVER_COLOR,
  PENDING_COLOR,
  carHref,
  totalOverBy,
  type ElementInfo,
  type PowerUnitCar,
} from "./powerUnitsModel";

type SortKey = "over" | "number" | "team" | "places";

const SORTS: ReadonlyArray<{ key: SortKey; label: string }> = [
  { key: "over", label: "Most over" },
  { key: "places", label: "Grid places" },
  { key: "number", label: "Car #" },
  { key: "team", label: "Team" },
];

const COMPARATORS: Record<SortKey, (a: PowerUnitCar, b: PowerUnitCar) => number> = {
  over: (a, b) => totalOverBy(b) - totalOverBy(a) || a.car_number - b.car_number,
  places: (a, b) => b.penalties.grid_places - a.penalties.grid_places || a.car_number - b.car_number,
  number: (a, b) => a.car_number - b.car_number,
  team: (a, b) => a.team.localeCompare(b.team) || a.car_number - b.car_number,
};

const GRID_COLUMNS = "grid-cols-[64px_minmax(170px,1.4fr)_repeat(7,minmax(92px,1fr))_112px_20px]";

function SortControls({
  sort,
  onSort,
  onlyOver,
  onToggleOver,
}: {
  sort: SortKey;
  onSort: (key: SortKey) => void;
  onlyOver: boolean;
  onToggleOver: () => void;
}) {
  const chip = (active: boolean) =>
    `rounded border px-2 py-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] transition-colors ${
      active ? "border-white/40 bg-white/10 text-white" : "border-[#2C3646] text-[#7F8797] hover:text-white"
    }`;
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      {SORTS.map((item) => (
        <button key={item.key} type="button" className={chip(sort === item.key)} onClick={() => onSort(item.key)}>
          {item.label}
        </button>
      ))}
      <button type="button" className={chip(onlyOver)} aria-pressed={onlyOver} onClick={onToggleOver}>
        Over only
      </button>
    </div>
  );
}

function PenaltyCell({ car }: { car: PowerUnitCar }) {
  const { grid_places: places, pit_lane_starts: pitLane, pending } = car.penalties;
  return (
    <div className="flex flex-col items-end gap-0.5 font-mono text-xs">
      <span className="font-black tabular-nums" style={{ color: places ? OVER_COLOR : "#5A6273" }}>
        {places ? `−${places}` : "—"}
      </span>
      {pitLane > 0 && (
        <span className="text-[10px] uppercase tracking-[0.12em] text-[#FFB4B1]">{pitLane}× pit lane</span>
      )}
      {pending > 0 && (
        <span className="text-[10px] uppercase tracking-[0.12em]" style={{ color: PENDING_COLOR }}>
          pending
        </span>
      )}
    </div>
  );
}

function CarRow({ car, codes }: { car: PowerUnitCar; codes: string[] }) {
  const color = getTeamColor(car.team);
  const usage = new Map(car.elements.map((item) => [item.code, item]));
  return (
    <Link
      href={carHref(car)}
      className={`group grid ${GRID_COLUMNS} items-center gap-3 border-l-[3px] bg-[#0D111B] px-3 py-2.5 transition-colors hover:bg-[#121825] focus-visible:bg-[#121825] focus-visible:outline-none`}
      style={{ borderLeftColor: color }}
    >
      <span
        className="flex h-9 w-12 items-center justify-center rounded font-mono text-base font-black tabular-nums text-white"
        style={{ background: `${color}26`, boxShadow: `inset 0 0 0 1px ${color}66` }}
      >
        {car.car_number}
      </span>
      <span className="min-w-0">
        <span className="block truncate text-sm font-bold text-white">{car.driver.name}</span>
        <span className="block truncate font-mono text-[10px] uppercase tracking-[0.16em] text-[#7F8797]">
          {car.team}
          {car.drivers.length > 1 && <span className="ml-1.5 text-[#9EC5FF]">+{car.drivers.length - 1} stand-in</span>}
        </span>
      </span>
      {codes.map((code) => {
        const item = usage.get(code);
        return (
          <span key={code} className="flex flex-col gap-1">
            {item && <ElementPips usage={item} teamColor={color} />}
            {item && <UsageCount usage={item} />}
          </span>
        );
      })}
      <PenaltyCell car={car} />
      <ChevronRight className="h-4 w-4 text-[#3A4354] transition-transform group-hover:translate-x-0.5 group-hover:text-white" />
    </Link>
  );
}

export function AllocationMatrix({ cars, elements }: { cars: PowerUnitCar[]; elements: ElementInfo[] }) {
  const [sort, setSort] = useState<SortKey>("over");
  const [onlyOver, setOnlyOver] = useState(false);
  const codes = elements.map((item) => item.code);
  const rows = useMemo(
    () => [...cars.filter((car) => !onlyOver || totalOverBy(car) > 0)].sort(COMPARATORS[sort]),
    [cars, onlyOver, sort],
  );

  return (
    <ConsolePanel>
      <ConsoleHeader
        label="Allocation matrix"
        right={
          <SortControls sort={sort} onSort={setSort} onlyOver={onlyOver} onToggleOver={() => setOnlyOver((v) => !v)} />
        }
      />
      <div className="overflow-x-auto">
        <div className="min-w-[1080px]">
          <div
            className={`grid ${GRID_COLUMNS} gap-3 border-b border-[#1E2633] bg-[#0F141E] px-3 py-2 font-mono text-[10px] uppercase tracking-[0.18em] text-[#6F7789]`}
          >
            <span>Car</span>
            <span>Driver · team</span>
            {elements.map((item) => (
              <span key={item.code} title={item.name}>
                {item.code} <span className="text-[#4A5263]">/{item.allowance ?? "?"}</span>
              </span>
            ))}
            <span className="text-right">PU grid drop</span>
            <span />
          </div>
          <div className="divide-y divide-[#1E2633]">
            {rows.map((car) => (
              <CarRow key={car.seat_id} car={car} codes={codes} />
            ))}
          </div>
          {rows.length === 0 && (
            <p className="p-4 text-sm text-[#8E96A8]">No car has used more units than it is allowed yet.</p>
          )}
        </div>
      </div>
    </ConsolePanel>
  );
}
