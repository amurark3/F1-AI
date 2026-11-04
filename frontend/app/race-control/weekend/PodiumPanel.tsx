"use client";

import { ArrowRight, Trophy } from "lucide-react";
import Link from "next/link";

import { getTeamColor } from "@/app/lib/teamColors";
import { AnimatedNumber } from "@/app/ui/AnimatedNumber";
import { DriverName } from "@/app/ui/names/DriverName";
import { TeamName } from "@/app/ui/names/TeamName";

import { Panel, rcFont } from "../components/RaceControlPrimitives";
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
  const color = getTeamColor(pick.team);
  const confidence = Math.round((pick.confidence_low + pick.confidence_high) / 2);
  return (
    <div className="flex min-w-0 flex-1 flex-col items-center justify-end">
      <div
        className="mb-2 w-full min-w-0 text-center motion-safe:animate-fade-up"
        style={{ animationDelay: `${rise + 0.5}s` }}
      >
        <p className="font-mono text-xl font-black text-white">{pick.driver_code}</p>
        <p className="truncate text-[11px] text-[#AEB6C6]">
          <DriverLink code={pick.driver_code} name={pick.driver_name}>
            <DriverName name={pick.driver_name} code={pick.driver_code} />
          </DriverLink>
        </p>
        <p className="truncate text-[10px] text-[#6F7789]">
          <TeamLink name={pick.team}>
            <TeamName name={pick.team} />
          </TeamLink>
        </p>
      </div>
      <div
        className={`relative w-full origin-bottom overflow-hidden rounded-t-md border-x border-t motion-safe:animate-rise-y ${height}`}
        style={{
          borderColor: `${color}88`,
          background: `linear-gradient(180deg, ${color}55 0%, ${color}14 70%, transparent 100%)`,
          animationDelay: `${rise}s`,
        }}
      >
        <div className="absolute inset-x-0 top-0 h-[3px]" style={{ background: color }} />
        <p className="mt-2 text-center font-mono text-3xl font-black text-white/90">{place}</p>
        <p className="text-center font-mono text-[10px] text-[#B7BDCA]">
          <AnimatedNumber value={confidence} />% conf.
        </p>
      </div>
    </div>
  );
}

export function PodiumPanel({ podium }: { podium: PodiumPick[] }) {
  const ready = podium.length >= 3;
  return (
    <Panel className="flex h-full flex-col p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#7F8797]" style={rcFont}>
            Prediction snapshot
          </p>
          <h2 className="mt-1 text-xl font-semibold text-white" style={rcFont}>
            Projected podium
          </h2>
        </div>
        <Trophy className="h-5 w-5 text-[#FFC93C]" aria-hidden="true" />
      </div>

      {ready ? (
        <div className="flex flex-1 items-end gap-2 border-b border-white/10">
          {/* `ready` means three picks, so every step has one. */}
          {STEPS.map(({ place, height, rise }) => (
            <Step key={place} pick={podium[place - 1]} place={place} height={height} rise={rise} />
          ))}
        </div>
      ) : (
        <p className="flex-1 text-sm text-[#7F8797]">
          The podium appears once the race model has inputs for this weekend.
        </p>
      )}

      <Link
        href="/race-control/grand-prix"
        className="mt-4 inline-flex w-full items-center justify-center gap-2 rounded-lg border border-[#00FF78]/35 bg-[#00FF78]/10 px-4 py-2.5 text-xs font-semibold uppercase tracking-wider text-[#00FF78] transition-colors hover:bg-[#00FF78] hover:text-black"
      >
        Full predicted order
        <ArrowRight className="h-4 w-4" aria-hidden="true" />
      </Link>
    </Panel>
  );
}
