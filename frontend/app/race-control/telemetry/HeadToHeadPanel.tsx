"use client";

import { useMemo } from "react";

import { AnalysisGate, AnalysisWarnings, ModeledNote } from "./AnalysisNotice";
import { LapCard, MiniSectorCard } from "./HeadToHeadCards";
import { pairColours, rankedDrivers, resolvePair, traceRows } from "./headToHeadModel";
import { resolveSegment } from "./qualifyingSegments";
import { TelemetryTraces } from "./TelemetryTraces";
import { useComparison, useLapList } from "./useAnalysisData";

import type { ComparisonResponse } from "./telemetryModel";

export interface HeadToHeadPanelProps {
  year: number;
  round: number | null;
  session: string | null;
  a: string | null;
  b: string | null;
  segment: number | null;
}

function Comparison({ data, part }: { data: ComparisonResponse; part?: string }) {
  const codes = { a: data.a?.driver.code ?? "A", b: data.b?.driver.code ?? "B" };
  const colours = pairColours(data);
  const rows = useMemo(() => traceRows(data.trace, data.gap), [data.trace, data.gap]);
  return (
    <div className="space-y-4">
      <div className="grid gap-5 lg:grid-cols-2">
        <LapCard data={data} colours={colours} codes={codes} part={part} />
        <MiniSectorCard data={data} colours={colours} codes={codes} />
        <TelemetryTraces rows={rows} colours={colours} codes={codes} />
      </div>
      <AnalysisWarnings warnings={data.warnings} />
      <ModeledNote
        modeled={data.modeled}
        extra="Both laps are put on one distance axis; the gap at the line equals the official lap-time difference."
      />
    </div>
  );
}

/** The comparison cards. The driver pickers live in the toolbar (`HeadToHeadControls`). */
export function HeadToHeadPanel({ year, round, session, a, b, segment }: HeadToHeadPanelProps) {
  const laps = useLapList(year, round, session);
  const choice = resolveSegment(laps.data, [a, b], segment);
  const { first, second } = resolvePair(rankedDrivers(laps.data?.drivers), a, b, choice?.segment ?? null);
  const comparison = useComparison(year, round, {
    session: laps.data ? session : null,
    a: first,
    b: second,
    segment: choice?.segment ?? null,
  });

  return (
    <div className="space-y-4">
      <AnalysisGate state={laps} loadingTitle="Loading the session's laps" />
      <AnalysisGate state={comparison} loadingTitle="Comparing the two laps" />
      {comparison.data?.available && <Comparison data={comparison.data} part={choice?.labels[choice.segment - 1]} />}
    </div>
  );
}
