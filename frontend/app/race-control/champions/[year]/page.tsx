import { notFound } from "next/navigation";

import { FIRST_SEASON, getSeasonDetail, listSeasonYears } from "@/app/lib/server/champions";
import { currentSeason } from "@/app/lib/server/raceControl";

import { SeasonDetailView } from "./SeasonDetailView";

import type { Metadata } from "next";

interface SeasonPageProps {
  params: Promise<{ year: string }>;
}

/**
 * Hourly background regeneration. The dataset only moves when a title is
 * decided, so this is not about freshness: it caps how long a render made
 * against a slow backend keeps serving an unseeded page.
 */
export const revalidate = 3_600;

/** Prerender the recent seasons; the rest render on demand and are then cached like the rest. */
export async function generateStaticParams(): Promise<Array<{ year: string }>> {
  const years = await listSeasonYears();
  return years.map((year) => ({ year }));
}

/** Awaits only `params`: the metadata must not hold the stream. */
export async function generateMetadata({ params }: SeasonPageProps): Promise<Metadata> {
  const { year } = await params;
  return {
    title: `${year} F1 Season | F1 AI`,
    description: `The ${year} Formula 1 World Champions and every race winner.`,
  };
}

/**
 * Awaits only `params`. A year outside the championship's range 404s without
 * data; a year in range that f1db lacks answers `{ error }` and each section
 * says so.
 */
export default async function SeasonDetailPage({ params }: SeasonPageProps) {
  const { year } = await params;
  const latest = currentSeason();
  const n = Number(year);
  if (!/^\d{4}$/.test(year) || n < FIRST_SEASON || n > latest) notFound();
  return <SeasonDetailView year={n} latest={latest} seed={getSeasonDetail(year)} />;
}
