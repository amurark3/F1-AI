"use client";

import type { LucideIcon } from "lucide-react";

export const rcFont = { fontFamily: "var(--font-geist-sans, Arial, Helvetica, sans-serif)" };

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
    <div className="mb-7 border-b border-white/10 pb-6">
      <p className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-[#00FF78]" style={rcFont}>
        {eyebrow}
      </p>
      <h1 className="text-3xl font-semibold leading-tight text-white sm:text-4xl" style={rcFont}>
        {title}
      </h1>
      {description && <p className="mt-3 max-w-5xl text-base leading-relaxed text-neutral-300">{description}</p>}
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
    <div className={`w-full min-w-0 rounded-lg border border-white/12 bg-[#101211] overflow-hidden ${className}`}>
      {accent && <div data-panel-accent className="mb-5 h-[3px]" style={{ background: accent }} />}
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
    <div className={`mb-7 flex w-full min-w-0 flex-col gap-4 sm:flex-row sm:flex-wrap [&>*]:min-w-[220px] [&>*]:flex-1 ${className}`}>
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
    <Panel className={`flex min-h-[124px] min-w-0 flex-1 flex-col p-5 ${className}`}>
      <Icon className="h-5 w-5 mb-3" style={{ color }} />
      <p className="mb-1 text-xs font-semibold uppercase tracking-[0.12em] text-neutral-400" style={rcFont}>
        {label}
      </p>
      <p className="break-words text-xl font-semibold leading-tight text-white" style={rcFont}>
        {value}
      </p>
      {sub && <p className="text-sm text-neutral-400 leading-snug mt-1">{sub}</p>}
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
      className="inline-flex items-center rounded px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider border"
      style={{ color, borderColor: `${color}55`, background: `${color}14`, ...rcFont }}
    >
      {children}
    </span>
  );
}

export function SkeletonPanel({ className = "h-32" }: { className?: string }) {
  return <div className={`w-full min-w-0 rounded-lg border border-white/10 bg-white/[0.04] animate-pulse ${className}`} />;
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
    <div className={`rounded-lg border px-4 py-3 ${styles}`}>
      <p className="text-sm font-semibold" style={rcFont}>{title}</p>
      <div className="mt-1 text-sm leading-relaxed text-neutral-200">{children}</div>
    </div>
  );
}
