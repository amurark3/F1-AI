"use client";

import { useState, useEffect } from "react";
import { useLiveTiming } from "../hooks/useLiveTiming";
import LiveTimingTower from "../components/LiveTimingTower";
import CommentaryPanel from "../components/CommentaryPanel";
import { API_BASE } from "../constants/api";

interface LiveRound {
  year: number;
  round: number;
  name: string;
}

export default function LivePage() {
  const [liveRound, setLiveRound] = useState<LiveRound | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const year = new Date().getFullYear();
    fetch(`${API_BASE}/api/schedule/${year}`)
      .then((res) => {
        if (!res.ok) throw new Error(`Schedule fetch failed: ${res.status}`);
        return res.json();
      })
      .then((races: Array<{ round: number; name: string; status: string }>) => {
        const inProgress = races.find((r) => r.status === "in_progress");
        if (inProgress) {
          setLiveRound({ year, round: inProgress.round, name: inProgress.name });
        } else {
          setLiveRound(null);
        }
      })
      .catch(() => {
        setLiveRound(null);
      })
      .finally(() => {
        setLoading(false);
      });
  }, []);

  // Always call the hook; it skips WebSocket when year/round are 0
  const { positions, sessionStatus, commentary, isConnected } = useLiveTiming(
    liveRound?.year ?? 0,
    liveRound?.round ?? 0,
  );

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <svg
          className="w-8 h-8 animate-spin text-neutral-500"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle
            className="opacity-25"
            cx="12"
            cy="12"
            r="10"
            stroke="currentColor"
            strokeWidth="4"
          />
          <path
            className="opacity-75"
            fill="currentColor"
            d="M4 12a8 8 0 018-8v8H4z"
          />
        </svg>
      </div>
    );
  }

  if (!liveRound) {
    return (
      <div className="max-w-7xl mx-auto px-4 py-16 text-center">
        <p className="text-4xl mb-4">&#127937;</p>
        <h1 className="text-2xl font-black uppercase italic mb-2">No Live Session</h1>
        <p className="text-neutral-400">Live timing appears here during race weekends.</p>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 py-6">
      <div className="mb-4">
        <h1 className="text-xl font-black uppercase italic">{liveRound.name}</h1>
        <span className="text-xs font-bold tracking-widest text-red-500 uppercase">
          &bull; LIVE
        </span>
      </div>
      <div className="flex flex-col lg:flex-row gap-6">
        <div className="flex-1 min-w-0">
          <LiveTimingTower
            positions={positions}
            sessionStatus={sessionStatus}
            isConnected={isConnected}
          />
        </div>
        <div className="w-full lg:w-80 shrink-0">
          <CommentaryPanel entries={commentary} />
        </div>
      </div>
    </div>
  );
}
