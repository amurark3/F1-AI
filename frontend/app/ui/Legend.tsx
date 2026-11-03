export type LegendMark = "swatch" | "rule" | "outline";

export interface LegendItem {
  /** What the mark stands for; unique within one legend. */
  label: string;
  /**
   * The mark's colour: a token from `tokens.ts`, or a team or compound
   * colour from the data. Leave it out for a plain note, such as "a
   * retirement counts as finishing behind".
   */
  color?: string;
  /** A filled square (the default), a thin upright rule for an event (a stop, a red flag), or an empty square. */
  mark?: LegendMark;
}

export interface LegendProps {
  items: readonly LegendItem[];
  /** The list's accessible name. */
  label?: string;
  className?: string;
}

const MARK_SHAPE: Record<LegendMark, string> = {
  swatch: "size-3 rounded-[2px]",
  rule: "h-3 w-0.5",
  outline: "size-3 rounded-[2px] border",
};

function Mark({ color, mark = "swatch" }: Omit<LegendItem, "label">) {
  if (color === undefined) return null;
  const style = mark === "outline" ? { borderColor: color } : { backgroundColor: color };
  return (
    <span aria-hidden="true" data-mark={mark} className={`inline-block shrink-0 ${MARK_SHAPE[mark]}`} style={style} />
  );
}

/**
 * A chart key (the mockups' `.legend`): a wrapping row of marks and labels,
 * in the mono caption tone. Legends are welcome wherever they add data
 * points. The spacing from the chart is the caller's (`mt-3.5` under one).
 */
export function Legend({ items, label = "Legend", className = "" }: LegendProps) {
  return (
    <ul
      aria-label={label}
      className={`flex flex-wrap gap-x-[18px] gap-y-2 font-mono text-[11px] font-medium leading-none text-rc-ink-3 ${className}`}
    >
      {items.map((item) => (
        <li key={item.label} className="inline-flex items-center gap-[7px]">
          <Mark color={item.color} mark={item.mark} />
          {item.label}
        </li>
      ))}
    </ul>
  );
}
