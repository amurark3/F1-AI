"use client";

import { Suspense } from "react";

import { SectionSkeleton } from "@/app/ui/section/Section";
import { SectionHead } from "@/app/ui/SectionHead";

import { ChampionHero } from "./ChampionHero";
import { ChampionWall } from "./ChampionWall";
import { TitleLeaderboards } from "./TitleLeaderboard";

import type { ChampionsSeeds } from "./useChampionsSections";

/**
 * The Champions page's shell. It renders at once; each section takes over its
 * own server seed (`use`) behind its own boundary, so none waits for another.
 */
export function ChampionsView({ seeds }: { seeds: ChampionsSeeds }) {
  return (
    <div className="space-y-14">
      <Suspense fallback={<SectionSkeleton className="h-[360px]" />}>
        <ChampionHero seeds={seeds} />
      </Suspense>

      <section aria-labelledby="most-titles">
        <SectionHead index={1} id="most-titles" title="Most titles" />
        <Suspense fallback={<SectionSkeleton className="h-[420px]" />}>
          <TitleLeaderboards seeds={seeds} />
        </Suspense>
      </section>

      <section aria-labelledby="every-champion">
        <SectionHead
          index={2}
          id="every-champion"
          title="Every champion"
          aside="Bar = constructors' champion that year"
        />
        <Suspense fallback={<SectionSkeleton className="h-[640px]" />}>
          <ChampionWall seeds={seeds} />
        </Suspense>
      </section>
    </div>
  );
}
