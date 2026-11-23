"use client";

import { Suspense } from "react";

import { GrandPrixView } from "./GrandPrixView";
import { DEFAULT_HUB_URL, useHubUrlState } from "./useHubUrlState";

import type { GrandPrixSeed } from "./hubSeed";

function UrlBoundView({ seed }: { seed: GrandPrixSeed }) {
  const url = useHubUrlState(seed.year);
  const year = url.year ?? seed.year;
  const seasonSeed: GrandPrixSeed =
    year === seed.year
      ? seed
      : {
          year,
          schedule: null,
          drivers: null,
          snapshots: { pre_qualifying: null, post_qualifying: null },
          snapshotRound: null,
          grid: null,
          sessions: null,
          strategy: null,
        };
  return <GrandPrixView key={year} seed={seasonSeed} url={url} />;
}

/**
 * The hub, pointed at whatever round and section the URL names.
 *
 * Reading the URL needs a Suspense boundary for the page to prerender. Its
 * fallback is the hub itself at the default selection, so the server still
 * renders the prefetched round in full and a plain link shows no flash.
 */
export function GrandPrixHub({ seed }: { seed: GrandPrixSeed }) {
  return (
    <Suspense fallback={<GrandPrixView seed={seed} url={DEFAULT_HUB_URL} />}>
      <UrlBoundView seed={seed} />
    </Suspense>
  );
}
