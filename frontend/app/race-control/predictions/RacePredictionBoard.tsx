"use client";

import { useMemo, useState } from "react";
import {
  AlertTriangle,
  BrainCircuit,
  Check,
  CircleDot,
  LockKeyhole,
  RefreshCw,
  ShieldAlert,
  Sparkles,
} from "lucide-react";
import { getTeamColor, type DriverPrediction } from "@/app/components/PredictionDriverCard";
import { InlineNotice, SectionLoader, StatusPill, rcFont } from "../components/RaceControlPrimitives";

interface RaceEvent {
  round: number;
  name: string;
  location: string;
  status: string;
  date?: string;
  sessions?: Record<string, string>;
  is_sprint?: boolean;
  circuit?: { circuit_name?: string; laps?: number; circuit_type?: string; length_km?: number } | null;
}

interface DriverStanding {
  code: string;
  name: string;
  team: string;
  position: number;
  points: number;
  wins: number;
}

interface RiskPrediction {
  driver_code: string;
  driver_name: string;
  team: string;
  projected_finish: number;
  dnf_risk_pct: number;
  crash_risk_pct: number;
  mechanical_risk_pct: number;
  risk_level: "low" | "medium" | "high";
  factors: string[];
}

interface PredictionReview {
  evaluated: boolean;
  reason?: string;
  winner_correct?: boolean;
  predicted_winner?: string;
  actual_winner?: string;
  top3_correct?: number;
  top3_possible?: number;
  top10_correct?: number;
  top10_possible?: number;
  exact_position_hits?: number;
  drivers_compared?: number;
  avg_position_error?: number;
  dnf_correct?: number;
  dnf_predicted?: number;
  dnf_actual?: number;
  crash_correct?: number;
  crash_predicted?: number;
  crash_actual?: number;
}

interface PredictionsResponse {
  year: number;
  round: number;
  grand_prix?: string;
  generated_at?: string;
  prediction_phase?: "pre_qualifying" | "post_qualifying";
  predictions: DriverPrediction[];
  risk_predictions?: RiskPrediction[];
  prediction_review?: PredictionReview;
  accuracy?: {
    recent_winner_pct?: number;
    recent_top3_pct?: number;
    recent_top10_pct?: number;
    exact_position_pct?: number;
    avg_position_error?: number;
    dnf_capture_pct?: number | null;
    crash_capture_pct?: number | null;
    races_evaluated: number;
    rolling_window?: number;
  };
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
    risk_count?: number;
  };
  model_inputs?: Array<{ label: string; status: string; impact: string; source: string }>;
  model_limitations?: string[];
  cache?: {
    status: "hit" | "stored" | "missing";
    stored_at?: string | null;
    updated_at?: string | null;
    valid_until?: string | null;
    policy?: string;
    snapshot_id?: string | null;
    snapshot_count?: number;
    recompute_count?: number;
    reason?: string | null;
  };
}

type DriverLookup = Record<string, DriverStanding>;
type TabKey = "predictions" | "podium" | "circuit" | "risk" | "model" | "results";

const POINTS_BY_POSITION = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1];
const tabs: Array<{ key: TabKey; label: string; locked?: boolean }> = [
  { key: "predictions", label: "Predictions" },
  { key: "podium", label: "Podium" },
  { key: "circuit", label: "Circuit" },
  { key: "risk", label: "DNF / Crash" },
  { key: "model", label: "Model I/O" },
  { key: "results", label: "Results" },
];

function confidenceMidpoint(prediction: DriverPrediction) {
  return Math.round((prediction.confidence_low + prediction.confidence_high) / 2);
}

function buildDriverLookup(drivers: DriverStanding[]): DriverLookup {
  return drivers.reduce<DriverLookup>((lookup, driver) => {
    lookup[driver.code.toUpperCase()] = driver;
    return lookup;
  }, {});
}

function driverDisplayName(prediction: DriverPrediction, lookup: DriverLookup) {
  const code = prediction.driver_code.toUpperCase();
  const name = lookup[code]?.name;
  if (name) return name;
  return prediction.driver_name && prediction.driver_name !== prediction.driver_code
    ? prediction.driver_name
    : prediction.driver_code;
}

function shortName(name: string) {
  const parts = name.trim().split(/\s+/);
  return parts.length > 1 ? parts[parts.length - 1] : name;
}

function formatDate(value?: string) {
  if (!value) return "date TBC";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "date TBC";
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", year: "numeric" }).format(date);
}

function formatTime(value?: string) {
  if (!value) return "time TBC";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "time TBC";
  return new Intl.DateTimeFormat("en-US", { hour: "2-digit", minute: "2-digit", timeZoneName: "short" }).format(date);
}

function formatSnapshotTime(value?: string | null) {
  if (!value) return "not stored";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "not stored";
  return new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" }).format(date);
}

function countdownTo(value?: string) {
  if (!value) return null;
  const target = new Date(value).getTime();
  if (Number.isNaN(target)) return null;
  const diff = target - Date.now();
  if (diff <= 0) return null;
  const days = Math.floor(diff / 86400000);
  const hours = Math.floor((diff % 86400000) / 3600000);
  const minutes = Math.floor((diff % 3600000) / 60000);
  return `${String(days).padStart(2, "0")}D ${String(hours).padStart(2, "0")}H ${String(minutes).padStart(2, "0")}M`;
}

function raceSessionTime(race?: RaceEvent | null) {
  if (!race?.sessions) return race?.date;
  return race.sessions.Race ?? race.sessions["Grand Prix"] ?? race.date;
}

function phaseLabel(phase?: string) {
  if (phase === "post_qualifying") return "post-qualifying";
  if (phase === "pre_qualifying") return "pre-qualifying";
  return "no snapshot";
}

function pointsForPosition(position: number) {
  return POINTS_BY_POSITION[position - 1] ?? 0;
}

function estimateWinPct(prediction: DriverPrediction) {
  const confidence = confidenceMidpoint(prediction);
  const pos = Math.max(1, prediction.position);
  const value = pos === 1 ? confidence * 0.62 : confidence * 0.45 * Math.pow(0.58, pos - 1);
  return Math.max(0.1, Math.min(99, value));
}

function estimatePodiumPct(prediction: DriverPrediction) {
  const confidence = confidenceMidpoint(prediction);
  const pos = Math.max(1, prediction.position);
  const value = pos <= 3
    ? confidence * 0.72 + (4 - pos) * 4
    : confidence * 0.4 * Math.pow(0.72, pos - 3);
  return Math.max(0.2, Math.min(99, value));
}

function formatPct(value: number) {
  return `${value.toFixed(value >= 10 ? 1 : 1)}%`;
}

function parseGridPosition(prediction: DriverPrediction) {
  const factors = (prediction.factors ?? []).join(" ");
  if (/pole position/i.test(factors)) return 1;
  const match = factors.match(/(?:qualifying|practice|front row start).*?P(\d+)/i)
    ?? factors.match(/P(\d+)\s*(?:in sessions)?/i);
  return match ? Number(match[1]) : null;
}

function deltaVsGrid(prediction: DriverPrediction) {
  const grid = parseGridPosition(prediction);
  if (!grid) return null;
  return grid - prediction.position;
}

function buildRiskLookup(rows: RiskPrediction[]) {
  return rows.reduce<Record<string, RiskPrediction>>((lookup, row) => {
    lookup[row.driver_code.toUpperCase()] = row;
    return lookup;
  }, {});
}

function modelStatusColor(status: string) {
  if (status === "available") return "#00FF78";
  if (status === "missing") return "#E10600";
  if (status === "limited" || status === "fallback") return "#F5C542";
  return "#3671C6";
}

function ConsolePanel({ children, className = "" }: { children: React.ReactNode; className?: string }) {
  return (
    <section className={`min-w-0 overflow-hidden rounded-md border border-[#1E2633] bg-[#0D111B] ${className}`}>
      {children}
    </section>
  );
}

function ConsoleHeader({ label, right }: { label: string; right?: React.ReactNode }) {
  return (
    <div className="flex min-h-10 items-center justify-between gap-3 border-b border-[#1E2633] bg-[#101520] px-4 py-2">
      <p className="font-mono text-[11px] font-bold uppercase tracking-[0.28em] text-[#7F8797]">{label}</p>
      {right}
    </div>
  );
}

function SeasonAccuracyStrip({
  schedule,
  selectedRound,
  data,
  onSelectRound,
}: {
  schedule: RaceEvent[];
  selectedRound: number | null;
  data?: PredictionsResponse;
  onSelectRound: (round: number) => void;
}) {
  const visible = schedule.slice(0, 12);
  const completed = schedule.filter((race) => race.status === "completed").length;
  const total = schedule.length || 0;
  const scored = data?.accuracy?.races_evaluated ?? 0;
  const window = data?.accuracy?.rolling_window ?? 8;

  return (
    <ConsolePanel>
      <ConsoleHeader
        label={`${new Date().getFullYear()} season - prediction accuracy`}
        right={<span className="font-mono text-[11px] text-[#7F8797]">{total} races / {completed} complete / {scored} of latest {window} scored</span>}
      />
      <div className="overflow-x-auto px-4 py-4">
        <div className="flex min-w-[920px] items-start justify-between gap-4">
          {visible.map((race) => {
            const active = race.round === selectedRound;
            const completedRace = race.status === "completed";
            const liveRace = race.status === "in_progress" || race.status === "live";
            const color = completedRace ? "#00FF78" : liveRace || active ? "#E10600" : "#333B49";
            const stateLabel = liveRace ? "live" : completedRace ? "scored" : active ? "selected" : "-";
            return (
              <button
                key={race.round}
                type="button"
                onClick={() => onSelectRound(race.round)}
                className="group flex w-16 shrink-0 flex-col items-center gap-2 text-center"
              >
                <span
                  className={`flex h-8 w-8 items-center justify-center rounded-full border text-[11px] transition-transform group-hover:scale-105 ${
                    active ? "ring-4 ring-[#E10600]/20" : ""
                  }`}
                  style={{ borderColor: `${color}88`, color, background: active ? `${color}22` : "transparent" }}
                >
                  {completedRace ? <Check className="h-3.5 w-3.5" /> : liveRace || active ? <CircleDot className="h-3.5 w-3.5 fill-current" /> : race.round}
                </span>
                <span className="font-mono text-[10px] font-bold uppercase tracking-[0.12em] text-[#A8AFBF]">{race.location.split(",")[0].slice(0, 3)}</span>
                <span className="font-mono text-[10px] text-[#596173]">{stateLabel}</span>
              </button>
            );
          })}
        </div>
        <div className="mt-4 flex flex-wrap gap-4 font-mono text-[10px] uppercase tracking-[0.18em] text-[#7F8797]">
          <LegendDot color="#00FF78" label="scored or complete" />
          <LegendDot color="#E10600" label="live or selected" />
          <LegendDot color="#333B49" label="future" />
        </div>
      </div>
    </ConsolePanel>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="inline-flex items-center gap-2">
      <span className="h-2 w-2 rounded-full" style={{ background: color }} />
      {label}
    </span>
  );
}

function RaceHeader({
  schedule,
  selectedRound,
  selectedRace,
  raceName,
  data,
  scheduleLoading,
  isComputing,
  computeReason,
  onSelectRound,
  onRun,
  onQualifyingRecompute,
}: {
  schedule: RaceEvent[];
  selectedRound: number | null;
  selectedRace: RaceEvent | null;
  raceName: string;
  data?: PredictionsResponse;
  scheduleLoading: boolean;
  isComputing: boolean;
  computeReason: "manual_compute" | "qualifying_recompute" | null;
  onSelectRound: (round: number) => void;
  onRun: () => void;
  onQualifyingRecompute: () => void;
}) {
  const raceTime = raceSessionTime(selectedRace);
  const countdown = countdownTo(raceTime);

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <select
            value={selectedRound ?? ""}
            onChange={(event) => onSelectRound(Number(event.target.value))}
            disabled={scheduleLoading || schedule.length === 0}
            className="h-10 rounded-md border border-[#1E2633] bg-[#0D111B] px-3 font-mono text-xs font-bold text-[#D7DBE7] outline-none focus:border-[#E10600]/70 disabled:text-[#596173]"
            aria-label="Select race"
          >
            <option value="">{scheduleLoading ? "Loading calendar..." : "Select race"}</option>
            {schedule.map((race) => (
              <option key={race.round} value={race.round}>
                {race.name} - Round {race.round}
              </option>
            ))}
          </select>
          <span className="hidden font-mono text-xs text-[#596173] sm:inline">/</span>
          <span className="font-mono text-xs text-[#8E96A8]">{phaseLabel(data?.prediction_phase)}</span>
        </div>

        <div className="flex flex-wrap gap-2">
          <button
            onClick={onRun}
            disabled={!selectedRound || isComputing}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-[#00FF78]/35 bg-[#00FF78]/10 px-3 font-mono text-[11px] font-bold uppercase tracking-[0.16em] text-[#00FF78] transition-colors hover:bg-[#00FF78] hover:text-black disabled:cursor-not-allowed disabled:border-white/10 disabled:bg-white/[0.03] disabled:text-[#596173]"
          >
            <Sparkles className="h-3.5 w-3.5" />
            {computeReason === "manual_compute" ? "running" : "run model"}
          </button>
          <button
            onClick={onQualifyingRecompute}
            disabled={!selectedRound || isComputing}
            className="inline-flex h-10 items-center justify-center gap-2 rounded-md border border-[#E10600]/35 bg-[#E10600]/10 px-3 font-mono text-[11px] font-bold uppercase tracking-[0.16em] text-[#FF6B67] transition-colors hover:bg-[#E10600] hover:text-white disabled:cursor-not-allowed disabled:border-white/10 disabled:bg-white/[0.03] disabled:text-[#596173]"
          >
            <RefreshCw className="h-3.5 w-3.5" />
            {computeReason === "qualifying_recompute" ? "recomputing" : "after quali"}
          </button>
        </div>
      </div>

      <div className="flex flex-col gap-3 border-b border-[#1E2633] pb-4 lg:flex-row lg:items-end lg:justify-between">
        <div>
          <h1 className="text-3xl font-black leading-tight text-white sm:text-4xl" style={rcFont}>{raceName}</h1>
          <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1 font-mono text-xs text-[#8E96A8]">
            <span>{selectedRace?.location ?? "location TBC"}</span>
            <span>Round {selectedRound ?? data?.round ?? "-"}/{data?.year ?? new Date().getFullYear()}</span>
            <span>Race {formatDate(raceTime)} - {formatTime(raceTime)}</span>
            <span>status <b className="text-white">{selectedRace?.status ?? "unknown"}</b></span>
          </div>
        </div>
        {countdown && (
          <div className="w-fit rounded-full border border-[#E10600]/40 bg-[#E10600]/10 px-4 py-2 font-mono text-xs font-bold uppercase tracking-[0.18em] text-white shadow-[0_0_24px_rgba(225,6,0,0.12)]">
            lights out in <span className="text-[#FF4655]">{countdown}</span>
          </div>
        )}
      </div>
    </div>
  );
}

function TabBar({ activeTab, setActiveTab }: { activeTab: TabKey; setActiveTab: (tab: TabKey) => void }) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-[#1E2633]">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          onClick={() => setActiveTab(tab.key)}
          className={`relative shrink-0 px-4 py-3 text-sm transition-colors ${
            activeTab === tab.key ? "text-white" : "text-[#6F7789] hover:text-[#D7DBE7]"
          }`}
        >
          <span className="inline-flex items-center gap-1.5">
            {tab.label}
            {tab.locked && <LockKeyhole className="h-3 w-3 text-[#C6A24B]" />}
          </span>
          {activeTab === tab.key && <span className="absolute inset-x-0 bottom-0 h-[2px] bg-[#E10600]" />}
        </button>
      ))}
    </div>
  );
}

function FullGridTable({
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
        right={<span className="font-mono text-[10px] uppercase tracking-[0.18em] text-[#7F8797]">P1-P22 / pts / win / podium / vs grid</span>}
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
                <tr key={prediction.driver_code} className="bg-[#0D111B] text-sm text-[#B7BDCA] transition-colors hover:bg-[#121825]">
                  <td className="px-4 py-3 font-mono text-[#8E96A8]">P{prediction.position}</td>
                  <td className="px-4 py-3">
                    <div className="flex min-w-0 items-center gap-3">
                      <span className="h-5 w-[3px] rounded-full" style={{ background: color }} />
                      <span className="font-mono text-sm font-black uppercase tracking-[0.08em] text-white">{prediction.driver_code}</span>
                      <span className="truncate text-[#AEB5C5]">{shortName(name)}</span>
                    </div>
                  </td>
                  <td className="px-4 py-3 text-[#AEB5C5]">{prediction.team || "-"}</td>
                  <td className="px-4 py-3 text-right font-mono text-[#7F8797]">{risk ? `${risk.dnf_risk_pct}%` : "-"}</td>
                  <td className="px-4 py-3 text-right font-mono text-white">{pointsForPosition(prediction.position)}</td>
                  <td className="px-4 py-3 text-right font-mono font-bold text-white">{formatPct(estimateWinPct(prediction))}</td>
                  <td className="px-4 py-3 text-right font-mono font-bold text-white">{formatPct(estimatePodiumPct(prediction))}</td>
                  <td className={`px-4 py-3 text-right font-mono font-bold ${delta == null ? "text-[#3F4756]" : delta > 0 ? "text-[#00FF78]" : delta < 0 ? "text-[#FF4655]" : "text-[#D7DBE7]"}`}>
                    {delta == null ? "-" : delta > 0 ? `+${delta}` : String(delta)}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-[#7F8797]">{risk ? `${risk.crash_risk_pct}%` : "-"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </ConsolePanel>
  );
}

function PodiumPanel({
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
          right={<span className="font-mono text-[10px] text-[#7F8797]">{data?.model_summary?.average_top3_confidence ?? "-"}% confidence</span>}
        />
        <div className="space-y-3 p-4">
          {podium.length ? podium.map((prediction, index) => {
            const color = getTeamColor(prediction.team);
            return (
              <div key={prediction.driver_code} className="flex items-center gap-4 rounded-md bg-[#151B28] px-4 py-3">
                <span className="w-9 font-mono text-sm font-black text-[#F5C542]">P{index + 1}</span>
                <span className="h-9 w-[3px] rounded-full" style={{ background: color }} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-bold text-white">{driverDisplayName(prediction, driverLookup)}</p>
                  <p className="truncate font-mono text-[11px] text-[#6F7789]">{prediction.team} - {prediction.driver_code}</p>
                </div>
                <p className="font-mono text-xl font-black text-white">{formatPct(estimatePodiumPct(prediction))}</p>
              </div>
            );
          }) : (
            <p className="p-4 text-sm text-[#7F8797]">Run the model to create a podium snapshot.</p>
          )}
        </div>
      </ConsolePanel>
    </div>
  );
}

function CircuitPanel({ selectedRace, data }: { selectedRace: RaceEvent | null; data?: PredictionsResponse }) {
  const circuit = selectedRace?.circuit;
  const sessions = Object.entries(selectedRace?.sessions ?? {});

  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_1fr]">
      <ConsolePanel>
        <ConsoleHeader label="This weekend" right={<span className="font-mono text-[10px] text-[#7F8797]">{circuit?.circuit_name ?? selectedRace?.location ?? "circuit TBC"}</span>} />
        <dl className="divide-y divide-[#1E2633] p-4 font-mono text-sm">
          <InfoRow label="Circuit" value={circuit?.circuit_name ?? selectedRace?.location ?? "-"} />
          <InfoRow label="Length" value={circuit?.length_km ? `${circuit.length_km} km` : circuit?.laps ? `${circuit.laps} laps` : "-"} />
          <InfoRow label="Type" value={circuit?.circuit_type ?? "-"} />
          <InfoRow label="Race" value={`${formatDate(raceSessionTime(selectedRace))} - ${formatTime(raceSessionTime(selectedRace))}`} />
          <InfoRow label="Status" value={selectedRace?.status ?? "-"} />
        </dl>
      </ConsolePanel>

      <ConsolePanel>
        <ConsoleHeader label="Session schedule" right={<span className="font-mono text-[10px] text-[#7F8797]">{sessions.length ? `${sessions.length} sessions` : "times TBC"}</span>} />
        <div className="divide-y divide-[#1E2633] p-4 font-mono text-sm">
          {sessions.length ? sessions.map(([label, value]) => (
            <InfoRow key={label} label={label} value={`${formatDate(value)} - ${formatTime(value)}`} />
          )) : (
            <p className="text-sm text-[#7F8797]">Session times have not been returned for this event.</p>
          )}
        </div>
      </ConsolePanel>

      <ConsolePanel className="xl:col-span-2">
        <ConsoleHeader label="Model stats" right={<span className="font-mono text-[10px] text-[#7F8797]">{data?.cache?.snapshot_id ?? "no snapshot"}</span>} />
        <div className="grid grid-cols-2 gap-6 p-4 md:grid-cols-4">
          <StatBlock label="Avg error" value={data?.accuracy?.avg_position_error == null ? "-" : String(data.accuracy.avg_position_error)} detail="positions across scored predictions" />
          <StatBlock label="Top 3 hit" value={data?.accuracy?.recent_top3_pct == null ? "-" : `${data.accuracy.recent_top3_pct}%`} detail={`latest ${data?.accuracy?.rolling_window ?? 8} scored max`} />
          <StatBlock label="Validated" value={String(data?.accuracy?.races_evaluated ?? 0)} detail="prediction/result pairs available" />
          <StatBlock label="Updated" value={formatSnapshotTime(data?.cache?.updated_at ?? data?.generated_at)} detail={data?.cache?.reason ?? "snapshot"} />
        </div>
      </ConsolePanel>
    </div>
  );
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4 py-3">
      <dt className="text-[#6F7789]">{label}</dt>
      <dd className="truncate text-right font-bold text-white">{value}</dd>
    </div>
  );
}

function StatBlock({ label, value, detail }: { label: string; value: string; detail: string }) {
  return (
    <div>
      <p className="font-mono text-[10px] uppercase tracking-[0.22em] text-[#6F7789]">{label}</p>
      <p className="mt-1 font-mono text-3xl font-black text-white">{value}</p>
      <p className="mt-1 text-xs text-[#6F7789]">{detail}</p>
    </div>
  );
}

function RiskTable({ rows }: { rows: RiskPrediction[] }) {
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
                <td className="px-4 py-3 font-mono font-bold text-white">{risk.driver_code} <span className="font-sans font-normal text-[#8E96A8]">{shortName(risk.driver_name)}</span></td>
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
        <p className="p-4 text-sm text-[#7F8797]">Run or recompute the model to generate DNF, crash, and mechanical risk rows.</p>
      )}
    </ConsolePanel>
  );
}

function ModelIO({ data }: { data?: PredictionsResponse }) {
  const inputs = data?.model_inputs ?? [];
  return (
    <div className="grid gap-4 xl:grid-cols-[1.2fr_0.8fr]">
      <ConsolePanel>
        <ConsoleHeader label="Inputs used" right={<BrainCircuit className="h-4 w-4 text-[#3671C6]" />} />
        <div className="divide-y divide-[#1E2633]">
          {inputs.length ? inputs.map((input) => (
            <div key={input.label} className="grid gap-3 px-4 py-4 md:grid-cols-[190px_minmax(0,1fr)_120px] md:items-start">
              <div>
                <p className="font-mono text-xs font-bold uppercase tracking-[0.16em] text-white">{input.label}</p>
                <p className="mt-1 text-xs text-[#596173]">{input.source}</p>
              </div>
              <p className="text-sm leading-relaxed text-[#AEB5C5]">{input.impact}</p>
              <span
                className="w-fit rounded border px-2 py-1 font-mono text-[10px] font-bold uppercase tracking-[0.16em]"
                style={{ color: modelStatusColor(input.status), borderColor: `${modelStatusColor(input.status)}55`, background: `${modelStatusColor(input.status)}14` }}
              >
                {input.status}
              </span>
            </div>
          )) : (
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

function ResultsReview({ review, accuracy }: { review?: PredictionReview; accuracy?: PredictionsResponse["accuracy"] }) {
  return (
    <ConsolePanel>
      <ConsoleHeader
        label={review?.evaluated ? "Post-race review" : "Rolling accuracy"}
        right={<StatusPill color={review?.winner_correct ? "#00FF78" : review?.evaluated ? "#E10600" : "#3671C6"}>{review?.evaluated ? (review.winner_correct ? "winner hit" : "winner miss") : `${accuracy?.races_evaluated ?? 0} scored predictions`}</StatusPill>}
      />
      {review?.evaluated ? (
        <div className="grid gap-4 p-4 sm:grid-cols-2 xl:grid-cols-3">
          <StatBlock label="Top 3" value={`${review.top3_correct ?? 0}/${review.top3_possible ?? 3}`} detail="predicted podium overlap" />
          <StatBlock label="Top 10" value={`${review.top10_correct ?? 0}/${review.top10_possible ?? 10}`} detail="points finish overlap" />
          <StatBlock label="Exact" value={`${review.exact_position_hits ?? 0}/${review.drivers_compared ?? 0}`} detail="exact finishing positions" />
          <StatBlock label="Avg error" value={`${review.avg_position_error ?? 0}`} detail="positions per compared driver" />
          <StatBlock label="DNF calls" value={`${review.dnf_correct ?? 0}/${review.dnf_actual ?? 0}`} detail="captured actual retirements" />
          <StatBlock label="Crash calls" value={`${review.crash_correct ?? 0}/${review.crash_actual ?? 0}`} detail="captured accident outcomes" />
        </div>
      ) : (
        <div className="grid gap-4 p-4 sm:grid-cols-2 xl:grid-cols-3">
          <StatBlock label="Winner" value={`${accuracy?.recent_winner_pct ?? 0}%`} detail={`latest ${accuracy?.rolling_window ?? 8} scored max`} />
          <StatBlock label="Top 3" value={`${accuracy?.recent_top3_pct ?? 0}%`} detail={`latest ${accuracy?.rolling_window ?? 8} scored max`} />
          <StatBlock label="Top 10" value={`${accuracy?.recent_top10_pct ?? 0}%`} detail={`latest ${accuracy?.rolling_window ?? 8} scored max`} />
          <StatBlock label="Avg error" value={`${accuracy?.avg_position_error ?? 0}`} detail="positions per driver" />
          <StatBlock label="DNF capture" value={accuracy?.dnf_capture_pct == null ? "n/a" : `${accuracy.dnf_capture_pct}%`} detail="actual DNF capture" />
          <StatBlock label="Crash capture" value={accuracy?.crash_capture_pct == null ? "n/a" : `${accuracy.crash_capture_pct}%`} detail="actual crash capture" />
        </div>
      )}
    </ConsolePanel>
  );
}

function StandbyPanel({ raceName, onRun, isComputing }: { raceName: string; onRun: () => void; isComputing: boolean }) {
  return (
    <ConsolePanel>
      <div className="flex flex-col gap-4 p-6 lg:flex-row lg:items-center lg:justify-between">
        <div>
          <p className="font-mono text-[11px] font-bold uppercase tracking-[0.24em] text-[#E10600]">No stored prediction</p>
          <h2 className="mt-2 text-3xl font-black text-white" style={rcFont}>{raceName}</h2>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-[#8E96A8]">
            Run the model when you want to create a saved snapshot. The snapshot stays fixed until you manually recompute it.
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

export interface RacePredictionBoardProps {
  schedule: RaceEvent[];
  scheduleError: boolean;
  scheduleLoading: boolean;
  selectedRound: number | null;
  selectedRace: RaceEvent | null;
  data?: PredictionsResponse;
  predictions: DriverPrediction[];
  riskPredictions: RiskPrediction[];
  podium: DriverPrediction[];
  drivers: DriverStanding[];
  driversError: boolean;
  raceName: string;
  predictionLoading: boolean;
  predictionError: boolean;
  isComputing: boolean;
  computeReason: "manual_compute" | "qualifying_recompute" | null;
  onSelectRound: (round: number) => void;
  onRun: () => void;
  onQualifyingRecompute: () => void;
  onRetry: () => void;
  onReloadSchedule: () => void;
  onReloadDrivers: () => void;
}

export function RacePredictionBoard({
  schedule,
  scheduleError,
  scheduleLoading,
  selectedRound,
  selectedRace,
  data,
  predictions,
  riskPredictions,
  podium,
  drivers,
  driversError,
  raceName,
  predictionLoading,
  predictionError,
  isComputing,
  computeReason,
  onSelectRound,
  onRun,
  onQualifyingRecompute,
  onRetry,
  onReloadSchedule,
  onReloadDrivers,
}: RacePredictionBoardProps) {
  const [activeTab, setActiveTab] = useState<TabKey>("predictions");
  const driverLookup = useMemo(() => buildDriverLookup(drivers), [drivers]);

  return (
    <div className="space-y-4">
      <SeasonAccuracyStrip schedule={schedule} selectedRound={selectedRound} data={data} onSelectRound={onSelectRound} />

      <RaceHeader
        schedule={schedule}
        selectedRound={selectedRound}
        selectedRace={selectedRace}
        raceName={raceName}
        data={data}
        scheduleLoading={scheduleLoading}
        isComputing={isComputing}
        computeReason={computeReason}
        onSelectRound={onSelectRound}
        onRun={onRun}
        onQualifyingRecompute={onQualifyingRecompute}
      />

      <TabBar activeTab={activeTab} setActiveTab={setActiveTab} />

      {scheduleError && (
        <InlineNotice title="Race calendar unavailable" tone="error">
          The race list could not be loaded.
          <button onClick={onReloadSchedule} className="ml-2 font-bold text-white underline decoration-white/30">Retry</button>
        </InlineNotice>
      )}

      {driversError && (
        <InlineNotice title="Driver standings unavailable" tone="warning">
          Driver-name lookups may be limited.
          <button onClick={onReloadDrivers} className="ml-2 font-bold text-white underline decoration-white/30">Retry</button>
        </InlineNotice>
      )}

      {predictionLoading && (
        <SectionLoader title="Loading stored snapshot" detail="Checking whether this Grand Prix already has a saved prediction." />
      )}

      {!predictionLoading && predictionError && predictions.length === 0 && (
        <ConsolePanel>
          <div className="flex items-start gap-4 p-6">
            <AlertTriangle className="mt-1 h-5 w-5 text-[#E10600]" />
            <div>
              <h2 className="text-xl font-black text-white" style={rcFont}>No Prediction Snapshot</h2>
              <p className="mt-2 text-sm text-[#8E96A8]">{data?.error ?? "The stored prediction could not be loaded."}</p>
              <div className="mt-4 flex flex-wrap gap-2">
                <button onClick={onRetry} className="rounded-md border border-[#1E2633] bg-white/[0.03] px-3 py-2 font-mono text-[11px] uppercase tracking-[0.16em] text-[#AEB5C5] hover:text-white">
                  check again
                </button>
                <button onClick={onRun} disabled={isComputing} className="rounded-md border border-[#00FF78]/35 bg-[#00FF78]/10 px-3 py-2 font-mono text-[11px] uppercase tracking-[0.16em] text-[#00FF78] hover:bg-[#00FF78] hover:text-black disabled:opacity-50">
                  run model
                </button>
              </div>
            </div>
          </div>
        </ConsolePanel>
      )}

      {isComputing && (
        <SectionLoader
          title={computeReason === "qualifying_recompute" ? "Recomputing after qualifying" : "Running prediction model"}
          detail="Building a fresh stored snapshot with finish order, model I/O, accuracy, and incident risk."
        />
      )}

      {!predictionLoading && predictions.length === 0 && !predictionError && (
        <StandbyPanel raceName={raceName} onRun={onRun} isComputing={isComputing} />
      )}

      {!predictionLoading && predictions.length > 0 && (
        <>
          {activeTab === "predictions" && (
            <FullGridTable predictions={predictions} riskPredictions={riskPredictions} driverLookup={driverLookup} />
          )}
          {activeTab === "podium" && (
            <PodiumPanel podium={podium} driverLookup={driverLookup} data={data} />
          )}
          {activeTab === "circuit" && (
            <CircuitPanel selectedRace={selectedRace} data={data} />
          )}
          {activeTab === "risk" && (
            <RiskTable rows={riskPredictions} />
          )}
          {activeTab === "model" && (
            <ModelIO data={data} />
          )}
          {activeTab === "results" && (
            <ResultsReview review={data?.prediction_review} accuracy={data?.accuracy} />
          )}
        </>
      )}

      {data?.warnings?.length ? (
        <InlineNotice title="Prediction notes" tone="warning">
          {data.warnings.slice(0, 2).join(" ")}
        </InlineNotice>
      ) : null}
    </div>
  );
}
