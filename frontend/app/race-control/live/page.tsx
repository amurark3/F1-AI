"use client";

import { Activity, RadioTower, Satellite } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import CommentaryPanel from "@/app/components/CommentaryPanel";
import LiveTimingTower from "@/app/components/LiveTimingTower";
import RaceCountdown from "@/app/components/RaceCountdown";
import { API_BASE } from "@/app/constants/api";
import { useLiveTiming } from "@/app/hooks/useLiveTiming";

import { MetricCard, MetricRow, PageLoader, Panel, SectionHeader, StatusPill, WorkspaceSplit, rcFont } from "../components/RaceControlPrimitives";

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
        <MetricCard label="Session state" value={liveRound ? "Live" : "Standby"} sub={liveRound ? liveRound.name : "No active session"} icon={RadioTower} color={liveRound ? "#E10600" : "#3671C6"} />
        <MetricCard label="Timing feed" value={timingFeedState} sub={`Season ${year} live lookup`} icon={Satellite} />
      </MetricRow>

      {!liveRound ? (
        <WorkspaceSplit className="xl:[&>*:first-child]:flex-1 xl:[&>*:last-child]:basis-[360px]">
          <section className="space-y-5">
            <RaceCountdown />
            <Panel className="p-5">
              <div className="flex items-start gap-4">
                <div className="flex h-11 w-11 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04]">
                  <Activity className="h-5 w-5 text-neutral-400" />
                </div>
                <div>
                  <h2 className="text-2xl font-black italic uppercase text-white" style={rcFont}>Control Room Idle</h2>
                  <p className="mt-2 max-w-3xl text-base leading-relaxed text-neutral-400">
                    No active F1 session is broadcasting. The timing tower connects automatically when the schedule reports an in-progress race weekend.
                  </p>
                </div>
              </div>
            </Panel>
          </section>

          <Panel className="p-5">
            <div className="mb-5 flex items-center justify-between">
              <h2 className="text-xl font-black italic uppercase text-white" style={rcFont}>Race Week Prep</h2>
              <StatusPill color="#3671C6">Standby</StatusPill>
            </div>
            <div className="space-y-3">
              <Link href="/race-control/engineer" className="flex items-center gap-3 rounded-lg border border-white/10 bg-white/[0.035] px-4 py-3 text-sm font-bold text-neutral-300 hover:text-white">
                <RadioTower className="h-4 w-4 text-[#00FF78]" />
                Ask the engineer for a pre-race brief
              </Link>
            </div>
          </Panel>
        </WorkspaceSplit>
      ) : (
        <WorkspaceSplit className="xl:[&>*:first-child]:flex-1 xl:[&>*:last-child]:basis-[380px]">
          <Panel className="p-5">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <p className="text-xs font-black uppercase tracking-[0.18em] text-[#00FF78]" style={rcFont}>Timing Tower</p>
                <h2 className="text-2xl font-black italic uppercase text-white" style={rcFont}>Track Position</h2>
              </div>
              <StatusPill color={isConnected ? "#00FF78" : "#FFF200"}>{isConnected ? "Connected" : "Linking"}</StatusPill>
            </div>
            <LiveTimingTower positions={positions} sessionStatus={sessionStatus} isConnected={isConnected} />
          </Panel>

          <CommentaryPanel entries={commentary} />
        </WorkspaceSplit>
      )}
    </div>
  );
}
