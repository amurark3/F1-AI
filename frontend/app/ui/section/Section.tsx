"use client";

import type { SectionState } from "./sectionState";
import type { ReactNode } from "react";

/** Mono caps at the size of the mockups' notes, as `SourceBadge` sets them. */
const MARK = "font-mono text-[10px] font-medium uppercase leading-none tracking-[0.1em]";

/**
 * The `EYEBROW` recipe (`typography.ts`) with line spacing: a long label
 * ("Prediction snapshot unavailable") wraps in a narrow column.
 */
const FAILURE_TITLE = "font-mono text-[11px] font-semibold uppercase leading-snug tracking-[0.22em] text-rc-ink-3";

interface RetryButtonProps {
  state: SectionState;
  /** A bordered button, for a notice that stands on its own; quiet text otherwise. */
  framed?: boolean;
  className?: string;
}

/**
 * Fetches a section again. Says "Retrying…" while any fetch for it is out,
 * so a press visibly does something before the answer lands.
 */
export function RetryButton({ state, framed = false, className = "" }: RetryButtonProps) {
  // The quiet variant pads its hit area without moving the line it sits on.
  const look = framed
    ? "rounded-sm border border-rc-line px-3 py-2 text-[11px] font-semibold tracking-[0.14em] text-rc-ink hover:border-rc-ink-3"
    : "-my-1.5 py-1.5 text-rc-ink-2 underline decoration-rc-dim underline-offset-2 hover:text-rc-ink";
  return (
    <button type="button" onClick={state.retry} className={`${MARK} ${look} ${className}`}>
      {state.refreshing ? "Retrying…" : "Retry"}
    </button>
  );
}

/**
 * The small "couldn't refresh · retry" mark that sits with data a refresh
 * failed to update. The data stays; the mark says it may be behind.
 */
export function StaleMark({ state, className = "" }: { state: SectionState; className?: string }) {
  return (
    <p className={`flex items-center gap-1.5 text-rc-ink-3 motion-safe:animate-fade-up ${MARK} ${className}`}>
      <span title={state.reason ?? undefined}>Couldn&apos;t refresh</span>
      <span aria-hidden="true">·</span>
      <RetryButton state={state} />
    </p>
  );
}

/** Where a section with no data says why, with a way to try again. */
function SectionFailure({ state, label }: { state: SectionState; label: string }) {
  return (
    <div className="rounded-md border border-l-2 border-rc-line border-l-f1-red bg-(--surface) p-5 motion-safe:animate-fade-up">
      <p className={FAILURE_TITLE}>{label} unavailable</p>
      <p className="mt-3 text-sm leading-relaxed text-rc-ink-2">{state.reason}</p>
      <RetryButton state={state} framed className="mt-4" />
    </div>
  );
}

/** What a screen reader hears when the section's state changes; nothing while it is fine. */
function announcement({ status, reason }: SectionState, label: string): string {
  const why = reason ? ` ${reason}` : "";
  if (status === "stale") return `${label} couldn't refresh. Showing the last data received.${why}`;
  if (status === "failed") return `${label} unavailable.${why}`;
  return "";
}

function SectionBody({ state, label, skeletonClassName = "h-32", children }: SectionProps) {
  if (state.status === "pending") {
    return (
      <div
        className={`w-full rounded-md border border-rc-line bg-(--surface-raised) motion-safe:animate-pulse ${skeletonClassName}`}
      />
    );
  }
  if (state.status === "failed") return <SectionFailure state={state} label={label} />;
  return (
    <>
      <div className="min-h-0 flex-1">{children}</div>
      {state.status === "stale" && <StaleMark state={state} className="mt-2 shrink-0 justify-end" />}
    </>
  );
}

interface SectionProps {
  /** From `useSection`. */
  state: SectionState;
  /** What the section shows, for its notices: "Weather feed" reads "Weather feed unavailable". */
  label: string;
  /** The skeleton's size while pending, near the content's, e.g. `h-[420px]`. */
  skeletonClassName?: string;
  /**
   * The frame's own classes. It is a column, so content that fills its
   * parent (`h-full`) still does when the frame is stretched (a grid cell,
   * a flex item) or given `h-full` itself.
   */
  className?: string;
  children: ReactNode;
}

/**
 * One data section of a page in its four states (see `SectionStatus`): a
 * skeleton while pending; its content when ready; its content and a stale
 * mark when a refresh failed; and the reason, with a retry, when it has no
 * data at all. "Unavailable" never covers data.
 *
 * Changes of state are announced politely from a live region that is always
 * present, so a screen reader hears a failure without losing its place.
 */
export function Section(props: SectionProps) {
  const { state, label, className = "" } = props;
  return (
    <div className={`relative flex min-w-0 flex-col ${className}`} aria-busy={state.status === "pending"}>
      <SectionBody {...props} />
      <p role="status" className="sr-only">
        {announcement(state, label)}
      </p>
    </div>
  );
}
