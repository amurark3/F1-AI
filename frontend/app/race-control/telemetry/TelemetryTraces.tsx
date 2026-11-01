"use client";

import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { DASH_B, type PairColours, type TraceRow } from "./headToHeadModel";

const GRID = "rgba(255,255,255,0.06)";
const AXIS = "rgba(255,255,255,0.35)";
const SYNC_ID = "head-to-head";

interface Codes {
  a: string;
  b: string;
}

interface TraceSpec {
  title: string;
  unit: string;
  keys: [keyof TraceRow, keyof TraceRow];
  height: number;
  step?: boolean;
  domain?: [number, number];
  /** How one value reads in the tooltip; defaults to the number and unit. */
  format?: (value: number) => string;
}

const SPECS: TraceSpec[] = [
  { title: "Speed", unit: "km/h", keys: ["speed_a", "speed_b"], height: 210 },
  { title: "Throttle", unit: "%", keys: ["throttle_a", "throttle_b"], height: 120, domain: [0, 100] },
  {
    title: "Brake",
    unit: "on/off",
    keys: ["brake_a", "brake_b"],
    height: 90,
    step: true,
    domain: [0, 100],
    format: (value) => (value > 0 ? "on" : "off"),
  },
  { title: "Gear", unit: "", keys: ["gear_a", "gear_b"], height: 110, step: true, domain: [1, 8] },
];

interface TraceTooltipProps {
  active?: boolean;
  payload?: ReadonlyArray<{ payload: TraceRow }>;
  /** The channel shown; null for the gap chart. */
  spec: TraceSpec | null;
  codes: Codes;
}

function TraceTooltip({ active, payload, spec, codes }: TraceTooltipProps) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  const read = (value: number) => spec?.format?.(value) ?? `${value} ${spec?.unit ?? ""}`.trim();
  const lines = spec
    ? [`${codes.a} ${read(row[spec.keys[0]])}`, `${codes.b} ${read(row[spec.keys[1]])}`]
    : [`${codes.b} ${row.delta > 0 ? "behind" : "ahead"} by ${Math.abs(row.delta).toFixed(3)}s`];
  return (
    <div className="rounded border border-white/10 bg-[#0F1210] px-2.5 py-1.5 font-mono text-[11px] text-neutral-200 shadow-xl">
      <p className="text-[#7F8797]">{Math.round(row.distance)} m</p>
      {lines.map((line) => (
        <p key={line}>{line}</p>
      ))}
    </div>
  );
}

function ChartTitle({ title, unit }: { title: string; unit: string }) {
  return (
    <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-[#7F8797]">
      {title}
      {unit && <span className="ml-1 font-normal normal-case tracking-normal">({unit})</span>}
    </p>
  );
}

function axisProps(last: boolean) {
  return {
    dataKey: "distance",
    type: "number" as const,
    domain: ["dataMin", "dataMax"] as [string, string],
    tick: last ? { fill: AXIS, fontSize: 10 } : false,
    tickFormatter: (value: number) => `${Math.round(value / 100) / 10} km`,
    stroke: GRID,
    height: last ? 24 : 4,
  };
}

function ChannelChart({
  rows,
  spec,
  colours,
  codes,
}: {
  rows: TraceRow[];
  spec: TraceSpec;
  colours: PairColours;
  codes: Codes;
}) {
  const type = spec.step ? "stepAfter" : "monotone";
  return (
    <div>
      <ChartTitle title={spec.title} unit={spec.unit} />
      <ResponsiveContainer width="100%" height={spec.height}>
        <LineChart data={rows} syncId={SYNC_ID} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis {...axisProps(spec.title === "Gear")} />
          <YAxis
            width={44}
            domain={spec.domain ?? ["auto", "auto"]}
            tick={{ fill: AXIS, fontSize: 10 }}
            stroke={GRID}
          />
          <Tooltip content={<TraceTooltip spec={spec} codes={codes} />} />
          <Line
            type={type}
            dataKey={spec.keys[0]}
            stroke={colours.a}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type={type}
            dataKey={spec.keys[1]}
            stroke={colours.b}
            strokeWidth={2}
            strokeDasharray={DASH_B}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function DeltaChart({ rows, codes }: { rows: TraceRow[]; codes: Codes }) {
  return (
    <div>
      <ChartTitle title={`Gap: ${codes.b} to ${codes.a}`} unit={`s, above 0 = ${codes.b} behind`} />
      <ResponsiveContainer width="100%" height={130}>
        <LineChart data={rows} syncId={SYNC_ID} margin={{ top: 4, right: 12, bottom: 0, left: 0 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis {...axisProps(false)} />
          <YAxis width={44} tick={{ fill: AXIS, fontSize: 10 }} stroke={GRID} />
          <ReferenceLine y={0} stroke={AXIS} />
          <Tooltip content={<TraceTooltip spec={null} codes={codes} />} />
          <Line
            type="monotone"
            dataKey="delta"
            stroke="#F0EFEC"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Speed, gap, throttle, brake and gear against distance, sharing one hover cursor. */
export function TelemetryTraces({ rows, colours, codes }: { rows: TraceRow[]; colours: PairColours; codes: Codes }) {
  const [speed, ...rest] = SPECS;
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px] text-[#A8AFBF]">
        <span className="inline-flex items-center gap-1.5">
          <svg width="22" height="6" aria-hidden>
            <line x1="0" y1="3" x2="22" y2="3" stroke={colours.a} strokeWidth="2" />
          </svg>
          {codes.a}
        </span>
        <span className="inline-flex items-center gap-1.5">
          <svg width="22" height="6" aria-hidden>
            <line x1="0" y1="3" x2="22" y2="3" stroke={colours.b} strokeWidth="2" strokeDasharray={DASH_B} />
          </svg>
          {codes.b}
        </span>
      </div>
      <ChannelChart rows={rows} spec={speed} colours={colours} codes={codes} />
      <DeltaChart rows={rows} codes={codes} />
      {rest.map((spec) => (
        <ChannelChart key={spec.title} rows={rows} spec={spec} colours={colours} codes={codes} />
      ))}
    </div>
  );
}
