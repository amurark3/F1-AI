"use client";

import { motion } from 'framer-motion';
import { ChevronDown } from 'lucide-react';

interface RaceEvent {
  round: number;
  name: string;
  status: string;
}

interface RaceJumpNavProps {
  schedule: RaceEvent[];
  activeRound: number | null;
  onJump: (round: number) => void;
}

export default function RaceJumpNav({ schedule, activeRound, onJump }: RaceJumpNavProps) {
  if (!schedule || schedule.length === 0) return null;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ type: "spring" as const, damping: 20, stiffness: 200, delay: 0.5 }}
      className="fixed bottom-4 right-4 sm:bottom-6 sm:right-6 z-40"
    >
      <div className="relative">
        <select
          value={activeRound ?? ""}
          onChange={(e) => onJump(Number(e.target.value))}
          className="appearance-none glass-strong border-white/10 text-white text-xs font-bold rounded-xl pl-3 pr-8 py-2.5 focus:ring-2 focus:ring-red-500/40 outline-none shadow-lg shadow-black/30 cursor-pointer max-w-[200px]"
        >
          {schedule.map((r) => (
            <option key={r.round} value={r.round}>
              R{r.round} — {r.name.replace("Grand Prix", "GP")}
              {r.status === "completed" ? " ✓" : r.status === "in_progress" ? " ●" : ""}
            </option>
          ))}
        </select>
        <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-gray-400">
          <ChevronDown className="h-3 w-3" />
        </div>
      </div>
    </motion.div>
  );
}
