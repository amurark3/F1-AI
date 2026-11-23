import { currentSeason, getSchedule } from "@/app/lib/server/raceControl";

import { Rewind } from "./Rewind";

import type { Metadata } from "next";

/** A classified race stops changing. */
export const revalidate = 900;

export const metadata: Metadata = {
  title: "F1 Race Rewind | F1 AI",
  description:
    "Replay any Grand Prix lap by lap: the order at the line, why each place changed, and the road order against the FIA final classification.",
};

/** Awaits nothing: the schedule's promise goes to the view, which takes it up behind its own boundary. */
export default function RewindPage() {
  const year = currentSeason();
  return <Rewind year={year} seeds={{ schedule: getSchedule(year) }} />;
}
