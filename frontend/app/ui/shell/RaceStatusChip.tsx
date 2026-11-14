"use client";

import { API_BASE } from "@/app/constants/api";

import { useSection } from "../section/useSection";
import { Tooltip } from "../Tooltip";
import { useClock } from "../useClock";

import { raceStatus, type RacePhase, type ShellRace } from "./raceStatus";

/** The fields of the Command Center's shell segment the chip reads. */
interface ShellSegment {
  race?: ShellRace | null;
}

/** The Command Center's settings for the same segment, so one request serves both. */
const SHELL_SWR = { revalidateOnFocus: false, dedupingInterval: 120_000 };

/** Red pulses while a session is on track; blue is upcoming; a weekend that has run goes quiet. */
const DOT: Record<RacePhase, string> = {
  live: "bg-rc-red-text motion-safe:animate-pulse",
  "pre-race": "bg-rc-blue",
  "post-race": "bg-rc-ink-3",
};

/**
 * The top bar's "● R20 · PRE-RACE": the selected weekend's round and where it
 * stands, with the next session's countdown (or what is on track) on hover,
 * focus or tap.
 *
 * It reads the Command Center's shell segment (schedule and standings, no
 * telemetry) and the page's one shared clock, so the phase turns live at the
 * scheduled start without a refetch. It renders nothing until both are in, and
 * nothing when the segment fails: the bar never shows a broken status.
 */
export function RaceStatusChip() {
  const now = useClock();
  const year = new Date().getFullYear();
  const { data } = useSection<ShellSegment>(`${API_BASE}/api/race-control/overview/${year}/shell`, {
    config: SHELL_SWR,
  });
  const race = data?.race;
  if (now === null || !race) return null;

  const status = raceStatus(race, now);
  return (
    <Tooltip
      label={
        <>
          <span aria-hidden="true" className={`size-1.75 shrink-0 rounded-full ${DOT[status.phase]}`} />
          {status.label}
        </>
      }
      className="inline-flex items-center gap-2.5 whitespace-nowrap font-mono text-[11px] font-medium uppercase leading-none tracking-[0.18em] text-rc-ink-2"
    >
      <span className="block font-semibold text-rc-ink">{status.event}</span>
      {status.detail ? <span className="block tabular-nums">{status.detail}</span> : null}
    </Tooltip>
  );
}
