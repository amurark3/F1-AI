"use client";

import { Suspense, use } from "react";

import { Section, SectionSkeleton } from "@/app/ui/section/Section";
import { SectionHead } from "@/app/ui/SectionHead";

import { ConstructorsColumns } from "./ConstructorsColumns";
import { DriversSection } from "./DriversSection";
import { StandingsHero } from "./StandingsHero";
import { TitleRaceChart } from "./TitleRaceChart";
import { useProgression, type StandingsSeeds } from "./useStandingsSections";

function TitleRaceSection({ year, seeds }: { year: number; seeds: Pick<StandingsSeeds, "progression"> }) {
  const progression = useProgression(year, use(seeds.progression));
  return (
    <Section state={progression} label="Title race" skeletonClassName="h-[380px]">
      {progression.data && <TitleRaceChart progression={progression.data} />}
    </Section>
  );
}

/**
 * The Standings page's shell. It renders at once; each section takes over its
 * own server seed (`use`) behind its own boundary, so none waits for another.
 */
export function StandingsView({ year, seeds }: { year: number; seeds: StandingsSeeds }) {
  return (
    <div className="space-y-14">
      <Suspense fallback={<SectionSkeleton className="h-[420px]" />}>
        <StandingsHero year={year} seeds={seeds} />
      </Suspense>

      <section aria-labelledby="drivers-order">
        <SectionHead index={1} id="drivers-order" title="Drivers' order" aside="Points · gap to the leader" />
        <div className="grid items-start gap-5 lg:grid-cols-[7fr_5fr]">
          <Suspense fallback={<SectionSkeleton className="h-[840px]" />}>
            <DriversSection year={year} seeds={seeds} />
          </Suspense>
          <div className="min-w-0 lg:sticky lg:top-21">
            <Suspense fallback={<SectionSkeleton className="h-[380px]" />}>
              <TitleRaceSection year={year} seeds={seeds} />
            </Suspense>
          </div>
        </div>
      </section>

      <section aria-labelledby="constructors">
        {/* P5.3b: the clinch calculator's line goes in this SectionHead's aside. */}
        <SectionHead index={2} id="constructors" title="Constructors" />
        <Suspense fallback={<SectionSkeleton className="h-[230px]" />}>
          <ConstructorsColumns year={year} seeds={seeds} />
        </Suspense>
      </section>
    </div>
  );
}
