"use client";

import { Flag, History, Lock } from "lucide-react";

import { LocalTime } from "@/app/components/LocalTime";

import { phaseDescription, phaseTabLabel } from "./predictionHelpers";

import type { PredictionPhase } from "./predictionModel";

/** What one phase tab knows about its own stored prediction. */
export interface PhaseTabState {
  phase: PredictionPhase;
  /** False while the phase cannot exist yet — qualifying has not run. */
  available: boolean;
  /** Whether a stored snapshot is currently loaded for this phase. */
  hasSnapshot: boolean;
  /** When that snapshot was stored, for the tab's subtitle. */
  storedAt?: string | null;
  /** True while this phase is being recomputed. */
  computing: boolean;
}

const PHASE_ICONS = {
  pre_qualifying: History,
  post_qualifying: Flag,
} as const;

/** Short status line under a tab heading: what this tab currently holds. */
function tabStatus(state: PhaseTabState) {
  if (!state.available) return <span className="text-[#596173]">awaiting qualifying</span>;
  if (state.computing) return <span className="text-[#F5C542]">running…</span>;
  if (!state.hasSnapshot) return <span className="text-[#596173]">not computed</span>;
  return (
    <span className="text-[#6F7789]">
      <LocalTime value={state.storedAt} style="stamp" fallback="stored" />
    </span>
  );
}

function PhaseTab({
  state,
  active,
  onSelect,
}: {
  state: PhaseTabState;
  active: boolean;
  onSelect: (phase: PredictionPhase) => void;
}) {
  const Icon = state.available ? PHASE_ICONS[state.phase] : Lock;
  const border = active ? "border-[#E10600]/60 bg-[#E10600]/[0.07]" : "border-[#1E2633] bg-[#0D111B]";
  const heading = active ? "text-white" : "text-[#AEB5C5]";

  return (
    <button
      type="button"
      onClick={() => onSelect(state.phase)}
      aria-pressed={active}
      className={`group flex min-w-0 flex-1 items-start gap-3 rounded-md border px-4 py-3 text-left transition-colors hover:border-[#E10600]/40 ${border}`}
    >
      <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${active ? "text-[#E10600]" : "text-[#596173]"}`} />
      <span className="min-w-0">
        <span className={`block truncate text-sm font-bold ${heading}`}>{phaseTabLabel(state.phase)}</span>
        <span className="mt-0.5 block truncate text-xs text-[#6F7789]">{phaseDescription(state.phase)}</span>
        <span className="mt-1 block font-mono text-[10px] uppercase tracking-[0.16em]">{tabStatus(state)}</span>
      </span>
    </button>
  );
}

export interface PredictionPhaseTabsProps {
  states: PhaseTabState[];
  activePhase: PredictionPhase;
  onSelectPhase: (phase: PredictionPhase) => void;
}

/**
 * The two predictions a race can hold, as side-by-side tabs.
 *
 * Selecting one switches every panel below to that phase's snapshot, so the
 * podium, risk rows and review always describe the prediction named above them.
 */
export function PredictionPhaseTabs({ states, activePhase, onSelectPhase }: PredictionPhaseTabsProps) {
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      {states.map((state) => (
        <PhaseTab
          key={state.phase}
          state={state}
          active={state.phase === activePhase}
          onSelect={onSelectPhase}
        />
      ))}
    </div>
  );
}
