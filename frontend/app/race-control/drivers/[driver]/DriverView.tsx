"use client";

import { API_BASE } from "@/app/constants/api";
import { Section } from "@/app/ui/section/Section";
import { useSection } from "@/app/ui/section/useSection";
import { SectionHead } from "@/app/ui/SectionHead";
import { SourceBadge } from "@/app/ui/SourceBadge";

import { CarAllocations } from "../../profiles/CarAllocations";
import { MissingProfile } from "../../profiles/MissingProfile";
import {
  isDriverProfile,
  profilesUrl,
  type DriverProfile,
  type DriverProfileResponse,
} from "../../profiles/profilesModel";

import { DriverHero } from "./DriverHero";
import { DriverKpis } from "./DriverKpis";
import { GridToFinish } from "./GridToFinish";
import { PointsPerRace } from "./PointsPerRace";
import { TeammateBattle } from "./TeammateBattle";

const REFRESH = { revalidateOnFocus: false, dedupingInterval: 180_000 };

function DriverSeason({ profile }: { profile: DriverProfile }) {
  return (
    <div>
      <DriverHero profile={profile} />
      <DriverKpis profile={profile} />
      <section className="pt-16">
        <SectionHead index={1} title="The season, race by race" />
        <GridToFinish profile={profile} />
        <div className="mt-5 grid gap-5 lg:grid-cols-2">
          <TeammateBattle profile={profile} />
          <PointsPerRace profile={profile} />
        </div>
      </section>
      <CarAllocations
        year={profile.year}
        scope={{ kind: "driver", driverId: profile.driver.id, lastName: profile.driver.last_name }}
      />
      <SourceBadge freshness={profile} className="mt-10" />
    </div>
  );
}

interface DriverViewProps {
  year: number;
  driverId: string;
  /** The server render's answer; null renders the skeleton and fetches in the browser. */
  seed: DriverProfileResponse | null;
}

/** The driver's season: one section on `/api/profiles/{year}/drivers/{id}`, with the power unit on its own endpoint. */
export function DriverView({ year, driverId, seed }: DriverViewProps) {
  const state = useSection<DriverProfileResponse>(
    profilesUrl(API_BASE, year, `drivers/${encodeURIComponent(driverId)}`),
    { seed, config: REFRESH },
  );
  const { data } = state;
  return (
    <Section
      state={state}
      label={isDriverProfile(data) ? `${data.driver.name} season` : "Driver season"}
      skeletonClassName="h-[760px]"
    >
      {isDriverProfile(data) ? (
        <DriverSeason profile={data} />
      ) : (
        <MissingProfile
          year={year}
          what="driver"
          id={driverId}
          backHref="/race-control/constructors"
          backLabel="All teams"
        />
      )}
    </Section>
  );
}
