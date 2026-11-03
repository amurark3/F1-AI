"use client";

import { ChevronRight } from "lucide-react";

import type { ReactNode } from "react";

interface DisclosureProps {
  title: string;
  /** Short text on the right of the summary row, e.g. a count. */
  hint?: ReactNode;
  defaultOpen?: boolean;
  /** Fires on every open and close, so content can load only once opened. */
  onOpenChange?: (open: boolean) => void;
  children: ReactNode;
  className?: string;
}

/**
 * A collapsed section that opens in place.
 *
 * Built on `<details>`, so keyboard and screen-reader behaviour come from the
 * browser rather than being re-implemented, and it works before hydration.
 */
export function Disclosure({
  title,
  hint,
  defaultOpen = false,
  onOpenChange,
  children,
  className = "",
}: DisclosureProps) {
  return (
    <details
      open={defaultOpen}
      onToggle={(event) => onOpenChange?.(event.currentTarget.open)}
      className={`group min-w-0 overflow-hidden rounded-md border border-[#1E2633] bg-[#0D111B] ${className}`}
    >
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 bg-[#101520] px-4 py-2 focus-visible:-outline-offset-2 [&::-webkit-details-marker]:hidden">
        <span className="flex items-center gap-2 font-mono text-[11px] font-bold uppercase tracking-[0.28em] text-[#B7BDCA]">
          <ChevronRight className="h-3.5 w-3.5 transition-transform group-open:rotate-90" aria-hidden="true" />
          {title}
        </span>
        {hint && <span className="text-xs text-[#6F7789]">{hint}</span>}
      </summary>
      <div className="border-t border-[#1E2633] p-4">{children}</div>
    </details>
  );
}
