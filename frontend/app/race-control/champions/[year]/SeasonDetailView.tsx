"use client";

import Link from "next/link";
import { Suspense, type ReactNode } from "react";

import { FIRST_SEASON, type SeasonDetail } from "@/app/lib/server/champions";
import { SectionSkeleton } from "@/app/ui/section/Section";
import { SectionHead } from "@/app/ui/SectionHead";

import { RoundByRound } from "./RoundByRound";
import { HeroFallback, SeasonHero } from "./SeasonHero";
import { RoundsAside, WinnerRows } from "./WinnerRows";

const CRUMB =
  "inline-flex min-h-11 items-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-[0.16em] text-rc-ink-3 transition-colors hover:text-rc-ink";

function Step({ year, children }: { year: number; children: ReactNode }) {
  return (
    <Link href={`/race-control/champions/${year}`} prefetch={false} aria-label={`${year} season`} className={CRUMB}>
      {children}
    </Link>
  );
}

interface SeasonDetailViewProps {
  year: number;
  /** The newest season: the stepper stops here, and only its pages link to drivers and teams. */
  latest: number;
  seed: Promise<SeasonDetail | null>;
}

/**
 * The season page's shell. It paints at once; each section takes the server's
 * seed (`use`) behind its own boundary, and all share one request.
 */
export function SeasonDetailView({ year, latest, seed }: SeasonDetailViewProps) {
  return (
    <div className="w-full">
      <nav aria-label="Seasons" className="flex items-center justify-between gap-4">
        <Link href="/race-control/champions" className={CRUMB}>
          <span aria-hidden="true">←</span> All champions
        </Link>
        <span className="flex gap-[22px]">
          {year > FIRST_SEASON && (
            <Step year={year - 1}>
              <span aria-hidden="true">‹</span> {year - 1}
            </Step>
          )}
          {year < latest && (
            <Step year={year + 1}>
              {year + 1} <span aria-hidden="true">›</span>
            </Step>
          )}
        </span>
      </nav>

      <section aria-label={`${year} season`} className="mt-3">
        <Suspense
          fallback={
            <>
              <HeroFallback year={year} />
              <SectionSkeleton className="h-[330px]" />
            </>
          }
        >
          <SeasonHero year={year} seed={seed} />
        </Suspense>
      </section>

      <section aria-labelledby="race-winners" className="mt-14">
        <SectionHead
          index={1}
          id="race-winners"
          title="Race winners"
          aside={
            <Suspense fallback={null}>
              <RoundsAside year={year} seed={seed} />
            </Suspense>
          }
        />
        <Suspense fallback={<SectionSkeleton className="h-[220px]" />}>
          <RoundByRound year={year} seed={seed} />
        </Suspense>
        <Suspense fallback={<SectionSkeleton className="mt-6 h-[560px]" />}>
          <WinnerRows year={year} seed={seed} linkable={year === latest} />
        </Suspense>
      </section>
    </div>
  );
}
