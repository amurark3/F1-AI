"use client";

import { teamLabel } from "@/app/ui/names/names";

import { formatLapTime } from "./telemetryModel";

import type { LapListDriver } from "./telemetryModel";

const LABEL = "font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-[#7F8797]";
const SELECT = "min-w-0 rounded border border-[#1E2633] bg-[#0A0E16] px-2 py-1.5 font-mono text-xs text-white";

export function DriverPicker({
  label,
  drivers,
  value,
  onChange,
}: {
  label: string;
  drivers: LapListDriver[];
  value: string | null;
  onChange: (code: string) => void;
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
        {drivers.map((driver) => (
          <option key={driver.code} value={driver.code}>
            {driver.code} · {teamLabel({ name: driver.team }, "name")} ·{" "}
            {driver.best === null ? "no valid lap" : formatLapTime(driver.best)}
          </option>
        ))}
      </select>
    </label>
  );
}

/** A driver's timed laps; empty value means their fastest valid lap. */
export function LapPicker({
  driver,
  value,
  onChange,
}: {
  driver: LapListDriver | undefined;
  value: number | null;
  onChange: (lap: number | null) => void;
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
        <option value="">Fastest valid lap</option>
        {driver.laps.map((lap) => (
          <option key={lap.number} value={lap.number}>
            Lap {lap.number} · {formatLapTime(lap.time)}
            {lap.deleted ? " · deleted" : ""}
            {lap.is_fastest ? " · fastest" : ""}
          </option>
        ))}
      </select>
    </label>
  );
}
