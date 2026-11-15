"use client";

import { teamLabel } from "@/app/ui/names/names";
import { Segmented } from "@/app/ui/Segmented";

import { groupDrivers, groupLaps, noTimeReason, segmentBest, type SegmentChoice } from "./qualifyingSegments";
import { formatLapTime } from "./telemetryModel";

import type { LapListDriver, TimedLap } from "./telemetryModel";

const LABEL = "font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-rc-ink-3";
const SELECT = "min-w-0 rounded border border-rc-line bg-rc-hero px-2 py-1.5 font-mono text-xs text-rc-ink";

/** What a driver's option says: their best in the part (or session), or why there is none. */
function timeText(driver: LapListDriver, choice: SegmentChoice | null): string {
  const best = segmentBest(driver, choice?.segment ?? null);
  if (best !== null) return formatLapTime(best);
  return choice === null ? "no valid lap" : noTimeReason(driver, choice);
}

/** Q1 · Q2 · Q3 (SQ1-SQ3), or the backend's notice when the parts are not published. */
export function SegmentPicker({
  choice,
  notice,
  onChange,
}: {
  choice: SegmentChoice | null;
  notice: string | null | undefined;
  onChange: (segment: number) => void;
}) {
  if (choice === null) return notice ? <p className="font-mono text-xs text-rc-ink-3">{notice}</p> : null;
  return (
    <Segmented
      label="Qualifying part"
      value={String(choice.segment)}
      onChange={(value) => {
        onChange(Number(value));
      }}
      options={choice.labels.map((label, index) => ({ value: String(index + 1), label }))}
    />
  );
}

export function DriverPicker({
  label,
  drivers,
  value,
  onChange,
  segments = null,
}: {
  label: string;
  drivers: LapListDriver[];
  value: string | null;
  onChange: (code: string) => void;
  /** The qualifying part on show; groups the drivers by how far they got. */
  segments?: SegmentChoice | null;
}) {
  return (
    <label className="flex min-w-0 items-center gap-2">
      <span className={LABEL}>{label}</span>
      <select
        className={SELECT}
        value={value ?? ""}
        onChange={(event) => {
          onChange(event.target.value);
        }}
      >
        {value === null && <option value="">Choose a driver</option>}
        {groupDrivers(drivers, segments).map((group) => {
          const options = group.drivers.map((driver) => (
            <option key={driver.code} value={driver.code}>
              {driver.code} · {teamLabel({ name: driver.team }, "name")} · {timeText(driver, segments)}
              {driver.note ? ` · ${driver.note}` : ""}
            </option>
          ));
          return group.heading === null ? (
            options
          ) : (
            <optgroup key={group.key} label={group.heading}>
              {options}
            </optgroup>
          );
        })}
      </select>
    </label>
  );
}

/** A driver's timed laps; empty value means their fastest valid lap. */
export function LapPicker({
  driver,
  value,
  onChange,
  segments = null,
}: {
  driver: LapListDriver | undefined;
  value: number | null;
  onChange: (lap: number | null) => void;
  /** The qualifying part on show; groups the laps under Q1 / Q2 / Q3. */
  segments?: SegmentChoice | null;
}) {
  if (!driver) return null;
  return (
    <label className="flex min-w-0 items-center gap-2">
      <span className={LABEL}>Lap</span>
      <select
        className={SELECT}
        value={value ?? ""}
        onChange={(event) => {
          onChange(event.target.value === "" ? null : Number(event.target.value));
        }}
      >
        <option value="">
          {segments ? `${segments.labels[segments.segment - 1]} · fastest valid lap` : "Fastest valid lap"}
        </option>
        {groupLaps(driver.laps, segments?.labels ?? null).map((group) => {
          const options = group.laps.map((lap) => <LapOption key={lap.number} lap={lap} />);
          return group.heading === null ? (
            options
          ) : (
            <optgroup key={group.heading} label={group.heading}>
              {options}
            </optgroup>
          );
        })}
      </select>
    </label>
  );
}

function LapOption({ lap }: { lap: TimedLap }) {
  return (
    <option value={lap.number}>
      Lap {lap.number} · {formatLapTime(lap.time)}
      {lap.deleted ? " · deleted" : ""}
      {lap.is_fastest ? " · fastest" : ""}
    </option>
  );
}
