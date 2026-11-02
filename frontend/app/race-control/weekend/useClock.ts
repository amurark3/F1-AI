import { useSyncExternalStore } from "react";

/**
 * One wall clock for every countdown on the page, ticking once a second.
 *
 * A countdown is measured from "now", and a prerendered page has no honest
 * "now" — so the server snapshot is null and callers render a placeholder until
 * the browser takes over. All subscribers share a single interval, which stops
 * when the last one unmounts.
 */
const TICK_MS = 1000;
const listeners = new Set<() => void>();
let nowMs: number | null = null;
let timer: ReturnType<typeof setInterval> | null = null;

function tick(): void {
  nowMs = Date.now();
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  if (timer === null) {
    nowMs = Date.now();
    timer = setInterval(tick, TICK_MS);
  }
  return () => {
    listeners.delete(listener);
    if (listeners.size === 0 && timer !== null) {
      clearInterval(timer);
      timer = null;
    }
  };
}

const getSnapshot = (): number | null => nowMs;
const getServerSnapshot = (): number | null => null;

/** Milliseconds since the epoch, refreshed each second; null on the server and before mount. */
export function useClock(): number | null {
  return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
