"use client";

import { Suspense } from "react";

import { DebriefsView } from "./DebriefsView";
import { DEFAULT_DEBRIEF_URL, useDebriefUrl } from "./useDebriefUrl";

import type { DebriefSeeds } from "./useDebriefSections";

function UrlBoundView({ year, seeds }: { year: number; seeds: DebriefSeeds }) {
  return <DebriefsView year={year} seeds={seeds} url={useDebriefUrl()} />;
}

/**
 * The debriefs, pointed at the round the URL names.
 *
 * Reading the URL needs a Suspense boundary for the page to prerender. Its
 * fallback is the page itself at the default round, so the server still
 * renders the prefetched debrief and a plain link shows no flash.
 */
export function Debriefs({ year, seeds }: { year: number; seeds: DebriefSeeds }) {
  return (
    <Suspense fallback={<DebriefsView year={year} seeds={seeds} url={DEFAULT_DEBRIEF_URL} />}>
      <UrlBoundView year={year} seeds={seeds} />
    </Suspense>
  );
}
