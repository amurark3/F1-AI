"use client";

import { DriverPicker, LapPicker } from "./AnalysisPickers";
import { defaultDriver } from "./trackMapSelection";
import { useLapList } from "./useAnalysisData";

export interface TrackMapControlsProps {
  year: number;
  round: number | null;
  session: string | null;
  driver: string | null;
  lap: number | null;
  onPick: (driver: string | null, lap: number | null) => void;
}

/** The speed map's driver and lap pickers, for the toolbar. Nothing until the session's laps are in. */
export function TrackMapControls({ year, round, session, driver, lap, onPick }: TrackMapControlsProps) {
  const drivers = useLapList(year, round, session).data?.drivers ?? [];
  if (drivers.length === 0) return null;
  const chosen = driver ?? defaultDriver(drivers);
  return (
    <>
      <DriverPicker
        label="Driver"
        drivers={drivers}
        value={chosen}
        onChange={(code) => {
          onPick(code, null);
        }}
      />
      <LapPicker
        driver={drivers.find((entry) => entry.code === chosen)}
        value={lap}
        onChange={(number) => {
          onPick(chosen, number);
        }}
      />
    </>
  );
}
