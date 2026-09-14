import {
  currentSeason,
  getDrivers,
  getPredictionSnapshot,
  getSchedule,
  getStartingGrid,
  getWeekendSessions,
  scheduleRaces,
} from "@/app/lib/server/raceControl";

import { GrandPrixView, type DriversResponse, type GrandPrixSeed } from "./GrandPrixView";
import { resolveDefaultRace } from "./predictionHelpers";

import type { StartingGridResponse } from "./gridModel";
import type { PredictionsResponse } from "./predictionModel";
import type { WeekendSessionsResponse } from "./sessionsModel";
import type { Metadata } from "next";

/** Grid and snapshots both move as practice and qualifying land. */
export const revalidate = 300;

export const metadata: Metadata = {
  title: "Grand Prix Hub | F1 AI",
  description:
    "Everything about a Formula 1 Grand Prix in one place: the circuit and session schedule, the official starting grid with any penalties applied, the model's predicted finishing order, incident risk, and how the call scored against the result.",
};

export default async function GrandPrixHubPage() {
  const year = currentSeason();

  // Schedule and entry list are independent; fetch them together.
  const [schedule, drivers] = await Promise.all([getSchedule(year), getDrivers<DriversResponse>(year)]);

  // The grid, the snapshots and the session results depend on which round the
  // schedule resolves to, so they can only be fetched once the schedule has
  // landed. All of them are prefetched so switching tabs paints immediately
  // instead of waiting on a round trip.
  //
  // Tyre stints are deliberately *not* prefetched. They come from a FastF1
  // session load that costs ~28 seconds warm and over two minutes cold, and
  // awaiting that here would block the whole page — including the Weekend tab
  // it opens on — behind a tab most visitors never select. The client fetches
  // it in the background instead, and the Stints tab shows its own loader.
  const defaultRace = resolveDefaultRace(scheduleRaces(schedule));
  const [preQualifying, postQualifying, grid, sessions] = defaultRace
    ? await Promise.all([
        getPredictionSnapshot<PredictionsResponse>(year, defaultRace.round, "pre_qualifying"),
        getPredictionSnapshot<PredictionsResponse>(year, defaultRace.round, "post_qualifying"),
        getStartingGrid<StartingGridResponse>(year, defaultRace.round),
        getWeekendSessions<WeekendSessionsResponse>(year, defaultRace.round),
      ])
    : [null, null, null, null];

  const seed: GrandPrixSeed = {
    year,
    schedule,
    drivers,
    snapshots: { pre_qualifying: preQualifying, post_qualifying: postQualifying },
    snapshotRound: defaultRace?.round ?? null,
    grid,
    sessions,
    strategy: null,
  };

  return <GrandPrixView seed={seed} />;
}
