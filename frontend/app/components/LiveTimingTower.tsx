"use client";

import React from "react";

import type { LivePosition, SessionStatus } from "../hooks/useLiveTiming";

interface Props {
  positions: LivePosition[];
  sessionStatus: SessionStatus | null;
  isConnected: boolean;
}

/** Header line naming the session and, when known, the lap. */
function SessionLine({ sessionStatus }: { sessionStatus: SessionStatus }) {
  return (
    <div className="mb-3 flex items-center gap-3">
      <span className="text-xs font-bold uppercase tracking-widest text-neutral-400">
        {sessionStatus.session_name ?? "Session"}
      </span>
      {sessionStatus.lap != null && (
        <span className="text-xs font-mono text-neutral-500">LAP {sessionStatus.lap}</span>
      )}
    </div>
  );
}

/** Centred placeholder used while the tower has nothing to show. */
function TowerNotice({ children, spinning }: { children: React.ReactNode; spinning?: boolean }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-neutral-400">
      {spinning ? (
        <svg className="w-6 h-6 animate-spin mb-3 text-neutral-500" fill="none" viewBox="0 0 24 24">
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
        </svg>
      ) : (
        <span className="inline-block w-3 h-3 rounded-full bg-neutral-500 animate-pulse mb-3" />
      )}
      <p className="text-sm">{children}</p>
    </div>
  );
}

export default function LiveTimingTower({ positions, sessionStatus, isConnected }: Props) {
  if (!isConnected) {
    return <TowerNotice>Connecting to live timing...</TowerNotice>;
  }

  // The backend sends positions only while a feed is actually delivering, so
  // an empty tower means nothing is running — never a stale classification.
  if (positions.length === 0) {
    const session = sessionStatus?.session_name;
    return (
      <TowerNotice spinning>
        {session ? `Waiting for ${session} timing data...` : "No session on track"}
      </TowerNotice>
    );
  }

  return (
    <div>
      {sessionStatus && <SessionLine sessionStatus={sessionStatus} />}

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-xs font-bold uppercase tracking-widest text-neutral-500 border-b border-white/10">
              <th className="pb-2 pr-4 text-left">POS</th>
              <th className="pb-2 pr-4 text-left">NO</th>
              <th className="pb-2 pr-4 text-left">DRIVER</th>
              <th className="pb-2 text-left">GAP</th>
            </tr>
          </thead>
          <tbody>
            {positions.map((p) => (
              <tr
                key={p.driver_number}
                className="border-b border-white/5 hover:bg-white/5 transition-colors"
              >
                <td className="py-2 pr-4 text-neutral-400 font-mono text-xs">P{p.position}</td>
                <td className="py-2 pr-4 text-neutral-500 font-mono text-xs">{p.driver_number}</td>
                <td
                  className={`py-2 pr-4 font-mono font-bold ${p.position === 1 ? "text-white" : "text-neutral-300"}`}
                >
                  {p.driver}
                </td>
                <td className="py-2 text-neutral-400 font-mono text-xs">
                  {p.gap === "LEADER" ? "—" : p.gap}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
