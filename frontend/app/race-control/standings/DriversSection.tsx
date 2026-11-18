"use client";

import { use } from "react";

import { getTeamColor } from "@/app/lib/teamColors";
import { DriverName } from "@/app/ui/names/DriverName";
import { RankBars, type RankBarItem } from "@/app/ui/RankBars";
import { Section } from "@/app/ui/section/Section";

import { StateTag } from "../grand-prix/StateTag";
import { DriverLink } from "../profiles/EntityLinks";

import { gapAside, isDecided } from "./standingsModel";
import { formatPoints, type DriverStanding } from "./teamsModel";
import { useProgression, useTeams, type StandingsSeeds } from "./useStandingsSections";

function driverItems(rows: readonly DriverStanding[], decided: boolean): RankBarItem[] {
  return rows.map((row, index) => ({
    id: row.driver,
    rank: row.position,
    label: (
      <DriverLink code={row.code} name={row.driver}>
        <DriverName name={row.driver} code={row.code} variant="full" />
      </DriverLink>
    ),
    detail: row.code,
    tag: index === 0 && decided ? <StateTag tone="gold">Champion</StateTag> : undefined,
    value: row.points,
    valueText: formatPoints(row.points),
    aside: gapAside(row.points, rows[0].points, index),
    color: getTeamColor(row.team),
  }));
}

/** The drivers' order: every driver's points and gap to the leader, the champion tagged once the title is won. */
export function DriversSection({
  year,
  seeds,
}: {
  year: number;
  seeds: Pick<StandingsSeeds, "teams" | "progression">;
}) {
  const teams = useTeams(year, use(seeds.teams));
  const progression = useProgression(year, use(seeds.progression));
  const rows = teams.data?.drivers ?? [];
  const decided = isDecided("drivers", undefined, progression.data);

  return (
    <Section state={teams} label="Drivers' standings" skeletonClassName="h-[840px]">
      <RankBars items={driverItems(rows, decided)} label="Drivers' championship points" />
    </Section>
  );
}
