"use client";

import { Check, CircleDot, Play } from "lucide-react";
import { useMemo } from "react";

import { formatUtc } from "@/app/lib/formatTime";

import { ConsoleHeader, ConsolePanel } from "./predictionConsole";
import { raceSessionTime } from "./predictionHelpers";
import { raceCode } from "./raceCode";
import { nextRoundNumber, roundState, roundStateColor, roundStateLabel } from "./roundState";
import { seasonSegments, segmentRange } from "./seasonSegments";

import type { RaceEvent } from "./predictionModel";
import type { RoundState } from "./roundState";
import type { SeasonSegment } from "./seasonSegments";
import type { CSSProperties } from "react";

/** Text colour for a round's code: readable first, state-tinted second. */
const CODE_COLOR: Record<RoundState, string> = {
  completed: "#A8AFBF",
  live: "#FF4655",
  next: "#F5C542",
  future: "#8E96A8",
};

/**
 * Column count for a selector row.
 *
 * Every row is given the same track count so the two halves of the season line
 * up column for column instead of each stretching to its own width. Custom
 * properties are outside `CSSProperties`, hence the assertion; the Tailwind
 * class below reads it back at `md` and up, leaving narrow screens to wrap.
 */
function columnsStyle(columns: number): CSSProperties {
  return { "--round-cols": columns } as CSSProperties;
}

/**
 * The state marker on a tile.
 *
 * Each state gets its own shape, not just its own colour, so the calendar is
 * still readable without colour vision: run, running, next, not yet run.
 */
function StateMark({ state, color }: { state: RoundState; color: string }) {
  if (state === "completed") return <Check className="h-2.5 w-2.5 shrink-0" style={{ color }} aria-hidden />;
  if (state === "live")
    return <CircleDot className="h-2.5 w-2.5 shrink-0 fill-current" style={{ color }} aria-hidden />;
  if (state === "next") return <Play className="h-2.5 w-2.5 shrink-0 fill-current" style={{ color }} aria-hidden />;
  return <span className="h-2.5 w-2.5 shrink-0" aria-hidden />;
}

function RoundTile({
  race,
  state,
  selected,
  onSelect,
}: {
  race: RaceEvent;
  state: RoundState;
  selected: boolean;
  onSelect: (round: number) => void;
}) {
  const color = roundStateColor(state);
  const stateLabel = roundStateLabel(state);
  return (
    <button
      type="button"
      onClick={() => {
        onSelect(race.round);
      }}
      title={`Round ${race.round} - ${race.name} (${stateLabel})`}
      aria-label={`Round ${race.round}, ${race.name}, ${stateLabel}`}
      aria-pressed={selected}
      className={`flex min-w-0 flex-col gap-1 rounded-[3px] border px-1 py-2 transition-colors hover:bg-white/[0.05] ${
        selected ? "ring-2 ring-white/45" : ""
      }`}
      style={{
        borderColor: selected ? color : `${color}40`,
        background: selected ? `${color}1F` : "transparent",
      }}
    >
      <span className="flex items-center justify-center gap-1">
        <span className="font-mono text-[9px] leading-none text-[#6F7789]">{race.round}</span>
        <StateMark state={state} color={color} />
      </span>
      <span
        className="truncate text-center font-mono text-[12px] font-bold leading-none tracking-[0.04em]"
        style={{ color: selected ? "#FFFFFF" : CODE_COLOR[state] }}
      >
        {raceCode(race.name)}
      </span>
      {/* UTC on purpose: a per-tile local clock would differ between the server
          render and the browser's first pass, and a race date is quoted in the
          circuit's own weekend anyway. */}
      <span className="hidden text-center font-mono text-[9px] leading-none text-[#4A5261] md:block">
        {formatUtc(raceSessionTime(race), "dayShort", "").toUpperCase()}
      </span>
    </button>
  );
}

/** One captioned run of rounds: the calendar up to the summer break, or after it. */
function SegmentRow({
  segment,
  columns,
  nextRound,
  selectedRound,
  onSelectRound,
}: {
  segment: SeasonSegment;
  columns: number;
  nextRound: number | null;
  selectedRound: number | null;
  onSelectRound: (round: number) => void;
}) {
  return (
    <div>
      {segment.label !== "" && (
        <p className="mb-1.5 flex items-baseline gap-2 font-mono text-[9px] uppercase tracking-[0.2em] text-[#596173]">
          <span className="text-[#7F8797]">{segmentRange(segment)}</span>
          <span>{segment.label}</span>
        </p>
      )}
      <div
        className="grid grid-cols-[repeat(auto-fit,minmax(46px,1fr))] gap-1.5 md:grid-cols-[repeat(var(--round-cols),minmax(0,1fr))]"
        style={columnsStyle(columns)}
      >
        {segment.races.map((race) => (
          <RoundTile
            key={race.round}
            race={race}
            state={roundState(race, nextRound)}
            selected={race.round === selectedRound}
            onSelect={onSelectRound}
          />
        ))}
      </div>
    </div>
  );
}

function LegendItem({ state }: { state: RoundState }) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <StateMark state={state} color={roundStateColor(state)} />
      {roundStateLabel(state)}
    </span>
  );
}

/**
 * The season calendar as a round selector.
 *
 * Every round is on screen at once. The row it replaced scrolled sideways once
 * a calendar passed about fourteen races, which hid half a 24-race season
 * behind a scrollbar and dragged the legend out of view with it. A long
 * calendar now breaks into two captioned rows at the summer shutdown — the
 * same split at every window width, and one the season itself already makes.
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
  const segments = useMemo(() => seasonSegments(schedule), [schedule]);
  const completed = schedule.filter((race) => race.status === "completed").length;
  const total = schedule.length;
  const nextRound = nextRoundNumber(schedule);
  const columns = segments.reduce((widest, segment) => Math.max(widest, segment.races.length), 0);

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
      <div className="px-4 py-3">
        {total === 0 ? (
          <p className="py-2 font-mono text-[11px] text-[#6F7789]">Season calendar unavailable.</p>
        ) : (
          <div className="space-y-3">
            {segments.map((segment) => (
              <SegmentRow
                key={segment.key}
                segment={segment}
                columns={columns}
                nextRound={nextRound}
                selectedRound={selectedRound}
                onSelectRound={onSelectRound}
              />
            ))}
          </div>
        )}
        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-[#161D28] pt-3 font-mono text-[10px] uppercase tracking-[0.16em] text-[#7F8797]">
          <LegendItem state="completed" />
          <LegendItem state="live" />
          <LegendItem state="next" />
          <LegendItem state="future" />
          <span className="inline-flex items-center gap-1.5">
            <span className="h-3 w-3 rounded-[2px] border border-white/60 ring-1 ring-white/30" aria-hidden />
            selected
          </span>
        </div>
      </div>
    </ConsolePanel>
  );
}
