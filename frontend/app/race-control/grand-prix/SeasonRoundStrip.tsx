"use client";

import { Check, CircleDot } from "lucide-react";

import { ConsoleHeader, ConsolePanel } from "./predictionConsole";
import { isLiveRace, roundColor, roundStateLabel } from "./predictionHelpers";
import { raceCode } from "./raceCode";

import type { RaceEvent } from "./predictionModel";

/** Round-selector glyph: check when scored, dot when live/selected, else the round number. */
function RoundGlyph({ completed, activeOrLive, round }: { completed: boolean; activeOrLive: boolean; round: number }) {
  if (completed) return <Check className="h-3.5 w-3.5" />;
  if (activeOrLive) return <CircleDot className="h-3.5 w-3.5 fill-current" />;
  return <>{round}</>;
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="h-2 w-2 rounded-full" style={{ background: color }} />
      {label}
    </span>
  );
}

/**
 * The season calendar as a round selector.
 *
 * This used to double as a prediction-accuracy readout, which made the
 * screen's primary navigation look like part of the model's output. The
 * accuracy figures now sit in the prediction section that owns them; this strip
 * reports only on the season and which round is in focus.
 */
export function SeasonRoundStrip({
  schedule,
  selectedRound,
  onSelectRound,
}: {
  schedule: RaceEvent[];
  selectedRound: number | null;
  onSelectRound: (round: number) => void;
}) {
  // Show the whole calendar, not a fixed slice — the "N races" count in the
  // header must match the number of dots. The row scrolls horizontally when the
  // season is longer than the panel (e.g. a full 22-race calendar).
  const completed = schedule.filter((race) => race.status === "completed").length;
  const total = schedule.length || 0;

  return (
    <ConsolePanel>
      <ConsoleHeader
        label={`${new Date().getFullYear()} season - select a round`}
        right={
          <span className="font-mono text-[11px] text-[#7F8797]">
            {total} races / {completed} complete
          </span>
        }
      />
      <div className="overflow-x-auto px-4 py-4">
        <div className="flex w-max items-start gap-5">
          {schedule.map((race) => {
            const active = race.round === selectedRound;
            const completedRace = race.status === "completed";
            const liveRace = isLiveRace(race.status);
            const color = roundColor(completedRace, liveRace, active);
            const stateLabel = roundStateLabel(liveRace, completedRace, active);
            return (
              <button
                key={race.round}
                type="button"
                onClick={() => onSelectRound(race.round)}
                title={`${race.name} - round ${race.round} (${stateLabel})`}
                aria-label={`${race.name}, round ${race.round}, ${stateLabel}`}
                aria-pressed={active}
                className="group flex w-16 shrink-0 flex-col items-center gap-2 text-center"
              >
                <span
                  className={`flex h-8 w-8 items-center justify-center rounded-full border text-[11px] transition-transform group-hover:scale-105 ${
                    active ? "ring-4 ring-[#E10600]/20" : ""
                  }`}
                  style={{ borderColor: `${color}88`, color, background: active ? `${color}22` : "transparent" }}
                >
                  <RoundGlyph completed={completedRace} activeOrLive={liveRace || active} round={race.round} />
                </span>
                <span className="font-mono text-[10px] font-bold uppercase tracking-[0.12em] text-[#A8AFBF]">
                  {raceCode(race.name)}
                </span>
                <span className="font-mono text-[10px] text-[#596173]">{stateLabel}</span>
              </button>
            );
          })}
        </div>
        <div className="mt-4 flex flex-wrap gap-4 font-mono text-[10px] uppercase tracking-[0.18em] text-[#7F8797]">
          <LegendDot color="#00FF78" label="complete" />
          <LegendDot color="#E10600" label="live or selected" />
          <LegendDot color="#333B49" label="future" />
        </div>
      </div>
    </ConsolePanel>
  );
}
