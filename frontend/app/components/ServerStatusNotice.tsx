"use client";

import { RotateCw } from "lucide-react";

import { useServerStatus } from "../hooks/useServerStatus";
import { dismissServerNotice, noticePhase, retryServerProbe } from "../lib/serverStatus";
import { DISPLAY, EYEBROW } from "../ui/typography";

const BUTTON =
  "inline-flex h-11 flex-1 items-center justify-center gap-2 rounded-md px-4 font-display text-[17px] font-bold uppercase tracking-widest transition-colors sm:flex-none";

/**
 * What the polite status region says. Empty while the backend is up, so it is
 * mounted always and a screen reader hears each change as it happens.
 */
function announcement(phase: ReturnType<typeof noticePhase>, detail: string | null): string {
  if (phase === "warming") return `Server starting: ${detail ?? "Server starting up"}`;
  if (phase === "launching") return "Back online";
  if (phase === "unreachable") return "Server isn't responding";
  return "";
}

/**
 * The restart notice's live region and its one card, mounted beside the page
 * in the root layout, never around it. Nothing is inert, scroll is never
 * locked and focus is never moved. The lights themselves sit in the top bar's
 * status slot (`WarmupLights`); this holds what a bar can't:
 *
 * - the announcement for assistive tech, in a `role="status"` region;
 * - after two minutes with no answer, a small bottom card (not a dialog) with
 *   Try again and Dismiss, since those need 44 px targets and shouldn't hide
 *   behind a tooltip.
 */
export default function ServerStatusNotice() {
  const server = useServerStatus();
  const phase = noticePhase(server);

  return (
    <>
      <div role="status" aria-label="Server status" className="sr-only">
        {announcement(phase, server.detail)}
      </div>
      {phase === "unreachable" ? (
        <div
          role="group"
          aria-label="Server isn't responding"
          className="fixed inset-x-4 bottom-[max(1rem,env(safe-area-inset-bottom))] z-40 rounded-md border border-rc-line bg-rc-raised p-4.5 shadow-lg motion-safe:animate-fade-up sm:inset-x-auto sm:bottom-6 sm:right-6 sm:w-90"
        >
          <p className={EYEBROW}>Server status</p>
          <h2 className={`${DISPLAY} mb-1.5 mt-2 text-2xl text-rc-ink`}>Server isn&apos;t responding</h2>
          <p className="text-[13px] leading-normal text-rc-ink-2">
            No answer for 2 minutes. It may be redeploying or down. Pages stay usable, and sections that need data offer
            their own retry.
          </p>
          <div className="mt-3.5 flex gap-2">
            <button
              type="button"
              onClick={retryServerProbe}
              className={`${BUTTON} bg-f1-red text-rc-ink hover:bg-f1-red/85`}
            >
              <RotateCw className="size-3.5" aria-hidden="true" />
              Try again
            </button>
            <button
              type="button"
              onClick={dismissServerNotice}
              className={`${BUTTON} border border-rc-line text-rc-ink-2 hover:border-rc-ink-3 hover:text-rc-ink`}
            >
              Dismiss
            </button>
          </div>
        </div>
      ) : null}
    </>
  );
}
