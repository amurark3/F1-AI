"use client";

import LiveTimingTower from "@/app/components/LiveTimingTower";
import { useLiveTiming } from "@/app/hooks/useLiveTiming";

import { Panel, StatusPill, rcFont } from "./RaceControlPrimitives";

interface LiveTimingPanelProps {
  year: number;
  /** The weekend the command centre is showing, from the shell segment. */
  race: { round: number; status: string } | null | undefined;
}

/**
 * The timing tower, shown on the command centre only while a session is live.
 *
 * It used to have a page of its own, which spent every hour off track showing a
 * countdown and an idle notice. Now it renders nothing unless the feed for the
 * running session is delivering. The socket opens only during a race weekend:
 * `in_progress` spans Friday practice to Sunday evening, and the backend idles
 * cheaply between sessions.
 */
export function LiveTimingPanel({ year, race }: LiveTimingPanelProps) {
  const weekendRound = race?.status === "in_progress" ? race.round : 0;
  const { positions, sessionStatus, isConnected } = useLiveTiming(weekendRound ? year : 0, weekendRound);

  if (sessionStatus?.status !== "live") return null;

  return (
    <Panel className="p-5">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.18em] text-[#E10600]" style={rcFont}>
            Live timing
          </p>
          <h2 className="text-2xl font-black italic uppercase text-white" style={rcFont}>
            Track Position
          </h2>
        </div>
        <StatusPill color={isConnected ? "#00FF78" : "#FFF200"}>{isConnected ? "Connected" : "Linking"}</StatusPill>
      </div>
      <LiveTimingTower positions={positions} sessionStatus={sessionStatus} isConnected={isConnected} />
    </Panel>
  );
}
