"use client";

import { Suspense, use } from "react";

import { GrandPrixView } from "./GrandPrixView";
import { emptySeed, type GrandPrixSeed } from "./hubSeed";
import { DEFAULT_HUB_URL, useHubUrlState } from "./useHubUrlState";

function UrlBoundView({ seed }: { seed: GrandPrixSeed }) {
  const url = useHubUrlState(seed.year);
  const year = url.year ?? seed.year;
  const seasonSeed = year === seed.year ? seed : emptySeed(year);
  return <GrandPrixView key={year} seed={seasonSeed} url={url} />;
}

/** The hub with the server seed in hand; reading the URL needs its own boundary. */
function Hub({ seed }: { seed: GrandPrixSeed }) {
  return (
    <Suspense fallback={<GrandPrixView seed={seed} url={DEFAULT_HUB_URL} />}>
      <UrlBoundView seed={seed} />
    </Suspense>
  );
}

function SeededHub({ seed }: { seed: Promise<GrandPrixSeed> }) {
  return <Hub seed={use(seed)} />;
}

/**
 * The hub, pointed at whatever round and section the URL names.
 *
 * Two boundaries. The outer one waits for the server seed, which is still on its
 * way when the page first streams: its fallback is the hub at the default URL
 * with nothing seeded, so the shell paints at once and each section fetches for
 * itself. The inner one is the URL's: reading it needs a boundary for the page
 * to prerender, and its fallback is the seeded hub at the default selection, so
 * a plain link shows no flash.
 */
export function GrandPrixHub({ year, seed }: { year: number; seed: Promise<GrandPrixSeed> }) {
  return (
    <Suspense fallback={<GrandPrixView seed={emptySeed(year)} url={DEFAULT_HUB_URL} />}>
      <SeededHub seed={seed} />
    </Suspense>
  );
}
