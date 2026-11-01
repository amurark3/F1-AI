"use client";

import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { compoundColor, compoundLabel } from "../grand-prix/tyreCompounds";

import { formatLapTime } from "./telemetryModel";

import type { FitLine, PaceRow, ScatterPoint } from "./degradationModel";
import type { AnalysisDriver } from "./telemetryModel";

const GRID = "rgba(255,255,255,0.06)";
const AXIS = "rgba(255,255,255,0.35)";
const EXCLUDED = "#596173";
const BAND = { sc: "#F5C542", vsc: "#F5C542", red: "#E8002D" } as Record<string, string>;
const TICK = { fill: AXIS, fontSize: 10 };
const PACE_DASH = "6 4";

interface PointTooltipProps {
  active?: boolean;
  payload?: ReadonlyArray<{ payload: ScatterPoint }>;
  labels: Record<string, string>;
}

function PointTooltip({ active, payload, labels }: PointTooltipProps) {
  if (!active || !payload?.length) return null;
  const entry = payload[0].payload;
  return (
    <div className="rounded border border-white/10 bg-[#0F1210] px-2.5 py-1.5 font-mono text-[11px] text-neutral-200 shadow-xl">
      <p className="text-white">
        {entry.driver} · lap {entry.lap} · {compoundLabel(entry.compound)}
      </p>
      <p>
        {formatLapTime(entry.y)} on a {entry.x}-lap-old set
      </p>
      <p className={entry.status === "clean" ? "text-[#7F8797]" : "text-[#F5C542]"}>
        {entry.status === "clean" ? "Fitted" : `Left out: ${labels[entry.status] ?? entry.status}`}
      </p>
    </div>
  );
}

/** Lap time against tyre age: clean laps by compound, the rest hollow grey, and each stint's fitted line. */
export function DegradationScatter({
  clean,
  excluded,
  fits,
  domain,
  labels,
  showExcluded,
}: {
  clean: Map<string, ScatterPoint[]>;
  excluded: ScatterPoint[];
  fits: FitLine[];
  domain: [number, number];
  labels: Record<string, string>;
  showExcluded: boolean;
}) {
  return (
    <ResponsiveContainer width="100%" height={380}>
      <ScatterChart margin={{ top: 8, right: 16, bottom: 20, left: 4 }}>
        <CartesianGrid stroke={GRID} />
        <XAxis
          type="number"
          dataKey="x"
          name="Tyre age"
          allowDecimals={false}
          tick={TICK}
          stroke={GRID}
          label={{
            value: "Tyre age (laps on the set)",
            position: "insideBottom",
            offset: -12,
            fill: AXIS,
            fontSize: 11,
          }}
        />
        <YAxis
          type="number"
          dataKey="y"
          name="Lap time"
          domain={domain}
          allowDataOverflow
          width={64}
          tick={TICK}
          stroke={GRID}
          tickFormatter={(value: number) => formatLapTime(value)}
        />
        <Tooltip content={<PointTooltip labels={labels} />} cursor={{ stroke: GRID }} />
        {showExcluded && (
          <Scatter data={excluded} fill="none" stroke={EXCLUDED} strokeWidth={1.5} isAnimationActive={false} />
        )}
        {[...clean.entries()].map(([compound, points]) => (
          <Scatter
            key={compound}
            data={points}
            fill={compoundColor(compound)}
            stroke="#0D111B"
            strokeWidth={1}
            isAnimationActive={false}
          />
        ))}
        {fits.map((fit) => (
          <Scatter
            key={fit.key}
            data={fit.points}
            line={{ stroke: compoundColor(fit.compound), strokeWidth: 2 }}
            shape={() => <g />}
            legendType="none"
            isAnimationActive={false}
            tooltipType="none"
          />
        ))}
      </ScatterChart>
    </ResponsiveContainer>
  );
}

interface PaceTooltipProps {
  active?: boolean;
  label?: number;
  payload?: Array<{ dataKey?: string | number; value?: number | null }>;
}

function PaceTooltip({ active, label, payload }: PaceTooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded border border-white/10 bg-[#0F1210] px-2.5 py-1.5 font-mono text-[11px] text-neutral-200 shadow-xl">
      <p className="text-[#7F8797]">Lap {label}</p>
      {payload.map((entry) => (
        <p key={String(entry.dataKey)}>
          {String(entry.dataKey)} {formatLapTime(entry.value ?? null)}
        </p>
      ))}
    </div>
  );
}

/** Each driver's line: team colour, dashed for the second car of a team so team-mates stay apart. */
function paceStyles(drivers: AnalysisDriver[]): Array<{ driver: AnalysisDriver; dashed: boolean }> {
  const teams = new Set<string>();
  return drivers.map((driver) => {
    const dashed = teams.has(driver.team);
    teams.add(driver.team);
    return { driver, dashed };
  });
}

function PaceLegend({ styles }: { styles: Array<{ driver: AnalysisDriver; dashed: boolean }> }) {
  return (
    <div className="mb-1 flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px] text-[#A8AFBF]">
      {styles.map(({ driver, dashed }) => (
        <span key={driver.code} className="inline-flex items-center gap-1.5">
          <svg width="22" height="6" aria-hidden>
            <line
              x1="0"
              y1="3"
              x2="22"
              y2="3"
              stroke={driver.colour}
              strokeWidth="2"
              strokeDasharray={dashed ? PACE_DASH : undefined}
            />
          </svg>
          {driver.code}
        </span>
      ))}
    </div>
  );
}

/** Lap time through the race per driver, with neutralised laps shaded. */
export function RacePaceChart({
  rows,
  drivers,
  domain,
  bands,
}: {
  rows: PaceRow[];
  drivers: AnalysisDriver[];
  domain: [number, number];
  bands: Array<{ kind: string; from_lap: number; to_lap: number }>;
}) {
  const styles = paceStyles(drivers);
  return (
    <>
      <PaceLegend styles={styles} />
      <ResponsiveContainer width="100%" height={320}>
        <LineChart data={rows} margin={{ top: 8, right: 16, bottom: 20, left: 4 }}>
          <CartesianGrid stroke={GRID} vertical={false} />
          <XAxis
            dataKey="lap"
            type="number"
            domain={["dataMin", "dataMax"]}
            allowDecimals={false}
            tick={TICK}
            stroke={GRID}
            label={{ value: "Lap", position: "insideBottom", offset: -12, fill: AXIS, fontSize: 11 }}
          />
          <YAxis
            domain={domain}
            allowDataOverflow
            width={64}
            tick={TICK}
            stroke={GRID}
            tickFormatter={(value: number) => formatLapTime(value)}
          />
          {bands.map((band) => (
            <ReferenceArea
              key={`${band.kind}-${band.from_lap}`}
              x1={band.from_lap - 0.5}
              x2={band.to_lap + 0.5}
              fill={BAND[band.kind] ?? EXCLUDED}
              fillOpacity={0.08}
              ifOverflow="hidden"
              label={{ value: band.kind.toUpperCase(), position: "insideTop", fill: AXIS, fontSize: 9 }}
            />
          ))}
          <Tooltip content={<PaceTooltip />} />
          {styles.map(({ driver, dashed }) => (
            <Line
              key={driver.code}
              type="linear"
              dataKey={driver.code}
              stroke={driver.colour}
              strokeWidth={2}
              strokeDasharray={dashed ? PACE_DASH : undefined}
              dot={false}
              connectNulls={false}
              isAnimationActive={false}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </>
  );
}

export function CompoundKey({ compounds, showExcluded }: { compounds: string[]; showExcluded: boolean }) {
  return (
    <div className="flex flex-wrap gap-x-4 gap-y-1 font-mono text-[11px] text-[#A8AFBF]">
      {compounds.map((compound) => (
        <span key={compound} className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: compoundColor(compound) }} aria-hidden />
          {compoundLabel(compound)}
        </span>
      ))}
      {showExcluded && (
        <span className="inline-flex items-center gap-1.5">
          <span className="h-2.5 w-2.5 rounded-full border-[1.5px]" style={{ borderColor: EXCLUDED }} aria-hidden />
          left out of the fit
        </span>
      )}
    </div>
  );
}
