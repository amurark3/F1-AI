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

import { chartTheme } from "@/app/ui/chartTheme";
import { Legend } from "@/app/ui/Legend";
import { f1, rc } from "@/app/ui/tokens";
import { useChartAnimation } from "@/app/ui/useChartAnimation";

import { compoundColor, compoundLabel, compoundTextColor } from "../grand-prix/tyreCompounds";

import { formatLapTime } from "./telemetryModel";

import type { LengthRow } from "./degradationInsights";
import type { FitLine, PaceRow, ScatterPoint } from "./degradationModel";
import type { AnalysisDriver } from "./telemetryModel";

/** Neutralised stretches are shaded grey; only a red flag takes the brand red. */
const BAND: Record<string, string> = { red: f1.red };
const PACE_DASH = "6 4";
const MARGIN = { top: 8, right: 16, bottom: 20, left: 4 };
const AXIS_LABEL = { fill: rc.ink3, fontSize: 11 };

interface PointTooltipProps {
  active?: boolean;
  payload?: ReadonlyArray<{ payload: ScatterPoint }>;
  labels: Record<string, string>;
}

export function PointTooltip({ active, payload, labels }: PointTooltipProps) {
  if (!active || !payload?.length) return null;
  const entry = payload[0].payload;
  return (
    <div style={chartTheme.tooltip.contentStyle} className="font-mono text-[11px]">
      <p className="text-rc-ink">
        {entry.driver} · lap {entry.lap} · {compoundLabel(entry.compound)}
      </p>
      <p>
        {formatLapTime(entry.y)} on a {entry.x}-lap-old set
      </p>
      <p className="text-rc-ink-3">
        {entry.status === "clean" ? "Fitted" : `Left out: ${labels[entry.status] ?? entry.status}`}
      </p>
    </div>
  );
}

/** Which compounds the scatter shows, and the hollow mark for laps left out of the fit. */
export function CompoundLegend({ compounds, showExcluded }: { compounds: string[]; showExcluded: boolean }) {
  return (
    <Legend
      className="mb-3"
      label="Compounds"
      items={[
        ...compounds.map((compound) => ({ label: compoundLabel(compound), color: compoundColor(compound) })),
        ...(showExcluded ? [{ label: "Left out of the fit", color: rc.ink3, mark: "outline" as const }] : []),
      ]}
    />
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
  const { series } = useChartAnimation();
  return (
    <ResponsiveContainer width="100%" height={340}>
      <ScatterChart margin={MARGIN}>
        <CartesianGrid {...chartTheme.grid} />
        <XAxis
          {...chartTheme.axis}
          type="number"
          dataKey="x"
          name="Tyre age"
          allowDecimals={false}
          label={{ ...AXIS_LABEL, value: "Tyre age (laps on the set)", position: "insideBottom", offset: -12 }}
        />
        <YAxis
          {...chartTheme.axis}
          type="number"
          dataKey="y"
          name="Lap time"
          domain={domain}
          allowDataOverflow
          width={64}
          tickFormatter={(value: number) => formatLapTime(value)}
        />
        <Tooltip {...chartTheme.tooltip} content={<PointTooltip labels={labels} />} />
        {showExcluded && <Scatter data={excluded} fill="none" stroke={rc.ink3} strokeWidth={1.5} {...series} />}
        {[...clean.entries()].map(([compound, points]) => (
          <Scatter
            key={compound}
            data={points}
            fill={compoundColor(compound)}
            stroke={rc.hero}
            strokeWidth={1}
            {...series}
          />
        ))}
        {fits.map((fit) => (
          <Scatter
            key={fit.key}
            data={fit.points}
            line={{ stroke: compoundColor(fit.compound), strokeWidth: 2 }}
            shape={() => <g />}
            legendType="none"
            tooltipType="none"
            {...series}
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

export function PaceTooltip({ active, label, payload }: PaceTooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div style={chartTheme.tooltip.contentStyle} className="font-mono text-[11px]">
      <p className="text-rc-ink-3">Lap {label}</p>
      {payload.map((entry) => (
        <p key={String(entry.dataKey)}>
          {String(entry.dataKey)} {formatLapTime(entry.value ?? null)}
        </p>
      ))}
    </div>
  );
}

/** Each driver's line: team colour, dashed for the second car of a team so team-mates stay apart. */
export function paceStyles(drivers: AnalysisDriver[]): Array<{ driver: AnalysisDriver; dashed: boolean }> {
  const teams = new Set<string>();
  return drivers.map((driver) => {
    const dashed = teams.has(driver.team);
    teams.add(driver.team);
    return { driver, dashed };
  });
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
  const { series } = useChartAnimation();
  const styles = paceStyles(drivers);
  return (
    <>
      <Legend
        className="mb-3"
        label="Drivers"
        items={styles.map(({ driver, dashed }) => ({
          label: dashed ? `${driver.code} (dashed)` : driver.code,
          color: driver.colour,
        }))}
      />
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={rows} margin={MARGIN}>
          <CartesianGrid {...chartTheme.grid} vertical={false} />
          <XAxis
            {...chartTheme.axis}
            dataKey="lap"
            type="number"
            domain={["dataMin", "dataMax"]}
            allowDecimals={false}
            label={{ ...AXIS_LABEL, value: "Lap", position: "insideBottom", offset: -12 }}
          />
          <YAxis
            {...chartTheme.axis}
            domain={domain}
            allowDataOverflow
            width={64}
            tickFormatter={(value: number) => formatLapTime(value)}
          />
          {bands.map((band) => (
            <ReferenceArea
              key={`${band.kind}-${band.from_lap}`}
              x1={band.from_lap - 0.5}
              x2={band.to_lap + 0.5}
              fill={BAND[band.kind] ?? rc.ink3}
              fillOpacity={0.1}
              ifOverflow="hidden"
              label={{ value: band.kind.toUpperCase(), position: "insideTop", fill: rc.ink3, fontSize: 9 }}
            />
          ))}
          <Tooltip {...chartTheme.tooltip} content={<PaceTooltip />} />
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
              {...series}
            />
          ))}
        </LineChart>
      </ResponsiveContainer>
    </>
  );
}

/** One row per driver: each stint a bar as long as the laps on that set, in the compound's colour. */
export function StintLengths({ rows }: { rows: LengthRow[] }) {
  const longest = Math.max(...rows.map((row) => row.stints.reduce((sum, stint) => sum + stint.laps, 0)));
  const compounds = [...new Set(rows.flatMap((row) => row.stints.map((stint) => stint.compound)))];
  return (
    <>
      <ul aria-label="Laps on each set" className="space-y-2.5">
        {rows.map((row) => (
          <li key={row.code} className="grid grid-cols-[110px_1fr] items-center gap-3">
            <span className="truncate text-[13px] text-rc-ink-2">{row.name}</span>
            <div className="flex h-7 gap-px overflow-hidden rounded-[3px]">
              {row.stints.map((stint) => (
                <b
                  key={stint.stint}
                  title={`${compoundLabel(stint.compound)} · laps ${stint.from}–${stint.to}`}
                  className="flex items-center justify-center font-mono text-[11px] font-bold"
                  style={{
                    width: `${(stint.laps / longest) * 100}%`,
                    background: compoundColor(stint.compound),
                    color: compoundTextColor(stint.compound),
                  }}
                >
                  {stint.laps}
                </b>
              ))}
            </div>
          </li>
        ))}
      </ul>
      <Legend
        className="mt-3.5"
        label="Compounds"
        items={compounds.map((compound) => ({ label: compoundLabel(compound), color: compoundColor(compound) }))}
      />
    </>
  );
}
