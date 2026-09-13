"use client";

import { useEffect, useState, useSyncExternalStore } from "react";

import { formatLocal, formatUtc, resolvedTimeZone, type TimeStyle } from "../lib/formatTime";
import { countdownTo } from "../race-control/predictions/predictionHelpers";

/**
 * Nothing to subscribe to — hydration happens once and never reverses, so the
 * unsubscribe callback has nothing to tear down.
 */
const neverChanges = () => {
  return () => undefined;
};

/**
 * False during the server render and the first client render, true afterwards.
 *
 * This is the hook that makes viewer-specific rendering safe. React requires
 * the first client render to match the server's output exactly, so anything
 * that depends on the browser — time zone, locale, the current time — has to
 * wait one render before it can appear.
 */
function useIsHydrated(): boolean {
  return useSyncExternalStore(
    neverChanges,
    () => true,
    () => false,
  );
}

interface LocalTimeProps {
  /** ISO timestamp from the backend, which publishes everything in UTC. */
  value: string | undefined | null;
  style: TimeStyle;
  /** Shown when the timestamp is missing or unparseable. */
  fallback?: string;
}

/**
 * A timestamp rendered in the viewer's own time zone.
 *
 * The server — and the first client render — emit UTC, so the prerendered HTML
 * is identical for every reader and hydration matches exactly. The viewer's
 * real zone takes over on the next render. Readers without JavaScript keep a
 * correct UTC time rather than one silently mislabelled with the build
 * machine's zone.
 */
export function LocalTime({ value, style, fallback = "—" }: LocalTimeProps) {
  const hydrated = useIsHydrated();

  return <>{hydrated ? formatLocal(value, style, fallback) : formatUtc(value, style, fallback)}</>;
}

/**
 * The viewer's time-zone name, for copy explaining which zone times are shown
 * in. Same contract as `LocalTime`: "UTC" until hydrated, then the real zone.
 */
export function LocalTimeZone() {
  const hydrated = useIsHydrated();

  return <>{hydrated ? resolvedTimeZone() : "UTC"}</>;
}

/** How often the countdown re-reads the clock. */
const COUNTDOWN_TICK_MS = 60_000;

/**
 * Time remaining until a session, or nothing once it has started.
 *
 * Renders nothing on the server. A countdown is measured from "now", and on a
 * prerendered page "now" is whenever the build ran — any server-rendered figure
 * would be wrong by however long the page has been cached.
 */
export function LocalCountdown({ value }: { value: string | undefined }) {
  const hydrated = useIsHydrated();
  const [, setTick] = useState(0);

  useEffect(() => {
    const timer = setInterval(() => setTick((count) => count + 1), COUNTDOWN_TICK_MS);
    return () => clearInterval(timer);
  }, []);

  const remaining = hydrated ? countdownTo(value) : null;
  if (remaining === null) return null;

  return (
    <div className="w-fit rounded-full border border-[#E10600]/40 bg-[#E10600]/10 px-4 py-2 font-mono text-xs font-bold uppercase tracking-[0.18em] text-white shadow-[0_0_24px_rgba(225,6,0,0.12)]">
      lights out in <span className="text-[#FF4655]">{remaining}</span>
    </div>
  );
}
