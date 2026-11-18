"use client";

import { Suspense } from "react";

import { SectionSkeleton } from "@/app/ui/section/Section";
import { SectionHead } from "@/app/ui/SectionHead";

import { AllocationMatrix } from "./AllocationMatrix";
import { GridPlacesRanking } from "./GridPlacesRanking";
import { HeroFallback, PowerUnitsHero } from "./PowerUnitsHero";

import type { PowerUnitsSeeds } from "./usePowerUnits";

/**
 * The Power Units season page's shell. It renders at once; each section takes
 * over its own server seed behind its own boundary, so none waits for another.
 */
export function PowerUnitsView({ year, seeds }: { year: number; seeds: PowerUnitsSeeds }) {
  return (
    <div className="space-y-14">
      <Suspense fallback={<HeroFallback year={year} />}>
        <PowerUnitsHero year={year} seeds={seeds} />
      </Suspense>

      <section aria-labelledby="pu-allocation">
        <SectionHead
          index={1}
          id="pu-allocation"
          title="Allocation by car"
          aside="Pips = elements used · red = beyond the allocation"
        />
        <Suspense fallback={<SectionSkeleton className="h-[1000px]" />}>
          <AllocationMatrix year={year} seeds={seeds} />
        </Suspense>
      </section>

      <section aria-labelledby="pu-ranking">
        <SectionHead index={2} id="pu-ranking" title="Who paid the most" />
        <Suspense fallback={<SectionSkeleton className="h-[640px]" />}>
          <GridPlacesRanking year={year} seeds={seeds} />
        </Suspense>
      </section>
    </div>
  );
}
