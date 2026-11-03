import { barPercents, barStaggerMs } from "./rankBarScale";
import { rc } from "./tokens";

import type { ReactNode } from "react";

export interface RankBarItem {
  /** Unique within the list; `highlight` names a row by it. */
  id: string;
  /** The row's name: a driver, a team, a car. Text, or a name component. */
  label: ReactNode;
  /** A mono caption after the name: a driver code, "Hard · 11 laps". */
  detail?: string;
  /** The bar's length, on a scale from zero. */
  value: number;
  /** The figure to show when it reads better than the bare number: "36%", "+0.123 s/lap". */
  valueText?: string;
  /** A second figure after the value, in the caption tone: the gap to the leader. */
  aside?: string;
  /** The bar's colour: a team colour from the data, or a token that carries a meaning (gold for titles). */
  color: string;
  /** The place in front of the row, from the data. The list never numbers rows itself, so ties stay the data's. */
  rank?: number | string;
}

export type RankBarSize = "regular" | "large";

export interface RankBarsProps {
  /** The rows, already in order. */
  items: readonly RankBarItem[];
  /** The list's accessible name: what is ranked, and by what ("Drivers' championship points"). */
  label: string;
  /** The top of the scale; the largest value when left out. */
  max?: number;
  /** The id of one row to bring forward. It keeps its colour and is marked current; the others go grey. */
  highlight?: string;
  /** `large` is the thicker bar of the constructors' table. */
  size?: RankBarSize;
  className?: string;
}

const BAR_HEIGHT: Record<RankBarSize, string> = { regular: "h-2.5", large: "h-3.5" };
const FIGURE = "text-right font-mono text-[13px] font-semibold leading-none";
const CAPTION = "text-rc-ink-3";

/**
 * The grid's columns, shared by every row through `subgrid` so bars start and
 * end in line: an optional place, the name (as wide as the longest, capped),
 * the bar, the figure, and an optional second figure.
 */
function columns(hasRank: boolean, hasAside: boolean): string {
  return [hasRank && "max-content", "fit-content(260px)", "minmax(48px, 1fr)", "max-content", hasAside && "max-content"]
    .filter(Boolean)
    .join(" ");
}

const NUMBER = new Intl.NumberFormat("en");

function figure(item: RankBarItem): string {
  if (item.valueText !== undefined) return item.valueText;
  return Number.isFinite(item.value) ? NUMBER.format(item.value) : "—";
}

/**
 * Ranked horizontal bars (the mockups' `.rank`): one row per entity with its
 * name, a bar from zero, and the figure written out, so no value rests on the
 * bar's length or colour alone.
 *
 * It is an ordered list named by `label`, and the text of each row reads in
 * full to a screen reader; the bars are hidden from it. Bars grow in once on
 * arrival, staggered, behind `motion-safe`, so the server's HTML is the chart
 * at rest.
 */
export function RankBars({ items, label, max, highlight, size = "regular", className = "" }: RankBarsProps) {
  const hasRank = items.some((item) => item.rank !== undefined);
  const hasAside = items.some((item) => item.aside !== undefined);
  const percents = barPercents(
    items.map((item) => item.value),
    max,
  );

  return (
    <ol
      aria-label={label}
      className={`grid gap-x-3 ${className}`}
      style={{ gridTemplateColumns: columns(hasRank, hasAside) }}
    >
      {items.map((item, index) => {
        const current = item.id === highlight;
        const quiet = highlight !== undefined && !current;
        return (
          <li
            key={item.id}
            aria-current={current ? "true" : undefined}
            className={`col-span-full grid min-h-8.5 grid-cols-subgrid items-center border-b border-rc-line-soft ${quiet ? CAPTION : "text-rc-ink"}`}
          >
            {hasRank && <span className={`${FIGURE} text-left ${CAPTION}`}>{item.rank}</span>}
            <span className="truncate font-semibold">
              {item.label}
              {item.detail !== undefined && (
                <>
                  {" "}
                  <span className={`ml-1.5 font-mono text-[11px] font-medium leading-none ${CAPTION}`}>
                    {item.detail}
                  </span>
                </>
              )}
            </span>
            <span aria-hidden="true" className={`relative rounded-[3px] bg-rc-ink/3 ${BAR_HEIGHT[size]}`}>
              <span
                data-fill
                className="absolute inset-y-0 left-0 origin-left rounded-[3px] motion-safe:animate-fill-x"
                style={{
                  width: `${percents[index]}%`,
                  backgroundColor: quiet ? rc.dim : item.color,
                  animationDelay: `${barStaggerMs(index)}ms`,
                }}
              />
            </span>
            <span className={FIGURE}>{figure(item)}</span>
            {hasAside && <span className={`${FIGURE} ${CAPTION}`}>{item.aside}</span>}
          </li>
        );
      })}
    </ol>
  );
}
