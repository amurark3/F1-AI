/**
 * Who drives for the team: one row per car of the latest race, with its
 * number, and anyone else who raced for the team beneath with their rounds, so
 * a seat swap is visible rather than folded into one name.
 */
import Link from "next/link";

import { driverHref } from "@/app/lib/entityLinks";
import { DriverName } from "@/app/ui/names/DriverName";

import { formatPoints, ordinalPosition, type TeamDriver, type TeamProfile } from "../../profiles/profilesModel";

import { driverRecord } from "./teamModel";

function count(value: number, word: string): string {
  return `${value} ${word}${value === 1 ? "" : "s"}`;
}

function Car({ driver, profile }: { driver: TeamDriver; profile: TeamProfile }) {
  const { wins, poles } = driverRecord(profile, driver.id);
  return (
    <div className="grid grid-cols-[auto_minmax(0,1fr)] items-center gap-5 px-6 py-6 sm:gap-6 sm:px-8 [&+&]:border-t [&+&]:border-rc-line">
      <span
        aria-hidden="true"
        className="min-w-[2ch] text-right font-display text-[64px] font-extrabold leading-[0.85] sm:min-w-[120px] sm:text-[96px]"
        style={{ color: profile.team.color }}
      >
        {driver.number ?? "—"}
      </span>
      {driver.number !== null && <span className="sr-only">Car {driver.number}</span>}
      <div className="min-w-0">
        <h2 className="font-display text-[32px] font-extrabold uppercase leading-none text-rc-ink">
          <Link href={driverHref(driver.id)} className="hover:underline">
            <DriverName
              name={driver.name}
              lastName={driver.last_name}
              code={driver.code}
              id={driver.id}
              year={profile.year}
            />
          </Link>
        </h2>
        <p className="mt-1.5 font-mono text-xs font-medium uppercase leading-normal tracking-[0.06em] text-rc-ink-3">
          {formatPoints(driver.points)} pts · {ordinalPosition(driver.position)} · {count(wins, "win")} ·{" "}
          {count(poles, "pole")}
        </p>
      </div>
    </div>
  );
}

function AlsoRaced({ drivers, year }: { drivers: TeamDriver[]; year: number }) {
  return (
    <p className="border-t border-rc-line px-6 py-4 font-mono text-[11px] text-rc-ink-3 sm:px-8">
      Also raced:{" "}
      {drivers.map((driver, index) => (
        <span key={driver.id}>
          {index > 0 && ", "}
          <Link href={driverHref(driver.id)} className="text-rc-ink-2 hover:underline">
            <DriverName
              variant="codeLast"
              name={driver.name}
              lastName={driver.last_name}
              code={driver.code}
              id={driver.id}
              year={year}
            />
          </Link>{" "}
          {driver.rounds_label}
        </span>
      ))}
    </p>
  );
}

export function TeamLineUp({ profile }: { profile: TeamProfile }) {
  const current = profile.drivers.filter((driver) => driver.current);
  const others = profile.drivers.filter((driver) => !driver.current);
  return (
    <div>
      {current.map((driver) => (
        <Car key={driver.id} driver={driver} profile={profile} />
      ))}
      {others.length > 0 && <AlsoRaced drivers={others} year={profile.year} />}
    </div>
  );
}
