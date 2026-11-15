"use client";

import { CartesianGrid, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { chartTheme } from "@/app/ui/chartTheme";
import { rc } from "@/app/ui/tokens";
import { useChartAnimation } from "@/app/ui/useChartAnimation";

import { DriverLegend, HeadToHeadCard } from "./HeadToHeadCard";
import { brakeTitle, deltaTitle, gearTitle, speedTitle, throttleTitle, type Codes } from "./headToHeadInsights";
import { DASH_B, type PairColours, type TraceRow } from "./headToHeadModel";

interface TraceSpec {
  eyebrow: string;
  unit: string;
  keys: [keyof TraceRow, keyof TraceRow];
  height: number;
  title: (rows: TraceRow[], codes: Codes) => string;
  step?: boolean;
  domain?: [number, number];
  /** How one value reads on the axis and in the tooltip; defaults to the number and unit. */
  format?: (value: number) => string;
}

const SPECS: TraceSpec[] = [
  { eyebrow: "Speed", unit: "km/h", keys: ["speed_a", "speed_b"], height: 190, title: speedTitle },
  {
    eyebrow: "Throttle",
    unit: "%",
    keys: ["throttle_a", "throttle_b"],
    height: 150,
    domain: [0, 100],
    title: throttleTitle,
  },
  {
    eyebrow: "Brake",
    unit: "on/off",
    keys: ["brake_a", "brake_b"],
    height: 110,
    step: true,
    domain: [0, 100],
    format: (value) => (value > 0 ? "on" : "off"),
    title: brakeTitle,
  },
  { eyebrow: "Gear", unit: "", keys: ["gear_a", "gear_b"], height: 150, step: true, domain: [1, 8], title: gearTitle },
];

const MARGIN = { top: 4, right: 12, bottom: 0, left: 0 };

interface TraceTooltipProps {
  active?: boolean;
  payload?: ReadonlyArray<{ payload: TraceRow }>;
  /** The channel shown; null for the gap chart. */
  spec: TraceSpec | null;
  codes: Codes;
}

function read(spec: TraceSpec, value: number): string {
  return spec.format?.(value) ?? `${value} ${spec.unit}`.trim();
}

export function TraceTooltip({ active, payload, spec, codes }: TraceTooltipProps) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  const lines = spec
    ? spec.keys.map((key, side) => `${side === 0 ? codes.a : codes.b} ${read(spec, row[key])}`)
    : [`${codes.b} ${row.delta > 0 ? "behind" : "ahead"} by ${Math.abs(row.delta).toFixed(3)}s`];
  return (
    <div style={chartTheme.tooltip.contentStyle} className="font-mono text-[11px]">
      <p className="text-rc-ink-3">{Math.round(row.distance)} m</p>
      {lines.map((line) => (
        <p key={line}>{line}</p>
      ))}
    </div>
  );
}

const axisX = {
  ...chartTheme.axis,
  dataKey: "distance",
  type: "number" as const,
  domain: ["dataMin", "dataMax"] as [string, string],
  tickFormatter: (value: number) => `${Math.round(value / 100) / 10} km`,
};

function ChannelCard({
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
  const animation = useChartAnimation();
  const type = spec.step ? "stepAfter" : "monotone";
  return (
    <HeadToHeadCard eyebrow={spec.eyebrow} title={spec.title(rows, codes)} sub={spec.unit || undefined}>
      <ResponsiveContainer width="100%" height={spec.height}>
        <LineChart data={rows} margin={MARGIN}>
          <CartesianGrid {...chartTheme.grid} vertical={false} />
          <XAxis {...axisX} />
          <YAxis {...chartTheme.axis} width={44} domain={spec.domain ?? ["auto", "auto"]} tickFormatter={spec.format} />
          <Tooltip {...chartTheme.tooltip} content={<TraceTooltip spec={spec} codes={codes} />} />
          <Line
            type={type}
            dataKey={spec.keys[0]}
            stroke={colours.a}
            strokeWidth={2}
            dot={false}
            {...animation.series}
          />
          <Line
            type={type}
            dataKey={spec.keys[1]}
            stroke={colours.b}
            strokeWidth={2}
            strokeDasharray={DASH_B}
            dot={false}
            {...animation.series}
          />
        </LineChart>
      </ResponsiveContainer>
      <DriverLegend colours={colours} codes={codes} />
    </HeadToHeadCard>
  );
}

/** The smoothed gap along the lap; it ends on the official lap-time gap. */
function DeltaCard({ rows, codes }: { rows: TraceRow[]; codes: Codes }) {
  const animation = useChartAnimation();
  return (
    <HeadToHeadCard
      eyebrow="Delta"
      title={deltaTitle(rows, codes)}
      sub={`Seconds, smoothed. Above 0 = ${codes.b} behind ${codes.a}; ends at the official gap.`}
    >
      <ResponsiveContainer width="100%" height={190}>
        <LineChart data={rows} margin={MARGIN}>
          <CartesianGrid {...chartTheme.grid} vertical={false} />
          <XAxis {...axisX} />
          <YAxis {...chartTheme.axis} width={44} />
          <ReferenceLine y={0} stroke={rc.ink3} />
          <Tooltip {...chartTheme.tooltip} content={<TraceTooltip spec={null} codes={codes} />} />
          <Line type="monotone" dataKey="delta" stroke={rc.ink} strokeWidth={2} dot={false} {...animation.series} />
        </LineChart>
      </ResponsiveContainer>
    </HeadToHeadCard>
  );
}

/** The gap, speed, throttle, brake and gear against distance, each its own card with its own title. */
export function TelemetryTraces({ rows, colours, codes }: { rows: TraceRow[]; colours: PairColours; codes: Codes }) {
  const [speed, ...rest] = SPECS;
  return (
    <>
      <DeltaCard rows={rows} codes={codes} />
      <ChannelCard rows={rows} spec={speed} colours={colours} codes={codes} />
      {rest.map((spec) => (
        <ChannelCard key={spec.eyebrow} rows={rows} spec={spec} colours={colours} codes={codes} />
      ))}
    </>
  );
}
