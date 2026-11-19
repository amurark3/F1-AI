import { currentSeason, getDebrief, getSchedule, scheduleRaces } from "@/app/lib/server/raceControl";

import { resolveDefaultDebriefRace } from "./debriefModel";
import { Debriefs } from "./Debriefs";

import type { DebriefSummary } from "./debriefTypes";
import type { Metadata } from "next";

/** Debriefs are written once a race is classified and then stop changing. */
export const revalidate = 900;

export const metadata: Metadata = {
  title: "F1 Race Debriefs | F1 AI",
  description:
    "Post-race breakdowns of every Grand Prix: result, lap leaders, race trace, grid to finish, penalties and on-track position changes.",
};

/** Awaits nothing: the promises go to the sections, which take them up behind their own boundaries. */
export default function DebriefsPage() {
  const year = currentSeason();
  const schedule = getSchedule(year);
  const summary = schedule.then((response) => {
    const race = resolveDefaultDebriefRace(scheduleRaces(response));
    if (!race) return null;
    // A backend still serving the old debrief has no `titles`: seed nothing and let the client ask again.
    return getDebrief<DebriefSummary>(year, race.round).then((data) => ({
      round: race.round,
      data: data?.titles ? data : null,
    }));
  });
  return <Debriefs year={year} seeds={{ schedule, summary }} />;
}
