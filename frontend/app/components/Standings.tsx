"use client";

import { motion } from "framer-motion";
import { useState } from "react";
import useSWR from "swr";

import { API_BASE } from "../constants/api";
import { fetcher } from "../utils/fetcher";

const TEAM_COLORS: Record<string, string> = {
  "Red Bull": "#3671C6",
  Mercedes: "#27F4D2",
  Ferrari: "#E8002D",
  McLaren: "#FF8000",
  "Aston Martin": "#229971",
  "Alpine F1 Team": "#FF87BC",
  Williams: "#64C4FF",
  "RB F1 Team": "#6692FF",
  "Haas F1 Team": "#B6BABD",
  Audi: "#FF0000",
  "Cadillac F1 Team": "#E0D4B8",
};

const getTeamColor = (team: string) => TEAM_COLORS[team] ?? "#6B7280";

const MEDAL: Record<number, { bg: string; text: string }> = {
  1: { bg: "rgba(255,215,0,0.10)", text: "#FFD700" },
  2: { bg: "rgba(192,192,192,0.08)", text: "#C0C0C0" },
  3: { bg: "rgba(205,127,50,0.08)", text: "#CD7F32" },
};

/** Derive F1-style 3-letter driver code from full name */
const driverCode = (fullName: string): string => {
  const parts = fullName.trim().split(/\s+/);
  return (parts[parts.length - 1] ?? parts[0]).slice(0, 3).toUpperCase();
};

interface StandingRow {
  position: number;
  driver?: string;
  team: string;
  points: number;
  wins: number;
}

const rowVariants = {
  hidden: { opacity: 0, x: 24 },
  visible: (i: number) => ({
    opacity: 1,
    x: 0,
    transition: { type: "spring" as const, damping: 22, stiffness: 200, delay: i * 0.025 },
  }),
};

const F1 = { fontFamily: "var(--font-barlow, var(--font-geist-sans))" };

export default function Standings() {
  const now = new Date();
  const defaultYear = now.getMonth() >= 1 ? now.getFullYear() : now.getFullYear() - 1;
  const [year, setYear] = useState(defaultYear);
  const [type, setType] = useState<"drivers" | "constructors">("drivers");

  const { data, isLoading } = useSWR<StandingRow[]>(`${API_BASE}/api/standings/${type}/${year}`, fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 60000,
  });

  const leaderPts = data?.[0]?.points ?? 1;
  const hasRows = !isLoading && Boolean(data) && (data?.length ?? 0) > 0;
  const showEmpty = !isLoading && (!data || data.length === 0);

  return (
    <div>
      {hasRows && data && <StandingsSummary data={data} type={type} />}

      {/* ── Controls ─────────────────────────────────────────── */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-5 gap-3">
        <div className="flex glass rounded-xl p-0.5 gap-0.5">
          {(["drivers", "constructors"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setType(t)}
              className="px-4 sm:px-5 py-2 rounded-[10px] text-xs font-black uppercase tracking-widest transition-all duration-200"
              style={{
                ...F1,
                background: type === t ? "#E10600" : "transparent",
                color: type === t ? "#fff" : "#525252",
                boxShadow: type === t ? "0 2px 14px rgba(225,6,0,0.3)" : "none",
              }}
            >
              {t}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-3">
          <span className="text-[10px] font-black uppercase tracking-[0.18em] text-neutral-600" style={F1}>
            Season
          </span>
          <select
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            className="appearance-none glass text-white text-sm font-bold rounded-xl px-3 py-2 focus:ring-1 focus:ring-[#E10600]/40 outline-none"
          >
            {[2021, 2022, 2023, 2024, 2025, 2026].map((y) => (
              <option key={y} value={y}>
                {y}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* ── Column headers ───────────────────────────────────── */}
      {hasRows && (
        <div
          className="flex items-center gap-2 px-4 sm:px-5 mb-1.5 pl-6 text-[9px] font-black uppercase tracking-[0.18em] text-neutral-700"
          style={F1}
        >
          <div className="w-8 sm:w-10 text-center">Pos</div>
          {type === "drivers" && <div className="w-10 hidden sm:block">Code</div>}
          <div className="flex-1">{type === "drivers" ? "Driver" : "Constructor"}</div>
          <div className="hidden sm:block w-14 text-center">Wins</div>
          <div className="w-16 sm:w-20 text-right">Gap</div>
          <div className="w-14 sm:w-20 text-right">Pts</div>
        </div>
      )}

      {/* ── Skeleton ─────────────────────────────────────────── */}
      {isLoading && (
        <div className="space-y-1.5">
          {Array.from({ length: 10 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3 p-3 sm:p-4 glass rounded-xl animate-pulse">
              <div className="h-6 w-7 bg-white/5 rounded" />
              <div className="h-4 flex-1 max-w-[10rem] bg-white/5 rounded" />
              <div className="h-4 w-14 bg-white/5 rounded ml-auto" />
            </div>
          ))}
        </div>
      )}

      {/* ── Empty ────────────────────────────────────────────── */}
      {showEmpty && (
        <div className="p-14 glass rounded-xl border border-dashed border-white/8 text-center">
          <p className="text-neutral-500 font-bold">No standings data for {year}</p>
        </div>
      )}

      {/* ── Rows ─────────────────────────────────────────────── */}
      {hasRows && data && (
        <div className="space-y-1">
          {data.map((row, index) => (
            <StandingsRow key={row.position} row={row} index={index} type={type} leaderPts={leaderPts} />
          ))}
        </div>
      )}
    </div>
  );
}

function StandingsSummary({ data, type }: { data: StandingRow[]; type: "drivers" | "constructors" }) {
  const leader = data[0];
  const second = data[1];
  const leaderName = type === "drivers" ? leader?.driver : leader?.team;
  const gapToSecond = leader && second ? leader.points - second.points : null;
  const totalWins = data.reduce((sum, row) => sum + row.wins, 0);

  const tiles = [
    { label: "Leader", value: leaderName ?? "TBC", sub: leader?.team ?? "Championship control" },
    { label: "Gap P1-P2", value: gapToSecond != null ? `${gapToSecond} pts` : "TBC", sub: "Primary pressure delta" },
    {
      label: "Classified",
      value: String(data.length),
      sub: type === "drivers" ? "Drivers tracked" : "Constructors tracked",
    },
    { label: "Wins", value: String(totalWins), sub: "Season win count" },
  ];

  return (
    <div className="grid grid-cols-2 lg:grid-cols-4 gap-2 sm:gap-3 mb-5">
      {tiles.map(({ label, value, sub }) => (
        <div key={label} className="glass rounded-xl px-4 py-3 min-w-0">
          <p className="text-[9px] font-black uppercase tracking-[0.18em] text-neutral-600 mb-1" style={F1}>
            {label}
          </p>
          <p className="text-lg sm:text-xl font-black uppercase text-white truncate" style={F1}>
            {value}
          </p>
          <p className="text-[10px] text-neutral-600 truncate">{sub}</p>
        </div>
      ))}
    </div>
  );
}

function StandingsRow({
  row,
  index,
  type,
  leaderPts,
}: {
  row: StandingRow;
  index: number;
  type: "drivers" | "constructors";
  leaderPts: number;
}) {
  const color = getTeamColor(row.team);
  const medal = MEDAL[row.position];
  const barPct = Math.round((row.points / leaderPts) * 100);
  const gap = index === 0 ? "—" : `–${leaderPts - row.points}`;
  const ptsPct = Math.round((row.points / (leaderPts || 1)) * 100);
  const code = row.driver ? driverCode(row.driver) : "";

  return (
    <motion.div
      custom={index}
      variants={rowVariants}
      initial="hidden"
      animate="visible"
      whileHover={{ x: 3 }}
      className="relative rounded-xl overflow-hidden border transition-all duration-150 group"
      style={{
        background: medal ? medal.bg : "rgba(255,255,255,0.022)",
        borderColor: medal ? `${medal.text}1A` : "rgba(255,255,255,0.05)",
      }}
    >
      {/* Championship points bar */}
      <div
        className="absolute left-0 top-0 bottom-0 opacity-[0.055] champ-bar"
        style={{ width: `${barPct}%`, background: color }}
      />
      {/* Team colour left bar */}
      <div className="absolute left-0 top-2 bottom-2 w-[3px] rounded-full" style={{ background: color }} />

      <div className="relative flex items-center gap-2 sm:gap-3 px-3 sm:px-4 py-3 pl-5 sm:pl-6">
        {/* Position */}
        <div
          className="w-7 sm:w-9 text-center font-black text-base sm:text-lg shrink-0 leading-none"
          style={{ color: medal ? medal.text : "#3a3a3a", ...F1 }}
        >
          {row.position}
        </div>

        {/* Driver code badge (drivers only, desktop) */}
        {type === "drivers" && (
          <div
            className="hidden sm:flex items-center justify-center h-6 w-10 rounded text-[10px] font-black shrink-0"
            style={{ background: `${color}1A`, color, ...F1 }}
          >
            {code}
          </div>
        )}

        {/* Name + team */}
        <div className="flex-1 min-w-0">
          {type === "drivers" ? (
            <>
              <p className={`font-bold text-sm truncate leading-tight ${medal ? "text-white" : "text-neutral-300"}`}>
                {row.driver}
              </p>
              <p className="text-[10px] font-semibold truncate mt-0.5" style={{ color }}>
                {row.team}
              </p>
            </>
          ) : (
            <div className="flex items-center gap-2">
              <div className="h-2.5 w-2.5 rounded-full shrink-0" style={{ background: color }} />
              <p className={`font-bold text-sm truncate ${medal ? "text-white" : "text-neutral-300"}`}>{row.team}</p>
            </div>
          )}
        </div>

        {/* Wins */}
        <div className="hidden sm:block text-center w-14 shrink-0">
          <p className={`font-mono text-sm ${row.wins > 0 ? "text-white" : "text-neutral-700"}`}>{row.wins}</p>
          <p className="text-[9px] text-neutral-700 uppercase tracking-wider">wins</p>
        </div>

        {/* Gap to leader */}
        <div className="text-right w-16 sm:w-20 shrink-0">
          <p className="font-mono text-sm" style={{ color: index === 0 ? "#E10600" : "#404040" }}>
            {gap}
          </p>
          <p className="text-[9px] text-neutral-700 uppercase tracking-wider">gap</p>
        </div>

        {/* Points + % */}
        <div className="text-right w-14 sm:w-20 shrink-0">
          <p
            className="font-mono font-black text-base sm:text-lg leading-none animate-count-in"
            style={{ color: medal ? medal.text : "#d4d4d4", ...F1 }}
          >
            {row.points}
          </p>
          <p className="text-[9px] uppercase tracking-wider" style={{ color: `${color}99` }}>
            {ptsPct}%
          </p>
        </div>
      </div>
    </motion.div>
  );
}
