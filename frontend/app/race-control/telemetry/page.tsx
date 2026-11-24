import { currentSeason, getSchedule } from "@/app/lib/server/raceControl";

import { TelemetryLab } from "./TelemetryLab";

import type { Metadata } from "next";

/** Only the calendar is server-rendered, and it streams: nothing is awaited. Every analysis loads in the browser. */
export const revalidate = 3600;

export const metadata: Metadata = {
  title: "Telemetry Lab | F1 AI",
  description:
    "Formula 1 lap telemetry from OpenF1: a lap mapped round the circuit by speed with its braking zones, two drivers' laps compared corner by corner, and tyre degradation per compound with the laps left out and why.",
};

export default function TelemetryLabPage() {
  const year = currentSeason();
  return <TelemetryLab year={year} schedule={getSchedule(year)} />;
}
