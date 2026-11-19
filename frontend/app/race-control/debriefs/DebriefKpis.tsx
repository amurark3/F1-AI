"use client";

import { useId, type ReactNode } from "react";

import { useSeasonDirectory } from "@/app/race-control/profiles/EntityLinks";
import { RetryButton, StaleMark } from "@/app/ui/section/Section";
import type { SectionState } from "@/app/ui/section/sectionState";
import { StatTile, StatTiles } from "@/app/ui/StatTile";

import { biggestClimb, lastOf, podiumOf, retirementCount, retirementGroups, winningMargin } from "./debriefModel";

import type { DebriefOvertakes, DebriefSummary } from "./debriefTypes";

interface Figure {
  value: ReactNode;
  unit?: string;
  sub: string;
}

function marginFigure(summary: DebriefSummary, directory: ReturnType<typeof useSeasonDirectory>): Figure {
  const [first, second] = podiumOf(summary);
  const margin = winningMargin(summary);
  if (!first || !second || !margin) return { value: "—", sub: "No winning margin to state" };
  return {
    value: margin.value,
    unit: margin.unit,
    sub: `${lastOf(first, directory)} over ${lastOf(second, directory)}`,
  };
}

function climbFigure(summary: DebriefSummary, directory: ReturnType<typeof useSeasonDirectory>): Figure {
  if (!summary.grid.available) return { value: "—", sub: "Waiting for the official starting grid" };
  const climb = biggestClimb(summary);
  if (!climb) return { value: "—", sub: "No driver gained places" };
  const from = climb.row.pit_lane ? "pit lane" : `P${climb.from}`;
  return {
    value: <span className="text-rc-gain">+{climb.gained}</span>,
    sub: `${lastOf(climb.row, directory)} · ${from} → P${climb.row.position}`,
  };
}

function retirementsFigure(summary: DebriefSummary, directory: ReturnType<typeof useSeasonDirectory>): Figure {
  const count = retirementCount(summary);
  if (count === 0) return { value: 0, sub: "No retirements" };
  return { value: count, sub: retirementGroups(summary, directory).join(", ") };
}

/** The position-changes tile, in the state of its own fetch: data stays on screen whenever there is some. */
function OvertakesTile({ state, data }: { state: SectionState; data: DebriefOvertakes | undefined }) {
  const labelId = useId();
  const failed = state.status === "failed";
  let value: ReactNode = "—";
  if (failed) value = <span className="text-base text-rc-ink-3">Unavailable</span>;
  else if (data?.available) value = data.total;
  let sub: string | null | undefined = "on-track position changes · OpenF1";
  if (state.status === "pending") sub = undefined;
  else if (failed) sub = state.reason;
  else if (data && !data.available) sub = "OpenF1 has no position changes for this race";
  return (
    <div role="group" aria-labelledby={labelId} className="min-w-0">
      <StatTile labelId={labelId} label="Overtakes" value={value} sub={sub} />
      {state.status === "stale" && <StaleMark state={state} className="mt-2" />}
      {failed && (
        <p className="mt-2">
          <RetryButton state={state} />
        </p>
      )}
    </div>
  );
}

export interface DebriefKpisProps {
  summary: DebriefSummary;
  overtakes: SectionState & { data: DebriefOvertakes | undefined };
}

/** Winning margin, position changes, the biggest climb and the retirements. */
export function DebriefKpis({ summary, overtakes }: DebriefKpisProps) {
  const directory = useSeasonDirectory();
  const margin = marginFigure(summary, directory);
  const climb = climbFigure(summary, directory);
  const retired = retirementsFigure(summary, directory);
  return (
    <StatTiles>
      <StatTile lead label="Winning margin" value={margin.value} unit={margin.unit} sub={margin.sub} />
      <OvertakesTile state={overtakes} data={overtakes.data} />
      <StatTile label="Biggest climb" value={climb.value} sub={climb.sub} />
      <StatTile label="Retirements" value={retired.value} sub={retired.sub} />
    </StatTiles>
  );
}
