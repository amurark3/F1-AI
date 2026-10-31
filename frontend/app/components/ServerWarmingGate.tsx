"use client";

import { useEffect, useState } from "react";

import { useScrollLock } from "../hooks/useScrollLock";
import { useServerStatus, type ServerState } from "../hooks/useServerStatus";
import { retryServerProbe } from "../lib/serverStatus";

import ServerWarmingOverlay, { type OverlayPhase } from "./ServerWarmingOverlay";

/** How long the lights-out moment holds. Matches `--animate-overlay-out` in globals.css. */
const LAUNCH_DURATION_MS = 1200;

function overlayPhase(server: ServerState, dismissedRun: number, launchedRun: number): OverlayPhase | null {
  if (server.status === "warming") return "warming";
  if (server.status === "unreachable") return dismissedRun === server.run ? null : "unreachable";
  // Only celebrate if the user actually waited. A server that was already warm
  // resolves on the first probe, so `waited` stays false and nothing is shown.
  if (server.status === "ready" && server.waited && launchedRun !== server.run) return "launching";
  return null;
}

/**
 * Blocks the app while the backend cold-starts.
 *
 * The free-tier Render instance spins down when idle and takes ~50s to come
 * back. Every page reads from it, so rather than let a visitor click into
 * panels that hang or error, the app sits behind a warm-up screen until
 * /api/ready says the server can answer. The app is made `inert` — unfocusable,
 * unclickable, hidden from assistive tech — not merely covered, so keyboard and
 * screen-reader users are held too. The `contents` wrapper adds no box, so the
 * layouts underneath are untouched.
 *
 * A warm server never shows anything: the screen appears only once a probe has
 * failed or is slow to answer. After ~3 minutes it offers a retry and a way
 * through, so a down server never locks the visitor out of the static pages.
 */
export default function ServerWarmingGate({ children }: { children: React.ReactNode }) {
  const server = useServerStatus();
  const [dismissedRun, setDismissedRun] = useState(0);
  const [launchedRun, setLaunchedRun] = useState(0);

  const phase = overlayPhase(server, dismissedRun, launchedRun);
  const blocking = phase === "warming" || phase === "unreachable";

  useEffect(() => {
    if (phase !== "launching") return;
    const timer = setTimeout(() => setLaunchedRun(server.run), LAUNCH_DURATION_MS);
    return () => clearTimeout(timer);
  }, [phase, server.run]);

  useScrollLock(blocking);

  return (
    <>
      <div className="contents" inert={blocking}>
        {children}
      </div>
      {phase && (
        <ServerWarmingOverlay
          phase={phase}
          stage={server.stage}
          detail={server.detail}
          warmingSince={server.warmingSince}
          onRetry={retryServerProbe}
          onContinue={() => setDismissedRun(server.run)}
        />
      )}
    </>
  );
}
