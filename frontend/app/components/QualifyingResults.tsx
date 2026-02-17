"use client";

import { useState } from 'react';
import { motion } from 'framer-motion';

interface QualifyingEntry {
  position: number;
  driver: string;
  full_name: string;
  team: string;
  time: string;
}

interface QualifyingResultsProps {
  qualifying: Record<string, QualifyingEntry[]> | null;
}

const TABS = ["Q3", "Q2", "Q1"] as const;

export default function QualifyingResults({ qualifying }: QualifyingResultsProps) {
  const [activeTab, setActiveTab] = useState<string>("Q3");

  if (!qualifying) return null;

  // Find first available tab if Q3 doesn't exist
  const availableTabs = TABS.filter(t => qualifying[t]?.length);
  if (availableTabs.length === 0) return null;

  const currentTab = qualifying[activeTab] ? activeTab : availableTabs[0];
  const entries = qualifying[currentTab] ?? [];

  return (
    <div className="space-y-3">
      {/* Tab bar */}
      <div className="flex gap-1 glass rounded-xl p-1">
        {TABS.map((tab) => {
          const available = qualifying[tab]?.length;
          return (
            <button
              key={tab}
              onClick={() => available && setActiveTab(tab)}
              disabled={!available}
              className={`flex-1 py-1.5 text-xs font-bold uppercase tracking-wider rounded-lg transition-all duration-300 ${
                currentTab === tab
                  ? "bg-gradient-to-r from-red-600 to-orange-500 text-white shadow-lg shadow-red-600/25"
                  : available
                    ? "text-neutral-500 hover:text-white hover:bg-white/5"
                    : "text-neutral-700 cursor-not-allowed"
              }`}
            >
              {tab}
            </button>
          );
        })}
      </div>

      {/* Results */}
      <div className="space-y-1">
        {/* Header */}
        <div className="grid grid-cols-[2rem_3rem_1fr_5rem] sm:grid-cols-[2.5rem_3.5rem_1fr_6rem] gap-1 text-[10px] font-bold uppercase tracking-wider text-neutral-600 px-2">
          <span>Pos</span>
          <span>No.</span>
          <span>Driver</span>
          <span className="text-right">Time</span>
        </div>

        {entries.map((e, i) => {
          const isPole = i === 0 && currentTab === "Q3";
          return (
            <motion.div
              key={`${currentTab}-${e.driver}`}
              initial={{ opacity: 0, x: 15 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ type: "spring" as const, damping: 22, stiffness: 250, delay: i * 0.02 }}
              className={`grid grid-cols-[2rem_3rem_1fr_5rem] sm:grid-cols-[2.5rem_3.5rem_1fr_6rem] gap-1 items-center px-2 py-1.5 rounded-lg text-xs ${
                isPole ? "glass border-red-500/30" : "hover:bg-white/3"
              }`}
            >
              <span className={`font-black ${isPole ? "bg-gradient-to-r from-red-500 to-orange-400 bg-clip-text text-transparent" : i < 3 ? "text-white" : "text-neutral-500"}`}>
                {e.position}
              </span>
              <span className="font-mono text-neutral-500">{e.driver}</span>
              <span className={`font-medium truncate ${i < 3 ? "text-white" : "text-neutral-300"}`}>
                {e.full_name}
              </span>
              <span className={`text-right font-mono ${isPole ? "text-white font-bold" : "text-neutral-400"}`}>
                {e.time}
              </span>
            </motion.div>
          );
        })}
      </div>
    </div>
  );
}
