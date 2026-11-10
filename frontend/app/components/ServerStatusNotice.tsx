"use client";

import { RotateCw, X } from "lucide-react";
import { useEffect, useState } from "react";

import { useServerStatus, type ServerState } from "../hooks/useServerStatus";
import { retryServerProbe } from "../lib/serverStatus";
import { EYEBROW } from "../ui/typography";

import StartLightGantry, { litCountForStage } from "./StartLightGantry";

/**
 * - `warming`: the backend is restarting (a deploy) or not answering yet.
 * - `unreachable`: the probe gave up; the reader can try again or dismiss it.
 * - `launching`: the backend just came back; lights out, then the notice goes.
 */
type NoticePhase = "warming" | "unreachable" | "launching";

/** How long "Back online" holds after a restart before the notice goes. */
const LAUNCH_DURATION_MS = 1200;

const COPY: Record<NoticePhase, { eyebrow: string; title: string; eyebrowTone: string }> = {
  warming: { eyebrow: "Formation lap", title: "Updating — back in a few seconds", eyebrowTone: "" },
  unreachable: { eyebrow: "Red flag", title: "Server isn't responding", eyebrowTone: "text-rc-red-text" },
  launching: { eyebrow: "Lights out", title: "Back online", eyebrowTone: "" },
};

const UNREACHABLE_DETAIL = "No answer for two minutes. It may be down.";

function noticePhase(server: ServerState, dismissedRun: number, launchedRun: number): NoticePhase | null {
  if (server.status === "warming") return "warming";
  if (server.status === "unreachable") return dismissedRun === server.run ? null : "unreachable";
  // Only say "back" if the reader saw it go. A server that was already up
  // answers the first probe ready, so `waited` stays false and nothing shows.
  if (server.status === "ready" && server.waited && launchedRun !== server.run) return "launching";
  return null;
}

function noticeDetail(phase: NoticePhase, detail: string | null): string | null {
  if (phase === "warming") return detail;
  if (phase === "unreachable") return UNREACHABLE_DETAIL;
  return null;
}

const BUTTON =
  "inline-flex min-h-9 items-center gap-1.5 rounded px-3 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] transition-colors";

function UnreachableActions({ onDismiss }: { onDismiss: () => void }) {
  return (
    <div className="mt-3 flex flex-wrap justify-end gap-2">
      <button
        type="button"
        onClick={retryServerProbe}
        className={`${BUTTON} bg-f1-red text-white hover:brightness-110`}
      >
        <RotateCw className="h-3.5 w-3.5" aria-hidden="true" />
        Try again
      </button>
      <button
        type="button"
        onClick={onDismiss}
        className={`${BUTTON} border border-rc-line text-rc-ink-2 hover:border-rc-ink-3 hover:text-rc-ink`}
      >
        <X className="h-3.5 w-3.5" aria-hidden="true" />
        Dismiss
      </button>
    </div>
  );
}

/**
 * Says so, without blocking anything, while the backend is not ready.
 *
 * The backend is always on, so this shows only while it restarts after a
 * deploy, or when it cannot be reached. Every page stays usable underneath:
 * nothing is made `inert`, scrolling is never locked, and the notice takes
 * pointer events only on its own card. Each section of a page already shows
 * its own pending or failed state; this explains why.
 *
 * The live region stays mounted, empty, while the server is up, so screen
 * readers announce the notice politely when it appears. The start lights
 * follow the backend's real warm-up stages, never a timer.
 */
export default function ServerStatusNotice() {
  const server = useServerStatus();
  const [dismissedRun, setDismissedRun] = useState(0);
  const [launchedRun, setLaunchedRun] = useState(0);

  const phase = noticePhase(server, dismissedRun, launchedRun);

  useEffect(() => {
    if (phase !== "launching") return;
    const timer = setTimeout(() => setLaunchedRun(server.run), LAUNCH_DURATION_MS);
    return () => clearTimeout(timer);
  }, [phase, server.run]);

  const copy = phase ? COPY[phase] : null;
  const detail = phase ? noticeDetail(phase, server.detail) : null;

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label="Server status"
      className="pointer-events-none fixed inset-x-4 bottom-[max(1rem,env(safe-area-inset-bottom))] z-[70] flex justify-end sm:left-auto sm:right-6 sm:bottom-[max(1.5rem,env(safe-area-inset-bottom))]"
    >
      {phase && copy && (
        <div className="pointer-events-auto w-full rounded border border-rc-line bg-rc-raised p-3 shadow-lg motion-safe:animate-fade-up sm:w-[22rem]">
          <div className="flex items-start gap-3">
            <StartLightGantry
              lit={phase === "unreachable" ? 0 : litCountForStage(server.stage)}
              out={phase === "launching"}
              label="Server restart progress"
            />
            <div className="min-w-0 flex-1">
              <p className={`${EYEBROW} ${copy.eyebrowTone}`}>{copy.eyebrow}</p>
              <p className="mt-1.5 text-sm font-semibold leading-snug text-rc-ink">{copy.title}</p>
              {detail && <p className="mt-1 text-xs leading-snug text-rc-ink-3">{detail}</p>}
            </div>
          </div>
          {phase === "unreachable" && <UnreachableActions onDismiss={() => setDismissedRun(server.run)} />}
        </div>
      )}
    </div>
  );
}
