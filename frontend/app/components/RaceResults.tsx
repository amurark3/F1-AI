"use client";

import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown } from 'lucide-react';
import { useState } from 'react';

export interface RaceResult {
  position: number | null;
  driver: string;
  full_name: string;
  team: string;
  grid: number | null;
  time: string;
  points: number;
  status: string;
}

interface RaceResultsProps {
  results: RaceResult[] | null;
}

const PODIUM_CUTOFF = 3;
const DEFAULT_VISIBLE = 10;

/** Grid-vs-finish delta, formatted for display. `"-"` when either is unknown. */
function positionChange(result: RaceResult): string {
  if (typeof result.grid !== "number" || typeof result.position !== "number") {
    return "-";
  }
  const diff = result.grid - result.position;
  if (diff > 0) return `+${diff}`;
  if (diff < 0) return `${diff}`;
  return "0";
}

function changeColor(change: string): string {
  if (change.startsWith("+")) return "text-green-400";
  if (change.startsWith("-")) return "text-red-400";
  return "text-neutral-600";
}

function RaceResultRow({ result, index }: { result: RaceResult; index: number }) {
  const change = positionChange(result);
  const isTop3 = typeof result.position === "number" && result.position <= PODIUM_CUTOFF;
  const isDNF = result.status !== "Finished" && !result.status.includes("Lap");

  return (
    <motion.div
      initial={{ opacity: 0, x: 20 }}
      animate={{ opacity: 1, x: 0 }}
      exit={{ opacity: 0, x: -20 }}
      transition={{ type: "spring" as const, damping: 22, stiffness: 250, delay: index * 0.02 }}
      className={`grid grid-cols-[2rem_3rem_1fr_3rem_3.5rem_5rem_2.5rem] sm:grid-cols-[2.5rem_3.5rem_1fr_3.5rem_3.5rem_6rem_3rem] gap-1 items-center px-2 py-1.5 rounded-lg text-xs ${
        isTop3 ? "glass" : "hover:bg-white/3"
      } ${isDNF ? "opacity-50" : ""}`}
    >
      <span className={`font-black ${isTop3 ? "text-white" : "text-neutral-500"}`}>
        {result.position ?? "-"}
      </span>
      <span className="font-mono text-neutral-500">{result.driver}</span>
      <span className={`font-medium truncate ${isTop3 ? "text-white" : "text-neutral-300"}`}>
        {result.full_name}
      </span>
      <span className="text-neutral-500 font-mono">{result.grid ?? "PL"}</span>
      <span className={`font-bold ${changeColor(change)}`}>{change}</span>
      <span className={`font-mono text-[11px] truncate ${isDNF ? "text-red-400" : "text-neutral-400"}`}>
        {result.time || "-"}
      </span>
      <span className={`text-right font-bold ${result.points > 0 ? "text-white" : "text-neutral-600"}`}>
        {result.points > 0 ? result.points : ""}
      </span>
    </motion.div>
  );
}

export default function RaceResults({ results }: RaceResultsProps) {
  const [expanded, setExpanded] = useState(false);

  if (!results || results.length === 0) return null;

  const visible = expanded ? results : results.slice(0, DEFAULT_VISIBLE);

  return (
    <div className="space-y-2">
      {/* Header row */}
      <div className="grid grid-cols-[2rem_3rem_1fr_3rem_3.5rem_5rem_2.5rem] sm:grid-cols-[2.5rem_3.5rem_1fr_3.5rem_3.5rem_6rem_3rem] gap-1 text-[10px] font-bold uppercase tracking-wider text-neutral-600 px-2">
        <span>Pos</span>
        <span>No.</span>
        <span>Driver</span>
        <span>Grid</span>
        <span>+/-</span>
        <span>Time</span>
        <span className="text-right">Pts</span>
      </div>

      <AnimatePresence initial={false}>
        {visible.map((r, i) => (
          <RaceResultRow key={r.driver} result={r} index={i} />
        ))}
      </AnimatePresence>

      {results.length > DEFAULT_VISIBLE && (
        <button
          onClick={() => setExpanded(!expanded)}
          className="flex items-center gap-1 mx-auto text-[11px] font-bold uppercase tracking-wider text-neutral-500 hover:text-white transition-colors py-2"
        >
          {expanded ? "Show less" : "Full classification"}
          <ChevronDown className={`h-3 w-3 transition-transform ${expanded ? "rotate-180" : ""}`} />
        </button>
      )}
    </div>
  );
}
