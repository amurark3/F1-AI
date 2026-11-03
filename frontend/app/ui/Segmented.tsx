"use client";

import { useRef, type KeyboardEvent, type ReactNode } from "react";

export interface SegmentedOption<V extends string> {
  value: V;
  label: ReactNode;
  /** Shown but not choosable yet, such as "After qualifying" before qualifying has run. */
  disabled?: boolean;
}

export interface SegmentedProps<V extends string> {
  options: ReadonlyArray<SegmentedOption<V>>;
  value: V;
  onChange: (value: V) => void;
  /** What the control chooses between, for screen readers: "Championship". */
  label: string;
  /**
   * `radiogroup` (the default) when the choice re-cuts what is already on
   * screen, such as drivers or teams in one table; `tablist` when each option
   * shows its own panel.
   */
  semantics?: "radiogroup" | "tablist";
  /** With `tablist`: the id of the panel the tabs control. */
  controls?: string;
  className?: string;
}

type Move = (index: number, count: number) => number;

const previous: Move = (index, count) => (index - 1 + count) % count;
const next: Move = (index, count) => (index + 1) % count;

/** Tabs move along their row only; Home and End jump to either end (WAI-ARIA tabs pattern). */
const TAB_MOVES: Partial<Record<string, Move>> = {
  ArrowLeft: previous,
  ArrowRight: next,
  Home: () => 0,
  End: (_index, count) => count - 1,
};

/** A radio group also answers the vertical arrows (WAI-ARIA radio group pattern). */
const RADIO_MOVES: Partial<Record<string, Move>> = { ...TAB_MOVES, ArrowUp: previous, ArrowDown: next };

/**
 * A segmented control (the mockups' `.seg`): two to four options, one chosen.
 *
 * One tab stop for the whole control. The arrow keys move between options and
 * choose as they go, wrapping at either end and skipping disabled options.
 * The focus ring is red text, as on every control in the kit.
 */
export function Segmented<V extends string>({
  options,
  value,
  onChange,
  label,
  semantics = "radiogroup",
  controls,
  className = "",
}: SegmentedProps<V>) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);
  const tabs = semantics === "tablist";
  const enabled = options.filter((option) => !option.disabled);
  // The tab stop: the chosen option, or the first enabled one when the choice is not available.
  const tabStop = enabled.some((option) => option.value === value) ? value : enabled.at(0)?.value;

  const choose = (choice: V) => {
    if (choice !== value) onChange(choice);
  };

  const onKeyDown = (event: KeyboardEvent<HTMLButtonElement>, from: V) => {
    const move = (tabs ? TAB_MOVES : RADIO_MOVES)[event.key];
    if (!move) return;
    event.preventDefault();
    const target =
      enabled[
        move(
          enabled.findIndex((option) => option.value === from),
          enabled.length,
        )
      ];
    choose(target.value);
    refs.current[options.indexOf(target)]?.focus();
  };

  return (
    <div
      role={semantics}
      aria-label={label}
      className={`inline-flex max-w-full flex-wrap rounded-md border border-rc-line bg-background p-0.5 ${className}`}
    >
      {options.map((option, index) => {
        const chosen = option.value === value;
        const state = tabs
          ? { role: "tab", "aria-selected": chosen, "aria-controls": controls }
          : { role: "radio", "aria-checked": chosen };
        return (
          <button
            key={option.value}
            ref={(node) => {
              refs.current[index] = node;
            }}
            type="button"
            {...state}
            tabIndex={option.value === tabStop ? 0 : -1}
            disabled={option.disabled}
            onClick={() => choose(option.value)}
            onKeyDown={(event) => onKeyDown(event, option.value)}
            className={`inline-flex min-h-6 items-center rounded px-3 py-1.5 font-mono text-[11px] font-semibold uppercase leading-none tracking-[0.14em] transition-colors focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-rc-red-text disabled:cursor-not-allowed disabled:opacity-40 ${
              chosen ? "bg-rc-raised text-rc-ink" : "text-rc-ink-3 enabled:hover:text-rc-ink-2"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
