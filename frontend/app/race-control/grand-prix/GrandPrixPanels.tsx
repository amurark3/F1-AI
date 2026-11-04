"use client";

import { BrainCircuit, ShieldAlert } from "lucide-react";
import { useMemo } from "react";

import { LocalTime } from "@/app/components/LocalTime";
import { getTeamColor } from "@/app/lib/teamColors";
import { DriverName } from "@/app/ui/names/DriverName";
import { PanelHeading } from "@/app/ui/PanelHeading";

import { ModelAttributionBars, type AttributionEntry } from "../components/Charts";
import { InfoRow, Panel } from "../components/RaceControlPrimitives";
import { DriverLink, TeamLink } from "../profiles/EntityLinks";

import {
  buildRiskLookup,
  circuitLengthLabel,
  deltaColor,
  deltaLabel,
  deltaVsGrid,
  driverDisplayName,
  estimatePodiumPct,
  estimateWinPct,
  formatPct,
  modelStatusColor,
  pointsForPosition,
} from "./predictionHelpers";
import { WeekendGlance } from "./WeekendGlance";

import type { DriverLookup, DriverPrediction, PredictionsResponse, RaceEvent, RiskPrediction } from "./predictionModel";

export function FullGridTable({
  predictions,
  riskPredictions,
  driverLookup,
}: {
  predictions: DriverPrediction[];
  riskPredictions: RiskPrediction[];
  driverLookup: DriverLookup;
}) {
  const riskLookup = useMemo(() => buildRiskLookup(riskPredictions), [riskPredictions]);

  return (
    <Panel as="section">
      <PanelHeading
        eyebrow="Race finish - full grid"
        aside={
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[#7F8797]">
            P1-P22 / pts / win / podium / vs grid
          </span>
        }
        inset
      />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[980px] border-collapse text-left">
          <thead className="bg-[#0F141E] font-mono text-[10px] uppercase tracking-[0.22em] text-[#6F7789]">
            <tr className="border-b border-[#1E2633]">
              <th className="w-16 px-4 py-3">Pos</th>
              <th className="px-4 py-3">Driver</th>
              <th className="px-4 py-3">Team</th>
              <th className="px-4 py-3 text-right">DNF%</th>
              <th className="px-4 py-3 text-right">Pts</th>
              <th className="px-4 py-3 text-right">Win est.</th>
              <th className="px-4 py-3 text-right">Podium est.</th>
              <th className="px-4 py-3 text-right">vs grid</th>
              <th className="px-4 py-3 text-right">Crash%</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#1E2633]">
            {predictions.map((prediction) => {
              const color = getTeamColor(prediction.team);
              const name = driverDisplayName(prediction, driverLookup);
              const delta = deltaVsGrid(prediction);
              const risk = riskLookup[prediction.driver_code.toUpperCase()];
              return (
                <tr
                  key={prediction.driver_code}
                  className="bg-[#0D111B] text-sm text-[#B7BDCA] transition-colors hover:bg-[#121825]"
                >
                  <td className="px-4 py-3 font-mono text-[#8E96A8]">P{prediction.position}</td>
                  <td className="px-4 py-3">
                    <div className="flex min-w-0 items-center gap-3">
                      <span className="h-5 w-[3px] rounded-full" style={{ background: color }} />
                      <span className="font-mono text-sm font-black uppercase tracking-[0.08em] text-white">
                        {prediction.driver_code}
                      </span>
                      <DriverLink code={prediction.driver_code} name={name} className="truncate text-[#AEB5C5]">
                        <DriverName variant="last" code={prediction.driver_code} name={name} />
                      </DriverLink>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-[#AEB5C5]">
                    {prediction.team ? <TeamLink name={prediction.team}>{prediction.team}</TeamLink> : "-"}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-[#7F8797]">
                    {risk ? `${risk.dnf_risk_pct}%` : "-"}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-white">
                    {pointsForPosition(prediction.position)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono font-bold text-white">
                    {formatPct(estimateWinPct(prediction))}
                  </td>
                  <td className="px-4 py-3 text-right font-mono font-bold text-white">
                    {formatPct(estimatePodiumPct(prediction))}
                  </td>
                  <td className={`px-4 py-3 text-right font-mono font-bold ${deltaColor(delta)}`}>
                    {deltaLabel(delta)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-[#7F8797]">
                    {risk ? `${risk.crash_risk_pct}%` : "-"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

export function PodiumPanel({
  podium,
  driverLookup,
  data,
}: {
  podium: DriverPrediction[];
  driverLookup: DriverLookup;
  data?: PredictionsResponse;
}) {
  return (
    <div className="space-y-4">
      <Panel as="section">
        <PanelHeading
          eyebrow="Predicted podium"
          aside={
            <span className="font-mono text-[10px] text-[#7F8797]">
              {data?.model_summary?.average_top3_confidence ?? "-"}% confidence
            </span>
          }
          inset
        />
        <div className="space-y-3 p-4">
          {podium.length ? (
            podium.map((prediction, index) => {
              const color = getTeamColor(prediction.team);
              return (
                <div key={prediction.driver_code} className="flex items-center gap-4 rounded-md bg-[#151B28] px-4 py-3">
                  <span className="w-9 font-mono text-sm font-black text-[#F5C542]">P{index + 1}</span>
                  <span className="h-9 w-[3px] rounded-full" style={{ background: color }} />
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-bold text-white">
                      <DriverLink code={prediction.driver_code}>
                        {driverDisplayName(prediction, driverLookup)}
                      </DriverLink>
                    </p>
                    <p className="truncate font-mono text-[11px] text-[#6F7789]">
                      {prediction.team} - {prediction.driver_code}
                    </p>
                  </div>
                  <p className="font-mono text-xl font-black text-white">{formatPct(estimatePodiumPct(prediction))}</p>
                </div>
              );
            })
          ) : (
            <p className="p-4 text-sm text-[#7F8797]">Run the model to create a podium snapshot.</p>
          )}
        </div>
      </Panel>

      <ModelWhyPanel prediction={podium[0]} driverLookup={driverLookup} />
    </div>
  );
}

function ModelWhyPanel({ prediction, driverLookup }: { prediction?: DriverPrediction; driverLookup: DriverLookup }) {
  const attribution = prediction?.model_attribution;
  if (!prediction || !attribution?.length) return null;

  // Show the strongest signals, largest absolute impact first.
  const data: AttributionEntry[] = [...attribution]
    .sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution))
    .slice(0, 6)
    .map((a) => ({ label: a.label, contribution: a.contribution }));

  return (
    <Panel as="section">
      <PanelHeading
        eyebrow={`Why the model picks ${driverDisplayName(prediction, driverLookup)}`}
        aside={<span className="font-mono text-[10px] text-[#7F8797]">exact linear attribution</span>}
        inset
      />
      <div className="p-4">
        <p className="mb-2 font-mono text-[11px] text-[#6F7789]">
          Per-signal effect on the projected finish — <span className="text-rc-gain">green improves</span>,{" "}
          <span className="text-rc-red-text">red worsens</span>.
        </p>
        <ModelAttributionBars data={data} />
      </div>
    </Panel>
  );
}

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

export function RiskTable({ rows }: { rows: RiskPrediction[] }) {
  return (
    <Panel as="section">
      <PanelHeading eyebrow="DNF and crash model" aside={<ShieldAlert className="h-4 w-4 text-[#E10600]" />} inset />
      {rows.length ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] border-collapse">
            <thead className="bg-[#0F141E] font-mono text-[10px] uppercase tracking-[0.22em] text-[#6F7789]">
              <tr className="border-b border-[#1E2633]">
                <th className="px-4 py-3 text-left">Driver</th>
                <th className="px-4 py-3 text-left">Team</th>
                <th className="px-4 py-3 text-right">DNF</th>
                <th className="px-4 py-3 text-right">Crash</th>
                <th className="px-4 py-3 text-right">Mechanical</th>
                <th className="px-4 py-3 text-left">Primary signal</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#1E2633]">
              {rows.map((risk) => (
                <tr key={risk.driver_code} className="bg-[#0D111B] text-sm text-[#B7BDCA] hover:bg-[#121825]">
                  <td className="px-4 py-3 font-mono font-bold text-white">
                    {risk.driver_code}{" "}
                    <DriverLink
                      code={risk.driver_code}
                      name={risk.driver_name}
                      className="font-sans font-normal text-[#8E96A8]"
                    >
                      <DriverName variant="last" code={risk.driver_code} name={risk.driver_name} />
                    </DriverLink>
                  </td>
                  <td className="px-4 py-3">
                    <TeamLink name={risk.team}>{risk.team}</TeamLink>
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-white">{risk.dnf_risk_pct}%</td>
                  <td className="px-4 py-3 text-right font-mono text-white">{risk.crash_risk_pct}%</td>
                  <td className="px-4 py-3 text-right font-mono text-white">{risk.mechanical_risk_pct}%</td>
                  <td className="px-4 py-3 text-[#7F8797]">{risk.factors?.[0] ?? risk.risk_level}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="p-4 text-sm text-[#7F8797]">
          Run or recompute the model to generate DNF, crash, and mechanical risk rows.
        </p>
      )}
    </Panel>
  );
}

export function ModelIO({ data }: { data?: PredictionsResponse }) {
  const inputs = data?.model_inputs ?? [];
  return (
    <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
      <Panel as="section">
        <PanelHeading eyebrow="Inputs used" aside={<BrainCircuit className="h-4 w-4 text-[#3671C6]" />} inset />
        <div className="divide-y divide-[#1E2633]">
          {inputs.length ? (
            inputs.map((input) => (
              <div
                key={input.label}
                className="grid gap-3 px-4 py-4 md:grid-cols-[190px_minmax(0,1fr)_120px] md:items-start"
              >
                <div>
                  <p className="font-mono text-xs font-bold uppercase tracking-[0.16em] text-white">{input.label}</p>
                  <p className="mt-1 text-xs text-[#596173]">{input.source}</p>
                </div>
                <p className="text-sm leading-relaxed text-[#AEB5C5]">{input.impact}</p>
                <span
                  className="w-fit rounded border px-2 py-1 font-mono text-[10px] font-bold uppercase tracking-[0.16em]"
                  style={{
                    color: modelStatusColor(input.status),
                    borderColor: `${modelStatusColor(input.status)}55`,
                    background: `${modelStatusColor(input.status)}14`,
                  }}
                >
                  {input.status}
                </span>
              </div>
            ))
          ) : (
            <p className="p-4 text-sm text-[#7F8797]">No model input coverage returned for this snapshot.</p>
          )}
        </div>
      </Panel>

      <Panel as="section">
        <PanelHeading eyebrow="Outputs generated" inset />
        <dl className="divide-y divide-[#1E2633] p-4 font-mono text-sm">
          <InfoRow label="Race order" value={`${data?.predictions?.length ?? 0} drivers`} />
          <InfoRow label="Risk rows" value={`${data?.risk_predictions?.length ?? 0} drivers`} />
          <InfoRow label="Snapshot versions" value={String(data?.cache?.snapshot_count ?? 0)} />
          <InfoRow label="Policy" value={data?.cache?.policy ?? "manual compute"} />
        </dl>
      </Panel>
    </div>
  );
}

/**
 * No stored prediction for this phase yet. Deliberately small, and with no
 * button of its own — the bar above holds the one run control.
 */
export function StandbyPanel({
  raceName,
  phaseName,
  phaseDetail,
}: {
  raceName: string;
  /** The phase this panel is standing in for, e.g. "After Qualifying". */
  phaseName: string;
  /** What that phase's model is fed. */
  phaseDetail: string;
}) {
  return (
    <Panel as="section">
      <div className="p-5">
        <p className="font-mono text-[11px] font-bold uppercase tracking-[0.24em] text-[#E10600]">
          No stored {phaseName.toLowerCase()} prediction for {raceName}
        </p>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-[#8E96A8]">
          {phaseDetail} Run it from the bar above to save a snapshot. It stays fixed until you run it again, and running
          one phase leaves the other alone.
        </p>
      </div>
    </Panel>
  );
}
