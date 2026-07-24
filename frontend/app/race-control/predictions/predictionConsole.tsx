import type { ReactNode } from "react";

export function ConsolePanel({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <section className={`min-w-0 overflow-hidden rounded-md border border-[#1E2633] bg-[#0D111B] ${className}`}>
      {children}
    </section>
  );
}

export function ConsoleHeader({ label, right }: { label: string; right?: ReactNode }) {
  return (
    <div className="flex min-h-10 items-center justify-between gap-3 border-b border-[#1E2633] bg-[#101520] px-4 py-2">
      <p className="font-mono text-[11px] font-bold uppercase tracking-[0.28em] text-[#7F8797]">{label}</p>
      {right}
    </div>
  );
}

export function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 py-3">
      <dt className="text-[#6F7789]">{label}</dt>
      <dd className="truncate text-right font-bold text-white">{value}</dd>
    </div>
  );
}

export function StatBlock({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div>
      <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-[#6F7789]">{label}</p>
      <p className="mt-1 font-mono text-3xl font-black text-white">{value}</p>
      <p className="mt-1 text-xs text-[#6F7789]">{detail}</p>
    </div>
  );
}
