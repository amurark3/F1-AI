"use client";

import { ArrowRight } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { grandPrixHref } from "@/app/lib/entityLinks";
import { PanelHeading } from "@/app/ui/PanelHeading";
import { Segmented } from "@/app/ui/Segmented";

import { Panel, SectionLoader } from "../components/RaceControlPrimitives";

import { GridPenalties } from "./GridPenalties";
import { StartingGrid } from "./StartingGrid";

import type { StartingGridResponse } from "./gridModel";
import type { WeekendSessionsResponse } from "./sessionsModel";

const KINDS = [
  { value: "race", label: "Grand Prix" },
  { value: "sprint", label: "Sprint" },
] as const;

type GridKind = (typeof KINDS)[number]["value"];

const LINK = "inline-flex items-center gap-1.5 font-mono text-xs text-rc-blue hover:text-rc-ink";

/** Where the story goes once the lights go out: Results classifies, the Debrief tells the race. */
function AfterTheStartPanel({ round }: { round: number | null }) {
  return (
    <Panel as="section" className="p-5">
      <PanelHeading
        eyebrow="After the start"
        title="The race is classified on Results"
        sub="The FIA final classification and its post-race penalties are on Results. Who moved where from this grid is the debrief's story."
      />
      <div className="flex flex-wrap gap-4">
        {round !== null && (
          <Link href={grandPrixHref(round, "results")} className={LINK}>
            Results
            <ArrowRight className="h-3.5 w-3.5" aria-hidden />
          </Link>
        )}
        <Link href="/race-control/debriefs" className={LINK}>
          Debrief
          <ArrowRight className="h-3.5 w-3.5" aria-hidden />
        </Link>
      </div>
    </Panel>
  );
}

/** The sprint's own grid sheet, shaped like the Grand Prix's. */
function sprintGrid(data?: WeekendSessionsResponse): StartingGridResponse | null {
  const session = data?.sessions.find((candidate) => candidate.kind === "grid");
  if (!data || session?.kind !== "grid") return null;
  return {
    year: data.year,
    round: data.round,
    available: true,
    provisional: false,
    source: "official_grid",
    grid: session.entries,
    penalties: session.penalties,
  };
}

/** Codes the qualifying classification disqualified, read from the Sessions payload. */
function disqualified(data?: WeekendSessionsResponse): ReadonlySet<string> {
  const qualifying = data?.sessions.find((session) => session.id === "qualifying");
  const rows = qualifying?.kind === "qualifying" ? qualifying.entries : [];
  return new Set(rows.filter((row) => row.position_text === "DSQ").map((row) => row.driver_code));
}

interface GridTabProps {
  grid?: StartingGridResponse;
  loading: boolean;
  sessions?: WeekendSessionsResponse;
  round: number | null;
  raceName: string;
}

/** The grid, the penalties behind it, and (on a sprint weekend) the sprint's grid. */
export function GridTab({ grid, loading, sessions, round, raceName }: GridTabProps) {
  const [chosen, setChosen] = useState<GridKind>("race");
  const sprint = sprintGrid(sessions);

  if (loading) {
    return (
      <SectionLoader
        title="Loading the starting grid"
        detail="Reading the published grid sheet for this Grand Prix, and any penalties applied to it."
      />
    );
  }

  const showing = chosen === "sprint" && sprint ? sprint : grid;

  return (
    <div className="space-y-4">
      {sprint && (
        <Segmented label="Grid" options={KINDS} value={showing === sprint ? "sprint" : "race"} onChange={setChosen} />
      )}
      <div className="grid items-start gap-4 lg:grid-cols-[3fr_1fr]">
        <StartingGrid
          data={showing}
          raceName={showing === sprint ? `${raceName} sprint` : raceName}
          dsqCodes={disqualified(sessions)}
        />
        <div className="space-y-4">
          <GridPenalties data={showing} />
          <AfterTheStartPanel round={round} />
        </div>
      </div>
    </div>
  );
}
