"use client";

import { DriverPicker, LapPicker, SegmentPicker } from "./AnalysisPickers";
import { resolveSegment } from "./qualifyingSegments";
import { defaultDriver } from "./trackMapSelection";
import { useLapList } from "./useAnalysisData";

export interface TrackMapControlsProps {
  year: number;
  round: number | null;
  session: string | null;
  driver: string | null;
  lap: number | null;
  segment: number | null;
  onPick: (driver: string | null, lap: number | null) => void;
  onSegment: (segment: number) => void;
}

/** The speed map's qualifying part, driver and lap pickers, for the toolbar. Nothing until the session's laps are in. */
export function TrackMapControls({
  year,
  round,
  session,
  driver,
  lap,
  segment,
  onPick,
  onSegment,
}: TrackMapControlsProps) {
  const list = useLapList(year, round, session).data;
  const drivers = list?.drivers ?? [];
  if (drivers.length === 0) return null;
  const choice = resolveSegment(list, [driver], segment);
  const chosen = driver ?? defaultDriver(drivers, choice?.segment ?? null);
  return (
    <>
      <SegmentPicker choice={choice} notice={list?.segments?.notice} onChange={onSegment} />
      <DriverPicker
        label="Driver"
        drivers={drivers}
        value={chosen}
        segments={choice}
        onChange={(code) => {
          onPick(code, null);
        }}
      />
      <LapPicker
        driver={drivers.find((entry) => entry.code === chosen)}
        value={lap}
        segments={choice}
        onChange={(number) => {
          onPick(chosen, number);
        }}
      />
    </>
  );
}
