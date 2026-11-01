"use client";

import { useMemo, useState } from "react";

import { InlineNotice, Panel } from "../components/RaceControlPrimitives";
import { compoundColor, compoundLabel } from "../grand-prix/tyreCompounds";

import { AnalysisGate, AnalysisWarnings, ModeledNote } from "./AnalysisNotice";
import { CompoundKey, DegradationScatter, RacePaceChart } from "./DegradationCharts";
import { defaultDrivers, fitLines, formatRate, paceDomain, paceRows, scatterGroups, yDomain } from "./degradationModel";
import { useDegradation } from "./useAnalysisData";

import type { DegradationResponse, DegradationStint } from "./telemetryModel";

export interface TyreDegPanelProps {
  year: number;
  round: number | null;
  session: string | null;
}

const TITLE = "font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-[#7F8797]";

function Toggle({ label, on, onChange }: { label: string; on: boolean; onChange: (on: boolean) => void }) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-2 font-mono text-xs text-[#A8AFBF]">
      <input
        type="checkbox"
        checked={on}
        onChange={(event) => {
          onChange(event.target.checked);
        }}
        className="accent-[#3987E5]"
      />
      {label}
    </label>
  );
}

function DriverChips({
  data,
  selected,
  onToggle,
}: {
  data: DegradationResponse;
  selected: string[];
  onToggle: (code: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-1.5" role="group" aria-label="Drivers">
      {(data.drivers ?? []).map((driver) => {
        const on = selected.includes(driver.code);
        return (
          <button
            key={driver.code}
            type="button"
            aria-pressed={on}
            onClick={() => {
              onToggle(driver.code);
            }}
            className={`inline-flex items-center gap-1.5 rounded border px-2 py-1 font-mono text-[11px] font-bold ${
              on ? "border-white/40 text-white" : "border-[#1E2633] text-[#6F7789]"
            }`}
          >
            <span className="h-2 w-2 rounded-full" style={{ background: driver.colour }} aria-hidden />
            {driver.position === null ? "" : `P${driver.position} `}
            {driver.code}
          </button>
        );
      })}
    </div>
  );
}

function CompoundTable({ data }: { data: DegradationResponse }) {
  const compounds = data.compounds ?? [];
  if (compounds.length === 0) {
    return <p className="font-mono text-xs text-[#6F7789]">No stint had enough clean laps to fit.</p>;
  }
  return (
    <table className="w-full max-w-2xl text-left font-mono text-xs">
      <caption className={`${TITLE} mb-1 text-left`}>Wear rate per compound, median over the stints fitted</caption>
      <thead className="text-[#7F8797]">
        <tr>
          <th className="py-1 pr-3 font-normal">Compound</th>
          <th className="py-1 pr-3 font-normal">Stints</th>
          <th className="py-1 pr-3 font-normal">Fuel-corrected</th>
          <th className="py-1 pr-3 font-normal">Raw</th>
          <th className="py-1 font-normal">Middle half of stints</th>
        </tr>
      </thead>
      <tbody className="text-neutral-200">
        {compounds.map((row) => (
          <tr key={row.compound} className="border-t border-[#161D28]">
            <td className="py-1 pr-3">
              <span className="inline-flex items-center gap-1.5">
                <span
                  className="h-2 w-2 rounded-full"
                  style={{ background: compoundColor(row.compound) }}
                  aria-hidden
                />
                {compoundLabel(row.compound)}
              </span>
            </td>
            <td className="py-1 pr-3">{row.stints}</td>
            <td className="py-1 pr-3">{row.corrected ? formatRate(row.median_slope) : "-"}</td>
            <td className="py-1 pr-3">{formatRate(row.median_raw_slope)}</td>
            <td className="py-1">
              {formatRate(row.iqr[0])} to {formatRate(row.iqr[1])}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function StintTable({ stints }: { stints: DegradationStint[] }) {
  if (stints.length === 0) return null;
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] text-left font-mono text-xs">
        <caption className={`${TITLE} mb-1 text-left`}>Stints of the selected drivers</caption>
        <thead className="text-[#7F8797]">
          <tr>
            <th className="py-1 pr-3 font-normal">Driver</th>
            <th className="py-1 pr-3 font-normal">Stint</th>
            <th className="py-1 pr-3 font-normal">Laps</th>
            <th className="py-1 pr-3 font-normal">Clean laps fitted</th>
            <th className="py-1 pr-3 font-normal">Raw rate</th>
            <th className="py-1 pr-3 font-normal">Fuel-corrected</th>
            <th className="py-1 font-normal">Fit (r²)</th>
          </tr>
        </thead>
        <tbody className="text-neutral-200">
          {stints.map((stint) => (
            <tr key={`${stint.driver}-${stint.stint}`} className="border-t border-[#161D28]">
              <td className="py-1 pr-3">{stint.driver}</td>
              <td className="py-1 pr-3">
                {stint.stint} · {compoundLabel(stint.compound)}
                {stint.tyre_life_start ? ` (${stint.tyre_life_start} laps old)` : ""}
              </td>
              <td className="py-1 pr-3">
                {stint.start_lap}-{stint.end_lap}
                {stint.boundary_checked ? "" : "*"}
              </td>
              <td className="py-1 pr-3">{stint.fit?.laps_fitted ?? "too few"}</td>
              <td className="py-1 pr-3">{formatRate(stint.fit?.raw.slope)}</td>
              <td className="py-1 pr-3">{formatRate(stint.fit?.corrected?.slope)}</td>
              <td className="py-1">{stint.fit ? (stint.fit.corrected ?? stint.fit.raw).r2.toFixed(2) : "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Assumptions({ data }: { data: DegradationResponse }) {
  const assumptions = data.assumptions;
  if (!assumptions) return null;
  const fuel = assumptions.fuel;
  return (
    <InlineNotice title="How this is worked out" tone="info">
      Only clean laps are fitted: not the opening lap, pit laps, safety-car, VSC or red-flag laps, the lap after a
      restart, wet laps, laps within {assumptions.traffic_gap_seconds}s of the car ahead, or laps over{" "}
      {Math.round(assumptions.outlier_factor * 100)}% of the driver&apos;s median. A stint needs{" "}
      {assumptions.min_fit_laps} clean laps for a rate.{" "}
      {fuel
        ? `Fuel correction assumes ${fuel.start_fuel_kg} kg at the start burnt evenly over ${fuel.race_laps} laps at ${fuel.seconds_per_kg} s/kg, which adds ${fuel.slope_effect.toFixed(3)} s/lap to every rate; the raw rate is shown beside it.`
        : "These laps are not fuel-corrected."}
    </InlineNotice>
  );
}

function Degradation({ data }: { data: DegradationResponse }) {
  const hasFuel = Boolean(data.assumptions?.fuel);
  const [picked, setPicked] = useState<string[] | null>(null);
  const [corrected, setCorrected] = useState(hasFuel);
  const [showExcluded, setShowExcluded] = useState(true);
  const selected = picked ?? defaultDrivers(data);
  const chosen = useMemo(() => new Set(selected), [selected]);
  const laps = useMemo(() => data.laps ?? [], [data.laps]);
  const useCorrected = corrected && hasFuel;
  const groups = useMemo(() => scatterGroups(laps, chosen, useCorrected), [laps, chosen, useCorrected]);
  const fits = useMemo(
    () => fitLines(data.stints ?? [], laps, chosen, useCorrected),
    [data.stints, laps, chosen, useCorrected],
  );
  const domain = yDomain(groups.clean);
  const paceDrivers = (data.drivers ?? []).filter((driver) => chosen.has(driver.code));
  const rows = useMemo(() => paceRows(laps, selected, useCorrected), [laps, selected, useCorrected]);
  const pace = paceDomain(rows, selected);
  const toggle = (code: string) => {
    setPicked(selected.includes(code) ? selected.filter((item) => item !== code) : [...selected, code]);
  };

  return (
    <Panel className="space-y-5 p-4">
      <CompoundTable data={data} />
      <DriverChips data={data} selected={selected} onToggle={toggle} />
      <div className="flex flex-wrap gap-4">
        {hasFuel && <Toggle label="Fuel-corrected times (modelled)" on={corrected} onChange={setCorrected} />}
        <Toggle label="Show laps left out of the fit" on={showExcluded} onChange={setShowExcluded} />
      </div>
      <div>
        <p className={`${TITLE} mb-2`}>Lap time against tyre age</p>
        <CompoundKey compounds={[...groups.clean.keys()]} showExcluded={showExcluded} />
        {domain ? (
          <DegradationScatter
            clean={groups.clean}
            excluded={groups.excluded}
            fits={fits}
            domain={domain}
            labels={data.status_labels ?? {}}
            showExcluded={showExcluded}
          />
        ) : (
          <p className="py-6 font-mono text-xs text-[#6F7789]">Pick a driver with clean laps to plot.</p>
        )}
      </div>
      {pace && (
        <div>
          <p className={`${TITLE} mb-2`}>Race pace, lap by lap (gaps are pit, safety-car and opening laps)</p>
          <RacePaceChart rows={rows} drivers={paceDrivers} domain={pace} bands={data.neutralised ?? []} />
        </div>
      )}
      <StintTable stints={(data.stints ?? []).filter((stint) => chosen.has(stint.driver))} />
      <Assumptions data={data} />
      <AnalysisWarnings warnings={data.warnings} />
      <ModeledNote
        modeled={data.modeled}
        extra="A * marks a stint change OpenF1 placed with no pit-out lap beside it."
      />
    </Panel>
  );
}

export function TyreDegPanel({ year, round, session }: TyreDegPanelProps) {
  const degradation = useDegradation(year, round, session);
  return (
    <div className="space-y-4">
      <AnalysisGate state={degradation} loadingTitle="Reading every lap of the race" />
      {degradation.data?.available && <Degradation key={`${year}-${round}-${session}`} data={degradation.data} />}
    </div>
  );
}
