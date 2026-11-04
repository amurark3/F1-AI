"use client";

import { teamLabel } from "@/app/ui/names/names";

import { rcFont } from "../components/RaceControlPrimitives";

import { formatLapTime } from "./telemetryModel";

import type { LapListDriver, WeekendSession } from "./telemetryModel";

const LABEL = "font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-[#7F8797]";
const SELECT = "min-w-0 rounded border border-[#1E2633] bg-[#0A0E16] px-2 py-1.5 font-mono text-xs text-white";

export function YearPicker({
  years,
  value,
  onChange,
}: {
  years: number[];
  value: number;
  onChange: (year: number) => void;
}) {
  return (
    <label className="flex items-center gap-2">
      <span className={LABEL}>Season</span>
      <select
        className={SELECT}
        value={value}
        onChange={(event) => {
          onChange(Number(event.target.value));
        }}
      >
        {years.map((year) => (
          <option key={year} value={year}>
            {year}
          </option>
        ))}
      </select>
    </label>
  );
}

/** One button per session the round runs; sessions not yet started are disabled. */
export function SessionPicker({
  sessions,
  value,
  allowed,
  onChange,
}: {
  sessions: WeekendSession[];
  value: string | null;
  allowed: (code: string) => boolean;
  onChange: (code: string) => void;
}) {
  const offered = sessions.filter((session) => allowed(session.code));
  if (offered.length === 0) {
    return <p className="font-mono text-xs text-[#6F7789]">No session of this kind on this weekend.</p>;
  }
  return (
    <div className="flex flex-wrap items-center gap-1.5" role="group" aria-label="Session">
      <span className={`${LABEL} mr-1`}>Session</span>
      {offered.map((session) => {
        const selected = session.code === value;
        return (
          <button
            key={session.code}
            type="button"
            disabled={!session.started}
            aria-pressed={selected}
            title={session.started ? session.name : `${session.name} has not started yet`}
            onClick={() => {
              onChange(session.code);
            }}
            className={`rounded border px-2.5 py-1 font-mono text-xs font-bold transition-colors disabled:cursor-not-allowed disabled:opacity-35 ${
              selected
                ? "border-[#3987E5] bg-[#3987E5]/15 text-white"
                : "border-[#1E2633] text-[#A8AFBF] hover:bg-white/[0.04]"
            }`}
            style={rcFont}
          >
            {session.name}
          </button>
        );
      })}
    </div>
  );
}

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
