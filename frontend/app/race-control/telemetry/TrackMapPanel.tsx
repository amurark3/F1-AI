"use client";

import { useMemo } from "react";

import { DriverName } from "@/app/ui/names/DriverName";
import { TeamName } from "@/app/ui/names/TeamName";
import { PanelHeading } from "@/app/ui/PanelHeading";

import { Panel } from "../components/RaceControlPrimitives";

import { AnalysisGate, AnalysisWarnings, ModeledNote } from "./AnalysisNotice";
import { resolveSegment, titleSegment } from "./qualifyingSegments";
import { formatLapTime } from "./telemetryModel";
import { GradientLegend, TrackMap, type MapMarker } from "./TrackMap";
import { SPEED_RAMP, speedScale } from "./trackMapGeometry";
import { defaultDriver } from "./trackMapSelection";
import { useLapList, useTrackMap } from "./useAnalysisData";

import type { TrackMapResponse } from "./telemetryModel";

export interface TrackMapPanelProps {
  year: number;
  round: number | null;
  session: string | null;
  driver: string | null;
  lap: number | null;
  segment: number | null;
}

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="min-w-[120px] flex-1 rounded border border-[#1E2633] bg-[#0A0E16] px-3 py-2">
      <p className="font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-[#7F8797]">{label}</p>
      <p className="mt-1 font-mono text-lg font-black text-white">{value}</p>
      {sub && <p className="text-[11px] text-[#6F7789]">{sub}</p>}
    </div>
  );
}

function mapMarkers(data: TrackMapResponse): MapMarker[] {
  const braking = (data.braking_zones ?? []).map((zone, index) => ({
    key: `brake-${index}`,
    x: zone.x,
    y: zone.y,
    label: `Braking from ${zone.entry_speed} to ${zone.min_speed} km/h at ${Math.round(zone.start)} m`,
    kind: "brake" as const,
  }));
  const top = data.stats?.top_speed;
  const peak: MapMarker[] = top
    ? [{ key: "top", x: top.x, y: top.y, label: `Top speed ${top.speed} km/h`, kind: "top" }]
    : [];
  return [...braking, ...peak];
}

function MapStats({ data }: { data: TrackMapResponse }) {
  const lap = data.lap;
  const stats = data.stats;
  if (!lap || !stats) return null;
  return (
    <div className="flex flex-wrap gap-2">
      <Stat
        label="Lap time"
        value={formatLapTime(lap.time)}
        sub={`Lap ${lap.number}${lap.is_fastest ? " · fastest valid" : ""}${lap.deleted ? " · deleted" : ""}`}
      />
      <Stat label="Top speed" value={`${stats.top_speed.speed} km/h`} sub="car telemetry" />
      <Stat
        label="Speed trap"
        value={lap.speed_traps.speed_trap === null ? "-" : `${lap.speed_traps.speed_trap} km/h`}
        sub="official trap"
      />
      <Stat label="Full throttle" value={`${stats.full_throttle_pct}%`} sub="of lap time" />
      <Stat label="On the brakes" value={`${stats.braking_pct}%`} sub="of lap time" />
    </div>
  );
}

function BrakingTable({ data }: { data: TrackMapResponse }) {
  const zones = data.braking_zones ?? [];
  if (zones.length === 0) return null;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[420px] text-left font-mono text-xs">
        <caption className="mb-2 text-left text-[10px] font-bold uppercase tracking-[0.18em] text-[#7F8797]">
          Braking zones, in lap order
        </caption>
        <thead className="text-[#7F8797]">
          <tr>
            <th className="py-1 pr-3 font-normal">#</th>
            <th className="py-1 pr-3 font-normal">From</th>
            <th className="py-1 pr-3 font-normal">Length</th>
            <th className="py-1 pr-3 font-normal">Entry</th>
            <th className="py-1 font-normal">Slowest</th>
          </tr>
        </thead>
        <tbody className="text-rc-ink">
          {zones.map((zone, index) => (
            <tr key={zone.start} className="border-t border-[#161D28]">
              <td className="py-1 pr-3 text-[#7F8797]">{index + 1}</td>
              <td className="py-1 pr-3">{Math.round(zone.start)} m</td>
              <td className="py-1 pr-3">{Math.round(zone.end - zone.start)} m</td>
              <td className="py-1 pr-3">{zone.entry_speed} km/h</td>
              <td className="py-1">{zone.min_speed} km/h</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SpeedMap({ data }: { data: TrackMapResponse }) {
  const points = data.points;
  const scale = useMemo(() => speedScale(points?.speed ?? []), [points]);
  if (!points) return null;
  const readout = (index: number) =>
    `${Math.round(points.distance[index])} m · ${points.speed[index]} km/h · gear ${points.gear[index]} · throttle ${points.throttle[index]}%${points.brake[index] > 0 ? " · braking" : ""}`;
  return (
    <div className="space-y-3">
      <TrackMap
        x={points.x}
        y={points.y}
        key={`${data.driver?.code}-${data.lap?.number}`}
        colourAt={(index) => scale.colour((points.speed[index] + points.speed[index + 1]) / 2)}
        corners={data.corners}
        markers={mapMarkers(data)}
        readout={readout}
        ariaLabel={`${data.driver?.code ?? ""} lap coloured by speed, ${Math.round(scale.min)} to ${Math.round(scale.max)} km/h`}
      />
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <GradientLegend colours={SPEED_RAMP} min={scale.min} max={scale.max} unit="km/h" />
        <span className="inline-flex items-center gap-1.5 font-mono text-[11px] text-[#A8AFBF]">
          <span className="h-2.5 w-2.5 rounded-full bg-[#D95926]" aria-hidden /> braking point
        </span>
        <span className="inline-flex items-center gap-1.5 font-mono text-[11px] text-[#A8AFBF]">
          <span className="h-2.5 w-2.5 rounded-full bg-[#F0EFEC]" aria-hidden /> top speed
        </span>
      </div>
    </div>
  );
}

/** "Q3 · fastest valid lap", or "Q3 · lap 12" for a chosen lap; the lap alone outside qualifying. */
function lapPhrase(part: string | null, lap: { number: number }, chosen: number | null): string {
  const what = chosen === null && part !== null ? "fastest valid lap" : `lap ${lap.number}`;
  return part === null ? what : `${part} · ${what}`;
}

export function TrackMapPanel({ year, round, session, driver, lap, segment }: TrackMapPanelProps) {
  const laps = useLapList(year, round, session);
  const drivers = laps.data?.drivers ?? [];
  const choice = resolveSegment(laps.data, [driver], segment);
  const code = driver ?? defaultDriver(drivers, choice?.segment ?? null);
  // Wait for the lap list: whether the session has qualifying parts decides what to ask for.
  const map = useTrackMap(year, round, {
    session: laps.data ? session : null,
    driver: code,
    lap,
    segment: choice?.segment ?? null,
  });
  const data = map.data;
  const part = titleSegment(drivers, code, lap, choice);

  return (
    <div className="space-y-4">
      <AnalysisGate state={laps} loadingTitle="Loading the session's laps" />
      <AnalysisGate state={map} loadingTitle="Loading the lap's telemetry" />
      {data?.available && (
        <Panel className="space-y-4 p-4">
          <PanelHeading
            as="h2"
            eyebrow="Speed map"
            title={
              data.driver && data.lap ? (
                <>
                  <DriverName name={data.driver.name} code={data.driver.code} year={year} /> ·{" "}
                  {lapPhrase(part, data.lap, lap)} · {formatLapTime(data.lap.time)}
                </>
              ) : undefined
            }
            sub={
              data.driver && (
                <>
                  <TeamName name={data.driver.team} year={year} />. Slow is deep blue, fast is pale.
                </>
              )
            }
            className="!mb-0"
          />
          <MapStats data={data} />
          <SpeedMap data={data} />
          <AnalysisWarnings warnings={data.warnings} />
          <BrakingTable data={data} />
          <ModeledNote
            modeled={data.modeled}
            extra="A braking zone is where the brake channel (on/off, ~4 samples a second) was on, so its start is known to within one sample."
          />
        </Panel>
      )}
    </div>
  );
}
