"use client";

import { DriverPicker, SegmentPicker } from "./AnalysisPickers";
import { rankedDrivers, resolvePair } from "./headToHeadModel";
import { resolveSegment } from "./qualifyingSegments";
import { useLapList } from "./useAnalysisData";

export interface HeadToHeadControlsProps {
  year: number;
  round: number | null;
  session: string | null;
  a: string | null;
  b: string | null;
  segment: number | null;
  onPick: (a: string | null, b: string | null) => void;
  onSegment: (segment: number) => void;
}

/** The qualifying part and the two driver pickers, for the toolbar. Nothing until two drivers have a valid lap. */
export function HeadToHeadControls({
  year,
  round,
  session,
  a,
  b,
  segment,
  onPick,
  onSegment,
}: HeadToHeadControlsProps) {
  const list = useLapList(year, round, session).data;
  const drivers = rankedDrivers(list?.drivers);
  if (drivers.length < 2) return null;
  const choice = resolveSegment(list, [a, b], segment);
  const { first, second } = resolvePair(drivers, a, b, choice?.segment ?? null);
  return (
    <>
      <SegmentPicker choice={choice} notice={list?.segments?.notice} onChange={onSegment} />
      <DriverPicker
        label="Driver A"
        drivers={drivers}
        value={first}
        segments={choice}
        onChange={(code) => {
          onPick(code, second === code ? first : second);
        }}
      />
      <DriverPicker
        label="Driver B"
        drivers={drivers}
        value={second}
        segments={choice}
        onChange={(code) => {
          onPick(first === code ? second : first, code);
        }}
      />
      <span className="font-mono text-[11px] text-rc-ink-3">
        {choice
          ? `Each driver's fastest valid lap in ${choice.labels[choice.segment - 1]}`
          : "Each driver's fastest valid lap"}
      </span>
    </>
  );
}
