"use client";

import { useEffect, useState } from 'react';

import { useServerStatus } from '../hooks/useServerStatus';

const rcMono = { fontFamily: 'var(--font-geist-mono, var(--font-geist-sans, monospace))' };

/**
 * Backend warm-up stages, in the order the server reports them. The index drives
 * how many start lights are illuminated, so the gantry fills as real work
 * completes rather than animating on a timer.
 */
const STAGE_ORDER = ['pending', 'database', 'model', 'season'] as const;
const LIGHT_COUNT = 5;

/** How long the lights-out celebration holds before the banner unmounts. */
const LAUNCH_DURATION_MS = 1800;

function litCountForStage(stage: string | null): number {
  const index = stage ? STAGE_ORDER.indexOf(stage as (typeof STAGE_ORDER)[number]) : -1;
  if (index < 0) return 1;
  // Final stage lights the fifth pod, so the gantry is full just before go.
  return Math.min(LIGHT_COUNT, index + 2);
}

function StartLight({ lit, active, out }: { lit: boolean; active: boolean; out: boolean }) {
  if (out) {
    return (
      <span
        className="h-2.5 w-2.5 rounded-full bg-[#E10600] animate-lights-out motion-reduce:animate-none"
        style={{ boxShadow: '0 0 6px rgba(225, 6, 0, 0.5)' }}
      />
    );
  }

  return (
    <span
      className={`h-2.5 w-2.5 rounded-full transition-colors ${
        lit ? 'bg-[#E10600] animate-light-on' : 'bg-[#1A2130] border border-[#232C3D]'
      } ${active ? 'animate-glow-pulse' : ''} motion-reduce:animate-none`}
      style={lit ? { boxShadow: '0 0 8px rgba(225, 6, 0, 0.55)' } : undefined}
    />
  );
}

/**
 * Thin status strip shown while the backend finishes warming up.
 *
 * Non-blocking by design: the free-tier cold start is ~50s, so gating the whole
 * app behind it would mean a blank spinner for most first-time visitors. The
 * static homepage stays readable underneath while the server wakes.
 *
 * The F1 start gantry is the progress indicator — lights fill as warm-up stages
 * complete, then go out when the server is ready, which is exactly what lights
 * out means on the grid.
 */
export default function ServerWarmingBanner() {
  const { isWarming, detail, stage, status, everWarmed } = useServerStatus();
  const [launchElapsed, setLaunchElapsed] = useState(false);

  // Only celebrate if the user actually waited. A server that was already warm
  // resolves on the first probe, so everWarmed stays false and nothing is shown.
  const launching = !isWarming && status === 'ready' && everWarmed && !launchElapsed;

  useEffect(() => {
    if (!launching) return;
    const timer = setTimeout(() => setLaunchElapsed(true), LAUNCH_DURATION_MS);
    return () => clearTimeout(timer);
  }, [launching]);

  if (!isWarming && !launching) return null;

  const lit = litCountForStage(stage);

  return (
    <div
      role="status"
      aria-live="polite"
      className="relative flex items-center gap-3 overflow-hidden border-b border-[#1E2633] bg-[#0D111B] px-4 py-2 sm:px-6"
    >
      {/* Start-light gantry */}
      <div
        className="flex shrink-0 items-center gap-1.5 rounded border border-[#1E2633] bg-[#080B11] px-2 py-1.5"
        aria-hidden="true"
      >
        {Array.from({ length: LIGHT_COUNT }).map((_, index) => (
          <StartLight
            key={index}
            lit={index < lit}
            active={!launching && index === lit - 1}
            out={launching}
          />
        ))}
      </div>

      {/* Car pulling away once the lights go out */}
      {launching && (
        <span
          aria-hidden="true"
          className="pointer-events-none absolute inset-y-0 left-0 flex items-center animate-car-launch motion-reduce:hidden"
        >
          <span
            className="ml-2 h-[3px] w-10 rounded-full"
            style={{
              background: 'linear-gradient(90deg, transparent, #E10600 55%, #FF6B5A)',
              boxShadow: '0 0 10px rgba(225, 6, 0, 0.6)',
            }}
          />
        </span>
      )}

      <p
        className="shrink-0 truncate text-[10px] font-bold uppercase tracking-[0.2em]"
        style={{ ...rcMono, color: launching ? '#00FF78' : '#7F8797' }}
      >
        {launching ? 'Lights out' : 'Formation lap'}
      </p>

      <p className="min-w-0 truncate text-xs text-[#8E96A8]">
        {launching
          ? 'Server ready — go racing.'
          : detail ?? 'Waking the server — the free-tier instance spins down when idle.'}
      </p>
    </div>
  );
}
