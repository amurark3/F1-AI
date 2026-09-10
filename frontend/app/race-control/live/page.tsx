"use client";

import { Activity, RadioTower, Satellite } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import CommentaryPanel from "@/app/components/CommentaryPanel";
import LiveTimingTower from "@/app/components/LiveTimingTower";
import RaceCountdown from "@/app/components/RaceCountdown";
import { API_BASE } from "@/app/constants/api";
import { useLiveTiming, type SessionStatus } from "@/app/hooks/useLiveTiming";

import {
  MetricCard,
  MetricRow,
  PageLoader,
  Panel,
  SectionHeader,
  StatusPill,
  WorkspaceSplit,
  rcFont,
} from "../components/RaceControlPrimitives";

interface LiveRound {
  year: number;
  round: number;
  name: string;
}

/** Label for the timing-feed metric based on connection and session presence. */
function resolveTimingFeedState(isConnected: boolean, hasRound: boolean): string {
  if (isConnected) return "Connected";
  return hasRound ? "Linking" : "Idle";
}

/**
 * Headline session state.
 *
 * A round being "in progress" only means the race weekend has started — the
 * first practice session opens it and it stays open until Sunday evening. Only
 * the socket knows whether a session is actually running and delivering data.
 */
function resolveSessionState(status: SessionStatus | null): { value: string; sub: string } {
  if (status?.status === "live") {
    return { value: "Live", sub: status.session_name ?? "Session on track" };
  }
  if (status?.status === "finished") {
    return { value: "Finished", sub: `${status.session_name ?? "Session"} complete` };
  }
  if (status?.session_name) {
    return { value: "Standby", sub: `${status.session_name} scheduled` };
  }
  return { value: "Standby", sub: "No session on track" };
}

export default function RaceControlLivePage() {
  const [liveRound, setLiveRound] = useState<LiveRound | null>(null);
  const [loading, setLoading] = useState(true);
  const year = new Date().getFullYear();

  useEffect(() => {
    let active = true;

    fetch(`${API_BASE}/api/schedule/${year}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Schedule fetch failed: ${res.status}`);
        return res.json();
      })
      .then((races: Array<{ round: number; name: string; status: string }>) => {
        if (!active) return;
        const inProgress = races.find((race) => race.status === "in_progress");
        setLiveRound(inProgress ? { year, round: inProgress.round, name: inProgress.name } : null);
      })
      .catch(() => {
        if (active) setLiveRound(null);
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [year]);

  const { positions, sessionStatus, commentary, isConnected } = useLiveTiming(
    liveRound?.year ?? 0,
    liveRound?.round ?? 0,
  );

  const timingFeedState = resolveTimingFeedState(isConnected, Boolean(liveRound));
  const sessionState = resolveSessionState(sessionStatus);
  const isSessionLive = sessionStatus?.status === "live";

  if (loading) {
    return (
      <div>
        <SectionHeader
          eyebrow="Live Timing & Commentary"
          title="Live Operations"
          description="Monitor active timing, track position, session state, and AI commentary from the race operations desk."
        />
        <PageLoader
          title="Checking live session"
          detail="Loading the race calendar and looking for an active session before opening the live desk."
        />
      </div>
    );
  }

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
        <MetricCard label="Timing feed" value={timingFeedState} sub={`Season ${year} live lookup`} icon={Satellite} />
      </MetricRow>

      {!isSessionLive ? (
        <LiveIdleView sessionName={sessionStatus?.session_name ?? null} />
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

function LiveIdleView({ sessionName }: { sessionName: string | null }) {
  return (
    <WorkspaceSplit className="xl:[&>*:first-child]:flex-1 xl:[&>*:last-child]:basis-[360px]">
      <section className="space-y-5">
        <RaceCountdown />
        <Panel className="p-5">
          <div className="flex items-start gap-4">
            <div className="flex h-11 w-11 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04]">
              <Activity className="h-5 w-5 text-neutral-400" />
            </div>
            <div>
              <h2 className="text-2xl font-black italic uppercase text-white" style={rcFont}>
                Control Room Idle
              </h2>
              <p className="mt-2 max-w-3xl text-base leading-relaxed text-neutral-400">
                {sessionName
                  ? `${sessionName} is scheduled but no timing data is coming through yet. The tower opens the moment the feed goes live.`
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
