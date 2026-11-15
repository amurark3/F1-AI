"use client";

import { getTeamColor } from "@/app/lib/teamColors";
import { DriverName } from "@/app/ui/names/DriverName";
import { driverLabel } from "@/app/ui/names/names";
import { TeamName } from "@/app/ui/names/TeamName";
import { PanelHeading } from "@/app/ui/PanelHeading";

import { ModelAttributionBars, type AttributionEntry } from "../components/Charts";
import { Panel } from "../components/RaceControlPrimitives";
import { DriverLink } from "../profiles/EntityLinks";

import { driverDisplayName, estimatePodiumPct, formatPct } from "./predictionHelpers";

import type { DriverLookup, DriverPrediction, PredictionsResponse } from "./predictionModel";

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
