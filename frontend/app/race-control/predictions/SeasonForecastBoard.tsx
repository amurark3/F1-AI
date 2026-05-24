"use client";

import { AlertTriangle, BarChart3, BrainCircuit, Gauge, Trophy } from "lucide-react";
import { getTeamColor } from "@/app/components/PredictionDriverCard";
import { InlineNotice, MetricCard, MetricRow, Panel, SectionLoader, StatusPill, WorkspaceSplit, rcFont } from "../components/RaceControlPrimitives";
import { SeasonProjectionChart } from "../components/Charts";

interface ForecastRow {
  key: string;
  code?: string | null;
  name: string;
  team: string;
  current_position: number;
  projected_position: number;
  position_delta: number;
  current_points: number;
  projected_points: number;
  wins: number;
  season_points_per_event: number;
  recent_points_per_event: number;
  trend: "Gaining" | "Holding" | "Sliding" | string;
  confidence: string;
}

interface ForecastResponse {
  year: number;
  completed_events: number;
  remaining_events: number;
  recent_window: number;
  drivers: ForecastRow[];
  constructors: ForecastRow[];
  notes?: string[];
  error?: string | null;
}

function pointsLabel(points: number) {
  return Number.isInteger(points) ? String(points) : points.toFixed(1);
}

function positionDeltaLabel(delta: number) {
  if (delta > 0) return `+${delta}`;
  if (delta < 0) return String(delta);
  return "-";
}

function forecastConfidence(data?: ForecastResponse) {
  if (!data) return "Pending";
  if (data.recent_window >= 3) return "Medium";
  if (data.recent_window > 0) return "Low";
  return "Standings only";
}

function MiniForecastFact({ label, value, tone }: { label: string; value: string; tone?: string }) {
  const color = tone === "Gaining" ? "#00FF78" : tone === "Sliding" ? "#E10600" : "#D4D4D4";
  return (
    <div className="rounded border border-white/8 bg-black/15 px-3 py-2">
      <p className="text-[10px] font-black uppercase tracking-[0.14em] text-neutral-500">{label}</p>
      <p className="mt-1 text-sm font-bold" style={{ color }}>{value}</p>
    </div>
  );
}

function ForecastRowCard({ row, type }: { row: ForecastRow; type: "driver" | "constructor" }) {
  const color = getTeamColor(row.team);
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.03] p-3">
      <div className="flex items-center gap-3">
        <div className="w-12 shrink-0 text-center">
          <p className="text-lg font-black italic text-white" style={rcFont}>P{row.projected_position}</p>
          <p className={row.position_delta > 0 ? "text-[10px] text-[#00FF78]" : row.position_delta < 0 ? "text-[10px] text-[#E10600]" : "text-[10px] text-neutral-500"}>
            {positionDeltaLabel(row.position_delta)}
          </p>
        </div>
        <span className="h-9 w-1.5 shrink-0 rounded-full" style={{ background: color }} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            {type === "driver" && row.code ? <span className="rounded px-2 py-0.5 text-xs font-black" style={{ color, background: `${color}20` }}>{row.code}</span> : null}
            <p className="truncate text-sm font-bold text-white">{row.name}</p>
          </div>
          <p className="mt-0.5 truncate text-xs font-semibold" style={{ color }}>{row.team}</p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-sm font-black text-white" style={rcFont}>{pointsLabel(row.projected_points)}</p>
          <p className="text-[10px] text-neutral-500">from {pointsLabel(row.current_points)}</p>
        </div>
      </div>
      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        <MiniForecastFact label="Season rate" value={`${pointsLabel(row.season_points_per_event)}/GP`} />
        <MiniForecastFact label="Recent form" value={`${pointsLabel(row.recent_points_per_event)}/GP`} />
        <MiniForecastFact label="Trend" value={row.trend} tone={row.trend} />
      </div>
    </div>
  );
}

function ForecastTable({ title, rows, type }: { title: string; rows: ForecastRow[]; type: "driver" | "constructor" }) {
  return (
    <Panel className="p-5">
      <div className="mb-5 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.18em] text-neutral-400" style={rcFont}>{type === "driver" ? "WDC" : "WCC"}</p>
          <h2 className="text-2xl font-black italic uppercase text-white" style={rcFont}>{title}</h2>
        </div>
        <StatusPill>{rows.length} entries</StatusPill>
      </div>
      <div className="space-y-2">
        {rows.length > 0 ? rows.map((row) => (
          <ForecastRowCard key={row.key} row={row} type={type} />
        )) : (
          <p className="text-sm text-neutral-500">Forecast rows are not available yet.</p>
        )}
      </div>
    </Panel>
  );
}

export interface SeasonForecastBoardProps {
  data?: ForecastResponse;
  isLoading: boolean;
  error: unknown;
  onRetry: () => void;
}

export function SeasonForecastBoard({ data, isLoading, error, onRetry }: SeasonForecastBoardProps) {
  if (isLoading && !data) {
    return (
      <SectionLoader
        title="Building championship forecast"
        detail="Combining current standings with recent race form for WDC and WCC projections."
      />
    );
  }

  if (error || data?.error) {
    return (
      <Panel className="p-8">
        <div className="flex items-start gap-4">
          <AlertTriangle className="mt-1 h-6 w-6 text-[#E10600]" />
          <div>
            <h2 className="text-2xl font-black italic uppercase text-white" style={rcFont}>Forecast Unavailable</h2>
            <p className="mt-2 text-base text-neutral-400">
              {data?.error ?? "The championship forecast could not be refreshed."}
            </p>
            <button onClick={onRetry} className="mt-5 rounded-lg border border-white/10 bg-white/[0.04] px-4 py-2 text-sm font-bold text-neutral-200 hover:text-white">
              Retry Forecast
            </button>
          </div>
        </div>
      </Panel>
    );
  }

  const driverLeader = data?.drivers?.[0];
  const constructorLeader = data?.constructors?.[0];

  const projectionChartData = (data?.drivers ?? []).slice(0, 10).map((row) => ({
    name: row.name,
    code: row.code ?? row.name.slice(0, 3).toUpperCase(),
    current: row.current_points,
    projected: row.projected_points,
    color: getTeamColor(row.team),
  }));

  return (
    <div className="space-y-5">
      <Panel className="p-5" accent="#00FF78">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <p className="text-xs font-black uppercase tracking-[0.18em] text-neutral-400" style={rcFont}>Automatic Season Projection</p>
            <h2 className="text-3xl font-black italic uppercase text-white leading-tight" style={rcFont}>WDC & WCC Forecast</h2>
            <p className="mt-2 max-w-4xl text-sm leading-relaxed text-neutral-400">
              Current points plus a blended season-rate and recent-form rate across remaining Grands Prix.
            </p>
          </div>
          <div className="flex flex-wrap gap-2 lg:justify-end">
            <StatusPill>{data?.completed_events ?? 0} completed</StatusPill>
            <StatusPill color="#3671C6">{data?.remaining_events ?? 0} remaining</StatusPill>
            <StatusPill color="#FF8000">last {data?.recent_window ?? 0} loaded GP</StatusPill>
          </div>
        </div>
      </Panel>

      <MetricRow>
        <MetricCard label="Projected WDC" value={driverLeader?.name ?? "No driver forecast"} sub={driverLeader ? `${driverLeader.team} · ${pointsLabel(driverLeader.projected_points)} pts` : "Awaiting standings"} icon={Trophy} />
        <MetricCard label="Projected WCC" value={constructorLeader?.name ?? "No constructor forecast"} sub={constructorLeader ? `${pointsLabel(constructorLeader.projected_points)} pts` : "Awaiting standings"} icon={BarChart3} color="#E10600" />
        <MetricCard label="Driver Form" value={driverLeader ? `${pointsLabel(driverLeader.recent_points_per_event)}/GP` : "No data"} sub="Leader recent scoring rate" icon={Gauge} color="#3671C6" />
        <MetricCard label="Forecast Confidence" value={forecastConfidence(data)} sub="Based on loaded recent races" icon={BrainCircuit} color="#BE3AFF" />
      </MetricRow>

      {projectionChartData.length > 0 && (
        <Panel className="p-5">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.18em] text-neutral-400" style={rcFont}>WDC Trajectory</p>
              <h2 className="text-xl font-black text-white" style={rcFont}>Current vs Projected Points</h2>
            </div>
            <StatusPill color="#3671C6">Top 10 drivers</StatusPill>
          </div>
          <SeasonProjectionChart data={projectionChartData} height={280} />
        </Panel>
      )}

      <WorkspaceSplit className="xl:[&>*:first-child]:basis-[54%] xl:[&>*:last-child]:flex-1">
        <ForecastTable title="Drivers' Championship Forecast" rows={data?.drivers ?? []} type="driver" />
        <ForecastTable title="Constructors' Championship Forecast" rows={data?.constructors ?? []} type="constructor" />
      </WorkspaceSplit>

      {data?.notes?.length ? (
        <InlineNotice title="Forecast Notes" tone="warning">
          <ul className="list-disc space-y-1 pl-4">
            {data.notes.map((note) => <li key={note}>{note}</li>)}
          </ul>
        </InlineNotice>
      ) : null}
    </div>
  );
}
