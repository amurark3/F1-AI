"use client";

import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { rcFont } from "../components/RaceControlPrimitives";

const GRID = "rgba(255,255,255,0.06)";
const AXIS = "rgba(255,255,255,0.35)";

export interface PointsEntry {
  label: string;
  name: string;
  points: number;
}

export interface PositionEntry {
  label: string;
  name: string;
  /** `null` for a retirement or a round not raced — drawn as a gap. */
  position: number | null;
}

interface TooltipProps<T> {
  active?: boolean;
  payload?: Array<{ payload: T }>;
}

function Card({ title, line }: { title: string; line: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-[#0F1210] px-3 py-2 text-sm shadow-xl">
      <p className="font-black uppercase tracking-wider text-white" style={rcFont}>
        {title}
      </p>
      <p className="mt-0.5 font-mono text-neutral-300">{line}</p>
    </div>
  );
}

function PointsTooltip({ active, payload }: TooltipProps<PointsEntry>) {
  if (!active || !payload?.length) return null;
  const entry = payload[0].payload;
  return <Card title={entry.name} line={`${entry.points} pts after ${entry.label}`} />;
}

function PositionTooltip({ active, payload }: TooltipProps<PositionEntry>) {
  if (!active || !payload?.length) return null;
  const entry = payload[0].payload;
  return (
    <Card title={entry.name} line={entry.position === null ? "No classified finish" : `Finished P${entry.position}`} />
  );
}

/** A team's points as the season went, one point per published round. */
export function CumulativePointsChart({
  data,
  color,
  height = 240,
}: {
  data: PointsEntry[];
  color: string;
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
        <XAxis dataKey="label" tick={{ fill: AXIS, fontSize: 10 }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fill: AXIS, fontSize: 10 }} axisLine={false} tickLine={false} width={40} />
        <Tooltip content={<PointsTooltip />} cursor={{ stroke: "rgba(255,255,255,0.12)" }} />
        <Line type="monotone" dataKey="points" stroke={color} strokeWidth={2.5} dot={{ r: 2.5, fill: color }} />
      </LineChart>
    </ResponsiveContainer>
  );
}

/**
 * Finishing position per round, P1 at the top. Retirements and rounds not
 * raced break the line rather than being drawn as a last place.
 */
export function FinishPositionChart({
  data,
  color,
  fieldSize,
  height = 220,
}: {
  data: PositionEntry[];
  color: string;
  fieldSize: number;
  height?: number;
}) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={GRID} vertical={false} />
        <XAxis dataKey="label" tick={{ fill: AXIS, fontSize: 10 }} axisLine={false} tickLine={false} />
        <YAxis
          reversed
          domain={[1, fieldSize]}
          allowDecimals={false}
          ticks={[1, 5, 10, 15, 20].filter((tick) => tick <= fieldSize)}
          tickFormatter={(value: number) => `P${value}`}
          tick={{ fill: AXIS, fontSize: 10 }}
          axisLine={false}
          tickLine={false}
          width={36}
        />
        <Tooltip content={<PositionTooltip />} cursor={{ stroke: "rgba(255,255,255,0.12)" }} />
        <Line type="monotone" dataKey="position" stroke={color} strokeWidth={2.5} dot={{ r: 3, fill: color }} />
      </LineChart>
    </ResponsiveContainer>
  );
}
