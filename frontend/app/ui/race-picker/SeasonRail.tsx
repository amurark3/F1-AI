"use client";

import { useId, useState } from "react";

import { tickLabel, tipAlign, type RailTick, type SeasonRail as Rail, type TickState } from "./railModel";
import { optionIndex, useActiveOption } from "./useActiveOption";

/** The bar for each state (`grand-prix.html` `.tick`): coloured by the winning team, outlined, or short and dim. */
const BAR: Record<TickState, string> = {
  won: "h-[22px] w-1.5 opacity-90",
  awaiting: "h-[22px] w-1.5 border border-rc-ink-3",
  upcoming: "h-3 w-1.5 bg-rc-dim",
};
const SELECTED_BAR = "h-[38px] w-[7px] bg-f1-red";
const TIP_ALIGN = { start: "translate-x-0", center: "-translate-x-1/2", end: "-translate-x-full" } as const;
/** Below this distance along the rail the selected round's label would sit on the key, so the key moves right. */
const KEY_SPAN = 25;

const CAPTION = "font-mono text-[9px] uppercase leading-none tracking-[0.16em] text-rc-ink-3";

function Tick({ tick, index, id, selected }: { tick: RailTick; index: number; id: string; selected: boolean }) {
  return (
    <span
      id={id}
      role="option"
      aria-selected={selected}
      aria-label={tickLabel(tick)}
      data-index={index}
      style={{ left: `${tick.left}%` }}
      className="absolute bottom-0 flex h-full w-3.5 -translate-x-1/2 cursor-pointer items-end justify-center"
    >
      <span
        className={`rounded-[1px] ${selected ? SELECTED_BAR : BAR[tick.state]}`}
        style={tick.color !== null && !selected ? { backgroundColor: tick.color } : undefined}
      />
    </span>
  );
}

/** The round under the pointer or the keyboard, named above its tick. Hidden from assistive tech: the option says it. */
function RailTip({ tick }: { tick: RailTick }) {
  return (
    <div
      aria-hidden="true"
      style={{ left: `${tick.left}%` }}
      className={`absolute bottom-[62px] z-10 hidden whitespace-nowrap rounded border border-rc-line bg-rc-raised px-2.5 py-2 text-xs leading-snug text-rc-ink sm:block ${TIP_ALIGN[tipAlign(tick.left)]}`}
    >
      <span className="block font-mono text-[10px] uppercase tracking-[0.08em] text-rc-ink-3">{tick.title}</span>
      <span className="font-medium">{tick.detail}</span>
    </div>
  );
}

export interface SeasonRailProps {
  rail: Rail;
  year: number;
  /** Index of the selected tick; -1 when the selection is not on the calendar. */
  selected: number;
  onSelect: (index: number) => void;
}

/**
 * The season as one rail: a listbox of rounds placed by date. Arrows, Home
 * and End walk it with a preview tip; Enter or Space (or a click) selects.
 */
export function SeasonRail({ rail, year, selected, onSelect }: SeasonRailProps) {
  const id = useId();
  const keys = useActiveOption(rail.ticks.length, selected, onSelect);
  const [hovered, setHovered] = useState<number | null>(null);
  const shown = hovered ?? keys.active;
  const current = selected === -1 ? null : rail.ticks[selected];

  return (
    // `overflow-x-clip` keeps the last month's label from widening a phone's page; the tip may still rise above.
    <div className="relative h-[84px] overflow-x-clip">
      <span
        aria-hidden="true"
        className={`absolute top-0 hidden sm:block ${(current?.left ?? 100) < KEY_SPAN ? "right-0" : "left-0"} ${CAPTION}`}
      >
        Tick colour · winning team
      </span>
      <div aria-hidden="true" className="absolute inset-x-0 top-[54px] h-px bg-rc-line" />
      {rail.months.map((month) => (
        <span
          key={month.label}
          aria-hidden="true"
          style={{ left: `${month.left}%` }}
          className={`absolute bottom-1.5 ${CAPTION}`}
        >
          {month.label}
        </span>
      ))}
      {current ? (
        <span
          aria-hidden="true"
          style={{ left: `${current.left}%` }}
          className="absolute -top-0.5 -translate-x-1/2 font-mono text-[10px] font-semibold leading-none tracking-[0.1em] text-rc-red-text"
        >
          R{current.race.round}
        </span>
      ) : null}
      <div
        role="listbox"
        tabIndex={0}
        aria-label={`${year} season rounds`}
        aria-activedescendant={keys.active === null ? undefined : `${id}-${keys.active}`}
        onFocus={keys.onFocus}
        onBlur={keys.reset}
        onKeyDown={keys.onKeyDown}
        onClick={(event) => {
          const index = optionIndex(event.target);
          if (index === null) return;
          keys.reset();
          onSelect(index);
        }}
        onPointerMove={(event) => setHovered(optionIndex(event.target))}
        onPointerLeave={() => setHovered(null)}
        className="absolute inset-x-0 bottom-[30px] h-[38px] rounded-sm"
      >
        {rail.ticks.map((tick, index) => (
          <Tick key={tick.race.round} tick={tick} index={index} id={`${id}-${index}`} selected={index === selected} />
        ))}
      </div>
      {shown === null ? null : <RailTip tick={rail.ticks[shown]} />}
    </div>
  );
}
