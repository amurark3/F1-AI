"use client";

import { countdownParts, type CountdownParts } from "./countdownParts";
import { useClock } from "./useClock";

export interface CountdownProps {
  /** The moment counted down to: an ISO timestamp, epoch milliseconds or a `Date`. */
  target: string | number | Date;
  /** The timer's accessible name, such as "Time to Practice 1". The visible caption is the caller's. */
  label: string;
  /** Adds a seconds cell. Off by default: the mockups count days, hours and minutes. */
  seconds?: boolean;
  /**
   * `hero` (the default) sits on the page, with cells on the panel colour;
   * `panel` sits inside a panel, with smaller cells on the page colour.
   */
  variant?: "hero" | "panel";
  className?: string;
}

const CELLS: ReadonlyArray<{ part: keyof CountdownParts; unit: string }> = [
  { part: "days", unit: "days" },
  { part: "hours", unit: "hrs" },
  { part: "minutes", unit: "min" },
  { part: "seconds", unit: "sec" },
];

const VARIANT = {
  hero: { cell: "min-w-[74px] bg-(--surface) pb-2 pt-2.5", digits: "text-[44px]" },
  panel: { cell: "min-w-[66px] bg-background pb-[7px] pt-2", digits: "text-[38px]" },
} as const;

/** Shown before the browser has a clock, and for a target that is not a date. */
const PLACEHOLDER = "--";

/**
 * Time left to a moment, in boxed cells (the mockups' `.clock`), ticking on
 * the page's one shared clock.
 *
 * The server renders dashes: a prerendered page has no honest "now". Once the
 * moment passes every cell reads 00; saying what is live is the caller's job.
 */
export function Countdown({ target, label, seconds = false, variant = "hero", className = "" }: CountdownProps) {
  const now = useClock();
  const targetMs = new Date(target).getTime();
  const parts = now === null || Number.isNaN(targetMs) ? null : countdownParts(targetMs, now);
  const style = VARIANT[variant];

  return (
    <div role="timer" aria-label={label} className={`flex gap-2 ${className}`}>
      {CELLS.slice(0, seconds ? 4 : 3).map(({ part, unit }) => (
        <div key={part} className={`rounded border border-rc-line px-1.5 text-center ${style.cell}`}>
          <span className={`block font-display font-extrabold leading-none tabular-nums text-rc-ink ${style.digits}`}>
            {parts ? parts[part] : PLACEHOLDER}
          </span>
          <span className="font-mono text-[9px] font-semibold uppercase leading-none tracking-[0.2em] text-rc-ink-3">
            {unit}
          </span>
        </div>
      ))}
    </div>
  );
}
