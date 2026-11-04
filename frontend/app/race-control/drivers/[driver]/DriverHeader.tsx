/**
 * Who the driver is this season, and the headline numbers.
 *
 * Server-safe: no state, no effects.
 */
import Link from "next/link";

import { grandPrixHref, teamHref } from "@/app/lib/entityLinks";
import { driverLabel } from "@/app/ui/names/names";
import { TeamName } from "@/app/ui/names/TeamName";
import { PanelHeading } from "@/app/ui/PanelHeading";

import { MetricCard, MetricRow, Panel, SectionHeader } from "../../components/RaceControlPrimitives";
import { championshipPoints, freshnessLine, ordinalPosition, type DriverProfile } from "../../profiles/profilesModel";

function plural(count: number, word: string): string {
  return `${count} ${word}${count === 1 ? "" : "s"}`;
}

function TeamLine({ profile }: { profile: DriverProfile }) {
  return (
    <p className="mb-5 flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-[#8E96A8]">
      {profile.teams.map((spell) => (
        <span key={spell.id} className="inline-flex items-center gap-2">
          <span className="h-3 w-1 rounded-full" style={{ background: spell.color }} aria-hidden="true" />
          <Link href={teamHref(spell.id)} className="font-bold text-white hover:underline">
            <TeamName name={spell.name} id={spell.id} year={profile.year} />
          </Link>
          {profile.teams.length > 1 && <span className="font-mono text-xs">{spell.rounds_label}</span>}
        </span>
      ))}
      <span>· {freshnessLine(profile.results_through, profile.year)}</span>
    </p>
  );
}

export function DriverHeader({ profile }: { profile: DriverProfile }) {
  const { driver, stats, standing, year } = profile;
  const eyebrow = [driver.number ? `#${driver.number}` : null, driver.code, driver.nationality, String(year)]
    .filter(Boolean)
    .join(" · ");
  return (
    <>
      <div className="[&>div]:mb-3">
        <SectionHeader
          eyebrow={eyebrow}
          title={driverLabel({ name: driver.name, code: driver.code, id: driver.id, year }, "full")}
        />
      </div>
      <TeamLine profile={profile} />
      <MetricRow>
        <MetricCard
          label="Championship"
          value={ordinalPosition(standing.position)}
          sub={championshipPoints(standing.points, profile)}
        />
        <MetricCard
          label="Wins"
          value={String(stats.wins)}
          sub={stats.best_finish ? `Best finish P${stats.best_finish}` : "No classified finish yet"}
        />
        <MetricCard
          label="Podiums"
          value={String(stats.podiums)}
          sub={`${plural(stats.poles, "pole")} · ${plural(stats.fastest_laps, "fastest lap")}`}
        />
        <MetricCard label="Starts" value={String(stats.starts)} sub={plural(stats.retirements, "retirement")} />
      </MetricRow>
    </>
  );
}

export function DriverWins({ profile }: { profile: DriverProfile }) {
  return (
    <Panel as="section" className="mb-5">
      <PanelHeading
        eyebrow={`Races won · ${profile.year}`}
        aside={<span className="text-xs text-[#6F7789]">{profile.wins.length}</span>}
        inset
      />
      {profile.wins.length === 0 ? (
        <p className="p-4 text-sm text-[#8E96A8]">No grand prix wins in {profile.year} yet.</p>
      ) : (
        <ul className="divide-y divide-[#1E2633]">
          {profile.wins.map((win) => (
            <li key={win.round} className="flex items-center gap-4 px-4 py-3 text-sm">
              <span className="w-10 font-mono text-xs font-bold text-[#6F7789]">R{win.round}</span>
              <Link href={grandPrixHref(win.round, "sessions")} className="font-bold text-white hover:underline">
                {win.name}
              </Link>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}
