/**
 * Shared presentational primitives for the Race Control surfaces.
 *
 * Intentionally *not* a client module: every export here is a pure function of
 * its props with no state, effects, or event handlers. Keeping the boundary off
 * lets server components render panels, metrics, and loaders into the initial
 * HTML — these are imported by almost every page, so a stray `"use client"`
 * here would pull all of them into the browser bundle for no benefit.
 */
import { StatTile, StatTiles } from "@/app/ui/StatTile";
import { rc } from "@/app/ui/tokens";

import type { ReactNode } from "react";

export const rcFont = { fontFamily: "var(--font-geist-sans, Arial, Helvetica, sans-serif)" };
const rcMono = { fontFamily: "var(--font-geist-mono, var(--font-geist-sans, monospace))" };

export function SectionHeader({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string;
  title: string;
  description?: string;
}) {
  return (
    <div className="mb-5 border-b border-[#1E2633] pb-4">
      <p className="mb-2 text-[11px] font-bold uppercase tracking-[0.24em] text-[#7F8797]" style={rcMono}>
        {eyebrow}
      </p>
      <h1 className="text-2xl font-black leading-tight text-white sm:text-3xl" style={rcFont}>
        {title}
      </h1>
      {description && <p className="mt-2 max-w-5xl text-sm leading-relaxed text-[#8E96A8]">{description}</p>}
    </div>
  );
}

export function Panel({
  children,
  className = "",
  accent,
  as: Tag = "div",
}: {
  children: ReactNode;
  className?: string;
  accent?: string;
  /** `section` when the panel is a region of the page with its own heading. */
  as?: "div" | "section";
}) {
  return (
    <Tag className={`w-full min-w-0 overflow-hidden rounded-md border border-rc-line bg-(--surface) ${className}`}>
      {accent && <div data-panel-accent className="h-[2px]" style={{ background: accent }} />}
      {children}
    </Tag>
  );
}

export function PageStack({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`flex w-full min-w-0 flex-col gap-5 ${className}`}>{children}</div>;
}

/** A row of {@link MetricCard}s: the kit's `StatTiles`, between two hairlines. */
export function MetricRow({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <StatTiles className={`mb-5 ${className}`}>{children}</StatTiles>;
}

export function WorkspaceSplit({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <div className={`${className} flex w-full min-w-0 flex-col gap-5 [&>*]:min-w-0 [&>*]:basis-auto`}>{children}</div>
  );
}

export function WrapRow({ children, className = "" }: { children: ReactNode; className?: string }) {
  return <div className={`flex w-full min-w-0 flex-wrap gap-3 ${className}`}>{children}</div>;
}

/**
 * One headline figure, drawn by the kit's `StatTile`: an eyebrow label, the
 * figure in display type and a caption. Neutral ink only; a figure's colour
 * would have to carry a meaning, and an icon adds none.
 */
export function MetricCard({
  label,
  value,
  sub,
  className = "",
}: {
  label: string;
  value: string;
  sub?: string;
  className?: string;
}) {
  return <StatTile label={label} value={value} sub={sub} className={className} />;
}

/**
 * A small status label. `color` must be a six-digit hex that carries the
 * status's meaning; without one the pill is neutral, never DRS green.
 */
export function StatusPill({ children, color = rc.ink2 }: { children: ReactNode; color?: string }) {
  return (
    <span
      className="inline-flex items-center rounded border px-2 py-1 text-[10px] font-bold uppercase tracking-[0.16em]"
      style={{ color, borderColor: `${color}55`, background: `${color}14`, ...rcMono }}
    >
      {children}
    </span>
  );
}

export function SkeletonPanel({ className = "h-32" }: { className?: string }) {
  return (
    <div
      className={`w-full min-w-0 rounded-md border border-rc-line bg-(--surface-raised) motion-safe:animate-pulse ${className}`}
    />
  );
}

/** The loading ring: a fill-red arc on a faint red track. Still under reduced motion. */
function Spinner({ className }: { className: string }) {
  return (
    <div
      data-spinner
      className={`rounded-full border-2 border-f1-red/30 border-t-f1-red motion-safe:animate-spin ${className}`}
    />
  );
}

export function PageLoader({
  title = "Preparing Race Control",
  detail = "Loading the baseline data for this workspace.",
}: {
  title?: string;
  detail?: string;
}) {
  return (
    <div className="w-full min-w-0 space-y-6" role="status" aria-live="polite">
      <Panel className="p-5">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div className="min-w-0">
            <div className="mb-3 h-3 w-44 rounded-full bg-f1-red/30 motion-safe:animate-pulse" />
            <p className="text-2xl font-semibold text-white" style={rcFont}>
              {title}
            </p>
            <p className="mt-2 max-w-2xl text-base leading-relaxed text-neutral-400">{detail}</p>
          </div>
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg border border-f1-red/25 bg-f1-red/10">
            <Spinner className="h-5 w-5" />
          </div>
        </div>
      </Panel>

      <div className="flex w-full min-w-0 flex-col gap-4 sm:flex-row sm:flex-wrap [&>*]:min-w-[220px] [&>*]:flex-1">
        {Array.from({ length: 4 }).map((_, index) => (
          <SkeletonPanel key={index} className="h-28" />
        ))}
      </div>

      <WorkspaceSplit>
        <SkeletonPanel className="h-80" />
        <SkeletonPanel className="h-80" />
      </WorkspaceSplit>
    </div>
  );
}

export function SectionLoader({
  title = "Refreshing section",
  detail = "Updating this panel from the latest available data.",
  className = "",
}: {
  title?: string;
  detail?: string;
  className?: string;
}) {
  return (
    <div className={`w-full min-w-0 space-y-5 ${className}`} role="status" aria-live="polite">
      <Panel className="p-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-f1-red/25 bg-f1-red/10">
            <Spinner className="h-4 w-4" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-white" style={rcFont}>
              {title}
            </p>
            <p className="mt-1 text-sm leading-relaxed text-neutral-400">{detail}</p>
          </div>
        </div>
      </Panel>
      <div className="flex w-full min-w-0 flex-col gap-4 [&>*]:min-w-0 [&>*]:flex-1">
        <SkeletonPanel className="h-72" />
        <SkeletonPanel className="h-72" />
      </div>
    </div>
  );
}

export function InlineNotice({
  title,
  children,
  tone = "info",
}: {
  title: string;
  children: ReactNode;
  tone?: "info" | "warning" | "error";
}) {
  const styles = {
    info: "border-[#3671C6]/35 bg-[#3671C6]/10 text-[#9EC5FF]",
    warning: "border-[#FFF200]/30 bg-[#FFF200]/10 text-[#FFF6A3]",
    error: "border-[#E10600]/35 bg-[#E10600]/10 text-[#FFB4B1]",
  }[tone];

  return (
    <div className={`rounded-md border px-4 py-3 ${styles}`}>
      <p className="font-mono text-[11px] font-bold uppercase tracking-[0.18em]">{title}</p>
      <div className="mt-1 text-sm leading-relaxed text-neutral-200">{children}</div>
    </div>
  );
}

/** One label and value in a `<dl>`, label left and value right. */
export function InfoRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-3">
      <dt className="text-[#6F7789]">{label}</dt>
      <dd className="truncate text-right font-bold text-white">{value}</dd>
    </div>
  );
}
