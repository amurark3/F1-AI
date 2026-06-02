"use client";

import type { LucideIcon } from "lucide-react";

interface HeaderMetric {
  label: string;
  value: string;
  icon: LucideIcon;
  tone?: "red" | "green" | "blue" | "purple" | "orange";
}

interface OperationalHeaderProps {
  eyebrow: string;
  title: string;
  description: string;
  metrics?: HeaderMetric[];
}

const TONE_COLORS = {
  red: "#E10600",
  green: "#00FF78",
  blue: "#3671C6",
  purple: "#BE3AFF",
  orange: "#FF8000",
};

const F1 = { fontFamily: "var(--font-barlow, var(--font-geist-sans))" };

export default function OperationalHeader({
  eyebrow,
  title,
  description,
  metrics = [],
}: OperationalHeaderProps) {
  return (
    <header className="mb-5 sm:mb-6">
      <div className="flex flex-col lg:flex-row lg:items-end justify-between gap-5">
        <div className="max-w-3xl">
          <div
            className="inline-flex items-center gap-2 px-3 py-1 rounded border border-white/10 text-[10px] font-black uppercase tracking-[0.2em] text-neutral-400 mb-4"
            style={F1}
          >
            <span className="h-[6px] w-[6px] rounded-full" style={{ background: "#E10600" }} />
            {eyebrow}
          </div>
          <h1 className="text-3xl sm:text-5xl font-black italic uppercase tracking-tight text-white leading-none" style={F1}>
            {title}
          </h1>
          <p className="text-sm text-neutral-500 mt-3 leading-relaxed">
            {description}
          </p>
        </div>

        {metrics.length > 0 && (
          <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-none lg:auto-cols-[minmax(108px,1fr)] lg:grid-flow-col gap-2 w-full lg:w-auto">
            {metrics.map(({ label, value, icon: Icon, tone = "red" }) => {
              const color = TONE_COLORS[tone];
              return (
                <div key={label} className="glass rounded-xl px-3 py-3 min-w-0">
                  <Icon className="h-4 w-4 mb-2" style={{ color }} />
                  <p className="text-[9px] font-black uppercase tracking-[0.16em] text-neutral-600 truncate">
                    {label}
                  </p>
                  <p className="text-xs sm:text-sm font-black uppercase text-white truncate" style={F1}>
                    {value}
                  </p>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </header>
  );
}
