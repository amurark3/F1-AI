"use client";

import { DISPLAY, EYEBROW } from "@/app/ui/typography";

import { Panel } from "../components/RaceControlPrimitives";
import { StateTag } from "../grand-prix/StateTag";

import { maxStep, stepKind, stepLabel } from "./rewindModel";

import type { RaceRewind, TrackKind } from "./rewindTypes";

const STEP_BUTTON =
  "rounded-sm border border-rc-line px-3 py-2 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-rc-ink hover:border-rc-ink-3 disabled:cursor-not-allowed disabled:opacity-40";

const TRACK_TAGS: Record<TrackKind, { text: string; tone: "neutral" | "red" }> = {
  sc: { text: "Safety Car", tone: "neutral" },
  vsc: { text: "VSC", tone: "neutral" },
  red: { text: "Red flag", tone: "red" },
};

interface ScrubberProps {
  data: RaceRewind;
  step: number;
  playing: boolean;
  onToggle: () => void;
  /** A manual move: it pauses playback. */
  onStep: (step: number) => void;
}

function Controls({ step, max, playing, onToggle, onStep }: Omit<ScrubberProps, "data"> & { max: number }) {
  return (
    <div className="flex items-center gap-2">
      <button
        type="button"
        aria-label="Previous lap"
        disabled={step <= 0}
        onClick={() => onStep(step - 1)}
        className={STEP_BUTTON}
      >
        ‹
      </button>
      <button type="button" aria-pressed={playing} onClick={onToggle} className={STEP_BUTTON}>
        {playing ? "❚❚ Pause" : "▶ Play"}
      </button>
      <button
        type="button"
        aria-label="Next lap"
        disabled={step >= max}
        onClick={() => onStep(step + 1)}
        className={STEP_BUTTON}
      >
        ›
      </button>
    </div>
  );
}

const READOUT_WORDS = { grid: "Grid", final: "Final" } as const;

function Readout({ data, step }: { data: RaceRewind; step: number }) {
  const at = stepKind(step, data);
  const track = at.kind === "lap" ? data.laps[at.lap - 1].track : null;
  return (
    <div className="flex items-center gap-3">
      <span className={EYEBROW}>After lap</span>
      <b className={`${DISPLAY} text-[34px] text-rc-ink`}>
        {at.kind === "lap" ? at.lap : READOUT_WORDS[at.kind]}
        {at.kind === "lap" && (
          <span className="ml-1.5 font-mono text-xs font-medium text-rc-ink-3">/ {data.total_laps}</span>
        )}
      </b>
      {track && <StateTag tone={TRACK_TAGS[track].tone}>{TRACK_TAGS[track].text}</StateTag>}
    </div>
  );
}

function Track({ data, step, onStep }: Pick<ScrubberProps, "data" | "step" | "onStep">) {
  const max = maxStep(data);
  return (
    <div>
      <div className="relative">
        <div aria-hidden="true" className="absolute inset-x-2 top-[3px]">
          {data.neutralisations
            .filter((period) => period.kind !== "red")
            .map((period) => (
              <span
                key={`${period.kind}-${period.start_lap}`}
                className="absolute top-0 h-1 bg-rc-ink-3/35"
                style={{
                  left: `${((period.start_lap - 1) / max) * 100}%`,
                  width: `${((period.end_lap - period.start_lap + 1) / max) * 100}%`,
                }}
              />
            ))}
        </div>
        <input
          type="range"
          min={0}
          max={max}
          step={1}
          value={step}
          aria-label="Lap"
          aria-valuetext={stepLabel(step, data)}
          onChange={(event) => onStep(Number(event.target.value))}
          className="relative w-full accent-f1-red"
        />
      </div>
      <div className="flex justify-between font-mono text-[10px] text-rc-ink-3">
        <span>Grid</span>
        <span>{`L${Math.round((data.total_laps + 1) / 2)}`}</span>
        <span>{data.final ? "Final" : `L${data.total_laps}`}</span>
      </div>
    </div>
  );
}

/** The replay's controls: previous, play, next, the lap read-out and the range. */
export function Scrubber({ data, step, playing, onToggle, onStep }: ScrubberProps) {
  return (
    <Panel className="mt-7 grid items-center gap-6 p-5 lg:grid-cols-[auto_auto_minmax(0,1fr)]">
      <Controls step={step} max={maxStep(data)} playing={playing} onToggle={onToggle} onStep={onStep} />
      <Readout data={data} step={step} />
      <Track data={data} step={step} onStep={onStep} />
    </Panel>
  );
}
