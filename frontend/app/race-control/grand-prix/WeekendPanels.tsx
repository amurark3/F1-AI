"use client";

import { LocalTime } from "@/app/components/LocalTime";
import { PanelHeading } from "@/app/ui/PanelHeading";

import { InfoRow, Panel } from "../components/RaceControlPrimitives";

import { circuitLengthLabel } from "./predictionHelpers";
import { WeekendGlance } from "./WeekendGlance";

import type { RaceEvent } from "./predictionModel";

function CircuitInfoPanel({ selectedRace }: { selectedRace: RaceEvent | null }) {
  const circuit = selectedRace?.circuit;

  return (
    <Panel as="section">
      <PanelHeading
        eyebrow="This weekend"
        aside={
          <span className="font-mono text-[10px] text-[#7F8797]">
            {circuit?.circuit_name ?? selectedRace?.location ?? "circuit TBC"}
          </span>
        }
        inset
      />
      {/* Name, race time and status are in the page header; this card adds the rest. */}
      <dl className="divide-y divide-[#1E2633] p-4 font-mono text-sm">
        <InfoRow label="Location" value={selectedRace?.location ?? "-"} />
        <InfoRow label="Length" value={circuitLengthLabel(circuit)} />
        <InfoRow label="Laps" value={circuit?.laps ? String(circuit.laps) : "-"} />
        <InfoRow label="Type" value={circuit?.circuit_type ?? "-"} />
      </dl>
    </Panel>
  );
}

function SessionSchedulePanel({ sessions }: { sessions: Array<[string, string]> }) {
  return (
    <Panel as="section">
      <PanelHeading
        eyebrow="Session schedule"
        aside={
          <span className="font-mono text-[10px] text-[#7F8797]">
            {sessions.length ? `${sessions.length} sessions` : "times TBC"}
          </span>
        }
        inset
      />
      <div className="divide-y divide-[#1E2633] p-4 font-mono text-sm">
        {sessions.length === 0 && (
          <p className="text-sm text-[#7F8797]">Session times have not been returned for this event.</p>
        )}
        {sessions.map(([label, value]) => (
          <InfoRow
            key={label}
            label={label}
            value={
              <>
                <LocalTime value={value} style="day" fallback="date TBC" /> -{" "}
                <LocalTime value={value} style="time" fallback="time TBC" />
              </>
            }
          />
        ))}
      </div>
    </Panel>
  );
}

/**
 * The event itself: where it is run and when each session starts.
 *
 * Reads only the schedule, so it renders on a weekend the prediction model has
 * never been run for — which is the whole reason it is no longer bundled with
 * the model's accuracy panel.
 */
export function WeekendPanel({ year, selectedRace }: { year: number; selectedRace: RaceEvent | null }) {
  const sessions = Object.entries(selectedRace?.sessions ?? {});

  return (
    <div className="grid gap-4 xl:grid-cols-3">
      <CircuitInfoPanel selectedRace={selectedRace} />
      <SessionSchedulePanel sessions={sessions} />
      {selectedRace && <WeekendGlance year={year} round={selectedRace.round} />}
    </div>
  );
}
