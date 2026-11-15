"use client";

import { LocalCountdown, LocalTime } from "@/app/components/LocalTime";

import { InlineNotice } from "../components/RaceControlPrimitives";

import { raceSessionTime } from "./predictionHelpers";

import type { RaceEvent } from "./predictionModel";

const STATUS_LABELS: Record<string, string> = {
  completed: "Completed",
  upcoming: "Upcoming",
  in_progress: "Race weekend",
  live: "Live",
};

/**
 * The event this screen is reporting on, in one line. The race picker above
 * is the one control that changes it; the countdown shows only while there is
 * still a race to count down to.
 */
export function RaceHeader({
  selectedRound,
  selectedRace,
  raceName,
}: {
  selectedRound: number | null;
  selectedRace: RaceEvent | null;
  raceName: string;
}) {
  const raceTime = raceSessionTime(selectedRace);
  const status = selectedRace?.status ?? "";

  return (
    <div className="flex flex-col gap-3 border-b border-rc-line pb-4 lg:flex-row lg:items-end lg:justify-between">
      <div>
        <h1 className="font-display text-3xl font-extrabold uppercase leading-tight text-rc-ink sm:text-4xl">
          {raceName}
        </h1>
        <p className="mt-2 flex flex-wrap gap-x-2 gap-y-1 font-mono text-xs text-rc-ink-2">
          <span>{selectedRace?.circuit?.circuit_name ?? selectedRace?.location ?? "Circuit TBC"}</span>
          <span aria-hidden="true">·</span>
          <span>Round {selectedRound ?? "-"}</span>
          <span aria-hidden="true">·</span>
          <span>
            Race <LocalTime value={raceTime} style="day" fallback="date TBC" />{" "}
            <LocalTime value={raceTime} style="time" fallback="time TBC" />
          </span>
          <span aria-hidden="true">·</span>
          <b className="text-rc-ink">{STATUS_LABELS[status] ?? (status || "Status unknown")}</b>
        </p>
      </div>
      {status !== "completed" && <LocalCountdown value={raceTime} />}
    </div>
  );
}

export function HubAlerts({
  scheduleError,
  driversError,
  onReloadSchedule,
  onReloadDrivers,
}: {
  scheduleError: boolean;
  driversError: boolean;
  onReloadSchedule: () => void;
  onReloadDrivers: () => void;
}) {
  return (
    <>
      {scheduleError && (
        <InlineNotice title="Race calendar unavailable" tone="error">
          The race list could not be loaded.
          <button onClick={onReloadSchedule} className="ml-2 font-bold text-white underline decoration-white/30">
            Retry
          </button>
        </InlineNotice>
      )}
      {driversError && (
        <InlineNotice title="Driver standings unavailable" tone="warning">
          Driver-name lookups may be limited.
          <button onClick={onReloadDrivers} className="ml-2 font-bold text-white underline decoration-white/30">
            Retry
          </button>
        </InlineNotice>
      )}
    </>
  );
}
