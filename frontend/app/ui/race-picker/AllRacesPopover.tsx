"use client";

import { ChevronDown } from "lucide-react";
import { useCallback, useId, useRef, useState, type FocusEvent } from "react";

import { useDismiss, type DismissReason } from "../shell/useDismiss";

import { shortRaceName, tickLabel, type RailTick } from "./railModel";
import { optionIndex, useActiveOption } from "./useActiveOption";

/** The swatch beside each race: the rail's tick, laid on its side. */
const SWATCH: Record<RailTick["state"], string> = {
  won: "",
  awaiting: "border border-rc-ink-3",
  upcoming: "bg-rc-dim",
};

interface RaceListProps {
  id: string;
  ticks: readonly RailTick[];
  year: number;
  selected: number;
  onChoose: (index: number) => void;
}

/** Every race of the season, one row each; it takes focus when it opens. */
function RaceList({ id, ticks, year, selected, onChoose }: RaceListProps) {
  const keys = useActiveOption(ticks.length, selected, onChoose);
  // React's `autoFocus` focuses form controls only; the list focuses itself as it mounts.
  const focusOnMount = useCallback((node: HTMLDivElement | null) => node?.focus(), []);

  return (
    <div
      ref={focusOnMount}
      id={id}
      role="listbox"
      tabIndex={0}
      aria-label={`All ${year} races`}
      aria-activedescendant={keys.active === null ? undefined : `${id}-${keys.active}`}
      onFocus={keys.onFocus}
      onBlur={keys.reset}
      onKeyDown={keys.onKeyDown}
      onClick={(event) => {
        const index = optionIndex(event.target);
        if (index !== null) onChoose(index);
      }}
      className="absolute inset-x-0 top-full z-20 mt-2 max-h-[min(60vh,28rem)] overflow-y-auto rounded-md border border-rc-line bg-rc-raised py-1 shadow-lg motion-safe:animate-overlay-in sm:right-auto sm:w-[22rem]"
    >
      {ticks.map((tick, index) => (
        <div
          key={tick.race.round}
          id={`${id}-${index}`}
          role="option"
          aria-selected={index === selected}
          aria-label={tickLabel(tick)}
          data-index={index}
          // The keyboard's row stays in view as it walks a list taller than the popover.
          ref={index === keys.active ? (node) => node?.scrollIntoView({ block: "nearest" }) : undefined}
          className={`flex cursor-pointer items-center gap-3 border-l-2 px-3 py-2 hover:bg-white/[0.04] ${
            index === selected ? "border-f1-red" : "border-transparent"
          } ${index === keys.active ? "bg-white/[0.06]" : ""}`}
        >
          <span
            aria-hidden="true"
            className={`h-3.5 w-1.5 shrink-0 rounded-[1px] ${SWATCH[tick.state]}`}
            style={tick.color === null ? undefined : { backgroundColor: tick.color }}
          />
          <span className="w-7 shrink-0 font-mono text-[11px] text-rc-ink-3">R{tick.race.round}</span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm text-rc-ink">{shortRaceName(tick.race.name)}</span>
            <span className="block truncate font-mono text-[10px] text-rc-ink-3">{tick.detail}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

export interface AllRacesPopoverProps {
  ticks: readonly RailTick[];
  year: number;
  /** Index of the selected round; -1 when it is not on the calendar. */
  selected: number;
  onSelect: (index: number) => void;
}

/**
 * "All races ▾": the whole calendar as a list, for choosing by name rather
 * than by place on the rail. Escape or choosing a race closes it and returns
 * focus to the button; a press outside or tabbing away closes it too.
 *
 * It hangs from the picker's header row (the nearest positioned ancestor),
 * full width on a phone.
 */
export function AllRacesPopover({ ticks, year, selected, onSelect }: AllRacesPopoverProps) {
  const listId = useId();
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);

  const close = useCallback((reason: DismissReason | "chosen") => {
    setOpen(false);
    if (reason !== "outside") triggerRef.current?.focus();
  }, []);
  useDismiss(open, rootRef, close);

  // Tabbing out closes it; a blur onto nothing is left to the outside-press check.
  const onBlur = (event: FocusEvent<HTMLDivElement>) => {
    const next = event.relatedTarget;
    if (next !== null && !event.currentTarget.contains(next)) setOpen(false);
  };

  return (
    // A presentation wrapper: it only hears focus leaving the button and the list inside it.
    <div ref={rootRef} role="presentation" onBlur={onBlur}>
      <button
        ref={triggerRef}
        type="button"
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={open ? listId : undefined}
        onClick={() => setOpen(!open)}
        className="inline-flex h-[34px] items-center gap-1.5 rounded border border-rc-line px-2.5 font-mono text-[10px] font-semibold uppercase leading-none tracking-[0.18em] text-rc-ink-2 transition-colors hover:border-rc-ink-3"
      >
        All races
        <ChevronDown aria-hidden="true" className={`size-3 ${open ? "rotate-180" : ""}`} />
      </button>
      {open ? (
        <RaceList
          id={listId}
          ticks={ticks}
          year={year}
          selected={selected}
          onChoose={(index) => {
            close("chosen");
            onSelect(index);
          }}
        />
      ) : null}
    </div>
  );
}
