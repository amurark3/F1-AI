"use client";

import { use } from "react";

import type { TitleEntry } from "@/app/lib/server/champions";
import { getTeamColor } from "@/app/lib/teamColors";
import { Panel } from "@/app/race-control/components/RaceControlPrimitives";
import { DriverName } from "@/app/ui/names/DriverName";
import { TeamName } from "@/app/ui/names/TeamName";
import { PanelHeading } from "@/app/ui/PanelHeading";
import { RankBars, type RankBarItem } from "@/app/ui/RankBars";
import { Section } from "@/app/ui/section/Section";
import { rc } from "@/app/ui/tokens";

import { leaderboardTitle, leaders } from "./championsModel";
import { useChampionStats, type ChampionsSeeds } from "./useChampionsSections";

type Kind = "drivers" | "constructors";

const COPY: Record<Kind, { eyebrow: string; label: string }> = {
  drivers: { eyebrow: "Drivers", label: "Drivers' titles" },
  constructors: { eyebrow: "Constructors", label: "Constructors' titles" },
};

function items(entries: TitleEntry[], kind: Kind): RankBarItem[] {
  return entries.map((entry) => ({
    id: entry.name,
    label:
      kind === "drivers" ? <DriverName name={entry.name} lastName={entry.last_name} /> : <TeamName name={entry.name} />,
    value: entry.titles,
    // Gold is a title; a constructor's bar is its team colour (data).
    color: kind === "drivers" ? rc.gold : getTeamColor(entry.name),
  }));
}

function LeaderboardCard({ entries, kind }: { entries: TitleEntry[]; kind: Kind }) {
  const shown = leaders(entries);
  return (
    <Panel className="p-5 sm:p-6">
      <PanelHeading eyebrow={COPY[kind].eyebrow} title={leaderboardTitle(entries, kind) ?? undefined} />
      {shown.length === 0 ? (
        <p className="text-sm text-rc-ink-3">No titles recorded.</p>
      ) : (
        <RankBars items={items(shown, kind)} label={COPY[kind].label} max={shown[0].titles} />
      )}
    </Panel>
  );
}

/** The two title leaderboards, drivers and constructors. */
export function TitleLeaderboards({ seeds }: { seeds: Pick<ChampionsSeeds, "stats"> }) {
  const stats = useChampionStats(use(seeds.stats));
  return (
    <Section state={stats} label="Title leaderboards" skeletonClassName="h-[420px]">
      {stats.data && (
        <div className="grid gap-5 lg:grid-cols-2">
          <LeaderboardCard entries={stats.data.most_driver_titles ?? []} kind="drivers" />
          <LeaderboardCard entries={stats.data.most_constructor_titles ?? []} kind="constructors" />
        </div>
      )}
    </Section>
  );
}
