"use client";

import { Flag, Medal, Timer, Trophy } from "lucide-react";
import { useRouter } from "next/navigation";

import { teamHref } from "@/app/lib/entityLinks";

import { MetricCard, MetricRow, SectionHeader } from "../../components/RaceControlPrimitives";
import {
  formatPoints,
  freshnessLine,
  ordinalPosition,
  type DirectoryTeam,
  type TeamProfile,
} from "../../profiles/profilesModel";

/** The team dropdown: picking a team opens its page. */
function TeamSwitcher({ teams, current }: { teams: DirectoryTeam[]; current: string }) {
  const router = useRouter();
  if (teams.length === 0) return null;
  return (
    <label className="block w-full sm:w-72">
      <span className="mb-2 block text-[10px] font-black uppercase tracking-[0.18em] text-neutral-500">Team</span>
      <select
        value={current}
        onChange={(event) => router.push(teamHref(event.target.value))}
        className="w-full rounded-lg border border-white/10 bg-[#101520] px-3 py-2 text-sm text-white outline-none focus-visible:ring-2 focus-visible:ring-[#00FF78]/50"
      >
        {teams.map((team) => (
          <option key={team.id} value={team.id}>
            {team.position ? `P${team.position} · ` : ""}
            {team.name}
          </option>
        ))}
      </select>
    </label>
  );
}

export function TeamHeader({ profile, teams }: { profile: TeamProfile; teams: DirectoryTeam[] }) {
  const { team, year } = profile;
  return (
    <>
      <div className="mb-5 flex flex-col gap-4 border-b border-[#1E2633] pb-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0 [&>div]:mb-0 [&>div]:border-0 [&>div]:pb-0">
          <SectionHeader
            eyebrow={`Teams & Drivers · ${year}`}
            title={team.full_name}
            description={freshnessLine(profile.results_through, year)}
          />
        </div>
        <TeamSwitcher teams={teams} current={team.id} />
      </div>
      <div className="mb-5 h-1 rounded-full" style={{ background: team.color }} aria-hidden="true" />
      <MetricRow>
        <MetricCard
          label="Championship"
          value={ordinalPosition(team.position)}
          sub={`${formatPoints(team.points)} pts`}
          icon={Trophy}
          color={team.color}
        />
        <MetricCard label="Wins" value={String(team.wins)} sub="Grand prix wins" icon={Flag} color="#FFD15C" />
        <MetricCard
          label="Podiums"
          value={String(team.podiums)}
          sub="Top-three finishes"
          icon={Medal}
          color="#E8E8E8"
        />
        <MetricCard label="Poles" value={String(team.poles)} sub="Grand prix poles" icon={Timer} color="#3671C6" />
      </MetricRow>
    </>
  );
}
