"use client";

import { getTeamColor } from "@/app/lib/teamColors";
import { useSeasonDirectory } from "@/app/race-control/profiles/EntityLinks";
import { DriverName } from "@/app/ui/names/DriverName";
import { PageHero } from "@/app/ui/PageHero";

import { StateTag } from "../grand-prix/StateTag";

import { debriefHeadline, debriefMeta, podiumOf, startPhrase } from "./debriefModel";

import type { DebriefRow, DebriefSummary } from "./debriefTypes";

/** Step heights and entrance delays by finishing place, as in the mockup. */
const STEPS = {
  1: { height: 160, delay: "0.35s", tone: "text-rc-gold" },
  2: { height: 120, delay: "0.15s", tone: "text-rc-silver" },
  3: { height: 92, delay: "0s", tone: "text-rc-bronze" },
} as const;

function figure(row: DebriefRow, position: 1 | 2 | 3): string {
  const result = position === 1 ? row.time : row.gap;
  const start = startPhrase(row);
  return [result, start ? `from ${start}` : null].filter(Boolean).join(" · ");
}

function Step({ row, position }: { row: DebriefRow; position: 1 | 2 | 3 }) {
  const step = STEPS[position];
  return (
    <div className="min-w-0 flex-1 text-center">
      <p className="font-display text-[26px] font-extrabold leading-none text-rc-ink">{row.driver_code}</p>
      <p className="mb-0.5 mt-1 text-xs text-rc-ink-2">
        <DriverName name={row.driver_name} code={row.driver_code} />
      </p>
      <p className="mb-2.5 font-mono text-[11px] font-medium leading-none text-rc-ink-3">{figure(row, position)}</p>
      <div
        data-step={position}
        className="grid origin-bottom place-items-start justify-center rounded-t border-x border-t-[3px] border-rc-line bg-white/[0.03] pt-2.5 motion-safe:animate-rise-y"
        style={{ height: step.height, borderTopColor: getTeamColor(row.team), animationDelay: step.delay }}
      >
        <span className={`font-display text-[34px] font-extrabold leading-none ${step.tone}`}>{position}</span>
      </div>
    </div>
  );
}

function Podium({ summary }: { summary: DebriefSummary }) {
  const [first, second, third] = podiumOf(summary);
  if (!first) return null;
  return (
    <div aria-label="Podium" role="group" className="flex items-end gap-2 border-b border-rc-line">
      {second && <Step row={second} position={2} />}
      <Step row={first} position={1} />
      {third && <Step row={third} position={3} />}
    </div>
  );
}

/** The race's headline, the one line of how it was won, and the podium. */
export function DebriefHero({ summary }: { summary: DebriefSummary }) {
  const directory = useSeasonDirectory();
  return (
    <PageHero
      eyebrow={
        <span className="inline-flex flex-wrap items-center gap-3">
          {`Race debrief · Round ${summary.round} · ${summary.race}`}
          {!summary.final && summary.available && <StateTag tone="blue">Provisional</StateTag>}
        </span>
      }
      title={debriefHeadline(summary, directory)}
      meta={debriefMeta(summary)}
      aside={summary.available ? <Podium summary={summary} /> : undefined}
    />
  );
}
