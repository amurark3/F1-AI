"use client";

import { BrainCircuit, ShieldAlert, Sparkles } from "lucide-react";
import { useMemo } from "react";

import { getTeamColor, type DriverPrediction } from "@/app/components/PredictionDriverCard";

import { ModelAttributionBars, type AttributionEntry } from "../components/Charts";
import { StatusPill, rcFont } from "../components/RaceControlPrimitives";

import { ConsoleHeader, ConsolePanel, InfoRow, StatBlock } from "./predictionConsole";
import {
  buildRiskLookup,
  circuitLengthLabel,
  deltaColor,
  deltaLabel,
  deltaVsGrid,
  driverDisplayName,
  estimatePodiumPct,
  estimateWinPct,
  formatDate,
  formatPct,
  formatSnapshotTime,
  formatTime,
  modelStatusColor,
  pointsForPosition,
  raceSessionTime,
  reviewBadgeLabel,
  reviewColor,
  shortName,
} from "./predictionHelpers";

import type { DriverLookup, PredictionReview, PredictionsResponse, RaceEvent, RiskPrediction } from "./predictionModel";

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
    <ConsolePanel>
      <ConsoleHeader
        label="Race finish - full grid"
        right={
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[#7F8797]">
            P1-P22 / pts / win / podium / vs grid
          </span>
        }
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
                      <span className="truncate text-[#AEB5C5]">{shortName(name)}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-[#AEB5C5]">{prediction.team || "-"}</td>
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
    </ConsolePanel>
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
      <ConsolePanel>
        <ConsoleHeader
          label="Predicted podium"
          right={
            <span className="font-mono text-[10px] text-[#7F8797]">
              {data?.model_summary?.average_top3_confidence ?? "-"}% confidence
            </span>
          }
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
                      {driverDisplayName(prediction, driverLookup)}
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
      </ConsolePanel>

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
    <ConsolePanel>
      <ConsoleHeader
        label={`Why the model picks ${driverDisplayName(prediction, driverLookup)}`}
        right={<span className="font-mono text-[10px] text-[#7F8797]">exact linear attribution</span>}
      />
      <div className="p-4">
        <p className="mb-2 font-mono text-[11px] text-[#6F7789]">
          Per-signal effect on the projected finish — <span className="text-[#00FF78]">green improves</span>,{" "}
          <span className="text-[#FF4655]">red worsens</span>.
        </p>
        <ModelAttributionBars data={data} />
      </div>
    </ConsolePanel>
  );
}

function CircuitInfoPanel({ selectedRace }: { selectedRace: RaceEvent | null }) {
  const circuit = selectedRace?.circuit;
  const raceTime = raceSessionTime(selectedRace);

  return (
    <ConsolePanel>
      <ConsoleHeader
        label="This weekend"
        right={
          <span className="font-mono text-[10px] text-[#7F8797]">
            {circuit?.circuit_name ?? selectedRace?.location ?? "circuit TBC"}
          </span>
        }
      />
      <dl className="divide-y divide-[#1E2633] p-4 font-mono text-sm">
        <InfoRow label="Circuit" value={circuit?.circuit_name ?? selectedRace?.location ?? "-"} />
        <InfoRow label="Length" value={circuitLengthLabel(circuit)} />
        <InfoRow label="Type" value={circuit?.circuit_type ?? "-"} />
        <InfoRow label="Race" value={`${formatDate(raceTime)} - ${formatTime(raceTime)}`} />
        <InfoRow label="Status" value={selectedRace?.status ?? "-"} />
      </dl>
    </ConsolePanel>
  );
}

function SessionSchedulePanel({ sessions }: { sessions: Array<[string, string]> }) {
  return (
    <ConsolePanel>
      <ConsoleHeader
        label="Session schedule"
        right={
          <span className="font-mono text-[10px] text-[#7F8797]">
            {sessions.length ? `${sessions.length} sessions` : "times TBC"}
          </span>
        }
      />
      <div className="divide-y divide-[#1E2633] p-4 font-mono text-sm">
        {sessions.length === 0 && (
          <p className="text-sm text-[#7F8797]">Session times have not been returned for this event.</p>
        )}
        {sessions.map(([label, value]) => (
          <InfoRow key={label} label={label} value={`${formatDate(value)} - ${formatTime(value)}`} />
        ))}
      </div>
    </ConsolePanel>
  );
}

function ModelStatsPanel({ data }: { data?: PredictionsResponse }) {
  const accuracy = data?.accuracy;
  const avgError = accuracy?.avg_position_error == null ? "-" : String(accuracy.avg_position_error);
  const top3 = accuracy?.recent_top3_pct == null ? "-" : `${accuracy.recent_top3_pct}%`;

  return (
    <ConsolePanel className="xl:col-span-2">
      <ConsoleHeader
        label="Model stats"
        right={
          <span className="font-mono text-[10px] text-[#7F8797]">{data?.cache?.snapshot_id ?? "no snapshot"}</span>
        }
      />
      <div className="grid grid-cols-2 gap-6 p-4 md:grid-cols-4">
        <StatBlock label="Avg error" value={avgError} detail="positions across scored predictions" />
        <StatBlock label="Top 3 hit" value={top3} detail={`latest ${accuracy?.rolling_window ?? 8} scored max`} />
        <StatBlock
          label="Validated"
          value={String(accuracy?.races_evaluated ?? 0)}
          detail="prediction/result pairs available"
        />
        <StatBlock
          label="Updated"
          value={formatSnapshotTime(data?.cache?.updated_at ?? data?.generated_at)}
          detail={data?.cache?.reason ?? "snapshot"}
        />
      </div>
    </ConsolePanel>
  );
}

export function CircuitPanel({ selectedRace, data }: { selectedRace: RaceEvent | null; data?: PredictionsResponse }) {
  const sessions = Object.entries(selectedRace?.sessions ?? {});

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_1fr]">
      <CircuitInfoPanel selectedRace={selectedRace} />
      <SessionSchedulePanel sessions={sessions} />
      <ModelStatsPanel data={data} />
    </div>
  );
}

export function RiskTable({ rows }: { rows: RiskPrediction[] }) {
  return (
    <ConsolePanel>
      <ConsoleHeader label="DNF and crash model" right={<ShieldAlert className="h-4 w-4 text-[#E10600]" />} />
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
                    <span className="font-sans font-normal text-[#8E96A8]">{shortName(risk.driver_name)}</span>
                  </td>
                  <td className="px-4 py-3">{risk.team}</td>
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
    </ConsolePanel>
  );
}

export function ModelIO({ data }: { data?: PredictionsResponse }) {
  const inputs = data?.model_inputs ?? [];
  return (
    <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
      <ConsolePanel>
        <ConsoleHeader label="Inputs used" right={<BrainCircuit className="h-4 w-4 text-[#3671C6]" />} />
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
      </ConsolePanel>

      <ConsolePanel>
        <ConsoleHeader label="Outputs generated" />
        <dl className="divide-y divide-[#1E2633] p-4 font-mono text-sm">
          <InfoRow label="Race order" value={`${data?.predictions?.length ?? 0} drivers`} />
          <InfoRow label="Risk rows" value={`${data?.risk_predictions?.length ?? 0} drivers`} />
          <InfoRow label="Snapshot versions" value={String(data?.cache?.snapshot_count ?? 0)} />
          <InfoRow label="Policy" value={data?.cache?.policy ?? "manual compute"} />
        </dl>
      </ConsolePanel>
    </div>
  );
}

function PostRaceReviewGrid({ review }: { review: PredictionReview }) {
  return (
    <div className="grid gap-4 p-4 sm:grid-cols-2 xl:grid-cols-3">
      <StatBlock
        label="Top 3"
        value={`${review.top3_correct ?? 0}/${review.top3_possible ?? 3}`}
        detail="predicted podium overlap"
      />
      <StatBlock
        label="Top 10"
        value={`${review.top10_correct ?? 0}/${review.top10_possible ?? 10}`}
        detail="points finish overlap"
      />
      <StatBlock
        label="Exact"
        value={`${review.exact_position_hits ?? 0}/${review.drivers_compared ?? 0}`}
        detail="exact finishing positions"
      />
      <StatBlock label="Avg error" value={`${review.avg_position_error ?? 0}`} detail="positions per compared driver" />
      <StatBlock
        label="DNF calls"
        value={`${review.dnf_correct ?? 0}/${review.dnf_actual ?? 0}`}
        detail="captured actual retirements"
      />
      <StatBlock
        label="Crash calls"
        value={`${review.crash_correct ?? 0}/${review.crash_actual ?? 0}`}
        detail="captured accident outcomes"
      />
    </div>
  );
}

function RollingAccuracyGrid({ accuracy }: { accuracy?: PredictionsResponse["accuracy"] }) {
  const window = accuracy?.rolling_window ?? 8;
  const dnfCapture = accuracy?.dnf_capture_pct == null ? "n/a" : `${accuracy.dnf_capture_pct}%`;
  const crashCapture = accuracy?.crash_capture_pct == null ? "n/a" : `${accuracy.crash_capture_pct}%`;

  return (
    <div className="grid gap-4 p-4 sm:grid-cols-2 xl:grid-cols-3">
      <StatBlock label="Winner" value={`${accuracy?.recent_winner_pct ?? 0}%`} detail={`latest ${window} scored max`} />
      <StatBlock label="Top 3" value={`${accuracy?.recent_top3_pct ?? 0}%`} detail={`latest ${window} scored max`} />
      <StatBlock label="Top 10" value={`${accuracy?.recent_top10_pct ?? 0}%`} detail={`latest ${window} scored max`} />
      <StatBlock label="Avg error" value={`${accuracy?.avg_position_error ?? 0}`} detail="positions per driver" />
      <StatBlock label="DNF capture" value={dnfCapture} detail="actual DNF capture" />
      <StatBlock label="Crash capture" value={crashCapture} detail="actual crash capture" />
    </div>
  );
}

export function ResultsReview({
  review,
  accuracy,
}: {
  review?: PredictionReview;
  accuracy?: PredictionsResponse["accuracy"];
}) {
  return (
    <ConsolePanel>
      <ConsoleHeader
        label={review?.evaluated ? "Post-race review" : "Rolling accuracy"}
        right={
          <StatusPill color={reviewColor(Boolean(review?.winner_correct), Boolean(review?.evaluated))}>
            {reviewBadgeLabel(review, accuracy?.races_evaluated ?? 0)}
          </StatusPill>
        }
      />
      {review?.evaluated ? <PostRaceReviewGrid review={review} /> : <RollingAccuracyGrid accuracy={accuracy} />}
    </ConsolePanel>
  );
}

export function StandbyPanel({
  raceName,
  onRun,
  isComputing,
}: {
  raceName: string;
  onRun: () => void;
  isComputing: boolean;
}) {
  return (
    <ConsolePanel>
      <div className="flex flex-col gap-4 p-6 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="font-mono text-[11px] font-bold uppercase tracking-[0.24em] text-[#E10600]">
            No stored prediction
          </p>
          <h2 className="mt-2 text-3xl font-black text-white" style={rcFont}>
            {raceName}
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-[#8E96A8]">
            Run the model when you want to create a saved snapshot. The snapshot stays fixed until you manually
            recompute it.
          </p>
        </div>
        <button
          onClick={onRun}
          disabled={isComputing}
          className="inline-flex h-11 w-fit items-center justify-center gap-2 rounded-md border border-[#00FF78]/35 bg-[#00FF78]/10 px-4 font-mono text-[11px] font-bold uppercase tracking-[0.16em] text-[#00FF78] hover:bg-[#00FF78] hover:text-black disabled:border-white/10 disabled:bg-white/[0.03] disabled:text-[#596173]"
        >
          <Sparkles className="h-3.5 w-3.5" />
          {isComputing ? "running" : "run model"}
        </button>
      </div>
    </ConsolePanel>
  );
}
