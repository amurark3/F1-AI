import { ArrowLeft, Trophy, Users, Flag } from "lucide-react";
import Link from "next/link";
import { notFound } from "next/navigation";


import {
  getSeasonDetail,
  listSeasonYears,
  type DriverChampion,
  type RaceWinner,
  type SeasonDetail,
} from "@/app/lib/server/champions";
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

import type { Metadata } from "next";

interface SeasonPageProps {
  params: Promise<{ year: string }>;
}

/**
 * Hourly background regeneration. The dataset only moves when a title is
 * decided, so this is not about freshness — it caps how long a render made
 * against an unreachable backend stays on the page.
 */
export const revalidate = 3_600;

/**
 * Prerender every season the archive knows about.
 *
 * `dynamicParams` stays on so a season added between builds still resolves —
 * it renders on demand and is then cached like the rest.
 */
export async function generateStaticParams(): Promise<Array<{ year: string }>> {
  const years = await listSeasonYears();
  return years.map((year) => ({ year }));
}

export async function generateMetadata({ params }: SeasonPageProps): Promise<Metadata> {
  const { year } = await params;
  const data = await getSeasonDetail(year);
  const champion = data?.driver_champion?.name;

  if (!champion) {
    return { title: `${year} F1 Season | F1 AI` };
  }

  return {
    title: `${year} F1 Season — ${champion} | F1 AI`,
    description: `${champion} took the ${year} Formula 1 World Championship with ${data.driver_champion?.points} points and ${data.driver_champion?.wins} wins. Full race winners and constructors' title.`,
  };
}

export default async function SeasonDetailPage({ params }: SeasonPageProps) {
  const { year } = await params;
  const data = await getSeasonDetail(year);

  // A season the dataset has never heard of is a genuine 404, not an outage.
  if (data?.error) notFound();

  if (!data) {
    return (
      <div className="w-full">
        <BackLink />
        <InlineNotice title={`Season ${year} unavailable`} tone="error">
          Could not load this season.
        </InlineNotice>
      </div>
    );
  }

  const driver = data.driver_champion;
  const teamColor = getTeamColor(driver?.team ?? "");
  const winners = data.race_winners ?? [];

  return (
    <div className="w-full">
      <BackLink />
      <SectionHeader
        eyebrow={data.is_in_progress ? "Season in progress" : "Champions"}
        title={`${data.season} Season`}
        description={
          data.is_in_progress ? "The title is not yet decided — current championship leaders are shown." : undefined
        }
      />

      <SeasonChampionMetrics data={data} driver={driver} teamColor={teamColor} raceCount={winners.length} />

      {data.runner_up && (
        <p className="mb-6 text-sm text-[#8E96A8]">
          Runner-up: <span className="font-semibold text-white">{data.runner_up.name}</span> ({data.runner_up.points}{" "}
          pts)
        </p>
      )}

      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-bold uppercase tracking-[0.22em] text-[#7F8797]" style={rcFont}>
          Race winners
        </h2>
        {data.is_in_progress && <StatusPill color="#FFF200">In Progress</StatusPill>}
      </div>

      <RaceWinnersList winners={winners} />
    </div>
  );
}

function SeasonChampionMetrics({
  data,
  driver,
  teamColor,
  raceCount,
}: {
  data: SeasonDetail;
  driver: DriverChampion | null;
  teamColor: string;
  raceCount: number;
}) {
  return (
    <MetricRow>
      <MetricCard
        label={data.is_in_progress ? "Championship Leader" : "World Champion"}
        value={driver?.code ?? "—"}
        sub={driver?.name}
        icon={Trophy}
        color={teamColor}
      />
      <MetricCard
        label="Points"
        value={driver ? String(driver.points) : "—"}
        sub={driver?.team ?? undefined}
        icon={Flag}
        color="#00FF78"
      />
      <MetricCard
        label="Wins"
        value={driver ? String(driver.wins) : "—"}
        sub={`of ${raceCount} races`}
        icon={Trophy}
        color="#FFD700"
      />
      <MetricCard
        label="Constructors' Champion"
        value={data.constructor_champion ? "" : "—"}
        sub={data.constructor_champion?.name ?? "Title introduced in 1958"}
        icon={Users}
        color="#00D2FF"
      />
    </MetricRow>
  );
}

function RaceWinnersList({ winners }: { winners: RaceWinner[] }) {
  if (winners.length === 0) {
    return (
      <InlineNotice title="No races yet" tone="info">
        No completed races recorded for this season.
      </InlineNotice>
    );
  }

  return (
    <Panel className="divide-y divide-[#1E2633]">
      {winners.map((race) => {
        const color = getTeamColor(race.team ?? "");
        return (
          <div key={race.round} className="flex items-center gap-3 px-4 py-2.5">
            <span className="w-8 shrink-0 font-mono text-sm font-bold text-[#6F7789]">R{race.round}</span>
            <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: color }} />
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-semibold text-white">{race.winner}</p>
              <p className="truncate text-xs text-[#8E96A8]">{race.race_name}</p>
            </div>
            <span className="hidden shrink-0 text-xs text-[#6F7789] sm:block">{race.team}</span>
          </div>
        );
      })}
    </Panel>
  );
}

function BackLink() {
  return (
    <Link
      href="/race-control/champions"
      className="mb-5 inline-flex items-center gap-1.5 text-xs font-bold uppercase tracking-[0.16em] text-[#8E96A8] transition-colors hover:text-white"
    >
      <ArrowLeft className="h-3.5 w-3.5" /> All champions
    </Link>
  );
}
