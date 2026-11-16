import Link from "next/link";

import { teamHref } from "@/app/lib/entityLinks";
import { DriverName } from "@/app/ui/names/DriverName";
import { TeamName } from "@/app/ui/names/TeamName";

import { formatPoints, type TeamsIndexTeam } from "../profiles/profilesModel";

import { gapLabel, shareLabel, shareNote, shareSegments, showRounds } from "./teamsIndexModel";

/** Entrance stagger stops growing after this many cards, so the last row isn't late. */
const STAGGER_CAP = 10;
const STAGGER_MS = 40;

interface TeamCardProps {
  team: TeamsIndexTeam;
  leader: TeamsIndexTeam;
  year: number;
  /** The round the results run through; a driver who raced fewer shows which. */
  through: number;
  index: number;
}

/** One team: its place, points, drivers and how its points split between them. */
export function TeamCard({ team, leader, year, through, index }: TeamCardProps) {
  const segments = shareSegments(team);
  return (
    <Link
      href={teamHref(team.id)}
      className="relative block overflow-hidden rounded-md border border-rc-line bg-(--surface) p-[22px] hover:border-rc-ink-3 motion-safe:animate-fade-up"
      style={{ animationDelay: `${Math.min(index, STAGGER_CAP) * STAGGER_MS}ms` }}
    >
      <i aria-hidden="true" className="absolute inset-x-0 top-0 h-[3px]" style={{ backgroundColor: team.color }} />
      <div className="mb-3.5 flex items-center gap-3.5">
        <span className="font-display text-[44px] font-extrabold leading-none text-rc-ink-3">
          {team.position ?? "—"}
        </span>
        <div>
          <h3 className="font-display text-2xl font-extrabold uppercase leading-none text-rc-ink">
            <TeamName name={team.name} fullName={team.full_name} id={team.id} year={year} variant="name" />
          </h3>
          <p className="mt-1 font-mono text-[11px] text-rc-ink-3">
            {formatPoints(team.points)} pts · {gapLabel(team, leader)}
          </p>
        </div>
      </div>
      {team.drivers.map((driver) => (
        <p
          key={driver.id}
          className="flex items-baseline justify-between gap-3 border-b border-rc-line-soft py-1.5 text-[13px] text-rc-ink"
        >
          <span>
            <DriverName
              name={driver.name}
              lastName={driver.last_name}
              code={driver.code}
              id={driver.id}
              year={year}
              variant="full"
            />
            {showRounds(driver, through) && (
              <span className="ml-2 font-mono text-[11px] text-rc-ink-3">{driver.rounds_label}</span>
            )}
          </span>
          <span className="font-mono">{formatPoints(driver.points)}</span>
        </p>
      ))}
      <div
        className="mt-3 flex h-2 gap-0.5 overflow-hidden rounded bg-rc-ink/4"
        role={segments.length > 0 ? "img" : undefined}
        aria-label={segments.length > 0 ? shareLabel(team, year) : undefined}
      >
        {segments.map(({ driver, points, percent, opacity }) => (
          <b
            key={driver.id}
            title={`${driver.name} · ${formatPoints(points)} pts`}
            className="block h-full motion-safe:animate-fill-x"
            style={{ width: `${percent}%`, backgroundColor: team.color, opacity }}
          />
        ))}
      </div>
      <p className="mt-2 text-xs text-rc-ink-3">{shareNote(team, year)}</p>
    </Link>
  );
}
