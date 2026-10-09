"use client";

import { Timer } from "lucide-react";
import { useMemo } from "react";

import { getTeamColor } from "@/app/lib/teamColors";

import { ConsoleHeader, ConsolePanel } from "./predictionConsole";
import {
  UNKNOWN_COMPOUND_COLOR,
  compoundColor,
  compoundInitial,
  compoundLabel,
  compoundTextColor,
  compoundsUsed,
} from "./tyreCompounds";

import type { DriverStint, DriverStrategy, RaceStrategyResponse } from "./strategyModel";

/** Below this share of race distance a bar has no room for its own label. */
const LABEL_MIN_SHARE = 0.07;

/**
 * How old the set was when it went on.
 *
 * "Not recorded" and "new" are different facts, and a chart that renders both
 * as zero laps claims the second when it only knows the first.
 */
function tyreAgeLabel(tyreLifeStart: number | null): string {
  if (tyreLifeStart === null) return "Tyre age not recorded";
  if (tyreLifeStart === 0) return "New set";
  return `Set had ${tyreLifeStart} lap(s) on it`;
}

/** One stint as a proportional segment of the race. */
function StintBar({ stint, share }: { stint: DriverStint; share: number }) {
  const color = compoundColor(stint.compound);
  const stop = stint.ended_by_stop;

  // A scrubbed set is the detail that usually explains a strategy, so it is
  // marked on the bar rather than hidden in a tooltip.
  const scrubbed = stint.fresh === false;
  const title = [
    `Stint ${stint.stint}: ${compoundLabel(stint.compound)}`,
    `Laps ${stint.start_lap}-${stint.end_lap} (${stint.laps})`,
    tyreAgeLabel(stint.tyre_life_start),
    stop ? `Stop ${stop.stop}: ${stop.time ?? "time not recorded"} on lap ${stop.lap}` : "Ran to the flag",
  ].join(" - ");

  return (
    <div
      className="relative flex h-7 w-full min-w-0 items-center justify-center overflow-hidden rounded-[2px]"
      style={{
        background: color,
        // A scrubbed set gets a hatch so it reads differently at a glance.
        backgroundImage: scrubbed
          ? "repeating-linear-gradient(45deg, rgba(0,0,0,0.28) 0 4px, transparent 4px 8px)"
          : undefined,
      }}
      title={title}
    >
      {share >= LABEL_MIN_SHARE && (
        <span
          className="font-mono text-[10px] font-black leading-none"
          style={{ color: compoundTextColor(stint.compound) }}
        >
          {compoundInitial(stint.compound)}
          <span className="ml-1 font-bold opacity-70">{stint.laps}</span>
        </span>
      )}
    </div>
  );
}

/**
 * A pit stop, drawn on the boundary between the stints it separates.
 *
 * With the pit-stop table removed this marker is the only place a stationary
 * time is surfaced, so it carries the full detail in its tooltip.
 */
function StopMarker({ stop }: { stop: NonNullable<DriverStint["ended_by_stop"]> }) {
  return (
    <span
      className="relative z-10 -mx-[3px] flex h-7 w-[6px] shrink-0 items-center justify-center bg-[#0D111B]"
      title={`Pit stop on lap ${stop.lap} - ${stop.time ?? "stationary time not published"} stationary`}
    >
      <span className="h-full w-[2px] bg-[#8E96A8]" />
    </span>
  );
}

/**
 * The boundary left by a red flag, which is not a pit stop.
 *
 * Drawn differently from a stop marker on purpose: the field changed tyres
 * because the race was suspended, not because anyone chose to box, and that is
 * why a driver can show two compounds beside a count of zero stops.
 */
function RedFlagMarker() {
  return (
    <span
      className="relative z-10 -mx-[3px] flex h-7 w-[6px] shrink-0 items-center justify-center bg-[#0D111B]"
      title="Tyres changed under a red flag - the race was suspended, so this is not counted as a pit stop"
    >
      <span className="h-full w-[2px] bg-[#E10600]" />
    </span>
  );
}

function DriverRow({ driver, raceLaps }: { driver: DriverStrategy; raceLaps: number }) {
  // From the backend, which counts stint boundaries rather than published stop
  // rows — a tyre change is a stop whether or not it was timed.
  const stops = driver.stops;

  return (
    <div className="flex items-center gap-3 px-4 py-1.5">
      {/* Rows are in finishing order, so the position is shown — otherwise the
          ordering looks arbitrary to anyone who does not know the result. */}
      <span className="flex w-24 shrink-0 items-center gap-2">
        <span className="w-7 shrink-0 text-right font-mono text-[11px] text-[#6F7789]">
          {driver.finish_position == null ? "-" : `P${driver.finish_position}`}
        </span>
        <span className="h-4 w-[3px] rounded-full" style={{ background: getTeamColor(driver.team) }} />
        <span className="font-mono text-xs font-black uppercase tracking-[0.06em] text-white">
          {driver.driver_code}
        </span>
      </span>
      <span className="flex min-w-0 flex-1 items-center">
        {driver.stints.map((stint) => {
          const share = stint.laps / raceLaps;
          return (
            <span key={stint.stint} className="flex min-w-0" style={{ width: `${share * 100}%` }}>
              <StintBar stint={stint} share={share} />
              {stint.ended_under_red_flag ? (
                <RedFlagMarker />
              ) : (
                stint.ended_by_stop && <StopMarker stop={stint.ended_by_stop} />
              )}
            </span>
          );
        })}
      </span>
      <span className="w-14 shrink-0 text-right font-mono text-[11px] text-[#7F8797]">
        {stops} stop{stops === 1 ? "" : "s"}
      </span>
    </div>
  );
}

function CompoundLegend({ compounds, anyUnknown }: { compounds: string[]; anyUnknown: boolean }) {
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t border-[#1E2633] px-4 py-3 font-mono text-[10px] uppercase tracking-[0.14em] text-[#7F8797]">
      {compounds.map((compound) => (
        <span key={compound} className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ background: compoundColor(compound) }} />
          {compoundLabel(compound)}
        </span>
      ))}
      {anyUnknown && (
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-sm" style={{ background: UNKNOWN_COMPOUND_COLOR }} />
          not recorded
        </span>
      )}
      <span className="inline-flex items-center gap-1.5">
        <span
          className="h-2.5 w-2.5 rounded-sm border border-[#4A5261]"
          style={{ backgroundImage: "repeating-linear-gradient(45deg, #8E96A8 0 2px, transparent 2px 4px)" }}
        />
        used set
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="h-3 w-[2px] bg-[#8E96A8]" />
        pit stop
      </span>
      <span className="inline-flex items-center gap-1.5">
        <span className="h-3 w-[2px] bg-[#E10600]" />
        red flag change
      </span>
    </div>
  );
}

/**
 * What the chart cannot say for itself.
 *
 * Chiefly why a driver can show two compounds beside "0 stops" — a red flag
 * changed the field's tyres for free — and whether the published stop sheet
 * timed every stop that was made.
 */
function ChartNotes({
  warnings,
  fastest,
}: {
  warnings?: string[];
  fastest?: RaceStrategyResponse["fastest_stop"];
}) {
  if (!warnings?.length && !fastest) return null;

  return (
    <div className="space-y-1.5 border-t border-[#1E2633] px-4 py-3 text-xs leading-relaxed text-[#596173]">
      {fastest && (
        <p>
          Fastest stop:{" "}
          <span className="font-mono font-bold text-[#00FF78]">{fastest.time}</span> by{" "}
          <span className="font-mono font-bold text-[#AEB5C5]">{fastest.driver_code}</span> on lap {fastest.lap}.
          Stationary time only — the lap-time cost of a stop is larger, and is not published.
        </p>
      )}
      {warnings?.map((warning) => <p key={warning}>{warning}</p>)}
    </div>
  );
}

/**
 * Every driver's race as a proportional tyre timeline.
 *
 * Bar width is share of that driver's own race distance, so a driver who
 * retired early shows a short row rather than a stretched one implying they
 * ran to the end.
 */
export function StintChart({ data }: { data?: RaceStrategyResponse }) {
  // A fresh `?? []` on every render would re-run every memo below it.
  const drivers = useMemo(() => data?.drivers ?? [], [data?.drivers]);

  const compounds = useMemo(
    () => compoundsUsed(drivers.flatMap((driver) => driver.stints.map((stint) => stint.compound))),
    [drivers],
  );
  const anyUnknown = useMemo(
    () => drivers.some((driver) => driver.stints.some((stint) => stint.compound === null)),
    [drivers],
  );
  // The full race distance, so a retirement's row is visibly short.
  const raceLaps = useMemo(
    () => Math.max(1, ...drivers.map((driver) => driver.total_laps)),
    [drivers],
  );

  return (
    <ConsolePanel>
      <ConsoleHeader
        label="Tyre stints"
        right={
          <span className="inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.18em] text-[#7F8797]">
            <Timer className="h-3.5 w-3.5 text-[#F5C542]" />
            {drivers.length ? `${raceLaps} laps / finishing order` : "no data"}
          </span>
        }
      />

      {drivers.length === 0 ? (
        <p className="p-4 text-sm leading-relaxed text-[#8E96A8]">
          {data?.warnings?.[0] ??
            "Tyre stint data appears here once the race has run and its timing data is available."}
        </p>
      ) : (
        <>
          <div className="py-2">
            {drivers.map((driver) => (
              <DriverRow key={driver.driver_code} driver={driver} raceLaps={raceLaps} />
            ))}
          </div>
          <CompoundLegend compounds={compounds} anyUnknown={anyUnknown} />
          <ChartNotes warnings={data?.warnings} fastest={data?.fastest_stop} />
        </>
      )}
    </ConsolePanel>
  );
}
