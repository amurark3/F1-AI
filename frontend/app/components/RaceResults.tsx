"use client";

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown } from 'lucide-react';

interface RaceResult {
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

export default function RaceResults({ results }: RaceResultsProps) {
  const [expanded, setExpanded] = useState(false);

  if (!results || results.length === 0) return null;

  const visible = expanded ? results : results.slice(0, 10);

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
        {visible.map((r, i) => {
          const pos = r.position ?? "-";
          const grid = r.grid ?? "PL";
          let change = "-";
          if (typeof r.grid === "number" && typeof r.position === "number") {
            const diff = r.grid - r.position;
            if (diff > 0) change = `+${diff}`;
            else if (diff < 0) change = `${diff}`;
            else change = "0";
          }

          const isTop3 = typeof r.position === "number" && r.position <= 3;
          const isDNF = r.status !== "Finished" && !r.status.includes("Lap");

          return (
            <motion.div
              key={r.driver}
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -20 }}
              transition={{ type: "spring" as const, damping: 22, stiffness: 250, delay: i * 0.02 }}
              className={`grid grid-cols-[2rem_3rem_1fr_3rem_3.5rem_5rem_2.5rem] sm:grid-cols-[2.5rem_3.5rem_1fr_3.5rem_3.5rem_6rem_3rem] gap-1 items-center px-2 py-1.5 rounded-lg text-xs ${
                isTop3 ? "glass" : "hover:bg-white/3"
              } ${isDNF ? "opacity-50" : ""}`}
            >
              <span className={`font-black ${isTop3 ? "text-white" : "text-neutral-500"}`}>
                {pos}
              </span>
              <span className="font-mono text-neutral-500">{r.driver}</span>
              <span className={`font-medium truncate ${isTop3 ? "text-white" : "text-neutral-300"}`}>
                {r.full_name}
              </span>
              <span className="text-neutral-500 font-mono">{grid}</span>
              <span className={`font-bold ${
                change.startsWith("+") ? "text-green-400" :
                change.startsWith("-") ? "text-red-400" : "text-neutral-600"
              }`}>
                {change}
              </span>
              <span className={`font-mono text-[11px] truncate ${isDNF ? "text-red-400" : "text-neutral-400"}`}>
                {r.time || "-"}
              </span>
              <span className={`text-right font-bold ${r.points > 0 ? "text-white" : "text-neutral-600"}`}>
                {r.points > 0 ? r.points : ""}
              </span>
            </motion.div>
          );
        })}
      </AnimatePresence>

      {results.length > 10 && (
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
