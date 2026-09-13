import { currentSeason, getDebrief, getSchedule, scheduleRaces } from "@/app/lib/server/raceControl";

import { resolveDefaultDebriefRace, type Debrief } from "./debriefModel";
import { DebriefsView, type DebriefSeed } from "./DebriefsView";

import type { Metadata } from "next";

/** Debriefs are written once a race is classified and then stop changing. */
export const revalidate = 900;

export const metadata: Metadata = {
  title: "F1 Race Debriefs | F1 AI",
  description:
    "Post-race breakdowns of every Formula 1 Grand Prix — podium, grid gain, points swings, non-finish statuses, and constructor impact.",
};

export default async function DebriefsPage() {
  const year = currentSeason();
  const schedule = await getSchedule(year);

  // Which debrief to prefetch depends on the schedule, so it follows it.
  const defaultRace = resolveDefaultDebriefRace(scheduleRaces(schedule));
  const debrief = defaultRace ? await getDebrief<Debrief>(year, defaultRace.round) : null;

  const seed: DebriefSeed = {
    year,
    schedule,
    debrief,
    debriefRound: defaultRace?.round ?? null,
  };

  return <DebriefsView seed={seed} />;
}
