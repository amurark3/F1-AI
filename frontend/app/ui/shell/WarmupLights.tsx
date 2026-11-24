"use client";

import { useEffect, useState } from "react";

import { LAUNCH_DURATION_MS, LIGHT_COUNT, type NoticePhase, type ServerState } from "@/app/lib/serverStatus";

import { Tooltip } from "../Tooltip";

/** Lights stay lit this long on "back online", then go out for the rest of the launch moment. */
export const LIGHTS_OUT_AFTER_MS = LAUNCH_DURATION_MS / 2;

const LABEL =
  "inline-flex items-center gap-2 whitespace-nowrap font-mono text-[10px] font-medium uppercase leading-none tracking-[0.14em] text-rc-ink-2 sm:gap-2.5 sm:text-[11px] sm:tracking-[0.18em]";
const STAGE_DETAIL = "Server starting up";

/** Whole seconds since `since`, ticking once a second while it is set. */
function useElapsedSeconds(since: number | null): number {
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    if (since === null) return undefined;
    const timer = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(timer);
  }, [since]);

  return since === null || now === null ? 0 : Math.max(0, Math.floor((now - since) / 1000));
}

function formatElapsed(totalSeconds: number): string {
  return `${Math.floor(totalSeconds / 60)}:${String(totalSeconds % 60).padStart(2, "0")}`;
}

/** The five lamps: lit ones are the brand red, unlit ones a dim ring. A lamp lights once as it comes on; all go dark together on `out`. */
function Lamps({ lit, out = false }: { lit: number; out?: boolean }) {
  return (
    <span
      aria-hidden="true"
      className="inline-flex gap-1 rounded-[3px] border border-rc-line bg-background px-[5px] py-[3px] sm:gap-[5px] sm:px-1.5 sm:py-1"
    >
      {Array.from({ length: LIGHT_COUNT }, (_, index) => (
        <i
          key={index}
          className={`size-2 rounded-full sm:size-2.5 ${
            index < lit
              ? "bg-f1-red motion-safe:animate-light-on"
              : `bg-rc-raised shadow-[inset_0_0_0_1px_var(--rc-dim)] ${out ? "motion-safe:animate-lights-out" : ""}`
          }`}
        />
      ))}
    </span>
  );
}

function StartingLights({ server }: { server: ServerState }) {
  const elapsed = useElapsedSeconds(server.warmingSince);
  return (
    <Tooltip
      className={`${LABEL} motion-safe:animate-fade-up`}
      label={
        <>
          <Lamps lit={server.lit} />
          <b className="font-semibold text-rc-ink">
            <span className="sm:hidden">Starting</span>
            <span className="hidden sm:inline">Server starting</span>
          </b>
          <span className="hidden text-rc-ink-3 sm:inline">
            {server.lit}/{LIGHT_COUNT}
          </span>
        </>
      }
    >
      <strong className="block font-sans text-[13px] font-semibold leading-snug text-rc-ink">
        {server.detail ?? STAGE_DETAIL}
      </strong>
      <span className="mb-2 mt-1 block font-mono text-[11px] leading-none tracking-[0.08em] text-rc-ink-3">
        Stage {server.lit} of {LIGHT_COUNT} · {formatElapsed(elapsed)}
      </span>
      Restarting after an update, or waking from sleep on the free tier (about a minute). Pages stay usable; data fills
      in when it&apos;s back.
    </Tooltip>
  );
}

/** Five lit, then, after a beat, all five out together. */
function BackOnlineLights() {
  const [out, setOut] = useState(false);
  useEffect(() => {
    const timer = setTimeout(() => setOut(true), LIGHTS_OUT_AFTER_MS);
    return () => clearTimeout(timer);
  }, []);
  return (
    <span className={LABEL}>
      <Lamps lit={out ? 0 : LIGHT_COUNT} out={out} />
      <b className="font-semibold text-rc-ink">Back online</b>
    </span>
  );
}

function StalledLights({ lit }: { lit: number }) {
  return (
    <span className={LABEL}>
      <Lamps lit={lit} />
      <b className="font-semibold text-rc-red-text">
        <span className="sm:hidden">No response</span>
        <span className="hidden sm:inline">Not responding</span>
      </b>
    </span>
  );
}

/**
 * The restart lights in the top bar's status slot: five lamps lit by the
 * backend's real warm-up stage, with a short label. Starting carries the stage
 * detail in a tooltip; back online plays lights out; unreachable stays quiet
 * (its buttons live in `ServerStatusNotice`'s card). It never blocks anything.
 */
export function WarmupLights({ phase, server }: { phase: NoticePhase; server: ServerState }) {
  if (phase === "warming") return <StartingLights server={server} />;
  if (phase === "launching") return <BackOnlineLights />;
  return <StalledLights lit={server.lit} />;
}
