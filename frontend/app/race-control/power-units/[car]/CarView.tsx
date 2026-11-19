"use client";

import Link from "next/link";
import { Suspense } from "react";

import { SectionSkeleton } from "@/app/ui/section/Section";
import { SectionHead } from "@/app/ui/SectionHead";

import { CarHero, CarHeroFallback } from "./CarHero";
import { CarSourceNote } from "./CarSourceNote";
import { CarStrip } from "./CarStrip";
import { ElementLedger } from "./ElementLedger";
import { SeasonTimeline } from "./SeasonTimeline";
import { WeekendLog } from "./WeekendLog";

import type { CarSectionProps } from "./useCar";

function SectionFallback({
  index,
  title,
  aside,
  height,
}: {
  index: number;
  title: string;
  aside?: string;
  height: string;
}) {
  return (
    <section>
      <SectionHead index={index} title={title} aside={aside} />
      <SectionSkeleton className={height} />
    </section>
  );
}

/**
 * The car page's shell. It renders at once, with the `h1` from the URL; each
 * section takes up the server's payload behind its own boundary.
 */
export function CarView(props: CarSectionProps) {
  const { year, segment } = props;
  return (
    <div className="w-full min-w-0">
      <div className="flex flex-col items-start gap-2.5 sm:flex-row sm:items-center sm:gap-x-5">
        <Link
          href="/race-control/power-units"
          className="flex-none font-mono text-[11px] font-medium uppercase leading-none tracking-[0.14em] text-rc-ink-3 hover:text-rc-ink"
        >
          ← All cars
        </Link>
        <Suspense fallback={<SectionSkeleton className="h-8 w-full" />}>
          <CarStrip {...props} />
        </Suspense>
      </div>
      <div className="mt-5">
        <Suspense fallback={<CarHeroFallback year={year} segment={segment} />}>
          <CarHero {...props} />
        </Suspense>
      </div>
      <div className="mt-14 space-y-14">
        <Suspense
          fallback={<SectionFallback index={1} title="Elements" aside="One tile per unit fitted" height="h-[720px]" />}
        >
          <ElementLedger {...props} />
        </Suspense>
        <Suspense
          fallback={
            <SectionFallback
              index={2}
              title="Season"
              aside="One cell per Grand Prix · select one for the weekend"
              height="h-[260px]"
            />
          }
        >
          <SeasonTimeline {...props} />
        </Suspense>
        <Suspense fallback={<SectionFallback index={3} title="Weekend by weekend" height="h-[1200px]" />}>
          <WeekendLog {...props} />
        </Suspense>
      </div>
      <Suspense fallback={null}>
        <CarSourceNote {...props} />
      </Suspense>
    </div>
  );
}
