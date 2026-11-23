"use client";

import { Suspense } from "react";

import type { ScheduleSeed } from "@/app/ui/race-picker/useSchedule";

import { RewindView } from "./RewindView";
import { DEFAULT_REWIND_URL, useRewindUrl } from "./useRewindUrl";

interface Seeds {
  schedule: Promise<ScheduleSeed>;
}

function UrlBoundView({ year, seeds }: { year: number; seeds: Seeds }) {
  return <RewindView year={year} seeds={seeds} url={useRewindUrl()} />;
}

/**
 * Race Rewind, pointed at the round and step the URL names.
 *
 * Reading the URL needs a Suspense boundary for the page to prerender. Its
 * fallback is the page at the default race, so the server still renders it
 * and a plain link shows no flash.
 */
export function Rewind({ year, seeds }: { year: number; seeds: Seeds }) {
  return (
    <Suspense fallback={<RewindView year={year} seeds={seeds} url={DEFAULT_REWIND_URL} />}>
      <UrlBoundView year={year} seeds={seeds} />
    </Suspense>
  );
}
