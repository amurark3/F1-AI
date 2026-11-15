"use client";

import { useMemo } from "react";

import { getTeamColor } from "@/app/lib/teamColors";
import { DriverName } from "@/app/ui/names/DriverName";
import { driverLabel } from "@/app/ui/names/names";
import { TeamName } from "@/app/ui/names/TeamName";
import { PanelHeading } from "@/app/ui/PanelHeading";

import { ModelAttributionBars, type AttributionEntry } from "../components/Charts";
import { Panel } from "../components/RaceControlPrimitives";
import { DriverLink, TeamLink } from "../profiles/EntityLinks";

import { gridColumnNote, gridDelta, gridDeltaCell } from "./gridDelta";
import {
  buildRiskLookup,
  driverDisplayName,
  estimatePodiumPct,
  estimateWinPct,
  formatPct,
  pointsForPosition,
} from "./predictionHelpers";

import type { StartingGridResponse } from "./gridModel";
import type { DriverLookup, DriverPrediction, PredictionsResponse, RiskPrediction } from "./predictionModel";

/**
 * The predicted finishing order. "vs grid" is the predicted finish against the
 * round's starting grid, the same grid the Grid tab draws, on both phase tabs.
 */
export function FullGridTable({
  predictions,
  riskPredictions,
  driverLookup,
  grid,
  gridLoading,
}: {
  predictions: DriverPrediction[];
  riskPredictions: RiskPrediction[];
  driverLookup: DriverLookup;
  grid?: StartingGridResponse;
  gridLoading: boolean;
}) {
  const riskLookup = useMemo(() => buildRiskLookup(riskPredictions), [riskPredictions]);

  return (
    <Panel as="section">
      <PanelHeading
        eyebrow="Race finish - full grid"
        aside={
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[#7F8797]">
            P1-P22 / pts / win / podium / {gridColumnNote(grid, gridLoading)}
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
              const vsGrid = gridDeltaCell(gridDelta(prediction, grid));
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
                    {prediction.team ? (
                      <TeamLink name={prediction.team}>
                        <TeamName name={prediction.team} />
                      </TeamLink>
                    ) : (
                      "-"
                    )}
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
                  <td className={`px-4 py-3 text-right font-mono font-bold ${vsGrid.className}`} title={vsGrid.note}>
                    {vsGrid.text}
                    <span className="sr-only"> ({vsGrid.note})</span>
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
                        <DriverName name={driverDisplayName(prediction, driverLookup)} code={prediction.driver_code} />
                      </DriverLink>
                    </p>
                    <p className="truncate font-mono text-[11px] text-[#6F7789]">
                      <TeamName name={prediction.team} /> - {prediction.driver_code}
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
        eyebrow={`Why the model picks ${driverLabel({ name: driverDisplayName(prediction, driverLookup), code: prediction.driver_code }, "full")}`}
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
