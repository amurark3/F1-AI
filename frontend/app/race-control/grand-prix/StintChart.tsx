"use client";

import { X } from "lucide-react";
import { useMemo } from "react";

import { getTeamColor } from "@/app/lib/teamColors";
import { Legend, type LegendItem } from "@/app/ui/Legend";
import { PanelHeading } from "@/app/ui/PanelHeading";
import { f1, rc } from "@/app/ui/tokens";

import { Panel } from "../components/RaceControlPrimitives";

import { StintOverlay } from "./StintOverlay";
import {
  finalStintLabel,
  redFlagLap,
  resultCode,
  retirementTag,
  stintEndingLabel,
  stopTimeLabel,
} from "./strategyModel";
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
      className="relative z-10 -mx-[3px] flex h-7 w-[6px] shrink-0 items-center justify-center bg-(--surface)"
      title={`Pit stop on lap ${stop.lap} - ${stopTimeLabel(stop)}`}
    >
      <span className="h-full w-[2px] bg-rc-ink-2" />
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
      className="relative z-10 -mx-[3px] flex h-7 w-[6px] shrink-0 items-center justify-center bg-(--surface)"
      title="Tyres changed under a red flag - the race was suspended, so this is not counted as a pit stop"
    >
      <span className="h-full w-[2px] bg-f1-red" />
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
      <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-rc-ink-3">
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
  const retired = retirementTag(driver);

  return (
    <div className="flex items-center gap-3 px-4 py-1.5" title={`${driver.driver_code}: ${finalStintLabel(driver)}`}>
      {/* Rows are in classification order, so the result is shown — otherwise
          the ordering looks arbitrary to anyone who does not know it. */}
      <span className="flex w-24 shrink-0 items-center gap-2">
        <span
          className={`w-8 shrink-0 text-right font-mono text-[11px] font-semibold ${retired ? "text-rc-red-text" : "text-rc-ink-3"}`}
        >
          {resultCode(driver)}
        </span>
        <span className="h-4 w-[3px] rounded-full" style={{ background: getTeamColor(driver.team) }} />
        <span className="font-mono text-xs font-black uppercase tracking-[0.06em] text-rc-ink">
          {driver.driver_code}
        </span>
      </span>
      <span className="flex min-w-0 flex-1 items-center">
        <StintTrack driver={driver} raceLaps={raceLaps} />
      </span>
      <span className="hidden w-24 shrink-0 text-right font-mono text-[11px] leading-tight text-rc-ink-3 sm:block">
        {stops} stop{stops === 1 ? "" : "s"}
        {retired && <span className="block text-rc-red-text">{retired}</span>}
      </span>
    </div>
  );
}

const MARK_NOTE = "inline-flex items-center gap-[7px]";

function ChartLegend({ compounds, anyUnknown }: { compounds: string[]; anyUnknown: boolean }) {
  const items: LegendItem[] = [
    ...compounds.map((compound) => ({ label: compoundLabel(compound), color: compoundColor(compound) })),
    ...(anyUnknown ? [{ label: "Not recorded", color: UNKNOWN_COMPOUND_COLOR }] : []),
    { label: "Pit stop", color: rc.ink2, mark: "rule" as const },
    { label: "Red flag change", color: f1.red, mark: "rule" as const },
  ];
  return (
    <div className="flex flex-wrap items-center gap-x-[18px] gap-y-2 border-t border-rc-line px-4 py-3">
      <Legend items={items} label="Tyre compounds and marks" />
      <ul
        aria-label="Stint marks"
        className="flex flex-wrap gap-x-[18px] gap-y-2 font-mono text-[11px] font-medium leading-none text-rc-ink-3"
      >
        <li className={MARK_NOTE}>
          <span
            aria-hidden="true"
            className="size-3 rounded-[2px] border border-rc-dim"
            style={{ backgroundImage: "repeating-linear-gradient(45deg, var(--rc-ink-2) 0 2px, transparent 2px 4px)" }}
          />
          Used set
        </li>
        <li className={MARK_NOTE}>
          <span
            aria-hidden="true"
            className="size-3 rounded-[1px]"
            style={{ backgroundImage: CHEQUER, backgroundSize: "5px 5px" }}
          />
          Took the flag
        </li>
        <li className={MARK_NOTE}>
          <X className="size-3 text-f1-red" strokeWidth={3} aria-hidden />
          Retired
        </li>
      </ul>
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
    <div className="space-y-1.5 border-t border-rc-line px-4 py-3 text-xs leading-relaxed text-rc-ink-3">
      {fastest && (
        <p>
          Quickest stop: <span className="font-mono font-bold text-rc-ink">{stopTimeLabel(fastest)}</span> by{" "}
          <span className="font-mono font-bold text-rc-ink-2">{fastest.driver_code}</span> on lap {fastest.lap}.
          Pit-lane time runs from pit entry to pit exit; the car stands still for only part of it.
        </p>
      )}
      {warnings?.map((warning) => (
        <p key={warning}>{warning}</p>
      ))}
    </div>
  );
}

/** The chart's finding, computed from the race: the red flag's free tyre change, else the stops made. */
function chartTitle(data: RaceStrategyResponse, raceLaps: number): string {
  const redLap = redFlagLap(data.neutralisations);
  const changed = data.drivers.filter((driver) => driver.red_flag_changes > 0).length;
  if (redLap !== null && changed > 0) {
    return `The red flag on lap ${redLap} gave ${changed} drivers a free tyre change`;
  }
  return `${data.stops_made} pit stops by ${data.drivers.length} cars over ${raceLaps} laps`;
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

  if (!data || drivers.length === 0) {
    return (
      <Panel as="section">
        <PanelHeading eyebrow="Tyre strategy" inset />
        <p className="p-4 text-sm leading-relaxed text-rc-ink-2">
          {data?.warnings?.[0] ??
            "Tyre stint data appears here once the race has run and its timing data is available."}
        </p>
      </Panel>
    );
  }

  return (
    <Panel as="section">
      <PanelHeading
        eyebrow="Tyre strategy"
        title={chartTitle(data, raceLaps)}
        sub={`${data.classification_source ? "Ordered by the classification" : "Ordered by finishing order"} · ${raceLaps} laps · bars end where each car's race ended`}
        inset
      />
      <div className="relative mt-10 py-2">
        <StintOverlay neutralisations={data.neutralisations} raceLaps={raceLaps} />
        {drivers.map((driver) => (
          <DriverRow key={driver.driver_code} driver={driver} raceLaps={raceLaps} />
        ))}
      </div>
      <ChartLegend compounds={compounds} anyUnknown={anyUnknown} />
      <ChartNotes warnings={data.warnings} fastest={data.fastest_stop} />
    </Panel>
  );
}
