"use client";

import { Suspense, use } from "react";

import { TelemetryView, type TelemetrySeed } from "./TelemetryView";
import { defaultTelemetryUrl, useTelemetryParams } from "./useTelemetryParams";

/**
 * The Telemetry Lab, with the season calendar still on its way from the server.
 *
 * Reading the URL needs a Suspense boundary for the page to prerender, and its
 * fallback is the lab at the default selection with no calendar: the frame paints
 * at once and the picker fills when the calendar lands (or the browser fetches it).
 */
export function TelemetryLab({ year, schedule }: { year: number; schedule: Promise<TelemetrySeed["schedule"]> }) {
  return (
    <Suspense fallback={<TelemetryView seed={{ year, schedule: null }} url={defaultTelemetryUrl(year)} />}>
      <UrlBoundLab year={year} schedule={schedule} />
    </Suspense>
  );
}

function UrlBoundLab({ year, schedule }: { year: number; schedule: Promise<TelemetrySeed["schedule"]> }) {
  const url = useTelemetryParams(year);
  // A URL for another season never waits on this season's calendar.
  return <TelemetryView seed={{ year, schedule: url.params.year === year ? use(schedule) : null }} url={url} />;
}
