"use client";

import { Timer, X } from "lucide-react";
import { useMemo } from "react";

import { getTeamColor } from "@/app/lib/teamColors";

import { ConsoleHeader, ConsolePanel } from "./predictionConsole";
import { finalStintLabel, resultCode, stintEndingLabel, stopTimeLabel } from "./strategyModel";
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

/** A chequered square: the first fill of each 25% turn alternates light and dark. */
const CHEQUER = "repeating-conic-gradient(var(--foreground) 0 25%, var(--surface) 0 50%)";

/** One stint as a proportional segment of the race. */
function StintBar({ stint, share, ending }: { stint: DriverStint; share: number; ending: string }) {
  const color = compoundColor(stint.compound);

  // A scrubbed set is the detail that usually explains a strategy, so it is
  // marked on the bar rather than hidden in a tooltip.
  const scrubbed = stint.fresh === false;
  const title = [
    `Stint ${stint.stint}: ${compoundLabel(stint.compound)}`,
    `Laps ${stint.start_lap}-${stint.end_lap} (${stint.laps})`,
    tyreAgeLabel(stint.tyre_life_start),
    ending,
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
 * With the pit-stop table removed this marker is the only place a stop's
 * time is surfaced, so it carries the full detail in its tooltip.
 */
function StopMarker({ stop }: { stop: NonNullable<DriverStint["ended_by_stop"]> }) {
  return (
    <span
      className="relative z-10 -mx-[3px] flex h-7 w-[6px] shrink-0 items-center justify-center bg-[#0D111B]"
      title={`Pit stop on lap ${stop.lap} - ${stopTimeLabel(stop)}`}
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

/**
 * How the race ended, drawn where the driver's last stint stops.
 *
 * Only what the classification says is drawn: a chequered square for the flag,
 * a cross for a retirement. Anything else (not started, disqualified, or no
 * result yet) is left unmarked and named in the row's tooltip.
 */
function FinishMarker({ driver }: { driver: DriverStrategy }) {
  const label = finalStintLabel(driver);
  if (driver.status === "finished") {
    return (
      <span className="relative z-10 -ml-[5px] flex h-7 w-[14px] shrink-0 items-center justify-center" title={label}>
        <span className="h-2.5 w-2.5 rounded-[1px]" style={{ backgroundImage: CHEQUER, backgroundSize: "5px 5px" }} />
      </span>
    );
  }
  if (driver.status === "dnf") {
    return (
      <span className="relative z-10 -ml-[5px] flex h-7 w-[14px] shrink-0 items-center justify-center" title={label}>
        <X className="h-3.5 w-3.5 text-f1-red" strokeWidth={3} aria-label={label} />
      </span>
    );
  }
  return null;
}

/** The stint bars, or for a car with no stint data, what the result says about it. */
function StintTrack({ driver, raceLaps }: { driver: DriverStrategy; raceLaps: number }) {
  if (driver.stints.length === 0) {
    return (
      <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-[#6F7789]">
        {driver.status === "dns" ? "Did not start" : "No stint data published"}
      </span>
    );
  }
  const lastIndex = driver.stints.length - 1;
  return (
    <>
      {driver.stints.map((stint, index) => {
        const share = stint.laps / raceLaps;
        const isLast = index === lastIndex;
        return (
          <span key={stint.stint} className="flex min-w-0" style={{ width: `${share * 100}%` }}>
            <StintBar stint={stint} share={share} ending={stintEndingLabel(stint, driver, isLast)} />
            {!isLast &&
              (stint.ended_under_red_flag ? (
                <RedFlagMarker />
              ) : (
                stint.ended_by_stop && <StopMarker stop={stint.ended_by_stop} />
              ))}
          </span>
        );
      })}
      <FinishMarker driver={driver} />
    </>
  );
}

function DriverRow({ driver, raceLaps }: { driver: DriverStrategy; raceLaps: number }) {
  // From the backend, which counts stint boundaries rather than published stop
  // rows — a tyre change is a stop whether or not it was timed.
  const stops = driver.stops;

  return (
    <div className="flex items-center gap-3 px-4 py-1.5" title={`${driver.driver_code}: ${finalStintLabel(driver)}`}>
      {/* Rows are in classification order, so the result is shown — otherwise
          the ordering looks arbitrary to anyone who does not know it. */}
      <span className="flex w-24 shrink-0 items-center gap-2">
        <span className="w-7 shrink-0 text-right font-mono text-[11px] text-[#6F7789]">{resultCode(driver)}</span>
        <span className="h-4 w-[3px] rounded-full" style={{ background: getTeamColor(driver.team) }} />
        <span className="font-mono text-xs font-black uppercase tracking-[0.06em] text-white">
          {driver.driver_code}
        </span>
      </span>
      <span className="flex min-w-0 flex-1 items-center">
        <StintTrack driver={driver} raceLaps={raceLaps} />
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
      <span className="inline-flex items-center gap-1.5">
        <span className="h-2.5 w-2.5 rounded-[1px]" style={{ backgroundImage: CHEQUER, backgroundSize: "5px 5px" }} />
        took the flag
      </span>
      <span className="inline-flex items-center gap-1.5">
        <X className="h-3 w-3 text-f1-red" strokeWidth={3} aria-hidden />
        retired
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
function ChartNotes({ warnings, fastest }: { warnings?: string[]; fastest?: RaceStrategyResponse["fastest_stop"] }) {
  if (!warnings?.length && !fastest) return null;

  return (
    <div className="space-y-1.5 border-t border-[#1E2633] px-4 py-3 text-xs leading-relaxed text-[#596173]">
      {fastest && (
        <p>
          Quickest stop: <span className="font-mono font-bold text-white">{stopTimeLabel(fastest)}</span> by{" "}
          <span className="font-mono font-bold text-[#AEB5C5]">{fastest.driver_code}</span> on lap {fastest.lap}.
          Pit-lane time runs from pit entry to pit exit; the car stands still for only part of it.
        </p>
      )}
      {warnings?.map((warning) => (
        <p key={warning}>{warning}</p>
      ))}
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
  const raceLaps = useMemo(() => Math.max(1, ...drivers.map((driver) => driver.total_laps)), [drivers]);

  return (
    <ConsolePanel>
      <ConsoleHeader
        label="Tyre stints"
        right={
          <span className="inline-flex items-center gap-2 font-mono text-[10px] uppercase tracking-[0.18em] text-[#7F8797]">
            <Timer className="h-3.5 w-3.5 text-[#F5C542]" />
            {drivers.length
              ? `${raceLaps} laps / ${data?.classification_source ? "classified" : "finishing"} order`
              : "no data"}
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
