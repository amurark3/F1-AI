"use client";

import { AlertTriangle, Check, RefreshCw } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Minimum time the spinner stays on screen.
 *
 * Standings resolve from a local dataset in a few milliseconds, so without a
 * floor the spinner would flash for a single frame and the button would read
 * as if the click did nothing.
 */
const MIN_SPIN_MS = 550;

/** How long the terminal state holds before the button returns to idle. */
const RESULT_HOLD_MS = 1800;

type RefreshPhase = "idle" | "refreshing" | "done" | "failed";

const PHASE_STYLES: Record<RefreshPhase, string> = {
  idle: "border-white/10 bg-white/[0.04] text-neutral-200 hover:bg-white/[0.08] hover:text-white",
  refreshing: "border-white/10 bg-white/[0.04] text-neutral-400",
  done: "border-[#00FF78]/35 bg-[#00FF78]/10 text-[#00FF78]",
  failed: "border-[#E10600]/35 bg-[#E10600]/10 text-[#FF6B67]",
};

const PHASE_LABELS: Record<RefreshPhase, string> = {
  idle: "Refresh",
  refreshing: "Refreshing",
  done: "Updated",
  failed: "Refresh failed",
};

const delay = (ms: number) => new Promise<void>((resolve) => setTimeout(resolve, ms));

function PhaseIcon({ phase }: { phase: RefreshPhase }) {
  if (phase === "done") {
    return <Check className="h-4 w-4" />;
  }
  if (phase === "failed") {
    return <AlertTriangle className="h-4 w-4" />;
  }
  const spin = phase === "refreshing" ? " animate-spin motion-reduce:animate-none" : "";
  return <RefreshCw className={`h-4 w-4${spin}`} />;
}

/**
 * Refresh control that reports what it is doing.
 *
 * Runs `onRefresh` and walks idle -> refreshing -> done/failed -> idle, so a
 * revalidation that returns identical data still gives the user visible
 * confirmation that the fetch happened.
 */
export function RefreshButton({
  onRefresh,
  className = "",
}: {
  onRefresh: () => Promise<unknown>;
  className?: string;
}) {
  const [phase, setPhase] = useState<RefreshPhase>("idle");
  const isMounted = useRef(true);
  const resetTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      isMounted.current = false;
      if (resetTimer.current) {
        clearTimeout(resetTimer.current);
      }
    },
    [],
  );

  const settle = useCallback((outcome: RefreshPhase) => {
    if (!isMounted.current) {
      return;
    }
    setPhase(outcome);
    resetTimer.current = setTimeout(() => {
      if (isMounted.current) {
        setPhase("idle");
      }
    }, RESULT_HOLD_MS);
  }, []);

  const handleRefresh = useCallback(async () => {
    if (resetTimer.current) {
      clearTimeout(resetTimer.current);
      resetTimer.current = null;
    }
    setPhase("refreshing");
    const startedAt = Date.now();

    let outcome: RefreshPhase = "done";
    try {
      await onRefresh();
    } catch (error) {
      console.error("Refresh failed:", error);
      outcome = "failed";
    }

    await delay(Math.max(0, MIN_SPIN_MS - (Date.now() - startedAt)));
    settle(outcome);
  }, [onRefresh, settle]);

  const busy = phase === "refreshing";

  return (
    <button
      type="button"
      onClick={() => void handleRefresh()}
      disabled={busy}
      aria-busy={busy}
      className={`inline-flex h-10 min-w-[9.5rem] items-center justify-center gap-2 rounded-lg border px-4 text-sm font-bold transition-colors disabled:cursor-not-allowed ${PHASE_STYLES[phase]} ${className}`}
    >
      <PhaseIcon phase={phase} />
      <span aria-live="polite">{PHASE_LABELS[phase]}</span>
    </button>
  );
}
