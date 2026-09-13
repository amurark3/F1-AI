import {
  currentSeason,
  getDrivers,
  getPredictionSnapshot,
  getSchedule,
  scheduleRaces,
} from "@/app/lib/server/raceControl";

import { resolveDefaultRace } from "./predictionHelpers";
import { PredictionsView, type DriversResponse, type PredictionSeed } from "./PredictionsView";

import type { PredictionsResponse } from "./predictionModel";
import type { Metadata } from "next";

/** Snapshots are recomputed as practice and qualifying land. */
export const revalidate = 300;

export const metadata: Metadata = {
  title: "F1 Race Predictions | F1 AI",
  description:
    "Model-ranked finishing order for the next Formula 1 Grand Prix, with the reasoning and confidence behind each driver's predicted position.",
};

export default async function RaceControlPredictionsPage() {
  const year = currentSeason();

  // Schedule and entry list are independent; fetch them together.
  const [schedule, drivers] = await Promise.all([getSchedule(year), getDrivers<DriversResponse>(year)]);

  // The snapshots depend on which round the schedule resolves to, so they can
  // only be fetched once the schedule has landed. Both phases are prefetched so
  // switching tabs paints immediately instead of waiting on a round trip.
  const defaultRace = resolveDefaultRace(scheduleRaces(schedule));
  const [preQualifying, postQualifying] = defaultRace
    ? await Promise.all([
        getPredictionSnapshot<PredictionsResponse>(year, defaultRace.round, "pre_qualifying"),
        getPredictionSnapshot<PredictionsResponse>(year, defaultRace.round, "post_qualifying"),
      ])
    : [null, null];

  const seed: PredictionSeed = {
    year,
    schedule,
    drivers,
    snapshots: { pre_qualifying: preQualifying, post_qualifying: postQualifying },
    snapshotRound: defaultRace?.round ?? null,
  };

  return <PredictionsView seed={seed} />;
}
