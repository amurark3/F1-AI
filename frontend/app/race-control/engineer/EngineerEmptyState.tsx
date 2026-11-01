"use client";

import { ArrowUpRight, BookOpenCheck, Flag, LineChart, Users } from "lucide-react";

import EngineerAvatar from "@/app/components/EngineerAvatar";

import { rcFont } from "../components/RaceControlPrimitives";

import type { LucideIcon } from "lucide-react";

interface StarterPrompt {
  category: string;
  color: string;
  icon: LucideIcon;
  prompt: string;
}

// Each starter carries its own accent so the grid scans by topic. The accent
// only tints the icon and label; the cards themselves stay neutral.
const PROMPTS: readonly StarterPrompt[] = [
  {
    category: "Strategy",
    color: "#FF4655",
    icon: Flag,
    prompt: "Build a race-week strategy brief for the next Grand Prix.",
  },
  {
    category: "Head to head",
    color: "#9EC5FF",
    icon: Users,
    prompt: "Compare Ferrari and McLaren from a constructor strategy perspective.",
  },
  {
    category: "Regulations",
    color: "#F5C542",
    icon: BookOpenCheck,
    prompt: "What regulation constraints matter for parc fermé decisions?",
  },
  {
    category: "Predictions",
    color: "#BE3AFF",
    icon: LineChart,
    prompt: "Who does the model favour for the next race, and why?",
  },
];

interface EngineerEmptyStateProps {
  onSendMessage: (prompt: string) => Promise<void> | void;
  isLoading: boolean;
}

export function EngineerEmptyState({ onSendMessage, isLoading }: EngineerEmptyStateProps) {
  return (
    <div className="flex min-h-full flex-col items-center justify-center bg-[radial-gradient(ellipse_at_top,rgba(225,6,0,0.08),transparent_55%)] px-4 py-10 text-center sm:px-6">
      <EngineerAvatar size="lg" />
      <p className="mt-5 flex items-center gap-2 font-mono text-[10px] font-bold uppercase tracking-[0.22em] text-[#7F8797]">
        <span className="h-1.5 w-1.5 rounded-full bg-[#00FF78] animate-glow-pulse" />
        Engineer channel open
      </p>
      <h2 className="mt-2 max-w-3xl text-3xl font-black leading-tight text-white sm:text-4xl" style={rcFont}>
        What do you need from the pit wall?
      </h2>
      <p className="mt-3 max-w-2xl text-sm leading-relaxed text-[#8E96A8] sm:text-base">
        Strategy briefs, driver deltas, regulation calls, prediction reads, race results, and live-session context, all
        answered from the race data in this thread.
      </p>

      <div className="mt-8 grid w-full max-w-4xl gap-3 sm:grid-cols-2">
        {PROMPTS.map((starter) => (
          <StarterCard key={starter.prompt} starter={starter} disabled={isLoading} onSelect={onSendMessage} />
        ))}
      </div>
    </div>
  );
}

interface StarterCardProps {
  starter: StarterPrompt;
  disabled: boolean;
  onSelect: (prompt: string) => Promise<void> | void;
}

function StarterCard({ starter, disabled, onSelect }: StarterCardProps) {
  const { category, color, icon: Icon, prompt } = starter;
  return (
    <button
      onClick={() => void onSelect(prompt)}
      disabled={disabled}
      className="group flex min-h-24 flex-col gap-2.5 rounded-md border border-[#1E2633] bg-[#0D111B] p-4 text-left transition-colors hover:border-[#2C3646] hover:bg-[#121825] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[#E10600]/40 disabled:cursor-not-allowed disabled:opacity-50"
    >
      <span className="flex w-full items-center gap-2">
        <Icon className="h-3.5 w-3.5 shrink-0" style={{ color }} />
        <span className="font-mono text-[10px] font-bold uppercase tracking-[0.18em]" style={{ color }}>
          {category}
        </span>
        <ArrowUpRight className="ml-auto h-3.5 w-3.5 text-[#3A4354] transition-colors group-hover:text-white" />
      </span>
      <span className="text-sm leading-relaxed text-[#B7BDCA] transition-colors group-hover:text-white">{prompt}</span>
    </button>
  );
}
