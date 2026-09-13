import { Trophy, Users, Flag, ChevronRight } from "lucide-react";
import Link from "next/link";


import { getChampions, getChampionStats, type SeasonChampion, type StatsResponse } from "@/app/lib/server/champions";
import { getTeamColor } from "@/app/lib/teamColors";
import {
  InlineNotice,
  MetricCard,
  MetricRow,
  Panel,
  SectionHeader,
  StatusPill,
  rcFont,
} from "@/app/race-control/components/RaceControlPrimitives";

import { TitleLeaderboard } from "./TitleLeaderboard";

import type { Metadata } from "next";

/**
 * Hourly background regeneration. The dataset only moves when a title is
 * decided, so this is not about freshness — it caps how long a render made
 * against an unreachable backend stays on the page.
 */
export const revalidate = 3_600;

export const metadata: Metadata = {
  title: "F1 World Champions (1950–Present) | F1 AI",
  description:
    "Every Formula 1 World Drivers' and Constructors' Champion since 1950, with points, wins, and the races that decided each title.",
};

export default async function ChampionsPage() {
  // Both are cached independently, so the slower one never delays the other.
  const [data, stats] = await Promise.all([getChampions(), getChampionStats()]);

  if (!data?.seasons || data.error) {
    return (
      <div className="w-full">
        <InlineNotice title="Could not load champions" tone="error">
          {data?.error ?? "The champions service is unavailable. Please try again shortly."}
        </InlineNotice>
      </div>
    );
  }

  const seasons = data.seasons;

  return (
    <div className="w-full">
      <SectionHeader
        eyebrow="1950 – Present"
        title="World Champions"
        description="Every Formula 1 World Champion since the championship began in 1950 — drivers, constructors, and the races that decided them."
      />

      <ChampionsMetrics seasons={seasons} stats={stats} />

      {(stats?.most_driver_titles?.length || stats?.most_constructor_titles?.length) && (
        <div className="mb-6 grid gap-4 lg:grid-cols-2">
          <TitleLeaderboard title="Most Drivers' Titles" entries={stats?.most_driver_titles ?? []} color="#FFD700" />
          <TitleLeaderboard
            title="Most Constructors' Titles"
            entries={stats?.most_constructor_titles ?? []}
            color="#00D2FF"
          />
        </div>
      )}

      <h2 className="mb-4 text-sm font-bold uppercase tracking-[0.22em] text-[#7F8797]" style={rcFont}>
        Season by season
      </h2>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {seasons.map((season) => (
          <SeasonCard key={season.season} season={season} />
        ))}
      </div>
    </div>
  );
}

function ChampionsMetrics({ seasons, stats }: { seasons: SeasonChampion[]; stats: StatsResponse | null }) {
  const topDriver = stats?.most_driver_titles?.[0];
  const topConstructor = stats?.most_constructor_titles?.[0];
  const current = seasons[0];
  const currentSub = current?.is_in_progress ? `${current.season} — in progress` : `${current?.season} champion`;

  return (
    <MetricRow>
      <MetricCard label="Seasons" value={String(seasons.length)} icon={Flag} color="#E10600" sub="1950 to present" />
      <MetricCard
        label="Most Driver Titles"
        value={topDriver ? String(topDriver.titles) : "—"}
        sub={topDriver?.name}
        icon={Trophy}
        color="#FFD700"
      />
      <MetricCard
        label="Most Constructor Titles"
        value={topConstructor ? String(topConstructor.titles) : "—"}
        sub={topConstructor?.name}
        icon={Users}
        color="#00D2FF"
      />
      <MetricCard
        label="Current Leader"
        value={current?.driver_champion?.code ?? "—"}
        sub={currentSub}
        icon={Trophy}
        color="#00FF78"
      />
    </MetricRow>
  );
}

function SeasonCard({ season }: { season: SeasonChampion }) {
  const driver = season.driver_champion;
  const teamColor = getTeamColor(driver?.team ?? "");

  return (
    <Link href={`/race-control/champions/${season.season}`} className="group block">
      <Panel accent={teamColor} className="h-full p-4 transition-colors hover:border-[#2C3646]">
        <div className="mb-3 flex items-center justify-between">
          <span className="font-mono text-2xl font-black text-white">{season.season}</span>
          {season.is_in_progress ? (
            <StatusPill color="#FFF200">In Progress</StatusPill>
          ) : (
            <ChevronRight className="h-4 w-4 text-[#4A5264] transition-transform group-hover:translate-x-0.5 group-hover:text-white" />
          )}
        </div>

        {driver ? (
          <div>
            <div className="flex items-center gap-2">
              <span className="h-2.5 w-2.5 shrink-0 rounded-full" style={{ background: teamColor }} />
              <span className="truncate text-base font-bold text-white" style={rcFont}>
                {driver.name}
              </span>
            </div>
            <p className="mt-0.5 truncate text-xs text-[#8E96A8]">
              {driver.team ?? "—"} · {driver.points} pts · {driver.wins} {driver.wins === 1 ? "win" : "wins"}
            </p>
          </div>
        ) : (
          <p className="text-sm text-[#6F7789]">No champion recorded</p>
        )}

        <div className="mt-3 border-t border-[#1E2633] pt-2">
          <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[#6F7789]">Constructor</p>
          <p className="truncate text-sm text-[#C6CBD6]">
            {season.constructor_champion ? season.constructor_champion.name : "— (title introduced 1958)"}
          </p>
        </div>
      </Panel>
    </Link>
  );
}
