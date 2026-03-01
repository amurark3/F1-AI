"use client";

import { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';

// Team colour map — matches Standings.tsx TEAM_COLORS exactly
const TEAM_COLORS: Record<string, string> = {
  "Red Bull Racing": "#3671C6",
  "Red Bull":        "#3671C6",
  "Mercedes":        "#27F4D2",
  "Ferrari":         "#E8002D",
  "McLaren":         "#FF8000",
  "Aston Martin":    "#229971",
  "Alpine F1 Team":  "#FF87BC",
  "Alpine":          "#FF87BC",
  "Williams":        "#64C4FF",
  "RB F1 Team":      "#6692FF",
  "RB":              "#6692FF",
  "Haas F1 Team":    "#B6BABD",
  "Haas":            "#B6BABD",
  "Kick Sauber":     "#52E252",
  "Audi":            "#FF0000",
  "Cadillac F1 Team": "#E0D4B8",
};

const getTeamColor = (team: string): string => {
  for (const [key, color] of Object.entries(TEAM_COLORS)) {
    if (team.includes(key) || key.includes(team)) return color;
  }
  return "#6B7280";
};

interface DriverPrediction {
  position: number;
  driver_code: string;
  driver_name: string;
  team: string;
  confidence_low: number;
  confidence_high: number;
  factors: string[];
}

interface PredictionDriverCardProps {
  prediction: DriverPrediction;
  index: number;  // for stagger animation
}

export const PredictionDriverCard = ({ prediction, index }: PredictionDriverCardProps) => {
  const [isExpanded, setIsExpanded] = useState(false);
  const teamColor = getTeamColor(prediction.team);
  const isTopThree = prediction.position <= 3;

  return (
    <motion.div
      initial={{ opacity: 0, x: 30 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ type: "spring", damping: 20, stiffness: 200, delay: index * 0.03 }}
      className={`relative rounded-2xl overflow-hidden transition-all duration-200 cursor-pointer ${
        isTopThree ? 'glass border border-white/8' : 'bg-white/3 border border-white/5'
      }`}
      onClick={() => setIsExpanded(prev => !prev)}
    >
      {/* Left team colour accent bar */}
      <div
        className="absolute left-0 top-0 bottom-0 w-1"
        style={{ backgroundColor: teamColor }}
      />

      {/* Always-visible header */}
      <div className="flex items-center gap-3 sm:gap-4 px-4 sm:px-5 py-3 sm:py-4 pl-5 sm:pl-6">
        {/* Position */}
        <div className={`w-8 sm:w-10 text-center font-black text-base sm:text-lg shrink-0 ${
          isTopThree ? 'text-white' : 'text-neutral-500'
        }`}>
          {prediction.position}
        </div>

        {/* Driver + Team */}
        <div className="flex-1 min-w-0">
          <p className={`font-bold truncate ${isTopThree ? 'text-white text-sm sm:text-base' : 'text-gray-300 text-sm'}`}>
            {prediction.driver_name}
          </p>
          <p className="text-[10px] sm:text-xs font-medium truncate" style={{ color: teamColor }}>
            {prediction.team}
          </p>
        </div>

        {/* Confidence range — the "win probability" field */}
        <div className="text-right shrink-0">
          <p className={`font-mono font-black text-base sm:text-lg ${isTopThree ? 'text-white' : 'text-gray-300'}`}>
            {prediction.confidence_low}–{prediction.confidence_high}%
          </p>
          <p className="text-[10px] text-neutral-600 uppercase tracking-wider">confidence</p>
        </div>

        {/* Expand chevron */}
        <div className={`transition-transform duration-300 ${isExpanded ? 'rotate-180' : ''} shrink-0`}>
          <svg className="w-4 h-4 text-neutral-500" fill="none" stroke="currentColor" strokeWidth={2} viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </div>

      {/* Expandable factors section */}
      <AnimatePresence>
        {isExpanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.25, ease: 'easeOut' }}
            className="overflow-hidden"
          >
            <div className="border-t border-white/8 mx-4 sm:mx-5" />
            <ul className="px-5 sm:px-6 py-3 space-y-2">
              {prediction.factors.slice(0, 3).map((factor, i) => (
                <li key={i} className="flex items-start gap-2">
                  <span className="shrink-0 mt-0.5" style={{ color: teamColor }}>›</span>
                  <span className="text-xs text-gray-400 leading-relaxed">{factor}</span>
                </li>
              ))}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.div>
  );
};
