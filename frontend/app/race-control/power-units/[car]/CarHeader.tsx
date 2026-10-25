/**
 * The car page's masthead: the number in livery colour, the driver beside it,
 * the season's tally, and a strip to jump to any other car.
 *
 * Server-safe: no state, no effects.
 */
import { ArrowLeft } from "lucide-react";
import Link from "next/link";

import { getTeamColor } from "@/app/lib/teamColors";

import { Panel, rcFont } from "../../components/RaceControlPrimitives";
import {
  OVER_COLOR,
  PENDING_COLOR,
  carHref,
  elementsOver,
  roundRuns,
  totalOverBy,
  type PowerUnitCar,
} from "../powerUnitsModel";

function Tally({ label, value, color }: { label: string; value: string; color?: string }) {
  return (
    <div className="min-w-[96px] rounded border border-[#1E2633] bg-[#0A0E16] px-3 py-2">
      <dt className="font-mono text-[10px] uppercase tracking-[0.16em] text-[#6F7789]">{label}</dt>
      <dd className="mt-1 font-mono text-xl font-black tabular-nums" style={{ color: color ?? "#FFFFFF" }}>
        {value}
      </dd>
    </div>
  );
}

function CarSwitcher({ cars, current }: { cars: PowerUnitCar[]; current: PowerUnitCar }) {
  const ordered = [...cars].sort((a, b) => a.car_number - b.car_number);
  return (
    <nav aria-label="Other cars" className="flex flex-wrap gap-1.5 border-t border-[#1E2633] px-5 py-3">
      {ordered.map((car) => {
        const color = getTeamColor(car.team);
        const active = car.seat_id === current.seat_id;
        return (
          <Link
            key={car.seat_id}
            href={carHref(car)}
            aria-current={active ? "page" : undefined}
            title={`${car.driver.name} · ${car.team}`}
            className={`rounded px-2 py-1 font-mono text-[11px] font-black tabular-nums transition-colors ${
              active ? "text-white" : "text-[#9AA1B0] hover:text-white"
            }`}
            style={{
              background: active ? `${color}55` : `${color}14`,
              boxShadow: `inset 0 0 0 1px ${active ? color : `${color}40`}`,
            }}
          >
            {car.car_number}
            {totalOverBy(car) > 0 && (
              <span
                className="ml-1 inline-block h-1.5 w-1.5 rounded-full align-middle"
                style={{ background: OVER_COLOR }}
              />
            )}
          </Link>
        );
      })}
    </nav>
  );
}

export function CarHeader({ car, cars }: { car: PowerUnitCar; cars: PowerUnitCar[] }) {
  const color = getTeamColor(car.team);
  const others = car.drivers.filter((item) => item.id !== car.driver.id);
  const over = totalOverBy(car);
  const { grid_places: places, pit_lane_starts: pitLane, pending } = car.penalties;
  return (
    <Panel accent={color} className="mb-5">
      <div className="flex flex-col gap-5 p-5 lg:flex-row lg:items-center">
        <div className="flex min-w-0 items-center gap-5">
          <span className="font-mono text-6xl font-black leading-none tabular-nums sm:text-7xl" style={{ color }}>
            {car.car_number}
          </span>
          <div className="min-w-0">
            <Link
              href="/race-control/power-units"
              className="mb-1 inline-flex items-center gap-1 font-mono text-[10px] uppercase tracking-[0.16em] text-[#7F8797] hover:text-white"
            >
              <ArrowLeft className="h-3 w-3" aria-hidden="true" /> All cars
            </Link>
            <h1 className="truncate text-3xl font-black text-white" style={rcFont}>
              {car.driver.name}
            </h1>
            <p className="font-mono text-xs uppercase tracking-[0.16em] text-[#8E96A8]">
              {car.team} · {car.driver.code}
            </p>
            {others.map((item) => (
              <p key={item.id} className="mt-1 text-xs text-[#9EC5FF]">
                Also raced by {item.name} (#{item.car_number}) at {roundRuns(item.rounds)}
              </p>
            ))}
          </div>
        </div>
        <dl className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:ml-auto">
          <Tally
            label="Elements over"
            value={`${elementsOver(car)} / ${car.elements.length}`}
            color={over ? OVER_COLOR : undefined}
          />
          <Tally label="Extra units" value={String(over)} color={over ? OVER_COLOR : undefined} />
          <Tally label="PU grid drop" value={places ? `−${places}` : "0"} color={places ? OVER_COLOR : undefined} />
          <Tally
            label={pending ? "Pending" : "Pit-lane starts"}
            value={String(pending || pitLane)}
            color={pending ? PENDING_COLOR : undefined}
          />
        </dl>
      </div>
      <CarSwitcher cars={cars} current={car} />
    </Panel>
  );
}
