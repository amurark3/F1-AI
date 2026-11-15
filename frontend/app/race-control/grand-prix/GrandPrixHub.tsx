"use client";

import { Suspense } from "react";

import { GrandPrixView } from "./GrandPrixView";
import { DEFAULT_HUB_URL, useHubUrlState } from "./useHubUrlState";

import type { GrandPrixSeed } from "./hubSeed";

function UrlBoundView({ seed }: { seed: GrandPrixSeed }) {
  return <GrandPrixView seed={seed} url={useHubUrlState()} />;
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
