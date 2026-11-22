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
  tooltip: { bg: rc.raised, border: rc.line },
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
