"use client";

import { useState, type KeyboardEvent } from "react";

/** Arrow keys step one option; the list reads along the rail or down the popover, so both pairs work. */
const STEPS: Partial<Record<string, -1 | 1>> = { ArrowLeft: -1, ArrowUp: -1, ArrowRight: 1, ArrowDown: 1 };

/** The option a key moves to from `index` in a list of `count`, stopping at either end; null for any other key. */
export function listMove(key: string, index: number, count: number): number | null {
  if (key === "Home") return 0;
  if (key === "End") return count - 1;
  const step = STEPS[key];
  return step === undefined ? null : Math.min(Math.max(index + step, 0), count - 1);
}

/** The option an event landed on, from its `data-index`; null for the list's own background. */
export function optionIndex(target: EventTarget): number | null {
  // Listening on the list, every target is an element.
  const option = (target as Element).closest<HTMLElement>("[data-index]");
  return option ? Number(option.dataset.index) : null;
}

export interface ActiveOption {
  /** The option the keyboard is on (`aria-activedescendant`); null while the list is not focused. */
  active: number | null;
  /** Clears the keyboard's place: on blur, and after a click. */
  reset: () => void;
  onFocus: () => void;
  onKeyDown: (event: KeyboardEvent) => void;
}

/**
 * A listbox that keeps focus itself and points at its active option
 * (`aria-activedescendant`), the WAI-ARIA listbox pattern with selection on
 * Enter or Space rather than on every arrow, so walking the season previews
 * each round without loading it. Focus starts on the selected option.
 */
export function useActiveOption(count: number, selected: number, onCommit: (index: number) => void): ActiveOption {
  const [active, setActive] = useState<number | null>(null);
  const home = Math.max(selected, 0);

  const onKeyDown = (event: KeyboardEvent) => {
    const from = active ?? home;
    const to = listMove(event.key, from, count);
    if (to !== null) {
      event.preventDefault();
      setActive(to);
    } else if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onCommit(from);
    }
  };

  return {
    active,
    reset: () => setActive(null),
    onFocus: () => setActive(home),
    onKeyDown,
  };
}
