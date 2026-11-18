"use client";

import { BrainCircuit, ShieldAlert } from "lucide-react";

import { DriverName } from "@/app/ui/names/DriverName";
import { TeamName } from "@/app/ui/names/TeamName";
import { PanelHeading } from "@/app/ui/PanelHeading";

import { InfoRow, Panel } from "../components/RaceControlPrimitives";
import { DriverLink, TeamLink } from "../profiles/EntityLinks";

import { modelStatusColor } from "./predictionHelpers";

import type { PredictionsResponse, RiskPrediction } from "./predictionModel";

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
                    <TeamLink name={risk.team}>
                      <TeamName name={risk.team} />
                    </TeamLink>
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
          {phaseDetail} This call has not been published yet. Once it is, it stays fixed.
        </p>
      </div>
    </Panel>
  );
}
