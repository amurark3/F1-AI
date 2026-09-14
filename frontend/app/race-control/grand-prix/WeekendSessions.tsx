"use client";

import { CalendarClock } from "lucide-react";
import { useState } from "react";

import { SectionLoader } from "../components/RaceControlPrimitives";

import { GridPenalties } from "./GridPenalties";
import { ConsoleHeader, ConsolePanel } from "./predictionConsole";
import { PracticeTable, QualifyingTable, RaceTable } from "./SessionTables";
import { StartingGrid } from "./StartingGrid";

import type { StartingGridResponse } from "./gridModel";
import type { GridSession, WeekendSession, WeekendSessionsResponse } from "./sessionsModel";

/**
 * A grid session rendered through the Grand Prix grid's own components.
 *
 * The sprint publishes a separate grid sheet with its own penalties, and the
 * backend returns it in the same shape, so the staggered drawing and the
 * penalties table are reused rather than reimplemented.
 */
function SprintGridSession({ session, raceName }: { session: GridSession; raceName: string }) {
  const payload: StartingGridResponse = {
    year: 0,
    round: 0,
    available: true,
    provisional: false,
    source: "official_grid",
    grid: session.entries,
    penalties: session.penalties,
  };

  return (
    <div className="space-y-4">
      <StartingGrid data={payload} raceName={`${raceName} sprint`} />
      <GridPenalties data={payload} />
    </div>
  );
}

function SessionBody({ session, raceName }: { session: WeekendSession; raceName: string }) {
  if (session.kind === "grid") {
    return <SprintGridSession session={session} raceName={raceName} />;
  }

  return (
    <ConsolePanel>
      <ConsoleHeader
        label={session.name}
        right={
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[#7F8797]">
            {session.entries.length} classified
          </span>
        }
      />
      <div className="overflow-x-auto">
        {session.kind === "practice" && <PracticeTable entries={session.entries} />}
        {session.kind === "qualifying" && <QualifyingTable entries={session.entries} />}
        {session.kind === "race" && <RaceTable entries={session.entries} />}
      </div>
    </ConsolePanel>
  );
}

function SessionTabs({
  sessions,
  activeId,
  onSelect,
}: {
  sessions: WeekendSession[];
  activeId: string;
  onSelect: (id: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-2" role="tablist" aria-label="Weekend sessions">
      {sessions.map((session) => {
        const active = session.id === activeId;
        return (
          <button
            key={session.id}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onSelect(session.id)}
            className={`rounded-md border px-3 py-2 font-mono text-[11px] font-bold uppercase tracking-[0.16em] transition-colors ${
              active
                ? "border-[#E10600]/60 bg-[#E10600]/[0.1] text-white"
                : "border-[#1E2633] bg-[#0D111B] text-[#8E96A8] hover:border-[#E10600]/40 hover:text-white"
            }`}
          >
            {session.label}
          </button>
        );
      })}
    </div>
  );
}

/**
 * Every session the weekend ran, each on its own tab.
 *
 * The tab set is whatever the backend returned, which is whatever produced a
 * classification — so a sprint weekend shows FP1 and the sprint set, a
 * conventional one shows three practice sessions, and a cancelled session is
 * absent rather than empty.
 */
export function WeekendSessions({
  data,
  loading,
  raceName,
}: {
  data?: WeekendSessionsResponse;
  loading: boolean;
  raceName: string;
}) {
  const sessions = data?.sessions ?? [];
  const [selectedId, setSelectedId] = useState<string | null>(null);

  if (loading) {
    return (
      <SectionLoader
        title="Loading session results"
        detail="Reading the practice and sprint classifications published for this weekend."
      />
    );
  }

  if (sessions.length === 0) {
    return (
      <ConsolePanel>
        <ConsoleHeader label="Weekend sessions" right={<CalendarClock className="h-4 w-4 text-[#596173]" />} />
        <p className="p-4 text-sm leading-relaxed text-[#8E96A8]">
          {data?.warnings?.[0] ??
            "Session results appear here once the weekend has been run and its classifications are published."}
        </p>
      </ConsolePanel>
    );
  }

  // Fall back to the first session whenever the selection is not in this
  // weekend — switching from a sprint round to a conventional one would
  // otherwise leave a "Sprint" tab selected that no longer exists.
  const active = sessions.find((session) => session.id === selectedId) ?? sessions[0];

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <SessionTabs sessions={sessions} activeId={active.id} onSelect={setSelectedId} />
        {data?.is_sprint && (
          <span className="rounded border border-[#F5C542]/40 bg-[#F5C542]/10 px-2.5 py-1 font-mono text-[10px] font-bold uppercase tracking-[0.16em] text-[#F5C542]">
            Sprint weekend
          </span>
        )}
      </div>
      <SessionBody session={active} raceName={raceName} />
    </div>
  );
}
