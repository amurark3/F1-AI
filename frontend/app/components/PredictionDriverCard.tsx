"use client";

import { motion } from 'framer-motion';

export const TEAM_COLORS: Record<string, string> = {
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

export const getTeamColor = (team: string): string => {
  for (const [key, color] of Object.entries(TEAM_COLORS)) {
    if (team.includes(key) || key.includes(team)) return color;
  }
  return "#6B7280";
};

export interface ModelAttribution {
  feature: string;
  label: string;
  value: number;
  contribution: number;
  direction: "helps" | "hurts";
}

export interface DriverPrediction {
  position: number;
  driver_code: string;
  driver_name: string;
  team: string;
  confidence_low: number;
  confidence_high: number;
  factors: string[];
  model_attribution?: ModelAttribution[] | null;
}

interface PredictionDriverCardProps {
  prediction: DriverPrediction;
  index: number;
}

const rowVariants = {
  hidden:  { opacity: 0, x: 24 },
  visible: (i: number) => ({
    opacity: 1, x: 0,
    transition: { type: 'spring' as const, damping: 22, stiffness: 210, delay: i * 0.025 },
  }),
};

export const PredictionDriverCard = ({ prediction, index }: PredictionDriverCardProps) => {
  const color   = getTeamColor(prediction.team);
  const midConf = Math.round((prediction.confidence_low + prediction.confidence_high) / 2);

  return (
    <motion.div
      custom={index}
      variants={rowVariants}
      initial="hidden"
      animate="visible"
      whileHover={{ scale: 1.007, x: 3 }}
      className="relative flex items-center gap-3 sm:gap-4 px-4 py-3 rounded-xl glass border border-white/5
        hover:border-white/12 overflow-hidden transition-all duration-150 group"
    >
      {/* Background confidence fill */}
      <div
        className="absolute left-0 top-0 bottom-0 opacity-[0.055] transition-all duration-700"
        style={{ width: `${prediction.confidence_high}%`, background: color }}
      />

      {/* Team colour left bar */}
      <div
        className="absolute left-0 top-2 bottom-2 w-[3px] rounded-full"
        style={{ background: color }}
      />

      {/* Position */}
      <div
        className="w-7 sm:w-9 text-center font-black text-base sm:text-lg shrink-0 text-neutral-500"
        style={{ fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}
      >
        {prediction.position}
      </div>

      {/* Driver code badge */}
      <div
        className="hidden sm:flex items-center justify-center h-7 w-11 rounded shrink-0 text-[11px] font-black"
        style={{
          background: `${color}22`,
          color,
          fontFamily: 'var(--font-barlow, var(--font-geist-sans))',
        }}
      >
        {prediction.driver_code}
      </div>

      {/* Name + team */}
      <div className="flex-1 min-w-0">
        <p className="font-bold text-sm text-white truncate leading-tight">{prediction.driver_name}</p>
        <p className="text-[10px] font-semibold truncate mt-0.5" style={{ color }}>{prediction.team}</p>
      </div>

      {/* Probability bar */}
      <div className="hidden md:flex flex-col gap-1 w-28 shrink-0">
        <div className="h-1.5 bg-white/8 rounded-full overflow-hidden">
          <motion.div
            className="h-full rounded-full"
            initial={{ width: 0 }}
            animate={{ width: `${midConf}%` }}
            transition={{ duration: 0.8, delay: index * 0.025, ease: [0.22, 1, 0.36, 1] }}
            style={{ background: color }}
          />
        </div>
        <div className="flex justify-between text-[9px] text-neutral-600 font-mono">
          <span>{prediction.confidence_low}%</span>
          <span>{prediction.confidence_high}%</span>
        </div>
      </div>

      {/* Factor chips — desktop only */}
      <div className="hidden lg:flex gap-1 flex-wrap max-w-[200px] shrink-0">
        {prediction.factors.slice(0, 2).map((f, i) => (
          <span
            key={i}
            className="text-[9px] px-1.5 py-0.5 rounded bg-white/5 text-neutral-500 leading-tight"
            style={{ maxWidth: 190 }}
          >
            {f.length > 28 ? `${f.slice(0, 26)  }…` : f}
          </span>
        ))}
      </div>

      {/* Confidence % */}
      <div className="text-right shrink-0 w-12 sm:w-14">
        <p
          className="font-mono font-black text-sm sm:text-base text-white leading-none"
          style={{ fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}
        >
          {midConf}%
        </p>
        <p className="text-[9px] text-neutral-600 uppercase tracking-wider">conf</p>
      </div>
    </motion.div>
  );
};
