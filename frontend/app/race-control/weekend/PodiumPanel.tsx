"use client";

import Link from "next/link";

import { getTeamColor } from "@/app/lib/teamColors";
import { AnimatedNumber } from "@/app/ui/AnimatedNumber";
import { DriverName } from "@/app/ui/names/DriverName";
import { TeamName } from "@/app/ui/names/TeamName";
import { PanelHeading } from "@/app/ui/PanelHeading";

import { Panel } from "../components/RaceControlPrimitives";
import { DriverLink, TeamLink } from "../profiles/EntityLinks";

export interface PodiumPick {
  driver_code: string;
  driver_name: string;
  team: string;
  confidence_low: number;
  confidence_high: number;
}

/** Drawn P2 · P1 · P3, with each step's height and the order the steps rise in. */
const STEPS = [
  { place: 2, height: "h-36", rise: 0.15 },
  { place: 1, height: "h-48", rise: 0.35 },
  { place: 3, height: "h-28", rise: 0 },
];

function Step({ pick, place, height, rise }: { pick: PodiumPick; place: number; height: string; rise: number }) {
  const confidence = Math.round((pick.confidence_low + pick.confidence_high) / 2);
  return (
    <div className="flex min-w-0 flex-1 flex-col items-center justify-end">
      <div
        className="mb-2 w-full min-w-0 text-center motion-safe:animate-fade-up"
        style={{ animationDelay: `${rise + 0.5}s` }}
      >
        <p className="font-display text-[28px] font-extrabold uppercase leading-none text-rc-ink">{pick.driver_code}</p>
        <p className="mt-1 truncate text-xs text-rc-ink-2">
          <DriverLink code={pick.driver_code} name={pick.driver_name}>
            <DriverName variant="last" name={pick.driver_name} code={pick.driver_code} />
          </DriverLink>
        </p>
        <p className="truncate text-[11px] text-rc-ink-3">
          <TeamLink name={pick.team}>
            <TeamName name={pick.team} />
          </TeamLink>
        </p>
      </div>
      <div
        className={`relative w-full origin-bottom rounded-t border-x border-t-[3px] border-rc-line bg-white/[0.03] pt-2.5 text-center motion-safe:animate-rise-y ${height}`}
        style={{ borderTopColor: getTeamColor(pick.team), animationDelay: `${rise}s` }}
      >
        <p className="font-display text-[44px] font-extrabold leading-none text-rc-ink">{place}</p>
        <p className="font-mono text-[10px] text-rc-ink-3">
          <AnimatedNumber value={confidence} />% conf.
        </p>
      </div>
    </div>
  );
}

export function PodiumPanel({ podium }: { podium: PodiumPick[] }) {
  const ready = podium.length >= 3;
  return (
    <Panel className="flex h-full flex-col p-5 sm:p-6">
      <PanelHeading as="h2" eyebrow="Prediction snapshot" title="Projected podium" />

      {ready ? (
        <div className="flex flex-1 items-end gap-2 border-b border-rc-line">
          {/* `ready` means three picks, so every step has one. */}
          {STEPS.map(({ place, height, rise }) => (
            <Step key={place} pick={podium[place - 1]} place={place} height={height} rise={rise} />
          ))}
        </div>
      ) : (
        <p className="flex-1 text-sm text-rc-ink-3">
          The podium appears once the race model has inputs for this weekend.
        </p>
      )}

      <Link
        href="/race-control/grand-prix?tab=predictions&view=order#predictions"
        className="mt-5 inline-block font-mono text-xs font-semibold uppercase tracking-[0.14em] text-rc-ink hover:underline"
      >
        Full predicted order →
      </Link>
    </Panel>
  );
}
