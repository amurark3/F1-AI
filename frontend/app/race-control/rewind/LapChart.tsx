"use client";

import { useMemo } from "react";

import { useSeasonDirectory } from "@/app/race-control/profiles/EntityLinks";
import { Legend, type LegendItem } from "@/app/ui/Legend";
import { PanelHeading } from "@/app/ui/PanelHeading";
import { f1, rc } from "@/app/ui/tokens";

import { CHART_FRAME, chartGeometry, cursorX, type ChartGeometry } from "./lapChartModel";
import { lapChartTitle, surnameFn } from "./rewindCopy";

import type { RaceRewind } from "./rewindTypes";

const CARD = "rounded-md border border-rc-line bg-(--surface) p-5 sm:p-6";
const AXIS = { fontFamily: "var(--font-geist-mono)", fontSize: 10, fill: rc.ink3 } as const;
const LABEL = { fontFamily: "var(--font-geist-mono)", fontSize: 11, fontWeight: 600 } as const;

function Plot({ geometry }: { geometry: ChartGeometry }) {
  const { top, bottom, left, right, labelX, axisY } = CHART_FRAME;
  return (
    <>
      {geometry.bands.map((band) => (
        <g key={band.x1}>
          <rect x={band.x1} y={top} width={band.x2 - band.x1} height={bottom - top} fill={rc.ink3} opacity={0.1} />
          <text x={band.x1 + 3} y={axisY} style={{ ...AXIS, fontSize: 9 }}>
            {band.label}
          </text>
        </g>
      ))}
      {geometry.ticks.y.map((tick) => (
        <g key={tick.label}>
          <line x1={left} x2={right} y1={tick.y} y2={tick.y} stroke={rc.line} />
          <text x={left - 8} y={tick.y + 3} textAnchor="end" style={AXIS}>
            {tick.label}
          </text>
        </g>
      ))}
      {geometry.ticks.x.map((tick) => (
        <text key={tick.label} x={tick.x} y={axisY} textAnchor="middle" style={AXIS}>
          {tick.label}
        </text>
      ))}
      {geometry.red && (
        <g>
          <line x1={geometry.red.x} x2={geometry.red.x} y1={top} y2={bottom} stroke={f1.red} strokeWidth={2} />
          <text x={geometry.red.x + 5} y={top + 10} style={{ ...AXIS, fill: rc.redText }}>
            {`RED FLAG · L${geometry.red.lap}`}
          </text>
        </g>
      )}
      {geometry.lines.map((line) => (
        <path
          key={line.code}
          d={line.d}
          pathLength={1}
          strokeDasharray="1 1"
          className="motion-safe:animate-track-draw"
          fill="none"
          stroke={line.color}
          strokeWidth={line.width}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      ))}
      {geometry.crosses.map((cross) => (
        <text key={cross.code} x={cross.x} y={cross.y + 3.5} textAnchor="middle" style={{ ...LABEL, fill: rc.ink3 }}>
          ×
        </text>
      ))}
      {geometry.labels.map((label) => (
        <text key={label.code} x={labelX} y={label.y} style={{ ...LABEL, fill: label.color }}>
          {label.code}
        </text>
      ))}
    </>
  );
}

/** The chart is built once per payload, so scrubbing only moves the cursor. */
export function LapChart({ data, step }: { data: RaceRewind; step: number }) {
  const directory = useSeasonDirectory();
  const geometry = useMemo(() => chartGeometry(data), [data]);
  const name = surnameFn(data, directory);
  const x = cursorX(data, step);
  const items: LegendItem[] = [
    ...geometry.leaders.map((leader) => ({ label: name(leader.code), color: leader.color })),
    { label: "Others", color: rc.dim },
    ...(geometry.bands.length > 0 ? [{ label: "VSC / Safety Car", color: rc.ink3 }] : []),
    ...(geometry.red ? [{ label: "Red flag", color: f1.red, mark: "rule" as const }] : []),
  ];
  return (
    <figure className={CARD}>
      <PanelHeading
        eyebrow="Lap chart"
        title={lapChartTitle(data, directory)}
        sub={`Place at the line after each lap, all ${data.drivers.length} cars · × = retired · from OpenF1 positions`}
      />
      <svg viewBox={`0 0 ${CHART_FRAME.width} ${CHART_FRAME.height}`} aria-hidden="true" className="h-auto w-full">
        <Plot geometry={geometry} />
        <line
          data-cursor=""
          x1={x}
          x2={x}
          y1={CHART_FRAME.top}
          y2={CHART_FRAME.bottom}
          stroke={rc.ink}
          strokeWidth={1.5}
        />
      </svg>
      <Legend items={items} label="Lap chart" className="mt-3.5" />
    </figure>
  );
}
