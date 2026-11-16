"use client";

import { API_BASE } from "@/app/constants/api";
import { PageHero } from "@/app/ui/PageHero";
import { Section } from "@/app/ui/section/Section";
import { useSection } from "@/app/ui/section/useSection";
import { SourceBadge } from "@/app/ui/SourceBadge";

import { profilesUrl, type TeamsIndex } from "../profiles/profilesModel";

import { TeamCard } from "./TeamCard";
import { teamsTitle } from "./teamsIndexModel";

const REFRESH = { revalidateOnFocus: false, dedupingInterval: 180_000 };

interface TeamsIndexViewProps {
  year: number;
  /** The server render's payload; null renders the skeleton and fetches in the browser. */
  seed: TeamsIndex | null;
}

function TeamsBody({ data, year }: { data: TeamsIndex; year: number }) {
  const [leader] = data.teams;
  if (!leader) {
    return <p className="text-sm text-rc-ink-3">No {year} teams published yet.</p>;
  }
  const through = data.results_through?.round ?? 0;
  return (
    <>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {data.teams.map((team, index) => (
          <TeamCard key={team.id} team={team} leader={leader} year={year} through={through} index={index} />
        ))}
      </div>
      <SourceBadge freshness={data} className="mt-6" />
    </>
  );
}

/** The Teams index: every team in championship order, with how its points split between its drivers. */
export function TeamsIndexView({ year, seed }: TeamsIndexViewProps) {
  const state = useSection<TeamsIndex>(profilesUrl(API_BASE, year, "teams"), { seed, config: REFRESH });
  const { data } = state;
  const round = data?.as_of_round;
  return (
    <div>
      <PageHero
        eyebrow={`${year} constructors${round ? ` · after round ${round}` : ""}`}
        title={data ? teamsTitle(data.teams.length) : "Teams"}
        meta="Ordered by the championship. The bar under each team shows how its points split between its drivers."
      />
      <div className="mt-7">
        <Section state={state} label="Teams" skeletonClassName="h-[640px]">
          {data && <TeamsBody data={data} year={year} />}
        </Section>
      </div>
    </div>
  );
}
