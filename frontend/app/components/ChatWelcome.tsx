"use client";

const EXAMPLE_PROMPTS = [
  { emoji: "🏎️", text: "Who won the 2024 Drivers' Championship?" },
  { emoji: "📊", text: "Compare Norris vs Verstappen qualifying at Monza 2024" },
  { emoji: "🏁", text: "What are the new rule changes for 2026?" },
  { emoji: "🔧", text: "Explain DRS and how it affects overtaking" },
  { emoji: "🗓️", text: "When is the next race this season?" },
  { emoji: "🏆", text: "Which team has the most constructors' titles?" },
];

interface ChatWelcomeProps {
  onSelectPrompt: (text: string) => void;
  disabled: boolean;
}

export default function ChatWelcome({ onSelectPrompt, disabled }: ChatWelcomeProps) {
  return (
    <div className="flex flex-col items-center justify-center h-full px-4 sm:px-6 pb-6 sm:pb-8">
      <div className="text-center mb-6 sm:mb-10">
        <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-red-600/10 border border-red-600/20 text-red-500 text-xs font-bold uppercase tracking-widest mb-4 sm:mb-6">
          <span className="inline-block h-1.5 w-1.5 rounded-full bg-red-500 animate-pulse" />
          AI Race Engineer
        </div>
        <h2 className="text-2xl sm:text-4xl md:text-5xl font-black italic tracking-tight text-white mb-2 sm:mb-3">
          Welcome to the <span className="text-red-500">Pit Wall</span>
        </h2>
        <p className="text-gray-500 text-sm sm:text-base max-w-lg mx-auto">
          Ask me anything about Formula 1 — race stats, driver comparisons,
          regulations, strategy, history, and more.
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 sm:gap-3 max-w-3xl w-full">
        {EXAMPLE_PROMPTS.map(({ emoji, text }) => (
          <button
            key={text}
            onClick={() => onSelectPrompt(text)}
            disabled={disabled}
            className="group text-left p-3 sm:p-4 rounded-xl bg-neutral-900/60 border border-neutral-800/60 hover:border-red-600/40 hover:bg-neutral-900 transition-all duration-200 disabled:opacity-50"
          >
            <span className="text-lg mb-2 block">{emoji}</span>
            <span className="text-sm text-gray-400 group-hover:text-gray-200 transition-colors leading-snug">
              {text}
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
