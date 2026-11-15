"use client";

import { DriverPicker } from "./AnalysisPickers";
import { rankedDrivers, resolvePair } from "./headToHeadModel";
import { useLapList } from "./useAnalysisData";

export interface HeadToHeadControlsProps {
  year: number;
  round: number | null;
  session: string | null;
  a: string | null;
  b: string | null;
  onPick: (a: string | null, b: string | null) => void;
}

/** The two driver pickers, for the toolbar. Nothing until two drivers have a valid lap. */
export function HeadToHeadControls({ year, round, session, a, b, onPick }: HeadToHeadControlsProps) {
  const drivers = rankedDrivers(useLapList(year, round, session).data?.drivers);
  if (drivers.length < 2) return null;
  const { first, second } = resolvePair(drivers, a, b);
  return (
    <>
      <DriverPicker
        label="Driver A"
        drivers={drivers}
        value={first}
        onChange={(code) => {
          onPick(code, second === code ? first : second);
        }}
      />
      <DriverPicker
        label="Driver B"
        drivers={drivers}
        value={second}
        onChange={(code) => {
          onPick(first === code ? second : first, code);
        }}
      />
      <span className="font-mono text-[11px] text-rc-ink-3">Each driver&apos;s fastest valid lap</span>
    </>
  );
}
