"use client";

import { AnimatedNumber } from "@/app/ui/AnimatedNumber";
import { driverLabel } from "@/app/ui/names/names";

import type { CircuitRecord, LapRecord } from "./weekendTypes";
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
  value: ReactNode;
  detail?: string;
  /** A worded value, set smaller than the numbers so it fits its cell. */
  worded?: boolean;
}

interface NumberStat {
  key: string;
  label: string;
  value: number | null | undefined;
  unit?: string;
  decimals?: number;
  /** A year reads oddly counting up from zero, so it is shown as is. */
  still?: boolean;
}

function numberStat({ key, label, value, unit = "", decimals = 0, still = false }: NumberStat): Stat | null {
  if (value === null || value === undefined) return null;
  return {
    key,
    label,
    value: (
      <>
        {still ? value : <AnimatedNumber value={value} decimals={decimals} />}
        {unit && <span className="ml-[0.15em] text-[0.45em] font-bold tracking-[0.04em] text-rc-ink-3">{unit}</span>}
      </>
    ),
  };
}

function directionStat(direction: CircuitRecord["direction"] | undefined): Stat | null {
  if (!direction) return null;
  const anti = direction === "anti-clockwise";
  return {
    key: "direction",
    label: "Direction",
    value: anti ? "Anti-clockwise" : "Clockwise",
    worded: true,
  };
}

function lapRecordStat(lapRecord: LapRecord | null | undefined): Stat | null {
  if (!lapRecord) return null;
  return {
    key: "lap-record",
    label: "Lap record",
    value: lapRecord.time,
    detail: `${driverLabel({ name: lapRecord.driver, lastName: lapRecord.last_name }, "last")} · ${lapRecord.year}`,
  };
}

function stats(record: CircuitRecord | null, lapRecord: LapRecord | null, basics: CircuitBasics): Stat[] {
  const candidates: Array<Stat | null> = [
    numberStat({
      key: "length",
      label: "Length",
      value: record?.length_km ?? basics.track_length_km,
      unit: "km",
      decimals: 3,
    }),
    numberStat({ key: "turns", label: "Turns", value: record?.turns }),
    numberStat({ key: "laps", label: "Laps", value: record?.laps ?? basics.laps }),
    numberStat({
      key: "distance",
      label: "Distance",
      value: record?.distance_km,
      unit: "km",
      decimals: 1,
    }),
    directionStat(record?.direction),
    lapRecordStat(lapRecord),
    numberStat({
      key: "first",
      label: "First GP",
      value: record?.first_year ?? basics.first_gp,
      still: true,
    }),
    numberStat({ key: "held", label: "GPs held here", value: record?.races_held }),
  ];
  return candidates.filter((stat): stat is Stat => stat !== null);
}

interface CircuitStatsProps {
  record: CircuitRecord | null;
  lapRecord: LapRecord | null;
  basics: CircuitBasics;
  className?: string;
}

export function CircuitStats({ record, lapRecord, basics, className = "" }: CircuitStatsProps) {
  const cells = stats(record, lapRecord, basics);
  if (cells.length === 0) return null;
  return (
    <dl className={`grid grid-cols-2 border-y border-rc-line sm:grid-cols-4 xl:grid-cols-8 ${className}`}>
      {cells.map(({ key, label, value, detail, worded }, index) => (
        <div
          key={key}
          className="min-w-0 py-4 pr-4 motion-safe:animate-fade-up xl:[&+&]:border-l xl:[&+&]:border-rc-line xl:[&+&]:pl-4"
          style={{ animationDelay: `${0.2 + index * 0.06}s` }}
        >
          <dt className="font-mono text-[10px] font-semibold uppercase tracking-[0.16em] text-rc-ink-3">{label}</dt>
          <dd
            className={`mt-2.5 whitespace-nowrap font-display font-extrabold leading-none text-rc-ink ${worded ? "pt-1.5 text-[20px] uppercase" : "text-[30px]"}`}
          >
            {value}
          </dd>
          {detail && <dd className="mt-1 truncate text-xs text-rc-ink-3">{detail}</dd>}
        </div>
      ))}
    </dl>
  );
}
