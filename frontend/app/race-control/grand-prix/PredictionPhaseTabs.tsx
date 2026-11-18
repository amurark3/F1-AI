"use client";

import { Flag, History, Lock } from "lucide-react";

import { LocalTime } from "@/app/components/LocalTime";

import { phaseDescription, phaseTabLabel } from "./predictionHelpers";

import type { PredictionPhase, PredictionsResponse } from "./predictionModel";

/** What one phase knows about its own stored prediction. */
export interface PhaseTabState {
  phase: PredictionPhase;
  /** False while the phase cannot exist yet — qualifying has not run. */
  available: boolean;
  /** Whether a stored snapshot is currently loaded for this phase. */
  hasSnapshot: boolean;
  /** When that snapshot was stored. */
  storedAt?: string | null;
}

const PHASE_ICONS = {
  pre_qualifying: History,
  post_qualifying: Flag,
} as const;

/** What the phase currently holds, in a few words. */
function phaseStatus(state: PhaseTabState) {
  if (!state.available) return <span className="text-[#596173]">awaiting qualifying</span>;
  if (!state.hasSnapshot) return <span className="text-[#596173]">not computed</span>;
  return <LocalTime value={state.storedAt} style="stamp" fallback="stored" />;
}

function PhaseButton({
  state,
  active,
  onSelect,
}: {
  state: PhaseTabState;
  active: boolean;
  onSelect: (phase: PredictionPhase) => void;
}) {
  const Icon = state.available ? PHASE_ICONS[state.phase] : Lock;
  return (
    <button
      type="button"
      onClick={() => onSelect(state.phase)}
      aria-pressed={active}
      title={phaseDescription(state.phase)}
      className={`flex min-w-0 items-center gap-2 rounded px-3 py-1.5 text-left transition-colors ${
        active ? "bg-[#E10600]/15 text-white" : "text-[#8E96A8] hover:text-white"
      }`}
    >
      <Icon className={`h-3.5 w-3.5 shrink-0 ${active ? "text-[#E10600]" : "text-[#596173]"}`} aria-hidden="true" />
      <span className="truncate text-sm font-bold">{phaseTabLabel(state.phase)}</span>
      <span className="hidden truncate font-mono text-[10px] uppercase tracking-[0.12em] text-[#6F7789] sm:inline">
        {phaseStatus(state)}
      </span>
    </button>
  );
}

/** The model's record over its latest scored races, as one chip. */
function AccuracyChip({ accuracy }: { accuracy?: PredictionsResponse["accuracy"] }) {
  const scored = accuracy?.races_evaluated ?? 0;
  if (scored === 0) {
    return <span className="font-mono text-[10px] uppercase tracking-[0.16em] text-[#596173]">not yet scored</span>;
  }
  const top3 = accuracy?.recent_top3_pct;
  const error = accuracy?.avg_position_error;
  return (
    <span
      className="rounded border border-[#1E2633] px-2 py-1 font-mono text-[10px] uppercase tracking-[0.14em] text-[#AEB5C5]"
      title={error == null ? undefined : `Average error ${error} positions across scored predictions`}
    >
      Top-3 {top3 == null ? "–" : `${top3}%`} · {scored} of last {accuracy?.rolling_window ?? 8} scored
    </span>
  );
}

export interface PredictionBarProps {
  states: PhaseTabState[];
  activePhase: PredictionPhase;
  onSelectPhase: (phase: PredictionPhase) => void;
  accuracy?: PredictionsResponse["accuracy"];
}

/**
 * The one control bar for a race's prediction: which of its two phases is on
 * screen (each shows when it was stored) and how the model has scored lately.
 * Selecting a phase switches every view below. Visitors cannot run the model:
 * the owner stores predictions through the key-locked compute endpoint.
 */
export function PredictionBar({ states, activePhase, onSelectPhase, accuracy }: PredictionBarProps) {
  return (
    <div className="flex flex-col gap-3 rounded-md border border-[#1E2633] bg-[#0D111B] p-2 lg:flex-row lg:items-center lg:justify-between">
      <div className="flex min-w-0 flex-wrap gap-1" role="group" aria-label="Prediction phase">
        {states.map((state) => (
          <PhaseButton key={state.phase} state={state} active={state.phase === activePhase} onSelect={onSelectPhase} />
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-3 px-1">
        <AccuracyChip accuracy={accuracy} />
      </div>
    </div>
  );
}
