import { notFound } from "next/navigation";

import { getSeasonDetail, listSeasonYears } from "@/app/lib/server/champions";

import { SeasonDetailView } from "./SeasonDetailView";

import type { Metadata } from "next";

interface SeasonPageProps {
  params: Promise<{ year: string }>;
}

/**
 * Hourly background regeneration. The dataset only moves when a title is
 * decided, so this is not about freshness — it caps how long a render made
 * against a slow backend keeps serving an unseeded page.
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

  // A season the dataset has never heard of is a genuine 404. An unreachable
  // backend is not — that returns null, and the view fetches for itself.
  if (data?.error) notFound();

  return <SeasonDetailView year={year} initial={data} />;
}
