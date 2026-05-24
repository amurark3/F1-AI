"use client";

import { AlertTriangle, BrainCircuit, Flag } from "lucide-react";
import { getTeamColor, type DriverPrediction } from "@/app/components/PredictionDriverCard";
import { InlineNotice, Panel, SectionLoader, StatusPill, WorkspaceSplit, rcFont } from "../components/RaceControlPrimitives";
import { ConfidenceBarChart } from "../components/Charts";

interface RaceEvent {
  round: number;
  name: string;
  location: string;
  status: string;
  is_sprint?: boolean;
}

interface DriverStanding {
  code: string;
  name: string;
  team: string;
  position: number;
  points: number;
  wins: number;
}

interface PredictionsResponse {
  year: number;
  round: number;
  grand_prix?: string;
  predictions: DriverPrediction[];
  accuracy?: { recent_top3_pct?: number; races_evaluated: number };
  error?: string;
  warnings?: string[];
  data_sources?: string[];
  model_summary?: {
    leader?: string | null;
    leader_code?: string | null;
    average_top3_confidence?: number | null;
    source_count?: number;
    status?: string;
    snapshot_policy?: string;
  };
  model_inputs?: Array<{ label: string; status: string; impact: string; source: string }>;
  model_limitations?: string[];
  cache?: { status: "hit" | "stored"; stored_at?: string | null; valid_until?: string | null; policy?: string };
}

type DriverLookup = Record<string, DriverStanding>;

function confidenceMidpoint(prediction: DriverPrediction) {
  return Math.round((prediction.confidence_low + prediction.confidence_high) / 2);
}

function buildDriverLookup(drivers: DriverStanding[]): DriverLookup {
  return drivers.reduce<DriverLookup>((lookup, driver) => {
    lookup[driver.code.toUpperCase()] = driver;
    return lookup;
  }, {});
}

function predictionDriverNameFromLookup(prediction: DriverPrediction, driverLookup: DriverLookup) {
  const code = (prediction.driver_code || "").toUpperCase();
  const nameFromStandings = driverLookup[code]?.name;
  if (nameFromStandings) return nameFromStandings;
  return prediction.driver_name && prediction.driver_name !== prediction.driver_code
    ? prediction.driver_name
    : prediction.driver_code;
}

function formatSnapshotTime(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "the next race";
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
}

function modelStatusColor(status: string) {
  if (status === "available") return "#00FF78";
  if (status === "missing") return "#E10600";
  if (status === "limited" || status === "fallback") return "#FFF200";
  return "#3671C6";
}

function WinnerCard({ prediction, driverLookup }: { prediction: DriverPrediction; driverLookup: DriverLookup }) {
  const color = getTeamColor(prediction.team);
  const confidence = confidenceMidpoint(prediction);
  const leadFactor = prediction.factors?.[0] ?? "Strongest aggregate race profile for the selected round.";
  const driverName = predictionDriverNameFromLookup(prediction, driverLookup);

  return (
    <div className="relative overflow-hidden rounded-lg border border-white/10 bg-black/25 p-5">
      <div className="absolute inset-y-0 left-0 w-1.5" style={{ background: color }} />
      <div className="flex flex-col gap-5 md:flex-row md:items-center md:justify-between">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.18em]" style={{ color, ...rcFont }}>Projected Winner</p>
          <h3 className="mt-2 break-words text-3xl font-black italic uppercase leading-tight text-white sm:text-4xl" style={rcFont}>{driverName}</h3>
          <p className="mt-2 text-xl font-bold text-white">{prediction.driver_code}</p>
          <p className="text-sm font-semibold" style={{ color }}>{prediction.team}</p>
        </div>
        <div className="rounded-lg border border-white/10 bg-white/[0.035] p-4 text-center md:w-36 md:shrink-0">
          <p className="text-4xl font-black text-white" style={rcFont}>{confidence}%</p>
          <p className="text-xs font-black uppercase tracking-[0.14em] text-neutral-400">Call Strength</p>
        </div>
      </div>
      <div className="mt-5 rounded-lg border border-white/10 bg-white/[0.035] p-4">
        <p className="text-xs font-black uppercase tracking-[0.14em] text-neutral-400" style={rcFont}>Pit Wall Read</p>
        <p className="mt-1 text-base leading-relaxed text-neutral-200">{leadFactor}</p>
      </div>
    </div>
  );
}

function PodiumSlot({ prediction, rank, driverLookup }: { prediction: DriverPrediction; rank: number; driverLookup: DriverLookup }) {
  const color = getTeamColor(prediction.team);
  const confidence = confidenceMidpoint(prediction);
  const driverName = predictionDriverNameFromLookup(prediction, driverLookup);

  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.035] p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-2xl font-black italic text-white" style={rcFont}>P{rank}</span>
        <span className="rounded px-2 py-1 text-xs font-black" style={{ color, background: `${color}22` }}>{prediction.driver_code}</span>
      </div>
      <p className="truncate text-sm font-bold text-white">{driverName}</p>
      <p className="truncate text-xs font-semibold" style={{ color }}>{prediction.team}</p>
      <div className="mt-3 h-2 overflow-hidden rounded-full bg-white/10">
        <div className="h-full rounded-full" style={{ width: `${confidence}%`, background: color }} />
      </div>
      <p className="mt-2 text-xs text-neutral-400">{confidence}% confidence</p>
    </div>
  );
}

function TimingTowerRow({ prediction, index, driverLookup }: { prediction: DriverPrediction; index: number; driverLookup: DriverLookup }) {
  const color = getTeamColor(prediction.team);
  const confidence = confidenceMidpoint(prediction);
  const driverName = predictionDriverNameFromLookup(prediction, driverLookup);

  return (
    <div className="flex items-center gap-3 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2.5">
      <div className="w-11 shrink-0 text-center text-lg font-black italic text-neutral-300" style={rcFont}>P{prediction.position || index + 1}</div>
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="rounded px-2 py-0.5 text-xs font-black" style={{ color, background: `${color}20` }}>{prediction.driver_code}</span>
          <p className="truncate text-sm font-bold text-white">{driverName}</p>
        </div>
        <p className="mt-0.5 truncate text-xs font-semibold" style={{ color }}>{prediction.team}</p>
      </div>
      <div className="w-24 shrink-0">
        <div className="mb-1 flex justify-between text-[10px] font-mono text-neutral-500">
          <span>{prediction.confidence_low}%</span>
          <span>{prediction.confidence_high}%</span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-white/10">
          <div className="h-full rounded-full" style={{ width: `${confidence}%`, background: color }} />
        </div>
      </div>
    </div>
  );
}

function ModelSourceCard({ input }: { input: { label: string; status: string; impact: string; source: string } }) {
  const color = modelStatusColor(input.status);
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.035] p-3">
      <div className="mb-2 flex items-start justify-between gap-3">
        <p className="text-sm font-black uppercase text-white" style={rcFont}>{input.label}</p>
        <StatusPill color={color}>{input.status}</StatusPill>
      </div>
      <p className="text-sm leading-relaxed text-neutral-300">{input.impact}</p>
      <p className="mt-2 text-xs text-neutral-500">{input.source}</p>
    </div>
  );
}

function RaceForecastStandby({ raceName }: { raceName: string }) {
  return (
    <Panel className="p-8" accent="#00FF78">
      <div className="flex flex-col gap-6 lg:flex-row lg:items-center">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.18em] text-[#00FF78]" style={rcFont}>Race Prediction Ready</p>
          <h2 className="mt-2 text-4xl font-black italic uppercase text-white leading-none" style={rcFont}>{raceName}</h2>
          <p className="mt-3 max-w-3xl text-base leading-relaxed text-neutral-400">
            Load the fixed race prediction result for the selected Grand Prix.
          </p>
        </div>
        <div className="rounded-lg border border-white/10 bg-black/20 p-5 lg:w-[320px] lg:shrink-0">
          <div className="mb-4 flex items-center justify-between">
            <StatusPill>Standby</StatusPill>
            <Flag className="h-5 w-5 text-neutral-500" />
          </div>
          <div className="space-y-3">
            {["Win call", "Podium branch", "Projected order", "Confidence bands"].map((item) => (
              <div key={item} className="flex items-center justify-between rounded-lg border border-white/10 bg-white/[0.035] px-3 py-2">
                <span className="text-sm font-bold text-neutral-300">{item}</span>
                <span className="text-xs font-mono text-neutral-500">Pending</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Panel>
  );
}

export interface RacePredictionBoardProps {
  schedule: RaceEvent[];
  scheduleError: boolean;
  scheduleLoading: boolean;
  selectedRound: number | null;
  selectedRace: RaceEvent | null;
  requested: boolean;
  data?: PredictionsResponse;
  predictions: DriverPrediction[];
  podium: DriverPrediction[];
  leader?: DriverPrediction;
  drivers: DriverStanding[];
  raceName: string;
  predictionLoading: boolean;
  predictionError: boolean;
  onSelectRound: (round: number) => void;
  onRun: () => void;
  onRetry: () => void;
  onReloadSchedule: () => void;
}

export function RacePredictionBoard({
  schedule,
  scheduleError,
  scheduleLoading,
  selectedRound,
  selectedRace,
  requested,
  data,
  predictions,
  podium,
  leader,
  drivers,
  raceName,
  predictionLoading,
  predictionError,
  onSelectRound,
  onRun,
  onRetry,
  onReloadSchedule,
}: RacePredictionBoardProps) {
  const modelSignals = Array.from(new Set(predictions.flatMap((p) => p.factors ?? []))).slice(0, 7);
  const modelInputs = data?.model_inputs ?? [];
  const snapshotLabel = data?.cache?.status === "hit" ? "Reused snapshot" : data?.cache ? "Saved snapshot" : null;
  const driverLookup = buildDriverLookup(drivers);

  const confidenceChartData = predictions.slice(0, 12).map((p) => ({
    code: p.driver_code,
    low: p.confidence_low,
    mid: confidenceMidpoint(p),
    high: p.confidence_high,
    color: getTeamColor(p.team),
  }));

  return (
    <div className="space-y-5">
      <Panel className="p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start">
          <label className="min-w-0 flex-1">
            <span className="block text-xs font-black uppercase tracking-[0.18em] text-neutral-300 mb-2" style={rcFont}>Grand Prix</span>
            <select
              value={selectedRound ?? ""}
              onChange={(e) => onSelectRound(Number(e.target.value))}
              disabled={scheduleLoading || schedule.length === 0}
              className="h-12 w-full rounded-lg border border-white/12 bg-[#151817] px-3 text-base font-semibold text-white outline-none focus:border-[#00FF78]/70 disabled:text-neutral-500"
            >
              <option value="">{scheduleLoading ? "Loading race calendar..." : "Select a race"}</option>
              {schedule.map((race) => (
                <option key={race.round} value={race.round}>
                  {race.name} ({race.status})
                </option>
              ))}
            </select>
            {selectedRace && <p className="mt-2 text-sm text-neutral-400">{selectedRace.location} · {selectedRace.status}</p>}
          </label>

          <button
            onClick={onRun}
            disabled={!selectedRound || predictionLoading}
            className="inline-flex h-12 w-full items-center justify-center rounded-lg bg-[#00FF78] px-6 text-sm font-black uppercase tracking-wider text-black transition-colors hover:bg-white disabled:cursor-not-allowed disabled:bg-white/10 disabled:text-neutral-500 lg:mt-6 lg:w-[230px] lg:shrink-0"
          >
            {predictionLoading ? "Updating..." : "Load Race Prediction"}
          </button>
        </div>

        <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {[
            ["Qualifying", "Grid position and qualifying sessions shape the opening stint risk."],
            ["Recent Form", "Recent finishes and current championship momentum."],
            ["Circuit History", "Track-specific patterns: overtaking index, previous results."],
            ["Team Strength", "Constructor pace and reliability context for the selected round."],
          ].map(([label, detail]) => (
            <div key={label} className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
              <p className="text-xs font-black uppercase tracking-[0.14em] text-neutral-300" style={rcFont}>{label}</p>
              <p className="mt-1 text-sm leading-relaxed text-neutral-500">{detail}</p>
            </div>
          ))}
        </div>

        {scheduleError && (
          <div className="mt-4">
            <InlineNotice title="Race Calendar Unavailable" tone="error">
              The race list could not be loaded.
              <button onClick={onReloadSchedule} className="ml-2 font-bold text-white underline decoration-white/30">Retry</button>
            </InlineNotice>
          </div>
        )}
      </Panel>

      {!requested && <RaceForecastStandby raceName={raceName} />}

      {requested && predictionLoading && (
        <SectionLoader title="Building race forecast" detail="Refreshing the selected Grand Prix prediction result and confidence bands." />
      )}

      {requested && !predictionLoading && predictionError && (
        <Panel className="p-8">
          <div className="flex items-start gap-4">
            <AlertTriangle className="mt-1 h-6 w-6 text-[#E10600]" />
            <div>
              <h2 className="text-2xl font-black italic uppercase text-white" style={rcFont}>Prediction Unavailable</h2>
              <p className="mt-2 text-base text-neutral-400">The model did not return enough usable inputs for this Grand Prix.</p>
              <button onClick={onRetry} className="mt-5 rounded-lg border border-white/10 bg-white/[0.04] px-4 py-2 text-sm font-bold text-neutral-200 hover:text-white">
                Retry Prediction
              </button>
            </div>
          </div>
        </Panel>
      )}

      {requested && !predictionLoading && predictions.length > 0 && (
        <div className="space-y-5">
          <Panel className="p-5" accent="#00FF78">
            <div className="mb-5 flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
              <div className="min-w-0">
                <p className="text-xs font-black uppercase tracking-[0.18em] text-neutral-400" style={rcFont}>Race Prediction Result</p>
                <h2 className="max-w-5xl break-words text-3xl font-black italic uppercase leading-tight text-white sm:text-4xl" style={rcFont}>{raceName}</h2>
              </div>
              <div className="flex shrink-0 flex-wrap gap-2 lg:justify-end">
                {snapshotLabel && <StatusPill color={data?.cache?.status === "hit" ? "#3671C6" : "#00FF78"}>{snapshotLabel}</StatusPill>}
                <StatusPill>{selectedRace?.name ?? `Round ${data?.round ?? selectedRound}`}</StatusPill>
              </div>
            </div>

            {leader && <WinnerCard prediction={leader} driverLookup={driverLookup} />}

            <div className="mt-5 flex flex-col gap-3 sm:flex-row sm:flex-wrap [&>*]:min-w-[160px] [&>*]:flex-[1_1_160px]">
              {podium.map((p, i) => (
                <PodiumSlot key={p.driver_code} prediction={p} rank={i + 1} driverLookup={driverLookup} />
              ))}
            </div>
          </Panel>

          {/* Confidence chart + classification side-by-side */}
          <Panel className="p-5">
            <div className="mb-4 flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-black uppercase tracking-[0.18em] text-neutral-400" style={rcFont}>Win Probability</p>
                <h2 className="text-xl font-black text-white" style={rcFont}>Confidence Distribution</h2>
              </div>
              <StatusPill color="#BE3AFF">Top 12 drivers</StatusPill>
            </div>
            <ConfidenceBarChart data={confidenceChartData} height={200} />
          </Panel>

          <WorkspaceSplit className="xl:[&>*:first-child]:basis-[62%] xl:[&>*:last-child]:flex-1">
            <Panel className="p-5">
              <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <p className="text-xs font-black uppercase tracking-[0.18em] text-neutral-400" style={rcFont}>Projected Classification</p>
                  <h2 className="text-2xl font-black italic uppercase text-white" style={rcFont}>Race Order</h2>
                </div>
                {data?.accuracy?.races_evaluated ? (
                  <StatusPill color="#3671C6">{data.accuracy.races_evaluated} reviewed races</StatusPill>
                ) : null}
              </div>
              <div className="space-y-2">
                {predictions.map((p, i) => (
                  <TimingTowerRow key={p.driver_code} prediction={p} index={i} driverLookup={driverLookup} />
                ))}
              </div>
            </Panel>

            <Panel className="p-5">
              <div className="mb-4 flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-black uppercase tracking-[0.18em] text-neutral-400" style={rcFont}>Model Transparency</p>
                  <h2 className="text-2xl font-black italic uppercase text-white" style={rcFont}>Input Coverage</h2>
                  {data?.cache?.valid_until && (
                    <p className="mt-1 text-xs text-neutral-500">
                      Snapshot valid until {formatSnapshotTime(data.cache.valid_until)}.
                    </p>
                  )}
                </div>
                <BrainCircuit className="h-5 w-5 shrink-0 text-[#BE3AFF]" />
              </div>

              <div className="mb-5 flex flex-col gap-3">
                {modelInputs.length > 0 ? modelInputs.map((input) => (
                  <ModelSourceCard key={input.label} input={input} />
                )) : (
                  <p className="text-sm text-neutral-500">Model source details were not returned for this snapshot.</p>
                )}
              </div>

              {typeof data?.model_summary?.average_top3_confidence === "number" && (
                <div className="mb-4 rounded-lg border border-white/10 bg-white/[0.035] p-4">
                  <p className="text-xs font-black uppercase tracking-[0.14em] text-neutral-400" style={rcFont}>Snapshot Read</p>
                  <p className="mt-2 text-sm leading-relaxed text-neutral-300">
                    {data.model_summary.snapshot_policy ?? "Race forecasts are fixed snapshots."}
                  </p>
                  <p className="mt-2 text-xs text-neutral-500">
                    Top-3 avg confidence: {data.model_summary.average_top3_confidence}% across {data.model_summary.source_count ?? 0} source groups.
                  </p>
                </div>
              )}

              {modelSignals.length > 0 && (
                <div className="flex flex-col gap-3">
                  <p className="text-xs font-black uppercase tracking-[0.14em] text-neutral-400" style={rcFont}>Leader Factors</p>
                  {modelSignals.map((signal) => (
                    <div key={signal} className="rounded-lg border border-white/10 bg-white/[0.035] p-3">
                      <p className="text-sm leading-relaxed text-neutral-300">{signal}</p>
                    </div>
                  ))}
                </div>
              )}

              {data?.model_limitations?.length ? (
                <div className="mt-4">
                  <InlineNotice title="Model Limits" tone="warning">
                    {data.model_limitations.slice(0, 3).join(" ")}
                  </InlineNotice>
                </div>
              ) : null}
            </Panel>
          </WorkspaceSplit>

          {data?.warnings?.length ? (
            <InlineNotice title="Prediction Notes" tone="warning">
              {data.warnings.slice(0, 2).join(" ")}
            </InlineNotice>
          ) : null}
        </div>
      )}
    </div>
  );
}
