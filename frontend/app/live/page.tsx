"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import { useLiveTiming } from "../hooks/useLiveTiming";
import LiveTimingTower from "../components/LiveTimingTower";
import CommentaryPanel from "../components/CommentaryPanel";
import ServerWarmingBanner from "../components/ServerWarmingBanner";
import RaceCountdown from "../components/RaceCountdown";
import { API_BASE } from "../constants/api";
import { motion } from "framer-motion";

interface LiveRound {
  year: number;
  round: number;
  name: string;
}

const QUICK_LINKS = [
  { href: "/",            label: "Pit Wall",    sub: "Ask the AI race engineer",    color: "#E10600" },
  { href: "/calendar",   label: "Calendar",    sub: "Full season schedule",         color: "#FF8000" },
  { href: "/standings",  label: "Standings",   sub: "Championship table",           color: "#3671C6" },
  { href: "/predictions",label: "Predictions", sub: "AI race outcome predictions",  color: "#BE3AFF" },
];

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
        setLiveRound(inProgress ? { year, round: inProgress.round, name: inProgress.name } : null);
      })
      .catch(() => setLiveRound(null))
      .finally(() => setLoading(false));
  }, []);

  const { positions, sessionStatus, commentary, isConnected } = useLiveTiming(
    liveRound?.year ?? 0,
    liveRound?.round ?? 0,
  );

  /* ── Loading ────────────────────────────────────────────── */
  if (loading) {
    return (
      <>
        <ServerWarmingBanner />
        <div className="flex items-center justify-center min-h-[70vh]">
          <div className="flex flex-col items-center gap-4">
            <div className="flex gap-2">
              {[0, 1, 2, 3, 4].map((i) => (
                <div
                  key={i}
                  className="h-6 w-4 rounded-sm animate-pit-blink"
                  style={{
                    background: '#E10600',
                    animationDelay: `${i * 0.22}s`,
                  }}
                />
              ))}
            </div>
            <p
              className="text-[11px] font-black uppercase tracking-[0.25em] text-neutral-600"
              style={{ fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}
            >
              Connecting to timing…
            </p>
          </div>
        </div>
      </>
    );
  }

  /* ── No live session ────────────────────────────────────── */
  if (!liveRound) {
    return (
      <>
        <ServerWarmingBanner />
        <div className="max-w-5xl mx-auto px-4 sm:px-6 py-10 sm:py-14">

          {/* Hero */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
            className="text-center mb-10"
          >
            {/* Chequered flag icon */}
            <div className="text-6xl mb-5 animate-flag inline-block">🏁</div>

            <div
              className="inline-flex items-center gap-2 px-3 py-1 rounded border border-white/10 text-[10px] font-black uppercase tracking-[0.2em] text-neutral-500 mb-5"
              style={{ fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}
            >
              <span className="h-[6px] w-[6px] rounded-full bg-neutral-600" />
              Session Inactive
            </div>

            <h1
              className="text-5xl sm:text-7xl font-black italic uppercase tracking-tighter text-white leading-none mb-3"
              style={{ fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}
            >
              No Live{' '}
              <span style={{ color: '#E10600' }}>Session</span>
            </h1>
            <p className="text-neutral-500 text-sm sm:text-base max-w-sm mx-auto">
              Live timing, sector data, and race commentary appear here during race weekends.
            </p>
          </motion.div>

          {/* Race countdown */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, delay: 0.1, ease: [0.22, 1, 0.36, 1] }}
          >
            <RaceCountdown />
          </motion.div>

          {/* Quick nav links */}
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.45, delay: 0.2, ease: [0.22, 1, 0.36, 1] }}
          >
            <p
              className="text-[10px] font-black uppercase tracking-[0.2em] text-neutral-600 mb-3"
              style={{ fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}
            >
              Explore
            </p>
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-3">
              {QUICK_LINKS.map(({ href, label, sub, color }) => (
                <Link
                  key={href}
                  href={href}
                  className="group glass rounded-xl overflow-hidden hover:border-white/15 transition-all duration-200"
                >
                  <div className="h-[2px]" style={{ background: color }} />
                  <div className="p-3 sm:p-4">
                    <p
                      className="text-sm font-black uppercase tracking-wide text-white mb-0.5 group-hover:text-white"
                      style={{ fontFamily: 'var(--font-barlow, var(--font-geist-sans))', color }}
                    >
                      {label}
                    </p>
                    <p className="text-[11px] text-neutral-500">{sub}</p>
                  </div>
                </Link>
              ))}
            </div>
          </motion.div>
        </div>
      </>
    );
  }

  /* ── Live session ───────────────────────────────────────── */
  return (
    <>
      <ServerWarmingBanner />
      <div className="max-w-7xl mx-auto px-4 py-6">
        <div className="mb-4 flex items-center gap-3">
          <div
            className="h-2 w-2 rounded-full animate-glow-pulse"
            style={{ background: '#E10600' }}
          />
          <div>
            <h1
              className="text-xl font-black uppercase italic leading-none"
              style={{ fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}
            >
              {liveRound.name}
            </h1>
            <span
              className="text-[10px] font-black tracking-widest uppercase"
              style={{ color: '#E10600', fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}
            >
              ● LIVE
            </span>
          </div>
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
    </>
  );
}
