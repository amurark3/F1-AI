"use client";

import { motion } from 'framer-motion';

interface PodiumEntry {
  position: number;
  driver: string;
  full_name: string;
  team: string;
}

interface PodiumDisplayProps {
  podium: PodiumEntry[] | null;
}

const TEAM_COLORS: Record<string, string> = {
  "Red Bull Racing": "#3671C6",
  "Mercedes": "#27F4D2",
  "Ferrari": "#E8002D",
  "McLaren": "#FF8000",
  "Aston Martin": "#229971",
  "Alpine": "#FF87BC",
  "Williams": "#64C4FF",
  "RB": "#6692FF",
  "Haas F1 Team": "#B6BABD",
  "Kick Sauber": "#52E252",
};

function getTeamColor(team: string): string {
  for (const [key, color] of Object.entries(TEAM_COLORS)) {
    if (team.includes(key)) return color;
  }
  return "#6B7280";
}

export default function PodiumDisplay({ podium }: PodiumDisplayProps) {
  if (!podium || podium.length < 3) return null;

  const p1 = podium[0];
  const p2 = podium[1];
  const p3 = podium[2];

  // Render order: P2 (left), P1 (center, taller), P3 (right)
  const steps = [
    { entry: p2, height: "h-20 sm:h-24", delay: 0.15, label: "2ND" },
    { entry: p1, height: "h-28 sm:h-32", delay: 0, label: "1ST" },
    { entry: p3, height: "h-16 sm:h-20", delay: 0.25, label: "3RD" },
  ];

  return (
    <div className="max-w-sm mx-auto flex items-end justify-center gap-2 sm:gap-3">
      {steps.map(({ entry, height, delay, label }) => (
        <motion.div
          key={entry.position}
          initial={{ opacity: 0, y: 30 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ type: "spring" as const, damping: 18, stiffness: 200, delay }}
          className="flex flex-col items-center flex-1 max-w-[140px]"
        >
          <p className="text-[10px] font-bold tracking-widest text-neutral-500 mb-1">{label}</p>
          <p
            className="text-lg sm:text-xl font-black"
            style={{ color: getTeamColor(entry.team) }}
          >
            {entry.driver}
          </p>
          <p className="text-[10px] text-neutral-500 truncate max-w-full mb-2">{entry.team}</p>
          <div
            className={`w-full ${height} rounded-t-xl flex items-center justify-center`}
            style={{
              background: `linear-gradient(to top, ${getTeamColor(entry.team)}22, ${getTeamColor(entry.team)}08)`,
              borderTop: `2px solid ${getTeamColor(entry.team)}66`,
            }}
          >
            <span className="text-2xl sm:text-3xl font-black text-white/20">
              {entry.position}
            </span>
          </div>
        </motion.div>
      ))}
    </div>
  );
}
