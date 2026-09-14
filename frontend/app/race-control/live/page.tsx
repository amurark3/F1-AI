import { currentSeason, getSchedule, scheduleRaces } from "@/app/lib/server/raceControl";

import { LiveView } from "./LiveView";

import type { Metadata } from "next";

/**
 * Short window, because this decides whether the live desk opens at all.
 *
 * `in_progress` marks a whole race weekend rather than a single session, so it
 * flips on a scale of hours — a minute of staleness never hides a running
 * session for long, and the timing socket supplies everything that actually
 * ticks.
 */
export const revalidate = 60;

export const metadata: Metadata = {
  title: "F1 Live Timing | F1 AI",
  description:
    "Live Formula 1 timing tower, track positions, sector deltas, session state, and AI race commentary from the operations desk.",
};

export default async function RaceControlLivePage() {
  const year = currentSeason();
  const schedule = await getSchedule(year);

  const inProgress = scheduleRaces(schedule).find((race) => race.status === "in_progress");
  const liveRound = inProgress
    ? { year, round: inProgress.round, name: inProgress.name, sessions: inProgress.sessions ?? null }
    : null;

  return <LiveView year={year} liveRound={liveRound} />;
}
