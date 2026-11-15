"use client";

import { useMemo, useState } from "react";

import { RankBars } from "@/app/ui/RankBars";

import { InlineNotice } from "../components/RaceControlPrimitives";
import { compoundColor, compoundLabel } from "../grand-prix/tyreCompounds";

import { AnalysisGate, AnalysisWarnings, ModeledNote } from "./AnalysisNotice";
import { CompoundLegend, DegradationScatter, RacePaceChart, StintLengths } from "./DegradationCharts";
import { lengthRows, lengthsTitle, paceTitle, scatterTitle, wearRows, wearTitle } from "./degradationInsights";
import { defaultDrivers, fitLines, formatRate, paceDomain, paceRows, scatterGroups, yDomain } from "./degradationModel";
import { HeadToHeadCard } from "./HeadToHeadCard";
import { useDegradation } from "./useAnalysisData";

import type { DegradationResponse } from "./telemetryModel";

export interface TyreDegPanelProps {
  year: number;
  round: number | null;
  session: string | null;
}

const EMPTY = "py-6 font-mono text-xs text-rc-ink-3";

function Toggle({ label, on, onChange }: { label: string; on: boolean; onChange: (on: boolean) => void }) {
  return (
    <label className="inline-flex cursor-pointer items-center gap-2 font-mono text-xs text-rc-ink-2">
      <input
        type="checkbox"
        checked={on}
        onChange={(event) => {
          onChange(event.target.checked);
        }}
        className="accent-rc-blue"
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
              on ? "border-rc-ink-3 text-rc-ink" : "border-rc-line text-rc-ink-3"
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
  const wear = useMemo(() => wearRows(data, chosen, useCorrected), [data, chosen, useCorrected]);
  const lengths = useMemo(() => lengthRows(data, chosen), [data, chosen]);
  const unit = useCorrected ? "fuel-corrected" : "raw";
  const toggle = (code: string) => {
    setPicked(selected.includes(code) ? selected.filter((item) => item !== code) : [...selected, code]);
  };

  return (
    <div className="space-y-4">
      <DriverChips data={data} selected={selected} onToggle={toggle} />
      <div className="flex flex-wrap gap-4">
        {hasFuel && <Toggle label="Fuel-corrected times (modelled)" on={corrected} onChange={setCorrected} />}
        <Toggle label="Show laps left out of the fit" on={showExcluded} onChange={setShowExcluded} />
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <HeadToHeadCard
          eyebrow="Degradation"
          title={scatterTitle(fits)}
          sub={`${unit} lap time against tyre age · only clean laps are fitted, the rest are hollow`}
        >
          {domain ? (
            <>
              <CompoundLegend compounds={[...groups.clean.keys()]} showExcluded={showExcluded} />
              <DegradationScatter
                clean={groups.clean}
                excluded={groups.excluded}
                fits={fits}
                domain={domain}
                labels={data.status_labels ?? {}}
                showExcluded={showExcluded}
              />
            </>
          ) : (
            <p className={EMPTY}>Pick a driver with clean laps to plot.</p>
          )}
        </HeadToHeadCard>
        <HeadToHeadCard
          eyebrow="Race pace"
          title={paceTitle(laps, selected, useCorrected)}
          sub={`${unit} lap times · gaps are pit stops and neutralised laps · quickest final stint by average clean lap`}
        >
          {pace ? (
            <RacePaceChart rows={rows} drivers={paceDrivers} domain={pace} bands={data.neutralised ?? []} />
          ) : (
            <p className={EMPTY}>Pick a driver with timed laps to plot.</p>
          )}
        </HeadToHeadCard>
        <HeadToHeadCard
          eyebrow="Wear rate by stint"
          title={wearTitle(wear)}
          sub={`Fitted slope, seconds lost per lap of tyre age · ${unit}${useCorrected ? " (raw beside it)" : ""}`}
        >
          {wear.length > 0 ? (
            <RankBars
              label="Wear rate by stint"
              items={wear.map((row) => ({
                id: row.id,
                label: row.name,
                detail: `${compoundLabel(row.compound)} · ${row.laps} laps`,
                value: row.rate,
                valueText: formatRate(row.rate),
                aside: useCorrected ? `raw ${formatRate(row.raw).replace(" s/lap", "")}` : undefined,
                color: compoundColor(row.compound),
              }))}
            />
          ) : (
            <p className={EMPTY}>No stint of the selected drivers had enough clean laps to fit.</p>
          )}
        </HeadToHeadCard>
        <HeadToHeadCard eyebrow="Stint lengths" title={lengthsTitle(lengths)} sub="Laps on each set">
          {lengths.length > 0 ? (
            <StintLengths rows={lengths} />
          ) : (
            <p className={EMPTY}>No stints for the selected drivers.</p>
          )}
        </HeadToHeadCard>
      </div>
      <Assumptions data={data} />
      <AnalysisWarnings warnings={data.warnings} />
      <ModeledNote modeled={data.modeled} />
    </div>
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
