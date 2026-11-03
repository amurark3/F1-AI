/**
 * Who drives for the team, and what it has won.
 *
 * The current line-up is whoever started the team's latest race. Anyone else
 * who raced for it this season is listed beneath with their rounds, so a seat
 * swap is visible rather than silently folded into one name.
 *
 * Server-safe: no state, no effects.
 */
import Link from "next/link";

import { driverHref, grandPrixHref } from "@/app/lib/entityLinks";
import { PanelHeading } from "@/app/ui/PanelHeading";

import { Panel } from "../../components/RaceControlPrimitives";
import { formatPoints, ordinalPosition, type TeamDriver, type TeamProfile } from "../../profiles/profilesModel";

function DriverCard({ driver, color }: { driver: TeamDriver; color: string }) {
  return (
    <Link
      href={driverHref(driver.id)}
      className="group flex min-w-0 items-center gap-4 rounded-md border border-[#1E2633] bg-[#101520] p-4 transition-colors hover:border-white/20"
    >
      <span className="font-mono text-3xl font-black tabular-nums" style={{ color }}>
        {driver.number ?? "—"}
      </span>
      <span className="min-w-0">
        <span className="block truncate text-base font-bold text-white group-hover:underline">{driver.name}</span>
        <span className="block text-xs text-[#8E96A8]">
          Championship {ordinalPosition(driver.position)} · {formatPoints(driver.points)} pts · {driver.wins} win
          {driver.wins === 1 ? "" : "s"}
        </span>
      </span>
    </Link>
  );
}

function AlsoRaced({ drivers }: { drivers: TeamDriver[] }) {
  if (drivers.length === 0) return null;
  return (
    <p className="mt-3 text-sm text-[#8E96A8]">
      <span className="font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-[#6F7789]">Also raced · </span>
      {drivers.map((driver, index) => (
        <span key={driver.id}>
          {index > 0 && ", "}
          <Link href={driverHref(driver.id)} className="font-bold text-white hover:underline">
            {driver.name}
          </Link>{" "}
          <span className="font-mono text-xs">{driver.rounds_label}</span>
        </span>
      ))}
    </p>
  );
}

export function TeamLineUp({ profile }: { profile: TeamProfile }) {
  const current = profile.drivers.filter((driver) => driver.current);
  const others = profile.drivers.filter((driver) => !driver.current);
  return (
    <Panel as="section" className="mb-5">
      <PanelHeading
        eyebrow="Drivers"
        aside={<span className="text-xs text-[#6F7789]">Started the latest race</span>}
        inset
      />
      <div className="p-4">
        <div className="grid gap-3 sm:grid-cols-2">
          {current.map((driver) => (
            <DriverCard key={driver.id} driver={driver} color={profile.team.color} />
          ))}
        </div>
        <AlsoRaced drivers={others} />
      </div>
    </Panel>
  );
}

export function TeamWins({ profile }: { profile: TeamProfile }) {
  const names = new Map(profile.drivers.map((driver) => [driver.id, driver.name]));
  return (
    <Panel as="section" className="mb-5">
      <PanelHeading
        eyebrow={`Race wins · ${profile.year}`}
        aside={<span className="text-xs text-[#6F7789]">{profile.wins.length}</span>}
        inset
      />
      {profile.wins.length === 0 ? (
        <p className="p-4 text-sm text-[#8E96A8]">No grand prix wins in {profile.year} yet.</p>
      ) : (
        <ul className="divide-y divide-[#1E2633]">
          {profile.wins.map((win) => (
            <li key={win.round} className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-3 text-sm">
              <span className="w-10 font-mono text-xs font-bold text-[#6F7789]">R{win.round}</span>
              <Link
                href={grandPrixHref(win.round, "sessions")}
                className="min-w-0 flex-1 font-bold text-white hover:underline"
              >
                {win.name}
              </Link>
              <Link href={driverHref(win.driver_id)} className="text-[#B7BDCA] hover:text-white hover:underline">
                {names.get(win.driver_id) ?? win.driver_id}
              </Link>
              <span className="font-mono text-xs text-[#6F7789]">
                {win.grid ? `from P${win.grid}` : "grid not recorded"}
              </span>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
