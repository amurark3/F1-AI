"use client";

import Link from "next/link";

import { useSeasonDirectory } from "@/app/race-control/profiles/EntityLinks";
import { Legend, type LegendItem } from "@/app/ui/Legend";
import { driverLabel } from "@/app/ui/names/names";
import { PanelHeading } from "@/app/ui/PanelHeading";
import { f1, rc } from "@/app/ui/tokens";

import { traceTitle } from "./lapsModel";
import { TRACE_FRAME, traceGeometry, type TraceGeometry } from "./raceTraceModel";

import type { DebriefLaps } from "./debriefTypes";

const CARD = "rounded-md border border-rc-line bg-(--surface) p-5 sm:p-6";
const AXIS = { fontFamily: "var(--font-geist-mono)", fontSize: 10, fill: rc.ink3 } as const;
const LABEL = { fontFamily: "var(--font-geist-mono)", fontSize: 11, fontWeight: 600 } as const;

function Plot({ geometry }: { geometry: TraceGeometry }) {
  const { top, bottom, left, right, labelX, width, height } = TRACE_FRAME;
  return (
    <svg viewBox={`0 0 ${width} ${height}`} aria-hidden="true" className="h-auto w-full">
      {geometry.bands.map((band) => (
        <g key={`${band.kind}-${band.x1}`}>
          <rect x={band.x1} y={top} width={band.x2 - band.x1} height={bottom - top} fill={rc.ink3} opacity={0.1} />
          <text x={band.x1 + 3} y={top + 10} style={{ ...AXIS, fontSize: 9 }}>
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
        <text key={tick.label} x={tick.x} y={height - 4} textAnchor="middle" style={AXIS}>
          {tick.label}
        </text>
      ))}
      {geometry.red && (
        <g data-red-flag="">
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
      {geometry.lines.map((line) => (
        <text key={line.code} x={labelX} y={line.labelY} style={{ ...LABEL, fill: line.quiet ? rc.ink2 : line.color }}>
          {line.code}
        </text>
      ))}
    </svg>
  );
}

function DataTable({ laps, title }: { laps: DebriefLaps; title: string }) {
  return (
    <div className="sr-only">
      <table>
        <caption>{title}</caption>
        <thead>
          <tr>
            <th scope="col">Driver</th>
            {laps.leaders.map((_, index) => (
              <th key={index} scope="col">{`L${index + 1}`}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {laps.trace.map((car) => (
            <tr key={car.driver_code}>
              <th scope="row">{car.driver_code}</th>
              {car.gaps.map((gap, index) => (
                <td key={index}>{gap === null ? "—" : `${gap} s`}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Gap to the leader at every line crossing for the first five cars home, with the neutralised laps marked. */
export function RaceTrace({ laps, year, round }: { laps: DebriefLaps; year: number; round: number }) {
  const directory = useSeasonDirectory();
  if (!laps.available || laps.trace.length === 0) {
    return (
      <div className={CARD}>
        <PanelHeading eyebrow="Race trace" />
        <p className="text-sm text-rc-ink-3">{laps.reason ?? "No race trace for this race."}</p>
      </div>
    );
  }
  const geometry = traceGeometry(laps);
  const title = traceTitle(laps.neutralisations);
  const last = (code: string) =>
    driverLabel(
      { name: laps.drivers.find((driver) => driver.driver_code === code)?.driver_name ?? code, code },
      "last",
      directory,
    );
  const podium = geometry.lines.filter((line) => !line.quiet);
  const rest = geometry.lines.filter((line) => line.quiet);
  const items: LegendItem[] = [
    ...podium.map((line) => ({ label: last(line.code), color: line.color })),
    ...(rest.length > 0 ? [{ label: rest.map((line) => last(line.code)).join(", "), color: rc.dim }] : []),
    ...(geometry.bands.length > 0 ? [{ label: "VSC / Safety Car", color: rc.ink3 }] : []),
    ...(geometry.red ? [{ label: "Red flag", color: f1.red, mark: "rule" as const }] : []),
  ];
  return (
    <figure className={CARD}>
      <PanelHeading
        eyebrow="Race trace"
        title={title}
        sub="Gap to the leader at each line crossing, top five · capped at 30 s"
      />
      <Plot geometry={geometry} />
      <DataTable laps={laps} title={title} />
      <Legend items={items} label="Race trace" className="mt-3.5" />
      <Link
        href={`/race-control/rewind?round=${round}&year=${year}`}
        className="mt-5 inline-block font-mono text-xs font-semibold uppercase tracking-[0.14em] text-rc-ink hover:underline"
      >
        Replay this race lap by lap →
      </Link>
    </figure>
  );
}
