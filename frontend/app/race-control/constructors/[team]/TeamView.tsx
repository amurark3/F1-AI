"use client";

import { API_BASE } from "@/app/constants/api";
import { Section } from "@/app/ui/section/Section";
import { useSection } from "@/app/ui/section/useSection";
import { SectionHead } from "@/app/ui/SectionHead";
import { SourceBadge } from "@/app/ui/SourceBadge";

import { CarAllocations } from "../../profiles/CarAllocations";
import { MissingProfile } from "../../profiles/MissingProfile";
import { isTeamProfile, profilesUrl, type TeamProfile, type TeamProfileResponse } from "../../profiles/profilesModel";

import { PointsByWeekend } from "./PointsByWeekend";
import { TeamHeatGrid } from "./TeamHeatGrid";
import { TeamHero } from "./TeamHero";
import { TeamKpis } from "./TeamKpis";

const REFRESH = { revalidateOnFocus: false, dedupingInterval: 180_000 };

function TeamSeason({ profile }: { profile: TeamProfile }) {
  const through = profile.results_through;
  return (
    <div>
      <TeamHero profile={profile} />
      <TeamKpis profile={profile} />
      <section className="pt-16">
        <SectionHead
          index={1}
          title="Every finish"
          aside={through ? `Race result by round · through R${through.round}` : "Race result by round"}
        />
        <TeamHeatGrid profile={profile} />
      </section>
      <section className="pt-16">
        <SectionHead index={2} title="Points by weekend" />
        <PointsByWeekend profile={profile} />
      </section>
      <CarAllocations year={profile.year} scope={{ kind: "team", teamId: profile.team.id }} />
      <SourceBadge freshness={profile} className="mt-10" />
    </div>
  );
}

interface TeamViewProps {
  year: number;
  teamId: string;
  /** The server render's answer; null renders the skeleton and fetches in the browser. */
  seed: TeamProfileResponse | null;
}

/** The team's season: one section on `/api/profiles/{year}/teams/{id}`, with the power units on their own endpoint. */
export function TeamView({ year, teamId, seed }: TeamViewProps) {
  const state = useSection<TeamProfileResponse>(profilesUrl(API_BASE, year, `teams/${encodeURIComponent(teamId)}`), {
    seed,
    config: REFRESH,
  });
  const { data } = state;
  return (
    <Section
      state={state}
      label={isTeamProfile(data) ? `${data.team.name} season` : "Team season"}
      skeletonClassName="h-[720px]"
    >
      {isTeamProfile(data) ? (
        <TeamSeason profile={data} />
      ) : (
        <MissingProfile
          year={year}
          what="team"
          id={teamId}
          backHref="/race-control/constructors"
          backLabel="All teams"
        />
      )}
    </Section>
  );
}
