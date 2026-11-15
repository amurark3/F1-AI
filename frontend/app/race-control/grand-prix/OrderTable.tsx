"use client";

import { getTeamColor } from "@/app/lib/teamColors";
import { DriverName } from "@/app/ui/names/DriverName";
import { driverLabel } from "@/app/ui/names/names";
import { PanelHeading } from "@/app/ui/PanelHeading";

import { Panel } from "../components/RaceControlPrimitives";
import { DriverLink } from "../profiles/EntityLinks";

import { gridColumnNote, gridDelta, gridDeltaCell } from "./gridDelta";
import { driverDisplayName } from "./predictionHelpers";
import { StateTag } from "./StateTag";

import type { StartingGridResponse } from "./gridModel";
import type { DriverLookup, DriverPrediction, PredictionPhase, PredictionsResponse } from "./predictionModel";

const HEAD = "pr-2.5 pb-2.5 font-mono text-[10px] font-semibold uppercase leading-none tracking-[0.16em] text-rc-ink-3";
const CELL = "border-b border-rc-line-soft py-2.5 pr-2.5 align-middle";

/** Agreement bands are scored 0-100, so the bar's left edge and width are the band itself. */
function AgreementBar({ prediction, color }: { prediction: DriverPrediction; color: string }) {
  const { confidence_low: low, confidence_high: high } = prediction;
  return (
    <span className="relative block h-2 w-full min-w-24 rounded-full bg-white/[0.03]" aria-hidden="true">
      <span
        className="absolute inset-y-0 origin-left rounded-full motion-safe:animate-fill-x"
        style={{ left: `${low}%`, width: `${high - low}%`, background: color }}
      />
    </span>
  );
}

function OrderRow({
  prediction,
  lookup,
  grid,
  showGrid,
}: {
  prediction: DriverPrediction;
  lookup: DriverLookup;
  grid?: StartingGridResponse;
  showGrid: boolean;
}) {
  const color = getTeamColor(prediction.team);
  const name = driverDisplayName(prediction, lookup);
  const vsGrid = gridDeltaCell(gridDelta(prediction, grid));
  const band = `${prediction.confidence_low}–${prediction.confidence_high}`;
  return (
    <tr>
      <td
        className={`${CELL} w-12 font-mono text-[13px] font-semibold ${prediction.position === 1 ? "text-rc-gold" : "text-rc-ink-3"}`}
      >
        P{prediction.position}
      </td>
      <td className={CELL}>
        <span className="inline-flex flex-wrap items-center gap-x-2.5 gap-y-1 font-semibold text-rc-ink">
          <span className="h-4 w-[3px] shrink-0 rounded-full" style={{ background: color }} />
          <DriverLink code={prediction.driver_code} name={name}>
            <DriverName code={prediction.driver_code} name={name} />
          </DriverLink>
          <span className="font-mono text-[11px] font-medium text-rc-ink-3">{prediction.driver_code}</span>
          {prediction.seat_tbc && (
            <span title={prediction.seat_tbc_reason ?? undefined}>
              <StateTag>Seat TBC</StateTag>
            </span>
          )}
        </span>
      </td>
      <td className={`${CELL} max-sm:hidden`}>
        <AgreementBar prediction={prediction} color={color} />
      </td>
      <td className={`${CELL} text-right font-mono text-[12px] font-semibold text-rc-ink-2`}>{band}</td>
      {showGrid && (
        <td
          className={`${CELL} pr-0 text-right font-mono text-[12px] font-semibold ${vsGrid.className}`}
          title={vsGrid.note}
        >
          {vsGrid.text}
          <span className="sr-only"> ({vsGrid.note})</span>
        </td>
      )}
    </tr>
  );
}

/** The finding: who the order puts first and second, from the rows. */
export function orderTitle(predictions: DriverPrediction[], lookup: DriverLookup): string {
  const [first, second] = predictions;
  const surname = (prediction: DriverPrediction) =>
    driverLabel({ name: driverDisplayName(prediction, lookup), code: prediction.driver_code }, "last");
  if (!second) return `${surname(first)} is called to win`;
  return `${surname(first)} is called to win, ${surname(second)} to follow`;
}

/**
 * The called finishing order: position, driver, how closely the model's
 * inputs agree (a score, not a chance), and after qualifying the places
 * against the starting grid.
 */
export function OrderTable({
  predictions,
  driverLookup,
  phase,
  grid,
  gridLoading,
  data,
}: {
  predictions: DriverPrediction[];
  driverLookup: DriverLookup;
  phase: PredictionPhase;
  grid?: StartingGridResponse;
  gridLoading: boolean;
  data?: PredictionsResponse;
}) {
  const showGrid = phase === "post_qualifying";
  const sources = data?.data_sources?.join(", ");
  return (
    <Panel as="section" className="p-5">
      <PanelHeading
        eyebrow={`Predicted order · ${predictions.length} cars`}
        title={orderTitle(predictions, driverLookup)}
        sub={`Agreement is how closely the model's inputs agree on each car, as a 0–100 band: a score, not a chance of finishing there${showGrid ? "" : " · vs grid joins after qualifying"}`}
      />
      <table className="w-full border-collapse text-left text-sm">
        <thead>
          <tr className="border-b border-rc-line">
            <th className={HEAD}>P</th>
            <th className={HEAD}>Driver</th>
            <th className={`${HEAD} max-sm:hidden`}>
              <span className="sr-only">Agreement band</span>
            </th>
            <th className={`${HEAD} text-right`}>Agreement</th>
            {showGrid && <th className={`${HEAD} pr-0 text-right`}>vs grid</th>}
          </tr>
        </thead>
        <tbody>
          {predictions.map((prediction) => (
            <OrderRow
              key={prediction.driver_code}
              prediction={prediction}
              lookup={driverLookup}
              grid={grid}
              showGrid={showGrid}
            />
          ))}
        </tbody>
      </table>
      <p className="mt-4 font-mono text-[10px] leading-relaxed tracking-[0.04em] text-rc-ink-3">
        {phase === "post_qualifying" ? "Post-qualifying" : "Pre-qualifying"} projection
        {sources ? ` · sources: ${sources}` : ""}
        {showGrid ? ` · ${gridColumnNote(grid, gridLoading)}` : ""}
      </p>
    </Panel>
  );
}
