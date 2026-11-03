import { EYEBROW } from "./typography";

import type { ReactNode } from "react";

export interface PanelHeadingProps {
  /** What kind of panel this is: "Schedule", "Degradation". */
  eyebrow?: ReactNode;
  /** The finding, as a sentence. On a chart it is computed from the data, never written by hand. */
  title: ReactNode;
  /** What the panel shows and how to read it: units, filters, what was left out. */
  sub?: ReactNode;
  /** A control at the right: a `Segmented`, a source badge. */
  aside?: ReactNode;
  /** Heading level: `h3` under a page's `SectionHead`, `h2` when the panel stands alone. */
  as?: "h2" | "h3";
  className?: string;
}

/** The head of a panel or chart card (the mockups' `.ph` and `.card h3`). */
export function PanelHeading({ eyebrow, title, sub, aside, as: Heading = "h3", className = "" }: PanelHeadingProps) {
  return (
    <div className={`mb-5 flex flex-wrap items-end justify-between gap-4 ${className}`}>
      <div className="min-w-0">
        {eyebrow != null && <p className={EYEBROW}>{eyebrow}</p>}
        <Heading className="mt-2 font-display text-[26px] font-extrabold uppercase leading-[1.05] text-balance text-rc-ink">
          {title}
        </Heading>
        {sub != null && <p className="mt-1 text-xs text-rc-ink-3">{sub}</p>}
      </div>
      {aside != null && <div className="shrink-0">{aside}</div>}
    </div>
  );
}
