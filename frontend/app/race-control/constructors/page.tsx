import { Suspense } from "react";

import { currentSeason } from "@/app/lib/server/raceControl";

import { TeamsIndexSeed } from "./TeamsIndexSeed";
import { TeamsIndexView } from "./TeamsIndexView";

import type { Metadata } from "next";

/** Follows the constructor table, which moves once per race weekend. */
export const revalidate = 900;

export const metadata: Metadata = {
  title: "F1 Teams | F1 AI",
  description:
    "Every Formula 1 team of the season in championship order, with its drivers and how its points split between them.",
};

/** Nothing here waits on the backend: the view paints its skeleton and the seed streams in. */
export default function ConstructorsPage() {
  const year = currentSeason();
  return (
    <Suspense fallback={<TeamsIndexView year={year} seed={null} />}>
      <TeamsIndexSeed year={year} />
    </Suspense>
  );
}
