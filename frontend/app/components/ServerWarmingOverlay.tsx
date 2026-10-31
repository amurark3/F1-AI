"use client";

import { RotateCw } from "lucide-react";
import { useEffect, useId, useRef, useState } from "react";

import StartLightGantry, { litCountForStage } from "./StartLightGantry";

/**
 * - `warming`: the server is booting; the app underneath is blocked.
 * - `unreachable`: the probe gave up; blocked until the user retries or continues.
 * - `launching`: warm-up just finished; the screen fades out without blocking.
 */
export type OverlayPhase = "warming" | "unreachable" | "launching";

const COPY: Record<OverlayPhase, { eyebrow: string; title: string; eyebrowColor: string }> = {
  warming: { eyebrow: "Formation lap", title: "Waking the server", eyebrowColor: "#7F8797" },
  unreachable: { eyebrow: "Red flag", title: "Server isn't responding", eyebrowColor: "#E10600" },
  launching: { eyebrow: "Lights out", title: "Server ready", eyebrowColor: "#00FF78" },
};

const FALLBACK_DETAIL: Record<OverlayPhase, string> = {
  warming: "Starting the server",
  unreachable: "It hasn't answered for a few minutes — it may be redeploying or down.",
  launching: "Go racing.",
};

const rcMono = { fontFamily: "var(--font-geist-mono, var(--font-geist-sans, monospace))" };
const barlow = { fontFamily: "var(--font-barlow, var(--font-geist-sans))" };

/** Whole seconds since `since`, ticking once a second while `since` is set. */
function useElapsedSeconds(since: number | null): number {
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    if (since === null) return;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [since]);

  if (since === null || now === null) return 0;
  return Math.max(0, Math.floor((now - since) / 1000));
}

function formatElapsed(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function UnreachableActions({ onRetry, onContinue }: { onRetry: () => void; onContinue: () => void }) {
  return (
    <div className="mt-6 flex flex-col gap-2 sm:flex-row-reverse sm:justify-center short:mt-4">
      <button
        type="button"
        autoFocus
        onClick={onRetry}
        className="inline-flex min-h-11 items-center justify-center gap-2 rounded-md bg-[#E10600] px-5 text-xs font-black uppercase tracking-widest text-white transition-colors hover:bg-[#FF1E10] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/60"
        style={barlow}
      >
        <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />
        Try again
      </button>
      <button
        type="button"
        onClick={onContinue}
        className="inline-flex min-h-11 items-center justify-center rounded-md border border-[#1E2633] px-5 text-xs font-black uppercase tracking-widest text-neutral-400 transition-colors hover:border-white/20 hover:bg-white/[0.04] hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#E10600]/50"
        style={barlow}
      >
        Continue anyway
      </button>
    </div>
  );
}

interface ServerWarmingOverlayProps {
  phase: OverlayPhase;
  stage: string | null;
  detail: string | null;
  warmingSince: number | null;
  onRetry: () => void;
  onContinue: () => void;
}

/**
 * Full-screen warm-up screen shown over the app while the backend cold-starts.
 *
 * Sized for phones first: the card fills the width up to a cap, the overlay
 * scrolls on its own (a landscape phone can be shorter than the card), touch
 * targets are 44px, and safe-area insets keep it clear of notches.
 */
export default function ServerWarmingOverlay({
  phase,
  stage,
  detail,
  warmingSince,
  onRetry,
  onContinue,
}: ServerWarmingOverlayProps) {
  const titleId = useId();
  const detailId = useId();
  const cardRef = useRef<HTMLDivElement>(null);
  const elapsed = useElapsedSeconds(phase === "warming" ? warmingSince : null);
  const copy = COPY[phase];
  const launching = phase === "launching";

  // Pull focus off the now-inert app (closing a phone keyboard with it) and
  // into the dialog, so screen readers announce it. Unreachable focuses its
  // primary action instead, via autoFocus.
  useEffect(() => {
    if (phase === "warming") cardRef.current?.focus({ preventScroll: true });
  }, [phase]);

  return (
    <div
      role="dialog"
      aria-modal={!launching}
      aria-labelledby={titleId}
      aria-describedby={detailId}
      className={`fixed inset-0 z-[100] overflow-y-auto overscroll-contain bg-[#07090D]/80 backdrop-blur-md motion-reduce:animate-none ${
        launching ? "pointer-events-none animate-overlay-out" : "animate-overlay-in"
      }`}
    >
      <div className="flex min-h-full items-center justify-center px-4 pb-[max(1.5rem,env(safe-area-inset-bottom))] pt-[max(1.5rem,env(safe-area-inset-top))]">
        <div
          ref={cardRef}
          tabIndex={-1}
          className="w-full max-w-sm rounded-2xl border border-[#1E2633] bg-[#0D111B]/95 p-6 text-center shadow-[0_24px_80px_rgba(0,0,0,0.6)] outline-none sm:max-w-md sm:p-8 short:p-5"
        >
          <StartLightGantry
            lit={phase === "unreachable" ? 0 : litCountForStage(stage)}
            out={launching}
            label="Server warm-up progress"
          />

          <p
            className="mt-6 text-[10px] font-bold uppercase tracking-[0.25em] sm:text-[11px] short:mt-4"
            style={{ ...rcMono, color: copy.eyebrowColor }}
          >
            {copy.eyebrow}
          </p>
          <h2
            id={titleId}
            className="mt-2 text-xl font-black uppercase italic leading-tight tracking-tight text-white sm:text-2xl"
            style={barlow}
          >
            {copy.title}
          </h2>
          <p id={detailId} role="status" aria-live="polite" className="mt-2 text-sm text-[#AEB5C4]">
            {phase === "warming" ? (detail ?? FALLBACK_DETAIL.warming) : FALLBACK_DETAIL[phase]}
          </p>

          {phase === "warming" && (
            <>
              <p className="mt-4 text-xs tabular-nums text-[#7F8797] short:mt-2" style={rcMono}>
                {formatElapsed(elapsed)} elapsed
              </p>
              <p className="mt-4 border-t border-[#1E2633] pt-4 text-xs leading-relaxed text-[#7F8797] short:mt-3 short:pt-3">
                The free-tier server sleeps when idle. A cold start usually takes under a minute.
              </p>
            </>
          )}

          {phase === "unreachable" && <UnreachableActions onRetry={onRetry} onContinue={onContinue} />}
        </div>
      </div>
    </div>
  );
}
