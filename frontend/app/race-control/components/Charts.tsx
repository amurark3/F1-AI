"use client";

import {
  AreaChart,
  Area,
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

function ChampionshipTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: ChampionshipEntry; value: number }> }) {
  if (!active || !payload?.length) return null;
  const entry = payload[0].payload;
  return (
    <ChartTooltipContainer>
      <p className="font-black uppercase tracking-wider text-white" style={rcFont}>{entry.name}</p>
      <p className="mt-0.5 font-mono text-neutral-300">{entry.points} pts · P{entry.position}</p>
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
        <Tooltip content={<ChampionshipTooltip />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
        <Bar dataKey="points" radius={[0, 4, 4, 0]} maxBarSize={20}>
          {sorted.map((entry) => (
            <Cell key={entry.name} fill={entry.color} fillOpacity={0.9} />
          ))}
        </Bar>
        {leader && (
          <ReferenceLine
            x={leader.points}
            stroke="rgba(255,255,255,0.15)"
            strokeDasharray="4 4"
          />
        )}
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

function DriverTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: DriverChampionshipEntry; value: number }> }) {
  if (!active || !payload?.length) return null;
  const entry = payload[0].payload;
  return (
    <ChartTooltipContainer>
      <p className="font-black uppercase tracking-wider text-white" style={rcFont}>{entry.name}</p>
      <p className="mt-0.5 font-mono text-neutral-300">{entry.points} pts · P{entry.position}</p>
    </ChartTooltipContainer>
  );
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
        <YAxis
          tick={{ fill: CHART_COLORS.axis, fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          width={36}
        />
        <Tooltip content={<DriverTooltip />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
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
      <p className="font-black uppercase tracking-wider text-white" style={rcFont}>{entry.code}</p>
      <p className="mt-0.5 font-mono text-neutral-300">{entry.mid}% · range {entry.low}–{entry.high}%</p>
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

function ProjectionTooltip({ active, payload, label }: { active?: boolean; payload?: Array<{ name: string; value: number; color: string }>; label?: string }) {
  if (!active || !payload?.length) return null;
  return (
    <ChartTooltipContainer>
      <p className="mb-1 font-black uppercase tracking-wider text-white" style={rcFont}>{label}</p>
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
        <YAxis
          tick={{ fill: CHART_COLORS.axis, fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          width={40}
        />
        <Tooltip content={<ProjectionTooltip />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
        <Legend
          wrapperStyle={{ fontSize: 11, color: "#737373", paddingTop: 8 }}
          formatter={(value) => value === "current" ? "Current pts" : "Projected pts"}
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
// Tyre life area chart for strategy page
// ---------------------------------------------------------------------------
interface TyreLapEntry {
  lap: number;
  degradation: number;
  threshold: number;
}

function TyreTooltip({ active, payload }: { active?: boolean; payload?: Array<{ name: string; value: number }> }) {
  if (!active || !payload?.length) return null;
  return (
    <ChartTooltipContainer>
      <p className="font-mono text-sm text-white">
        Deg: <span className="font-black">{payload[0]?.value}%</span>
      </p>
    </ChartTooltipContainer>
  );
}

export function TyreDegradationChart({
  tyreAge,
  pitLap,
  compoundLife,
  color = "#00FF78",
  height = 140,
}: {
  tyreAge: number;
  pitLap: number;
  compoundLife: number;
  color?: string;
  height?: number;
}) {
  const laps = Math.max(pitLap + 4, compoundLife + 2);
  const data: TyreLapEntry[] = Array.from({ length: laps }, (_, i) => {
    const lap = i + 1;
    const age = lap;
    const rawDeg = Math.min(100, (age / compoundLife) * 100);
    const degradation = Math.round(Math.pow(rawDeg / 100, 1.4) * 100);
    return { lap, degradation, threshold: 80 };
  });

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 4, right: 8, bottom: 4, left: 0 }}>
        <defs>
          <linearGradient id="tyreGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%" stopColor={color} stopOpacity={0.3} />
            <stop offset="95%" stopColor={color} stopOpacity={0.03} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={CHART_COLORS.grid} />
        <XAxis
          dataKey="lap"
          tick={{ fill: CHART_COLORS.axis, fontSize: 9 }}
          axisLine={false}
          tickLine={false}
          tickFormatter={(v: number) => `L${v}`}
          interval={Math.floor(laps / 5)}
        />
        <YAxis
          domain={[0, 100]}
          tick={{ fill: CHART_COLORS.axis, fontSize: 9 }}
          axisLine={false}
          tickLine={false}
          width={28}
          tickFormatter={(v: number) => `${v}%`}
        />
        <Tooltip content={<TyreTooltip />} cursor={{ stroke: "rgba(255,255,255,0.1)" }} />
        <ReferenceLine x={tyreAge} stroke="rgba(255,255,255,0.3)" strokeDasharray="4 4" label={{ value: "Now", fill: "#737373", fontSize: 9 }} />
        <ReferenceLine x={pitLap} stroke={color} strokeDasharray="4 4" strokeWidth={1.5} label={{ value: "Stop", fill: color, fontSize: 9 }} />
        <ReferenceLine y={80} stroke="#FFF200" strokeDasharray="3 3" strokeWidth={1} />
        <Area type="monotone" dataKey="degradation" stroke={color} strokeWidth={2} fill="url(#tyreGrad)" dot={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

