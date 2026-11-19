"use client";

import { useState } from "react";

import { API_BASE } from "@/app/constants/api";
import { PanelHeading } from "@/app/ui/PanelHeading";
import { Section } from "@/app/ui/section/Section";
import { useSection } from "@/app/ui/section/useSection";
import { Segmented } from "@/app/ui/Segmented";

import { Panel } from "../components/RaceControlPrimitives";

import {
  provenanceNote,
  resultsTitle,
  type RaceResultsResponse,
  type ResultsKind,
  type SessionResult,
} from "./resultsModel";
import { ChangedAfterFlagPanel, DebriefLinkPanel, FastestLapPanel } from "./ResultsSidePanels";
import { ResultsTable } from "./ResultsTable";

const KINDS = [
  { value: "sprint", label: "Sprint" },
  { value: "race", label: "Grand Prix" },
] as const;
const REFRESH = { revalidateOnFocus: false, dedupingInterval: 120_000 };

/** Final is a quiet caption; provisional is info blue, set apart by its outline too. */
function FinalTag({ final }: { final: boolean }) {
  const tone = final ? "border-rc-line text-rc-ink-3" : "border-rc-blue text-rc-blue";
  return (
    <span
      className={`rounded-sm border px-1.5 py-1 font-mono text-[10px] font-medium uppercase leading-none tracking-[0.1em] ${tone}`}
    >
      {final ? "Final" : "Provisional"}
    </span>
  );
}

function ClassificationPanel({ result, year, kind }: { result: SessionResult; year: number; kind: ResultsKind }) {
  const lapsRun = Math.max(0, ...result.classification.map((row) => row.laps ?? 0));
  return (
    <Panel as="section" className="p-5">
      <PanelHeading
        eyebrow={kind === "race" ? "Race classification" : "Sprint classification"}
        title={resultsTitle(result)}
        sub={`${lapsRun} laps · time for the winner, gap to the winner for everyone else · a retirement reads DNF with its reason, never a place`}
        aside={<FinalTag final={result.final} />}
      />
      <ResultsTable result={result} year={year} />
      <p className="mt-4 font-mono text-[10px] leading-relaxed tracking-[0.04em] text-rc-ink-3">
        {provenanceNote(result)}
      </p>
    </Panel>
  );
}

function ResultsBody({ data, year, round }: { data: RaceResultsResponse; year: number; round: number }) {
  const [chosen, setChosen] = useState<ResultsKind>("race");
  const kind: ResultsKind = chosen === "sprint" && data.sprint ? "sprint" : "race";
  const result = data[kind];

  return (
    <div className="space-y-4">
      {data.sprint && <Segmented label="Classification" options={KINDS} value={kind} onChange={setChosen} />}
      {result ? (
        <div className="grid items-start gap-4 lg:grid-cols-[3fr_1fr]">
          <ClassificationPanel result={result} year={year} kind={kind} />
          <div className="space-y-4">
            <ChangedAfterFlagPanel changes={result.changed_after_flag} year={year} />
            <FastestLapPanel lap={result.fastest_lap} year={year} />
            <DebriefLinkPanel round={round} />
          </div>
        </div>
      ) : (
        <Panel as="section" className="p-5 text-sm text-rc-ink-3">
          No classification has been published for this race yet.
        </Panel>
      )}
    </div>
  );
}

/**
 * The Results tab: the official classification of the round's race (and its
 * sprint). It owns its own request, so it fills in, fails or goes stale without
 * the rest of the hub waiting on it.
 */
export function ResultsTab({ year, round }: { year: number; round: number }) {
  const state = useSection<RaceResultsResponse>(`${API_BASE}/api/race-control/results/${year}/${round}`, {
    config: REFRESH,
  });
  return (
    <Section state={state} label="Race results" skeletonClassName="h-[520px]">
      {state.data && <ResultsBody data={state.data} year={year} round={round} />}
    </Section>
  );
}
