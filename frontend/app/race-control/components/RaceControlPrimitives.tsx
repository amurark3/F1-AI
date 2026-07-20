"use client";

import type { LucideIcon } from "lucide-react";

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
}: {
  children: React.ReactNode;
  className?: string;
  accent?: string;
}) {
  return (
    <div className={`w-full min-w-0 overflow-hidden rounded-md border border-[#1E2633] bg-[#0D111B] ${className}`}>
      {accent && <div data-panel-accent className="h-[2px]" style={{ background: accent }} />}
      {children}
    </div>
  );
}

export function PageStack({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={`flex w-full min-w-0 flex-col gap-5 ${className}`}>{children}</div>;
}

export function MetricRow({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`mb-5 grid w-full min-w-0 gap-3 sm:grid-cols-2 xl:grid-cols-4 ${className}`}>
      {children}
    </div>
  );
}

export function WorkspaceSplit({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`${className} flex w-full min-w-0 flex-col gap-5 [&>*]:min-w-0 [&>*]:basis-auto`}>
      {children}
    </div>
  );
}

export function WrapRow({
  children,
  className = "",
}: {
  children: React.ReactNode;
  className?: string;
}) {
  return <div className={`flex w-full min-w-0 flex-wrap gap-3 ${className}`}>{children}</div>;
}

export function MetricCard({
  label,
  value,
  sub,
  icon: Icon,
  color = "#00FF78",
  className = "",
}: {
  label: string;
  value: string;
  sub?: string;
  icon: LucideIcon;
  color?: string;
  className?: string;
}) {
  return (
    <Panel className={`flex min-h-[96px] min-w-0 flex-col justify-between p-4 ${className}`}>
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="truncate text-[10px] font-bold uppercase tracking-[0.22em] text-[#7F8797]" style={rcMono}>
          {label}
        </p>
        <Icon className="h-4 w-4 shrink-0" style={{ color }} />
      </div>
      <p className="break-words font-mono text-2xl font-black leading-tight text-white">
        {value}
      </p>
      {sub && <p className="mt-1 line-clamp-2 text-xs leading-snug text-[#6F7789]">{sub}</p>}
    </Panel>
  );
}

export function StatusPill({
  children,
  color = "#00FF78",
}: {
  children: React.ReactNode;
  color?: string;
}) {
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
  return <div className={`w-full min-w-0 animate-pulse rounded-md border border-[#1E2633] bg-[#101520] ${className}`} />;
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
            <div className="mb-3 h-3 w-44 rounded-full bg-[#00FF78]/30 animate-pulse" />
            <p className="text-2xl font-semibold text-white" style={rcFont}>{title}</p>
            <p className="mt-2 max-w-2xl text-base leading-relaxed text-neutral-400">{detail}</p>
          </div>
          <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-lg border border-[#00FF78]/25 bg-[#00FF78]/10">
            <div className="h-5 w-5 rounded-full border-2 border-[#00FF78]/30 border-t-[#00FF78] animate-spin" />
          </div>
        </div>
      </Panel>

      <div className="flex w-full min-w-0 flex-col gap-4 sm:flex-row sm:flex-wrap [&>*]:min-w-[220px] [&>*]:flex-1">
        {Array.from({ length: 4 }).map((_, index) => <SkeletonPanel key={index} className="h-28" />)}
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
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-[#00FF78]/25 bg-[#00FF78]/10">
            <div className="h-4 w-4 rounded-full border-2 border-[#00FF78]/30 border-t-[#00FF78] animate-spin" />
          </div>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-white" style={rcFont}>{title}</p>
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
  children: React.ReactNode;
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
