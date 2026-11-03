"use client";

import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Cell,
  ReferenceLine,
} from "recharts";

import { rc } from "@/app/ui/tokens";

import { rcFont } from "./RaceControlPrimitives";

const CHART_COLORS = {
  grid: "rgba(255,255,255,0.06)",
  axis: "rgba(255,255,255,0.25)",
  tooltip: { bg: "#0F1210", border: "rgba(255,255,255,0.12)" },
};

function ChartTooltipContainer({ children }: { children: React.ReactNode }) {
  return (
    <div
      className="rounded-lg border px-3 py-2 text-sm shadow-xl"
      style={{ background: CHART_COLORS.tooltip.bg, borderColor: CHART_COLORS.tooltip.border }}
    >
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Championship points horizontal bar chart
// ---------------------------------------------------------------------------
interface ChampionshipEntry {
  name: string;
  points: number;
  color: string;
  position: number;
}

/** Shared shape behind both the constructor and driver standings tooltips. */
interface PointsStandingEntry {
  name: string;
  points: number;
  position: number;
}

function PointsStandingTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: Array<{ payload: PointsStandingEntry }>;
}) {
  if (!active || !payload?.length) return null;
  const entry = payload[0].payload;
  return (
    <ChartTooltipContainer>
      <p className="font-black uppercase tracking-wider text-white" style={rcFont}>
        {entry.name}
      </p>
      <p className="mt-0.5 font-mono text-neutral-300">
        {entry.points} pts · P{entry.position}
      </p>
    </ChartTooltipContainer>
  );
}

export function ChampionshipBarChart({ data, height = 320 }: { data: ChampionshipEntry[]; height?: number }) {
  const sorted = [...data].sort((a, b) => a.position - b.position);
  const leader = sorted[0];

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={sorted} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} horizontal={false} />
        <XAxis
          type="number"
          domain={[0, (leader?.points ?? 100) * 1.1]}
          tick={{ fill: CHART_COLORS.axis, fontSize: 11 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v: number) => String(v)}
        />
        <YAxis
          type="category"
          dataKey="name"
          width={96}
          tick={{ fill: "#d4d4d4", fontSize: 11, fontWeight: 700 }}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip content={<PointsStandingTooltip />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
        <Bar dataKey="points" radius={[0, 4, 4, 0]} maxBarSize={20}>
          {sorted.map((entry) => (
            <Cell key={entry.name} fill={entry.color} fillOpacity={0.9} />
          ))}
        </Bar>
        {leader && <ReferenceLine x={leader.points} stroke="rgba(255,255,255,0.15)" strokeDasharray="4 4" />}
      </BarChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// Driver points grouped bar chart (WDC)
// ---------------------------------------------------------------------------
interface DriverChampionshipEntry {
  name: string;
  code: string;
  points: number;
  color: string;
  position: number;
}

export function DriverChampionshipChart({ data, height = 280 }: { data: DriverChampionshipEntry[]; height?: number }) {
  // Presentational only: callers decide which drivers are in frame.
  const sorted = [...data].sort((a, b) => a.position - b.position);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={sorted} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} vertical={false} />
        <XAxis
          dataKey="code"
          tick={{ fill: "#d4d4d4", fontSize: 10, fontWeight: 700 }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis tick={{ fill: CHART_COLORS.axis, fontSize: 10 }} axisLine={false} tickLine={false} width={36} />
        <Tooltip content={<PointsStandingTooltip />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
        <Bar dataKey="points" radius={[3, 3, 0, 0]} maxBarSize={28}>
          {sorted.map((entry) => (
            <Cell key={entry.code} fill={entry.color} fillOpacity={0.9} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// Model attribution — exact per-feature contributions to one driver's
// predicted finish (from the linear model). Negative = improves the projection
// (gain green: places gained); positive = worsens it (red). This is generative UI over the
// structured `model_attribution` the prediction API returns.
// ---------------------------------------------------------------------------
export interface AttributionEntry {
  label: string;
  contribution: number;
}

/** Places gained in the projection: the gain token, never DRS green. */
const ATTRIBUTION_HELP = rc.gain;
const ATTRIBUTION_HURT = rc.redText;

function AttributionTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: AttributionEntry }> }) {
  if (!active || !payload?.length) return null;
  const entry = payload[0].payload;
  const helps = entry.contribution < 0;
  return (
    <ChartTooltipContainer>
      <p className="font-black uppercase tracking-wider text-white" style={rcFont}>
        {entry.label}
      </p>
      <p className="mt-0.5 font-mono text-sm" style={{ color: helps ? ATTRIBUTION_HELP : ATTRIBUTION_HURT }}>
        {helps ? "improves" : "worsens"} projection by {Math.abs(entry.contribution).toFixed(2)} places
      </p>
    </ChartTooltipContainer>
  );
}

export function ModelAttributionBars({ data, height = 200 }: { data: AttributionEntry[]; height?: number }) {
  if (!data.length) return null;
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} layout="vertical" margin={{ top: 4, right: 16, bottom: 4, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} horizontal={false} />
        <XAxis type="number" tick={{ fill: CHART_COLORS.axis, fontSize: 10 }} axisLine={false} tickLine={false} />
        <YAxis
          type="category"
          dataKey="label"
          tick={{ fill: "#AEB5C5", fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          width={120}
        />
        <Tooltip content={<AttributionTooltip />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
        <ReferenceLine x={0} stroke={CHART_COLORS.axis} />
        <Bar dataKey="contribution" radius={[2, 2, 2, 2]} maxBarSize={16}>
          {data.map((entry) => (
            <Cell
              key={entry.label}
              fill={entry.contribution < 0 ? ATTRIBUTION_HELP : ATTRIBUTION_HURT}
              fillOpacity={0.85}
            />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
