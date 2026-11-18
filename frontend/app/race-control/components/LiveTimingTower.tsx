"use client";

import { useLiveTiming, type LivePosition, type SessionStatus } from "@/app/hooks/useLiveTiming";
import { NEUTRAL_TEAM_COLOR, getTeamColor } from "@/app/lib/teamColors";
import { DriverName } from "@/app/ui/names/DriverName";
import { PanelHeading } from "@/app/ui/PanelHeading";

import { StateTag } from "../grand-prix/StateTag";

import { Panel } from "./RaceControlPrimitives";

import type { CSSProperties } from "react";

interface LiveTimingTowerProps {
  year: number;
  /** The weekend the command centre is showing, from the shell segment. */
  race: { round: number; status: string } | null | undefined;
}

const NOTICE = "py-10 text-center text-sm text-rc-ink-3";
const NO_GAP = "—";

function GapCell({ gap }: { gap: string }) {
  if (gap === "LEADER")
    return <span className="text-right font-mono text-[13px] font-medium text-rc-ink-3">Leader</span>;
  if (gap === NO_GAP) return <span className="text-right font-mono text-[13px] text-rc-ink-3">{NO_GAP}</span>;
  return <span className="text-right font-mono text-[13px] font-semibold text-rc-ink">{gap}</span>;
}

function Row({ row, year }: { row: LivePosition; year: number }) {
  return (
    <li className="grid min-h-9 grid-cols-[22px_3px_minmax(0,1fr)_72px] items-center gap-3 border-b border-rc-line-soft sm:grid-cols-[26px_3px_minmax(0,1fr)_30px_76px]">
      <span
        className={`text-right font-mono text-[13px] font-semibold ${row.position === 1 ? "text-rc-gold" : "text-rc-ink-3"}`}
      >
        {row.position}
      </span>
      <span
        aria-hidden="true"
        className="h-[18px] rounded-[1px]"
        style={{ background: row.team ? getTeamColor(row.team) : NEUTRAL_TEAM_COLOR }}
      />
      <span className="min-w-0 truncate font-semibold text-rc-ink">
        <DriverName variant="codeLast" name={row.driver} code={row.driver} year={year} />
      </span>
      <span className="hidden text-right font-mono text-[11px] text-rc-ink-3 sm:block">{row.driver_number}</span>
      <GapCell gap={row.gap} />
    </li>
  );
}

function Body({
  positions,
  sessionStatus,
  isConnected,
  year,
}: {
  positions: LivePosition[];
  sessionStatus: SessionStatus;
  isConnected: boolean;
  year: number;
}) {
  if (!isConnected) return <p className={NOTICE}>Connecting to live timing…</p>;
  if (positions.length === 0) {
    return (
      <p className={NOTICE}>
        {sessionStatus.session_name ? `Waiting for ${sessionStatus.session_name} timing data…` : "No session on track"}
      </p>
    );
  }
  return (
    <>
      <ol
        aria-label="Running order"
        className="grid lg:grid-flow-col lg:grid-cols-2 lg:gap-x-10 lg:[grid-template-rows:repeat(var(--rows),auto)]"
        style={{ "--rows": Math.ceil(positions.length / 2) } as CSSProperties}
      >
        {positions.map((row) => (
          <Row key={row.driver_number} row={row} year={year} />
        ))}
      </ol>
      {positions.some((row) => row.gap === NO_GAP) && (
        <p className="mt-4 font-mono text-[10px] uppercase leading-[1.6] tracking-[0.1em] text-rc-ink-3">
          — = the feed has no gap for this car
        </p>
      )}
    </>
  );
}

/**
 * The timing tower, shown on the command centre only while a session is live.
 *
 * It renders nothing unless the feed for the running session is delivering.
 * The socket opens only during a race weekend: `in_progress` spans Friday
 * practice to Sunday evening, and the backend idles cheaply between sessions.
 */
export function LiveTimingTower({ year, race }: LiveTimingTowerProps) {
  const weekendRound = race?.status === "in_progress" ? race.round : 0;
  const { positions, sessionStatus, isConnected } = useLiveTiming(weekendRound ? year : 0, weekendRound);

  if (sessionStatus?.status !== "live") return null;

  const { session_name, lap, feed_age_seconds } = sessionStatus;
  return (
    <Panel as="section" className="p-5 sm:p-6">
      <PanelHeading
        as="h2"
        eyebrow={
          <span className="inline-flex items-center gap-2 text-rc-red-text">
            <span aria-hidden="true" className="size-[7px] rounded-full bg-rc-red-text" />
            Live timing
          </span>
        }
        title={`${session_name ?? "Session"}${lap !== null ? ` · Lap ${lap}` : ""}`}
        sub={`Gap to the leader, from OpenF1's position and interval feeds${
          feed_age_seconds !== null ? ` · updated ${Math.round(feed_age_seconds)} s ago` : ""
        }`}
        aside={isConnected ? <StateTag tone="red">Connected</StateTag> : <StateTag>Linking</StateTag>}
      />
      <Body positions={positions} sessionStatus={sessionStatus} isConnected={isConnected} year={year} />
    </Panel>
  );
}
