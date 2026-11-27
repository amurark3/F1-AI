import { barStaggerMs } from "./rankBarScale";

export interface ColumnBarItem {
  /** Unique within the chart. */
  id: string;
  /** The label under the column: "R7". */
  axis: string;
  /** The bar's size on a scale from zero; negative grows below a zero line, null draws no bar. */
  value: number | null;
  /** The figure at the bar's end, shown from `sm` up ("55", "+3"). */
  valueText?: string;
  /** The bar's colour: a team colour from the data, or a token that carries a meaning. */
  color?: string;
  /** What stands where a bar would, when `value` is null: "DNF", "—". */
  marker?: string;
  markerTone?: "alert" | "muted";
  /** The column in words, for the tooltip and screen readers: "R2 Chinese GP: 55 points". */
  description: string;
}

export interface ColumnBarsProps {
  items: readonly ColumnBarItem[];
  /** The list's accessible name: what the columns are, per what. */
  label: string;
  /** The top of the scale; the largest size when left out. */
  max?: number;
  /** The chart's height in px. */
  height?: number;
  className?: string;
}

const PX_PER_COLUMN = 20;
const TICK = "absolute inset-x-0 h-[1.5px] bg-rc-dim";
const MARKER_TONE = { alert: "text-rc-red-text", muted: "text-rc-ink-3" } as const;

function scaleOf(items: readonly ColumnBarItem[], max: number | undefined): number {
  const largest = Math.max(0, ...items.map((item) => Math.abs(item.value ?? 0)));
  const scale = max ?? largest;
  return scale > 0 ? scale : 1;
}

/** A bar's length as a percentage of the plot (of half of it when the plot splits at zero). */
function percent(value: number, scale: number, signed: boolean): number {
  const share = Math.min(Math.abs(value) / scale, 1) * (signed ? 50 : 100);
  return Math.round(share * 100) / 100;
}

function Bar({ item, scale, signed, index }: { item: ColumnBarItem; scale: number; signed: boolean; index: number }) {
  const value = item.value!;
  const negative = value < 0;
  const place = negative ? "top-1/2 origin-top" : `${signed ? "bottom-1/2" : "bottom-0"} origin-bottom`;
  return (
    <span
      data-bar
      className={`absolute inset-x-0 rounded-[2px] bg-rc-ink-3 motion-safe:animate-rise-y ${place}`}
      style={{
        height: `${percent(value, scale, signed)}%`,
        backgroundColor: item.color,
        animationDelay: `${barStaggerMs(index)}ms`,
      }}
    >
      {item.valueText !== undefined && (
        <span
          data-value
          className={`absolute inset-x-0 hidden text-center font-mono text-[11px] font-semibold leading-none text-rc-ink-2 sm:block ${negative ? "top-full pt-1" : "bottom-full pb-1"}`}
        >
          {item.valueText}
        </span>
      )}
    </span>
  );
}

function Mark({ item, signed }: { item: ColumnBarItem; signed: boolean }) {
  if (item.value === null) {
    if (item.marker === undefined) return null;
    return (
      <span
        data-marker
        className={`absolute inset-x-0 text-center font-mono text-[10px] font-semibold leading-none max-sm:[writing-mode:vertical-rl] ${MARKER_TONE[item.markerTone ?? "muted"]} ${signed ? "top-1/2 -translate-y-1/2" : "bottom-0"}`}
      >
        {item.marker}
      </span>
    );
  }
  return item.value === 0 ? <span data-tick className={`${TICK} ${signed ? "top-1/2" : "bottom-0"}`} /> : null;
}

/**
 * Per-round columns (the mockups' `.cols`): one bar per round on a scale from
 * zero, the round's label underneath, and the figure written beside the bar's
 * end from `sm` up. A negative value grows below a zero line; a missing one
 * shows its marker ("DNF") instead of a bar. Every column carries its own
 * sentence, so no value rests on a bar's height or colour alone.
 *
 * Wider than its box, the chart scrolls sideways inside it (20 px a column),
 * so the page never does. Bars rise in once, behind `motion-safe`.
 */
export function ColumnBars({ items, label, max, height = 160, className = "" }: ColumnBarsProps) {
  const scale = scaleOf(items, max);
  const signed = items.some((item) => (item.value ?? 0) < 0);
  return (
    <div className={`overflow-x-auto overflow-y-hidden ${className}`}>
      <ol
        aria-label={label}
        className="grid gap-1"
        style={{
          gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))`,
          minWidth: `${items.length * PX_PER_COLUMN}px`,
          height: `${height}px`,
        }}
      >
        {items.map((item, index) => (
          <li key={item.id} title={item.description} className="relative">
            <span className={`absolute inset-x-0 top-5 ${signed ? "bottom-10" : "bottom-6"}`}>
              {signed && <span data-zero-line className="absolute -inset-x-0.5 top-1/2 h-px bg-rc-line" />}
              {item.value !== null && item.value !== 0 && (
                <Bar item={item} scale={scale} signed={signed} index={index} />
              )}
              <Mark item={item} signed={signed} />
            </span>
            <span
              data-axis
              aria-hidden="true"
              className="absolute inset-x-0 bottom-0 text-center font-mono text-[10px] leading-none text-rc-ink-3"
            >
              {item.axis}
            </span>
            <span className="sr-only">{item.description}</span>
          </li>
        ))}
      </ol>
    </div>
  );
}
