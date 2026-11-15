"use client";

import { LocalTime } from "@/app/components/LocalTime";
import { PanelHeading } from "@/app/ui/PanelHeading";
import { useClock } from "@/app/ui/useClock";

import { Panel } from "../components/RaceControlPrimitives";

import { scheduleNodes, type ScheduleState } from "./weekendTabModel";

const STATE_WORD: Record<ScheduleState, string> = { done: "Done", live: "Live", next: "Next", later: "" };
const STATE_TONE: Record<ScheduleState, string> = {
  done: "text-rc-ink-3",
  live: "text-rc-red-text",
  next: "text-rc-blue",
  later: "text-rc-ink-3",
};

/** Every session's start in the viewer's own time zone, marked done, live or next. */
export function WeekendSchedule({ sessions }: { sessions: Record<string, string> }) {
  const nodes = scheduleNodes(sessions, useClock());
  return (
    <Panel as="section" className="p-5">
      <PanelHeading eyebrow="Schedule" sub="Times are in your time zone." />
      {nodes.length === 0 ? (
        <p className="mt-4 text-sm text-rc-ink-2">Session times have not been returned for this event.</p>
      ) : (
        <ol className="mt-4 divide-y divide-rc-line-soft">
          {nodes.map(({ name, startsAt, state }) => (
            <li key={name} className="flex items-baseline justify-between gap-4 py-2.5 text-sm">
              <span className={`font-semibold ${state === "done" ? "text-rc-ink-3" : "text-rc-ink"}`}>{name}</span>
              <span className="flex items-baseline gap-3 font-mono text-xs text-rc-ink-2">
                <LocalTime value={startsAt} style="day" fallback="date TBC" />
                <LocalTime value={startsAt} style="time" fallback="time TBC" />
                <span className={`w-10 text-right text-[10px] uppercase tracking-[0.14em] ${STATE_TONE[state]}`}>
                  {STATE_WORD[state]}
                </span>
              </span>
            </li>
          ))}
        </ol>
      )}
    </Panel>
  );
}
