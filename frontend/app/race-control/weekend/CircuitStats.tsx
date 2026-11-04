"use client";

import { Flag, Gauge, Milestone, RotateCcw, RotateCw, Route, Timer, Trophy, Waypoints } from "lucide-react";

import { AnimatedNumber } from "@/app/ui/AnimatedNumber";
import { driverLabel } from "@/app/ui/names/names";

import type { CircuitRecord, LapRecord } from "./weekendTypes";
import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

/** What the shell already knows about the circuit, used where f1db has no record. */
export interface CircuitBasics {
  track_length_km?: number | null;
  laps?: number | null;
  first_gp?: number | null;
}

interface Stat {
  key: string;
  label: string;
  icon: LucideIcon;
  value: ReactNode;
  detail?: string;
  /** A worded value, set smaller than the numbers so it fits its cell. */
  worded?: boolean;
}

interface NumberStat {
  key: string;
  label: string;
  icon: LucideIcon;
  value: number | null | undefined;
  unit?: string;
  decimals?: number;
  /** A year reads oddly counting up from zero, so it is shown as is. */
  still?: boolean;
}

function numberStat({ key, label, icon, value, unit = "", decimals = 0, still = false }: NumberStat): Stat | null {
  if (value === null || value === undefined) return null;
  return {
    key,
    label,
    icon,
    value: (
      <>
        {still ? value : <AnimatedNumber value={value} decimals={decimals} />}
        {unit && <span className="ml-0.5 text-xs text-[#8E96A8]">{unit}</span>}
      </>
    ),
  };
}

function directionStat(direction: CircuitRecord["direction"] | undefined): Stat | null {
  if (!direction) return null;
  const anti = direction === "anti-clockwise";
  const Icon = anti ? RotateCcw : RotateCw;
  return {
    key: "direction",
    label: "Direction",
    icon: Icon,
    value: anti ? "Anti-clockwise" : "Clockwise",
    worded: true,
  };
}

function lapRecordStat(lapRecord: LapRecord | null | undefined): Stat | null {
  if (!lapRecord) return null;
  return {
    key: "lap-record",
    label: "Lap record",
    icon: Timer,
    value: lapRecord.time,
    detail: `${driverLabel({ name: lapRecord.driver, lastName: lapRecord.last_name }, "last")} · ${lapRecord.year}`,
  };
}

function stats(record: CircuitRecord | null, lapRecord: LapRecord | null, basics: CircuitBasics): Stat[] {
  const candidates: Array<Stat | null> = [
    numberStat({
      key: "length",
      label: "Length",
      icon: Route,
      value: record?.length_km ?? basics.track_length_km,
      unit: "km",
      decimals: 3,
    }),
    numberStat({ key: "turns", label: "Turns", icon: Waypoints, value: record?.turns }),
    numberStat({ key: "laps", label: "Laps", icon: Flag, value: record?.laps ?? basics.laps }),
    numberStat({
      key: "distance",
      label: "Distance",
      icon: Milestone,
      value: record?.distance_km,
      unit: "km",
      decimals: 1,
    }),
    directionStat(record?.direction),
    lapRecordStat(lapRecord),
    numberStat({
      key: "first",
      label: "First GP",
      icon: Gauge,
      value: record?.first_year ?? basics.first_gp,
      still: true,
    }),
    numberStat({ key: "held", label: "GPs held here", icon: Trophy, value: record?.races_held }),
  ];
  return candidates.filter((stat): stat is Stat => stat !== null);
}

interface CircuitStatsProps {
  record: CircuitRecord | null;
  lapRecord: LapRecord | null;
  basics: CircuitBasics;
}

export function CircuitStats({ record, lapRecord, basics }: CircuitStatsProps) {
  const cells = stats(record, lapRecord, basics);
  if (cells.length === 0) return null;
  return (
    <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-lg border border-white/10 bg-white/10 sm:grid-cols-4 xl:grid-cols-8">
      {cells.map(({ key, label, icon: Icon, value, detail, worded }, index) => (
        <div
          key={key}
          className="min-w-0 bg-[#0B0F18] px-3 py-3 motion-safe:animate-fade-up"
          style={{ animationDelay: `${0.2 + index * 0.06}s` }}
        >
          <dt className="flex items-center gap-1.5 font-mono text-[9px] font-bold uppercase tracking-[0.16em] text-[#7F8797]">
            <Icon
              className={`h-3 w-3 shrink-0 text-[#E10600] ${key === "direction" ? "motion-safe:animate-wx-spin" : ""}`}
              style={
                key === "direction" && record?.direction === "anti-clockwise"
                  ? { animationDirection: "reverse" }
                  : undefined
              }
              aria-hidden="true"
            />
            {label}
          </dt>
          <dd
            className={`mt-1 truncate font-black text-white ${worded ? "pt-1 font-sans text-sm" : "font-mono text-lg"}`}
          >
            {value}
          </dd>
          {detail && <dd className="truncate text-[11px] text-[#7F8797]">{detail}</dd>}
        </div>
      ))}
    </dl>
  );
}
