"use client";

import { Activity, RadioTower, Satellite } from "lucide-react";
import Link from "next/link";

import CommentaryPanel from "@/app/components/CommentaryPanel";
import LiveTimingTower from "@/app/components/LiveTimingTower";
import { useLiveTiming, type SessionStatus } from "@/app/hooks/useLiveTiming";

import {
  MetricCard,
  MetricRow,
  Panel,
  SectionHeader,
  StatusPill,
  WorkspaceSplit,
  rcFont,
} from "../components/RaceControlPrimitives";

import WeekendCountdown from "./WeekendCountdown";

interface LiveRound {
  year: number;
  round: number;
  name: string;
  /** Session name to UTC start time, so the desk can count to the next one. */
  sessions: Record<string, string> | null;
}

/** A feed age in seconds, as the coarsest useful span. */
function formatFeedAge(seconds: number): string {
  if (seconds < 60) return `${String(seconds)}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${String(minutes)}m ago`;
  return `${String(Math.floor(minutes / 60))}h ago`;
}

/**
 * The timing-feed metric.
 *
 * Reports how long ago the newest sample landed rather than only whether the
 * socket is up. The position feed emits on a change, so minutes of silence
 * mean the order is holding — worth showing, never worth hiding the tower for.
 */
function resolveTimingFeed(
  isConnected: boolean,
  hasRound: boolean,
  status: SessionStatus | null,
  year: number,
): { value: string; sub: string } {
  const lookup = `Season ${String(year)} live lookup`;
  if (!isConnected) return { value: hasRound ? "Linking" : "Idle", sub: lookup };

  const age = status?.feed_age_seconds;
  if (age === null || age === undefined) return { value: "Connected", sub: lookup };
  return { value: "Connected", sub: `Last sample ${formatFeedAge(age)}` };
}

/**
 * Headline session state.
 *
 * A round being "in progress" only means the race weekend has started — the
 * first practice session opens it and it stays open until Sunday evening. Only
 * the socket knows whether a session is actually running and delivering data.
 *
 * The three standby cases are not the same thing and must not read the same:
 * a session under way whose feed has not opened, a gap between sessions, and
 * an empty calendar.
 */
function resolveSessionState(status: SessionStatus | null): { value: string; sub: string } {
  if (status?.status === "live") {
    return { value: "Live", sub: status.session_name ?? "Session on track" };
  }
  if (status?.status === "finished") {
    return { value: "Finished", sub: `${status.session_name ?? "Session"} complete` };
  }
  if (status?.session_name) {
    return { value: "Standby", sub: `${status.session_name} — awaiting feed` };
  }
  return { value: "Standby", sub: "No session on track" };
}

interface LiveViewProps {
  /** The season being monitored, shown even when no session is running. */
  year: number;
  /** The running weekend, resolved on the server. Null when nothing is live. */
  liveRound: LiveRound | null;
}

/**
 * Live operations board.
 *
 * Stays a client component for the timing WebSocket, but no longer opens with a
 * loading state: the server has already resolved which round is running, so the
 * page paints its standby or live chrome immediately and the socket only
 * supplies the ticking data.
 */
export function LiveView({ year, liveRound }: LiveViewProps) {
  const { positions, sessionStatus, commentary, isConnected } = useLiveTiming(
    liveRound?.year ?? 0,
    liveRound?.round ?? 0,
  );

  const timingFeed = resolveTimingFeed(isConnected, Boolean(liveRound), sessionStatus, year);
  const sessionState = resolveSessionState(sessionStatus);
  const isSessionLive = sessionStatus?.status === "live";

  return (
    <div>
      <SectionHeader
        eyebrow="Live Timing & Commentary"
        title={liveRound?.name ?? "Live Operations"}
        description="Monitor active timing, track position, session state, and AI commentary from the race operations desk."
      />

      <MetricRow>
        <MetricCard
          label="Session state"
          value={sessionState.value}
          sub={sessionState.sub}
          icon={RadioTower}
          color={isSessionLive ? "#E10600" : "#3671C6"}
        />
        <MetricCard label="Timing feed" value={timingFeed.value} sub={timingFeed.sub} icon={Satellite} />
      </MetricRow>

      {!isSessionLive ? (
        <LiveIdleView
          sessionName={sessionStatus?.session_name ?? null}
          sessions={liveRound?.sessions ?? null}
          weekendName={liveRound?.name ?? null}
        />
      ) : (
        <LiveActiveView
          positions={positions}
          sessionStatus={sessionStatus}
          commentary={commentary}
          isConnected={isConnected}
        />
      )}
    </div>
  );
}

interface LiveIdleViewProps {
  /** Named when a session window is open but its feed has not opened yet. */
  sessionName: string | null;
  sessions: Record<string, string> | null;
  weekendName: string | null;
}

function LiveIdleView({ sessionName, sessions, weekendName }: LiveIdleViewProps) {
  const awaitingFeed = sessionName !== null;

  return (
    <WorkspaceSplit className="xl:[&>*:first-child]:flex-1 xl:[&>*:last-child]:basis-[360px]">
      <section className="space-y-5">
        <WeekendCountdown sessions={sessions} weekendName={weekendName} />
        <Panel className="p-5">
          <div className="flex items-start gap-4">
            <div className="flex h-11 w-11 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04]">
              <Activity className={`h-5 w-5 ${awaitingFeed ? "text-[#3671C6]" : "text-neutral-400"}`} />
            </div>
            <div>
              <h2 className="text-2xl font-black italic uppercase text-white" style={rcFont}>
                {awaitingFeed ? "Awaiting Feed" : "Control Room Idle"}
              </h2>
              <p className="mt-2 max-w-3xl text-base leading-relaxed text-neutral-400">
                {awaitingFeed
                  ? `${sessionName} is under way, but the timing feed has not started publishing. The tower opens on the first sample.`
                  : "No F1 session is on track. The timing tower opens automatically when a session starts broadcasting."}
              </p>
            </div>
          </div>
        </Panel>
      </section>

      <Panel className="p-5">
        <div className="mb-5 flex items-center justify-between">
          <h2 className="text-xl font-black italic uppercase text-white" style={rcFont}>
            Race Week Prep
          </h2>
          <StatusPill color="#3671C6">Standby</StatusPill>
        </div>
        <div className="space-y-3">
          <Link
            href="/race-control/engineer"
            className="flex items-center gap-3 rounded-lg border border-white/10 bg-white/[0.035] px-4 py-3 text-sm font-bold text-neutral-300 hover:text-white"
          >
            <RadioTower className="h-4 w-4 text-[#00FF78]" />
            Ask the engineer for a pre-race brief
          </Link>
        </div>
      </Panel>
    </WorkspaceSplit>
  );
}

type LiveTimingState = ReturnType<typeof useLiveTiming>;

function LiveActiveView({
  positions,
  sessionStatus,
  commentary,
  isConnected,
}: Pick<LiveTimingState, "positions" | "sessionStatus" | "commentary" | "isConnected">) {
  return (
    <WorkspaceSplit className="xl:[&>*:first-child]:flex-1 xl:[&>*:last-child]:basis-[380px]">
      <Panel className="p-5">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.18em] text-[#00FF78]" style={rcFont}>
              Timing Tower
            </p>
            <h2 className="text-2xl font-black italic uppercase text-white" style={rcFont}>
              Track Position
            </h2>
          </div>
          <StatusPill color={isConnected ? "#00FF78" : "#FFF200"}>{isConnected ? "Connected" : "Linking"}</StatusPill>
        </div>
        <LiveTimingTower positions={positions} sessionStatus={sessionStatus} isConnected={isConnected} />
      </Panel>

      <CommentaryPanel entries={commentary} />
    </WorkspaceSplit>
  );
}
