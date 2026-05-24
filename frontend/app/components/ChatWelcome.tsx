"use client";

import type { CSSProperties, ComponentType } from 'react';
import { motion } from 'framer-motion';
import { BarChart3, CalendarClock, FileSearch, Gauge, History, Trophy } from 'lucide-react';

interface Prompt {
  color: string;
  label: string;
  text: string;
  icon: ComponentType<{ className?: string; style?: CSSProperties }>;
}

const PROMPTS: Prompt[] = [
  { color: '#E10600', label: 'Championship',  text: "Brief me on the current title fight and the biggest points swing risk", icon: Trophy },
  { color: '#3671C6', label: 'Driver Delta',  text: 'Compare Norris vs Verstappen qualifying at Monza 2024', icon: BarChart3 },
  { color: '#FF8000', label: 'Regulations',   text: 'What 2026 regulation changes matter most for race operations?', icon: FileSearch },
  { color: '#27F4D2', label: 'Technical',     text: 'Explain DRS in terms of attack, defense, and race strategy', icon: Gauge },
  { color: '#00CC00', label: 'Schedule',      text: 'When is the next race and what sessions should I watch?', icon: CalendarClock },
  { color: '#BE3AFF', label: 'History',       text: "Which team has the most constructors' titles?", icon: History },
];

const containerVariants = {
  hidden: {},
  visible: { transition: { staggerChildren: 0.055 } },
};

const cardVariants = {
  hidden:  { opacity: 0, x: 32, skewX: -3 },
  visible: { opacity: 1, x: 0,  skewX: 0, transition: { type: 'spring' as const, damping: 22, stiffness: 210 } },
};

interface ChatWelcomeProps {
  onSelectPrompt: (text: string) => void;
  disabled: boolean;
}

export default function ChatWelcome({ onSelectPrompt, disabled }: ChatWelcomeProps) {
  return (
    <div className="flex flex-col items-center justify-center h-full px-4 sm:px-6 pb-6 sm:pb-8">

      {/* ── Hero heading ─────────────────────────────── */}
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
        className="text-center mb-8 sm:mb-12"
      >
        {/* Sector-time style badge */}
        <div className="inline-flex items-center gap-2 px-3 py-1 mb-5 rounded border text-[10px] font-black uppercase tracking-[0.2em] sector-best">
          <span
            className="h-[7px] w-[7px] rounded-full animate-glow-pulse"
            style={{ background: '#BE3AFF' }}
          />
          Public Pit Wall
        </div>

        <h1
          className="text-5xl sm:text-6xl md:text-7xl font-black italic tracking-tighter uppercase text-white mb-3 leading-none"
          style={{ fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}
        >
          Pit{' '}
          <span style={{ color: '#E10600' }}>Wall</span>
        </h1>

        {/* Speed lines decoration */}
        <div className="flex items-center justify-center gap-1 mb-4">
          {[40, 64, 96, 64, 40].map((w, i) => (
            <motion.div
              key={i}
              className="h-[2px] rounded-full"
              style={{ width: w, background: i === 2 ? '#E10600' : 'rgba(255,255,255,0.12)' }}
              initial={{ scaleX: 0 }}
              animate={{ scaleX: 1 }}
              transition={{ delay: 0.3 + i * 0.05, duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
            />
          ))}
        </div>

        <p className="text-neutral-500 text-sm sm:text-base max-w-md mx-auto leading-relaxed">
          Ask the race engineer for race context, driver comparisons, regulations,
          strategy language, and championship implications.
        </p>
      </motion.div>

      {/* ── Prompt cards ─────────────────────────────── */}
      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="visible"
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5 sm:gap-3 max-w-3xl w-full"
      >
        {PROMPTS.map(({ color, label, text, icon: Icon }) => (
          <motion.button
            key={text}
            variants={cardVariants}
            whileHover={{ scale: 1.02, x: 3 }}
            whileTap={{ scale: 0.97 }}
            onClick={() => onSelectPrompt(text)}
            disabled={disabled}
            className="group text-left rounded-xl glass overflow-hidden
              hover:border-white/15 transition-all duration-200 disabled:opacity-40"
          >
            {/* coloured top stripe */}
            <div className="h-[2px] w-full" style={{ background: color }} />

            <div className="px-4 pt-3 pb-4">
              {/* category label */}
              <Icon className="h-4 w-4 mb-3" style={{ color }} />
              <div
                className="text-[9px] font-black uppercase tracking-[0.18em] mb-2"
                style={{ color }}
              >
                {label}
              </div>
              <p className="text-sm text-neutral-400 group-hover:text-neutral-200 transition-colors leading-snug">
                {text}
              </p>
            </div>
          </motion.button>
        ))}
      </motion.div>
    </div>
  );
}
