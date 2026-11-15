"use client";

import { CalendarClock } from "lucide-react";
import { useState } from "react";

import { PanelHeading } from "@/app/ui/PanelHeading";
import { Segmented } from "@/app/ui/Segmented";

import { Panel, SectionLoader } from "../components/RaceControlPrimitives";

import { poleMargin, qualifyingTitle, standInCount } from "./qualifyingModel";
import { QualifyingSidePanels } from "./QualifyingSidePanels";
import { PracticeTable, QualifyingTable } from "./SessionTables";
import { FinalTag } from "./StateTag";

import type { PracticeSession, QualifyingSession, WeekendSession, WeekendSessionsResponse } from "./sessionsModel";

type ShownSession = PracticeSession | QualifyingSession;

/** The Sessions tab shows practice and qualifying; races and grids have their own tabs. */
function shownSessions(data?: WeekendSessionsResponse): ShownSession[] {
  return (data?.sessions ?? []).filter(
    (session: WeekendSession): session is ShownSession => session.kind === "practice" || session.kind === "qualifying",
  );
}

function practiceTitle(session: PracticeSession): string {
  const leader = session.entries.find((entry) => entry.position === 1);
  return leader ? `${leader.driver_name} fastest in ${session.name}` : session.name;
}

function PracticePanel({ session }: { session: PracticeSession }) {
  const standIns = standInCount(session.entries);
  return (
    <Panel as="section" className="p-5">
      <PanelHeading
        eyebrow={`${session.name} classification`}
        title={practiceTitle(session)}
        sub={`best lap · gap to the fastest · laps run${standIns > 0 ? ` · ${standIns} car${standIns === 1 ? "" : "s"} driven by a stand-in` : ""}`}
        aside={<FinalTag final />}
      />
      <PracticeTable entries={session.entries} label={session.label} />
      <p className="mt-4 font-mono text-[10px] leading-relaxed tracking-[0.04em] text-rc-ink-3">
        Classification: f1db, mirroring the FIA final session classification · a driver who is not on the
        weekend&rsquo;s entry list is marked as a stand-in for the regular driver of that car
      </p>
    </Panel>
  );
}

function QualifyingPanel({ session }: { session: QualifyingSession }) {
  const margin = poleMargin(session.entries);
  return (
    <div className="grid items-start gap-4 lg:grid-cols-[3fr_1fr]">
      <Panel as="section" className="p-5">
        <PanelHeading
          eyebrow={`${session.name} classification`}
          title={qualifyingTitle(margin, session.name)}
          sub="grouped by the part each car ran in · gap and bar = behind the fastest lap of that part · purple = fastest in that part"
          aside={<FinalTag final />}
        />
        <QualifyingTable entries={session.entries} />
        <p className="mt-4 font-mono text-[10px] leading-relaxed tracking-[0.04em] text-rc-ink-3">
          Classification and part times: f1db, mirroring the FIA final qualifying classification · gaps computed inside
          each car&rsquo;s own part · race and sprint classifications are on Results
        </p>
      </Panel>
      <QualifyingSidePanels entries={session.entries} margin={margin} />
    </div>
  );
}

function SessionBody({ session }: { session: ShownSession }) {
  return session.kind === "practice" ? <PracticePanel session={session} /> : <QualifyingPanel session={session} />;
}

const SESSION_PICKER = "Weekend session";

/** Practice and qualifying, one pill each. The pills are whatever the weekend ran. */
export function SessionsTab({ data, loading }: { data?: WeekendSessionsResponse; loading: boolean }) {
  const sessions = shownSessions(data);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  if (loading) {
    return (
      <SectionLoader
        title="Loading session results"
        detail="Reading the practice and qualifying classifications published for this weekend."
      />
    );
  }

  if (sessions.length === 0) {
    return (
      <Panel as="section">
        <PanelHeading
          eyebrow="Weekend sessions"
          aside={<CalendarClock className="h-4 w-4 text-rc-ink-3" aria-hidden />}
          inset
        />
        <p className="p-4 text-sm leading-relaxed text-rc-ink-3">
          {data?.warnings?.[0] ??
            "Session results appear here once the weekend has been run and its classifications are published."}
        </p>
      </Panel>
    );
  }

  // The selection may name a session another round does not have: fall back to the first.
  const active = sessions.find((session) => session.id === selectedId) ?? sessions[sessions.length - 1];

  return (
    <div className="space-y-4">
      <Segmented
        label={SESSION_PICKER}
        options={sessions.map((session) => ({ value: session.id, label: session.label }))}
        value={active.id}
        onChange={setSelectedId}
      />
      <SessionBody session={active} />
    </div>
  );
}
