"use client";

import { motion } from 'framer-motion';

const EXAMPLE_PROMPTS = [
  { emoji: "🏎️", text: "Who won the 2024 Drivers' Championship?" },
  { emoji: "📊", text: "Compare Norris vs Verstappen qualifying at Monza 2024" },
  { emoji: "🏁", text: "What are the new rule changes for 2026?" },
  { emoji: "🔧", text: "Explain DRS and how it affects overtaking" },
  { emoji: "🗓️", text: "When is the next race this season?" },
  { emoji: "🏆", text: "Which team has the most constructors' titles?" },
];

const containerVariants = {
  hidden: {},
  visible: {
    transition: { staggerChildren: 0.07 },
  },
};

const cardVariants = {
  hidden: { opacity: 0, x: 40 },
  visible: {
    opacity: 1,
    x: 0,
    transition: { type: "spring" as const, damping: 20, stiffness: 200 },
  },
};

interface ChatWelcomeProps {
  onSelectPrompt: (text: string) => void;
  disabled: boolean;
}

export default function ChatWelcome({ onSelectPrompt, disabled }: ChatWelcomeProps) {
  return (
    <div className="flex flex-col items-center justify-center h-full px-4 sm:px-6 pb-6 sm:pb-8">
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5, ease: "easeOut" }}
        className="text-center mb-6 sm:mb-10"
      >
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-gradient-to-r from-red-600/15 to-orange-500/15 border border-red-500/20 text-red-400 text-xs font-bold uppercase tracking-widest mb-4 sm:mb-6">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-red-500 animate-glow-pulse shadow-sm shadow-red-500/50" />
          AI Race Engineer
        </div>
        <h2 className="text-2xl sm:text-4xl md:text-5xl font-black italic tracking-tight text-white mb-2 sm:mb-3">
          Welcome to the{' '}
          <span className="bg-gradient-to-r from-red-500 to-orange-400 bg-clip-text text-transparent">
            Pit Wall
          </span>
        </h2>
        <p className="text-neutral-400 text-sm sm:text-base max-w-lg mx-auto">
          Ask me anything about Formula 1 — race stats, driver comparisons,
          regulations, strategy, history, and more.
        </p>
      </motion.div>

      <motion.div
        variants={containerVariants}
        initial="hidden"
        animate="visible"
        className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3 sm:gap-4 max-w-3xl w-full"
      >
        {EXAMPLE_PROMPTS.map(({ emoji, text }) => (
          <motion.button
            key={text}
            variants={cardVariants}
            whileHover={{ scale: 1.03, x: 4 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => onSelectPrompt(text)}
            disabled={disabled}
            className="group text-left p-4 sm:p-5 rounded-2xl glass hover:border-red-500/30 hover:bg-white/8 hover:shadow-lg hover:shadow-red-600/5 transition-all duration-300 disabled:opacity-50"
          >
            <span className="text-2xl mb-2.5 block">{emoji}</span>
            <span className="text-sm text-neutral-400 group-hover:text-neutral-200 transition-colors leading-snug">
              {text}
            </span>
          </motion.button>
        ))}
      </motion.div>
    </div>
  );
}
