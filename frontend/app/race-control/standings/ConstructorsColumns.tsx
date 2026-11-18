"use client";

import { use } from "react";

import { getTeamColor } from "@/app/lib/teamColors";
import { TeamName } from "@/app/ui/names/TeamName";
import { RankBars, type RankBarItem } from "@/app/ui/RankBars";
import { Section } from "@/app/ui/section/Section";

import { TeamLink } from "../profiles/EntityLinks";

import { columnsOf } from "./standingsModel";
import { formatPoints, type Team } from "./teamsModel";
import { useTeams, type StandingsSeeds } from "./useStandingsSections";

function teamItems(rows: readonly Team[]): RankBarItem[] {
  return rows.map((row) => ({
    id: row.slug,
    rank: row.position,
    label: (
      <TeamLink id={row.slug} name={row.name}>
        <TeamName id={row.slug} name={row.name} />
      </TeamLink>
    ),
    value: row.points,
    valueText: formatPoints(row.points),
    color: getTeamColor(row.name),
  }));
}

function placesLabel(rows: readonly Team[]): string {
  return `Constructors' championship points, places ${rows[0].position}–${rows[rows.length - 1].position}`;
}

/** The constructors in two columns, read down each; both bars share one scale. */
export function ConstructorsColumns({ year, seeds }: { year: number; seeds: Pick<StandingsSeeds, "teams"> }) {
  const teams = useTeams(year, use(seeds.teams));
  const rows = teams.data?.teams ?? [];
  const max = rows[0]?.points;

  return (
    <Section state={teams} label="Constructors' standings" skeletonClassName="h-[230px]">
      <div className="grid gap-x-10 lg:grid-cols-2">
        {columnsOf(rows)
          .filter((column) => column.length > 0)
          .map((column) => (
            <RankBars
              key={column[0].slug}
              items={teamItems(column)}
              label={placesLabel(column)}
              max={max}
              size="large"
            />
          ))}
      </div>
    </Section>
  );
}
