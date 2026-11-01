import { Suspense } from "react";

import { currentSeason, getSchedule } from "@/app/lib/server/raceControl";

import { PageLoader } from "../components/RaceControlPrimitives";

import { TelemetryView } from "./TelemetryView";

import type { Metadata } from "next";

/** Only the calendar is server-rendered; every analysis loads in the browser. */
export const revalidate = 3600;

export const metadata: Metadata = {
  title: "Telemetry Lab | F1 AI",
  description:
    "Formula 1 lap telemetry from OpenF1: a lap mapped round the circuit by speed with its braking zones, two drivers' laps compared corner by corner, and tyre degradation per compound with the laps left out and why.",
};

export default async function TelemetryLabPage() {
  const year = currentSeason();
  const schedule = await getSchedule(year);

  // The view reads its selection from the URL, which needs a Suspense boundary
  // for the page to prerender.
  return (
    <Suspense fallback={<PageLoader title="Opening the Telemetry Lab" detail="Loading the season calendar." />}>
      <TelemetryView seed={{ year, schedule }} />
    </Suspense>
  );
}
