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
  Legend,
} from "recharts";

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
  const top10 = [...data].sort((a, b) => a.position - b.position).slice(0, 10);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={top10} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
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
          {top10.map((entry) => (
            <Cell key={entry.code} fill={entry.color} fillOpacity={0.9} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// Confidence interval range chart for predictions
// ---------------------------------------------------------------------------
interface ConfidenceEntry {
  code: string;
  low: number;
  mid: number;
  high: number;
  color: string;
}

function ConfidenceTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: ConfidenceEntry }> }) {
  if (!active || !payload?.length) return null;
  const entry = payload[0].payload;
  return (
    <ChartTooltipContainer>
      <p className="font-black uppercase tracking-wider text-white" style={rcFont}>
        {entry.code}
      </p>
      <p className="mt-0.5 font-mono text-neutral-300">
        {entry.mid}% · range {entry.low}–{entry.high}%
      </p>
    </ChartTooltipContainer>
  );
}

export function ConfidenceBarChart({ data, height = 220 }: { data: ConfidenceEntry[]; height?: number }) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} vertical={false} />
        <XAxis
          dataKey="code"
          tick={{ fill: "#d4d4d4", fontSize: 10, fontWeight: 700 }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          domain={[0, 100]}
          tick={{ fill: CHART_COLORS.axis, fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          width={32}
          tickFormatter={(v: number) => `${v}%`}
        />
        <Tooltip content={<ConfidenceTooltip />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
        <Bar dataKey="mid" radius={[3, 3, 0, 0]} maxBarSize={24}>
          {data.map((entry) => (
            <Cell key={entry.code} fill={entry.color} fillOpacity={0.85} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// Season projection area chart — current vs projected points
// ---------------------------------------------------------------------------
interface ProjectionEntry {
  name: string;
  current: number;
  projected: number;
  color: string;
  code?: string;
}

function ProjectionTooltip({
  active,
  payload,
  label,
}: {
  active?: boolean;
  payload?: Array<{ name: string; value: number; color: string }>;
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <ChartTooltipContainer>
      <p className="mb-1 font-black uppercase tracking-wider text-white" style={rcFont}>
        {label}
      </p>
      {payload.map((p) => (
        <p key={p.name} className="font-mono text-sm" style={{ color: p.color }}>
          {p.name}: {p.value} pts
        </p>
      ))}
    </ChartTooltipContainer>
  );
}

export function SeasonProjectionChart({ data, height = 300 }: { data: ProjectionEntry[]; height?: number }) {
  const top8 = data.slice(0, 8);

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={top8} margin={{ top: 4, right: 8, bottom: 4, left: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} vertical={false} />
        <XAxis
          dataKey="code"
          tick={{ fill: "#d4d4d4", fontSize: 10, fontWeight: 700 }}
          axisLine={false}
          tickLine={false}
        />
        <YAxis tick={{ fill: CHART_COLORS.axis, fontSize: 10 }} axisLine={false} tickLine={false} width={40} />
        <Tooltip content={<ProjectionTooltip />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
        <Legend
          wrapperStyle={{ fontSize: 11, color: "#737373", paddingTop: 8 }}
          formatter={(value) => (value === "current" ? "Current pts" : "Projected pts")}
        />
        <Bar dataKey="current" fill="rgba(255,255,255,0.15)" radius={[2, 2, 0, 0]} maxBarSize={16} name="current" />
        <Bar dataKey="projected" radius={[2, 2, 0, 0]} maxBarSize={16} name="projected">
          {top8.map((entry) => (
            <Cell key={entry.name} fill={entry.color} fillOpacity={0.85} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// Model attribution — exact per-feature contributions to one driver's
// predicted finish (from the linear model). Negative = improves the projection
// (green); positive = worsens it (red). This is generative UI over the
// structured `model_attribution` the prediction API returns.
// ---------------------------------------------------------------------------
export interface AttributionEntry {
  label: string;
  contribution: number;
}

const ATTRIBUTION_HELP = "#00FF78";
const ATTRIBUTION_HURT = "#FF4655";

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
