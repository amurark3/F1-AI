import { f1 } from "./tokens";
import { DISPLAY, EYEBROW } from "./typography";

import type { ReactNode } from "react";

export interface PageHeroProps {
  /** The mono caption above the title: section, season, round. */
  eyebrow?: ReactNode;
  /** The page's one `h1`. A driver's full name on driver pages. */
  title: ReactNode;
  /** One line under the rule, in the secondary tone. */
  meta?: ReactNode;
  /**
   * Colour of the rule under the title, and of the band's top edge. Brand red
   * by default; the team's colour on team and driver pages, gold for a
   * champion. A blank value (a team colour the feed left out) falls back to red.
   */
  accent?: string | null;
  /** Entity pages: sets the hero on the framed hero band. */
  band?: boolean;
  /** A leading column before the title: the car number on driver pages. */
  lead?: ReactNode;
  /** A right-hand column: a team's lineup, a circuit map. */
  aside?: ReactNode;
  /** Anything under the meta line: a countdown, a headline figure. */
  children?: ReactNode;
  className?: string;
}

/** The two looks in the mockups: `page-title` on most pages, the framed band on team and driver pages. */
const LAYOUT = {
  plain: {
    frame: "",
    columns: "gap-8 lg:grid-cols-[5fr_6fr]",
    body: "",
    title: "text-[clamp(48px,5.4vw,84px)]",
    aside: "",
  },
  band: {
    frame: "relative overflow-hidden rounded-md border border-rc-line bg-rc-hero",
    columns: "lg:grid-cols-[1.1fr_1fr]",
    body: "p-6 sm:p-9",
    title: "text-[clamp(64px,8vw,120px)]",
    aside: "border-t border-rc-line lg:border-l lg:border-t-0",
  },
} as const;

/** With a lead, the band is three columns and the cells inherit the band's padding. */
const LEAD = {
  columns: "lg:grid-cols-[auto_minmax(0,1fr)_auto] lg:items-end gap-x-9",
  lead: "px-6 pt-6 sm:px-9 lg:pb-9",
  body: "p-6 sm:p-9 lg:pl-0",
  /** driver.html's size: the car number takes the room the band title would. */
  title: "text-[clamp(48px,6vw,92px)]",
} as const;

/** Each line rises in on entrance, a beat after the one above; the rule then draws out from the left. */
const RISE = "motion-safe:animate-fade-up";

function accentColor(accent: string | null | undefined): string {
  return accent?.trim() ? accent : f1.red;
}

/**
 * The head of a page: eyebrow, condensed title, the accent rule, a meta line.
 *
 * Entrance motion is CSS only and sits behind `motion-safe`, so a reader who
 * prefers reduced motion sees the hero at rest, and the server's HTML is
 * already final.
 */
export function PageHero({
  eyebrow,
  title,
  meta,
  accent,
  band = false,
  lead,
  aside,
  children,
  className = "",
}: PageHeroProps) {
  const layout = band ? LAYOUT.band : LAYOUT.plain;
  const color = accentColor(accent);
  const hasLead = lead != null;
  const columns = hasLead ? LEAD.columns : layout.columns;
  const asideClass = hasLead ? LEAD.body : layout.aside;

  return (
    <header
      data-band={band ? "" : undefined}
      className={`grid min-w-0 ${layout.frame} ${aside == null && !hasLead ? "" : columns} ${className}`}
    >
      {band && (
        <div aria-hidden="true" className="absolute inset-x-0 top-0 h-[3px]" style={{ backgroundColor: color }} />
      )}
      {hasLead && <div className={`min-w-0 ${LEAD.lead}`}>{lead}</div>}
      <div className={`min-w-0 ${hasLead ? LEAD.body : layout.body}`}>
        {eyebrow != null && <p className={`${EYEBROW} ${RISE}`}>{eyebrow}</p>}
        <h1
          className={`${DISPLAY} ${hasLead ? LEAD.title : layout.title} mt-3.5 text-rc-ink ${RISE} [animation-delay:60ms]`}
        >
          {title}
        </h1>
        <div
          aria-hidden="true"
          data-hero-rule=""
          className="mb-4 mt-[22px] h-[3px] w-24 origin-left motion-safe:animate-fill-x [animation-delay:250ms]"
          style={{ backgroundColor: color }}
        />
        {meta != null && (
          <p className={`max-w-[70ch] text-[15px] text-rc-ink-2 ${RISE} [animation-delay:120ms]`}>{meta}</p>
        )}
        {children != null && <div className={`mt-8 ${RISE} [animation-delay:200ms]`}>{children}</div>}
      </div>
      {aside != null && <div className={`min-w-0 ${asideClass}`}>{aside}</div>}
    </header>
  );
}
