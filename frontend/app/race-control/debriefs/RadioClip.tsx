"use client";

import { DriverName } from "@/app/ui/names/DriverName";

import { circuitClock, mmss, pauseLabel, playLabel } from "./radioModel";

import type { RadioClip as Clip } from "./debriefTypes";

export type ClipState = "idle" | "playing" | "paused" | "failed";

interface RadioClipProps {
  clip: Clip;
  offset: number | null;
  state: ClipState;
  elapsed: number;
  duration: number | null;
  onToggle: (url: string) => void;
}

const BASE =
  "relative inline-grid h-[34px] grid-cols-[22px_3px_auto_auto] items-center gap-2 overflow-hidden rounded border border-rc-line bg-(--surface) pl-1.5 pr-3 text-rc-ink hover:border-rc-ink-3";
const ACTIVE = "border-rc-ink-2 bg-rc-raised";

function timeText(props: RadioClipProps): string {
  if (props.state === "failed") return "Can't play";
  if (props.state === "idle") return circuitClock(props.clip.at, props.offset);
  return props.duration === null ? mmss(props.elapsed) : `${mmss(props.elapsed)} / ${mmss(props.duration)}`;
}

/** One team-radio clip as a play / pause chip; the section's one audio element does the playing. */
export function RadioClip(props: RadioClipProps) {
  const { clip, offset, state, elapsed, duration, onToggle } = props;
  const playing = state === "playing";
  const active = playing || state === "paused";
  const label = playing
    ? pauseLabel(clip)
    : `${playLabel(clip, offset)}${state === "failed" ? " (couldn't load)" : ""}`;
  const progress = duration ? `${(elapsed / duration) * 100}%` : "0%";
  return (
    <button
      type="button"
      aria-label={label}
      aria-pressed={playing}
      onClick={() => onToggle(clip.url)}
      className={`${BASE} ${active ? ACTIVE : ""}`}
    >
      <span
        aria-hidden="true"
        className={`grid size-[22px] place-items-center rounded-full text-[9px] ${playing ? "bg-rc-ink text-(--background)" : "bg-rc-raised text-rc-ink"}`}
      >
        {playing ? "❚❚" : "▶"}
      </span>
      <i aria-hidden="true" className="h-4 w-[3px]" style={{ background: clip.colour }} />
      <b className="font-mono text-xs font-semibold">
        <DriverName name={clip.driver_name} code={clip.driver_code} variant="code" />
      </b>
      <span className="font-mono text-[11px] font-medium text-rc-ink-3">{timeText(props)}</span>
      {active && (
        <span aria-hidden="true" className="absolute inset-x-0 bottom-0 h-0.5 bg-rc-line">
          <span className="block h-0.5 bg-rc-ink" style={{ width: progress }} />
        </span>
      )}
    </button>
  );
}
