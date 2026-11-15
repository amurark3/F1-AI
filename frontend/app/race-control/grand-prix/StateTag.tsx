import type { ReactNode } from "react";

const TONES = {
  neutral: "border-rc-line text-rc-ink-3",
  red: "border-rc-red-text text-rc-red-text",
  blue: "border-rc-blue text-rc-blue",
  gain: "border-rc-gain text-rc-gain",
} as const;

export type StateTone = keyof typeof TONES;

/**
 * A special state in the hub's one vocabulary (`DSQ`, `Pit lane`, `Up 1 · LAW DSQ`):
 * mono caps in an outlined box, so the state reads in text and shape, not colour alone.
 */
export function StateTag({ children, tone = "neutral" }: { children: ReactNode; tone?: StateTone }) {
  return (
    <span
      className={`inline-block rounded-sm border px-1.5 py-1 font-mono text-[10px] font-medium uppercase leading-none tracking-[0.1em] ${TONES[tone]}`}
    >
      {children}
    </span>
  );
}

/** Final is a quiet caption; provisional is info blue (the shared rule for the section title's tag). */
export function FinalTag({ final }: { final: boolean }) {
  return <StateTag tone={final ? "neutral" : "blue"}>{final ? "Final" : "Provisional"}</StateTag>;
}
