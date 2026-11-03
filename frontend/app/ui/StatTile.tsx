import { EYEBROW } from "./typography";

import type { ReactNode } from "react";

export interface StatTileProps {
  /** What the figure counts, as an eyebrow. */
  label: string;
  /** The figure itself. An `AnimatedNumber` is welcome here. */
  value: ReactNode;
  /** A small unit or denominator after the figure: "km", "of 19". */
  unit?: string;
  /** A caption under the figure: who, when, out of what. */
  sub?: ReactNode;
  /** The row's headline figure: a wider tile and a larger figure. */
  lead?: boolean;
  className?: string;
}

/**
 * One figure with its label (the mockups' `.kpis` cell).
 *
 * Inside {@link StatTiles} the row sets the spacing and hairlines; alone, the
 * caller places it.
 */
export function StatTile({ label, value, unit, sub, lead = false, className = "" }: StatTileProps) {
  return (
    <div data-lead={lead ? "" : undefined} className={`min-w-0 ${className}`}>
      <p className={EYEBROW}>{label}</p>
      <p
        className={`mt-2.5 font-display font-extrabold leading-none tabular-nums text-rc-ink ${lead ? "text-[56px]" : "text-[40px]"}`}
      >
        {value}
        {unit ? (
          <span className="ml-[0.15em] text-[0.45em] font-bold tracking-[0.04em] text-rc-ink-3">{unit}</span>
        ) : null}
      </p>
      {sub != null && <p className="mt-1 text-xs text-rc-ink-3">{sub}</p>}
    </div>
  );
}

/**
 * A row of {@link StatTile}s between two hairlines, one rule between each
 * tile. A `lead` tile takes half again the width of the others: on a grid of
 * equal columns it spans three to their two, so the ratio holds wherever it
 * sits and includes the padding, as the mockups' `fr` tracks do. Below `lg`
 * the tiles stack, divided by rules.
 */
export function StatTiles({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div
      className={`divide-y divide-rc-line border-y border-rc-line lg:grid lg:auto-cols-fr lg:grid-flow-col lg:divide-x lg:divide-y-0 [&>*]:py-[18px] [&>*]:pr-5 lg:[&>*]:col-span-2 lg:[&>*+*]:pl-5 lg:[&>[data-lead]]:col-span-3 ${className}`}
    >
      {children}
    </div>
  );
}
