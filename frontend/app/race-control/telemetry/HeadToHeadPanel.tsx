"use client";

import { useMemo } from "react";

import { Panel, rcFont } from "../components/RaceControlPrimitives";

import { AnalysisGate, AnalysisWarnings, ModeledNote } from "./AnalysisNotice";
import { DriverPicker } from "./AnalysisPickers";
import { gainLabel, miniSectorAt, pairColours, traceRows, winnerColour, type PairColours } from "./headToHeadModel";
import { formatGap, formatLapTime } from "./telemetryModel";
import { TelemetryTraces } from "./TelemetryTraces";
import { TrackMap } from "./TrackMap";
import { EVEN_COLOUR } from "./trackMapGeometry";
import { useComparison, useLapList } from "./useAnalysisData";

import type { ComparisonResponse, Stretch } from "./telemetryModel";

export interface HeadToHeadPanelProps {
  year: number;
  round: number | null;
  session: string | null;
  a: string | null;
  b: string | null;
  onPick: (a: string | null, b: string | null) => void;
}

interface Codes {
  a: string;
  b: string;
}

function LapSummary({ data, codes }: { data: ComparisonResponse; codes: Codes }) {
  const gap = data.gap ?? 0;
  const ahead = gap >= 0 ? codes.a : codes.b;
  return (
    <div className="flex flex-wrap items-end gap-x-6 gap-y-2">
      <div>
        <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-[#7F8797]">Lap times</p>
        <p className="font-mono text-sm text-white">
          {codes.a} {formatLapTime(data.a?.lap.time)} · {codes.b} {formatLapTime(data.b?.lap.time)}
        </p>
      </div>
      <div>
        <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-[#7F8797]">At the line</p>
        <p className="font-mono text-2xl font-black text-white" style={rcFont}>
          {ahead} by {Math.abs(gap).toFixed(3)}s
        </p>
      </div>
    </div>
  );
}

function SectorTable({ data, codes }: { data: ComparisonResponse; codes: Codes }) {
  return (
    <table className="w-full max-w-md text-left font-mono text-xs">
      <caption className="mb-1 text-left text-[10px] font-bold uppercase tracking-[0.18em] text-[#7F8797]">
        Official sector times
      </caption>
      <thead className="text-[#7F8797]">
        <tr>
          <th className="py-1 pr-3 font-normal">Sector</th>
          <th className="py-1 pr-3 font-normal">{codes.a}</th>
          <th className="py-1 pr-3 font-normal">{codes.b}</th>
          <th className="py-1 font-normal">
            {codes.b} vs {codes.a}
          </th>
        </tr>
      </thead>
      <tbody className="text-neutral-200">
        {(data.sectors ?? []).map((sector) => (
          <tr key={sector.sector} className="border-t border-[#161D28]">
            <td className="py-1 pr-3">S{sector.sector}</td>
            <td className="py-1 pr-3">{formatLapTime(sector.a)}</td>
            <td className="py-1 pr-3">{formatLapTime(sector.b)}</td>
            <td className="py-1">{formatGap(sector.gain)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function GainList({ title, stretches, codes }: { title: string; stretches: Stretch[]; codes: Codes }) {
  return (
    <div className="min-w-[200px] flex-1">
      <p className="mb-1 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-[#7F8797]">{title}</p>
      {stretches.length === 0 ? (
        <p className="font-mono text-xs text-[#6F7789]">Nowhere.</p>
      ) : (
        <ul className="space-y-0.5 font-mono text-xs text-neutral-200">
          {stretches.map((stretch) => (
            <li key={stretch.label}>
              {stretch.label} · {gainLabel(stretch, codes)}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function SectorMap({ data, colours, codes }: { data: ComparisonResponse; colours: PairColours; codes: Codes }) {
  const map = data.map;
  const stretches = useMemo(() => data.mini_sectors ?? [], [data.mini_sectors]);
  const owner = useMemo(() => miniSectorAt(stretches, map?.distance ?? []), [stretches, map]);
  if (!map) return null;
  const at = (index: number) => stretches[owner[index]] as Stretch | undefined;
  return (
    <div className="space-y-2">
      <TrackMap
        x={map.x}
        y={map.y}
        colourAt={(index) => winnerColour(at(index)?.faster ?? "even", colours)}
        dashedAt={(index) => at(index)?.faster === "b"}
        corners={data.corner_markers}
        readout={(index) => {
          const stretch = at(index);
          return `${Math.round(map.distance[index])} m · ${stretch ? `${stretch.label} · ${gainLabel(stretch, codes)}` : "-"}`;
        }}
        ariaLabel={`Circuit coloured by who was faster in each of ${stretches.length} mini-sectors`}
      />
      <div className="flex flex-wrap gap-x-4 font-mono text-[11px] text-[#A8AFBF]">
        <span className="inline-flex items-center gap-1.5">
          <span className="h-1 w-5 rounded" style={{ background: colours.a }} aria-hidden /> {codes.a} faster
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-1 w-5 rounded border-t-2 border-dashed" style={{ borderColor: colours.b }} aria-hidden />{" "}
          {codes.b} faster
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="h-1 w-5 rounded" style={{ background: EVEN_COLOUR }} aria-hidden /> even
        </span>
      </div>
    </div>
  );
}

function CornerTable({ data, codes }: { data: ComparisonResponse; codes: Codes }) {
  const corners = data.corners ?? [];
  if (corners.length === 0) return null;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[360px] text-left font-mono text-xs">
        <caption className="mb-1 text-left text-[10px] font-bold uppercase tracking-[0.18em] text-[#7F8797]">
          Time gained corner by corner (each corner owns the track halfway to its neighbours)
        </caption>
        <thead className="text-[#7F8797]">
          <tr>
            <th className="py-1 pr-3 font-normal">Corner</th>
            <th className="py-1 pr-3 font-normal">Stretch</th>
            <th className="py-1 font-normal">Faster</th>
          </tr>
        </thead>
        <tbody className="text-neutral-200">
          {corners.map((corner) => (
            <tr key={corner.label} className="border-t border-[#161D28]">
              <td className="py-1 pr-3">{corner.label}</td>
              <td className="py-1 pr-3">
                {Math.round(corner.start)}-{Math.round(corner.end)} m
              </td>
              <td className="py-1">{gainLabel(corner, codes)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Comparison({ data }: { data: ComparisonResponse }) {
  const codes = { a: data.a?.driver.code ?? "A", b: data.b?.driver.code ?? "B" };
  const colours = pairColours(data);
  const rows = useMemo(() => traceRows(data.trace), [data.trace]);
  const gains = data.biggest_gains ?? { a: [], b: [] };
  return (
    <Panel className="space-y-5 p-4">
      <LapSummary data={data} codes={codes} />
      <div className="flex flex-wrap gap-6">
        <SectorTable data={data} codes={codes} />
        <GainList title={`Where ${codes.a} gains most`} stretches={gains.a} codes={codes} />
        <GainList title={`Where ${codes.b} gains most`} stretches={gains.b} codes={codes} />
      </div>
      <SectorMap data={data} colours={colours} codes={codes} />
      <TelemetryTraces rows={rows} colours={colours} codes={codes} />
      <CornerTable data={data} codes={codes} />
      <AnalysisWarnings warnings={data.warnings} />
      <ModeledNote
        modeled={data.modeled}
        extra="Both laps are put on one distance axis; the gap at the line equals the official lap-time difference."
      />
    </Panel>
  );
}

export function HeadToHeadPanel({ year, round, session, a, b, onPick }: HeadToHeadPanelProps) {
  const laps = useLapList(year, round, session);
  const drivers = (laps.data?.drivers ?? []).filter((driver) => driver.best !== null);
  const first = a ?? drivers[0]?.code ?? null;
  const second = b ?? drivers.find((driver) => driver.code !== first)?.code ?? null;
  const comparison = useComparison(year, round, { session, a: first, b: second });

  return (
    <div className="space-y-4">
      <AnalysisGate state={laps} loadingTitle="Loading the session's laps" />
      {drivers.length > 1 && (
        <div className="flex flex-wrap items-center gap-3">
          <DriverPicker
            label="Driver A"
            drivers={drivers}
            value={first}
            onChange={(code) => {
              onPick(code, second === code ? first : second);
            }}
          />
          <DriverPicker
            label="Driver B"
            drivers={drivers}
            value={second}
            onChange={(code) => {
              onPick(first === code ? second : first, code);
            }}
          />
          <span className="font-mono text-[11px] text-[#6F7789]">Each driver&apos;s fastest valid lap</span>
        </div>
      )}
      <AnalysisGate state={comparison} loadingTitle="Comparing the two laps" />
      {comparison.data?.available && <Comparison data={comparison.data} />}
    </div>
  );
}
