import { EYEBROW } from "./typography";

import type { ReactNode } from "react";

export interface SectionHeadProps {
  /** The section's place on the page, from 1; shown as a two-digit numeral. */
  index: number;
  title: ReactNode;
  /** At the far right. A string reads as an eyebrow caption; anything else renders as given. */
  aside?: ReactNode;
  /** Heading level: `h2` under the page's `h1`. */
  as?: "h2" | "h3";
  /** For `aria-labelledby` on the section, or an in-page link. */
  id?: string;
  className?: string;
}

/**
 * The head of a page section (the mockups' `.section-head`): an index
 * numeral, a condensed title and a hairline under both. The numeral orders
 * the page for the eye only, so screen readers skip it.
 */
export function SectionHead({ index, title, aside, as: Heading = "h2", id, className = "" }: SectionHeadProps) {
  return (
    <div className={`mb-6 flex items-baseline gap-4 border-b border-rc-line pb-3.5 ${className}`}>
      <span aria-hidden="true" className="font-mono text-[13px] font-semibold leading-none text-rc-red-text">
        {String(index).padStart(2, "0")}
      </span>
      <Heading id={id} className="min-w-0 font-display text-[34px] font-extrabold uppercase leading-none text-rc-ink">
        {title}
      </Heading>
      {aside != null && (
        <div className="ml-auto shrink-0">{typeof aside === "string" ? <p className={EYEBROW}>{aside}</p> : aside}</div>
      )}
    </div>
  );
}
