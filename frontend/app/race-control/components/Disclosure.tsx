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
      className={`group min-w-0 overflow-hidden rounded-md border border-rc-line bg-(--surface) ${className}`}
    >
      <summary className="flex min-h-11 cursor-pointer list-none items-center justify-between gap-3 px-5 py-2 focus-visible:-outline-offset-2 [&::-webkit-details-marker]:hidden">
        <span className="flex items-center gap-2 font-mono text-[11px] font-semibold uppercase tracking-[0.22em] text-rc-ink-2">
          <ChevronRight
            className="h-3.5 w-3.5 text-rc-ink-3 transition-transform group-open:rotate-90"
            aria-hidden="true"
          />
          {title}
        </span>
        {hint && <span className="text-xs text-rc-ink-3">{hint}</span>}
      </summary>
      <div className="border-t border-rc-line px-5 py-1">{children}</div>
    </details>
  );
}
