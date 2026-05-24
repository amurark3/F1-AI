"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import { Flag, RefreshCw, ShieldCheck, Target, Trophy } from "lucide-react";
import { getTeamColor } from "@/app/components/PredictionDriverCard";
import { API_BASE } from "@/app/constants/api";
import { fetcher } from "@/app/utils/fetcher";
import { InlineNotice, PageLoader, Panel, SectionHeader, SectionLoader, StatusPill, WorkspaceSplit, rcFont } from "../components/RaceControlPrimitives";

interface DriverOption {
  code: string;
  name: string;
  team: string;
  position: number;
  points: number;
  wins: number;
}

interface DriversResponse {
  year: number;
  source: string;
  drivers: DriverOption[];
  error?: string | null;
}

interface BattleFact {
  key: string;
  label: string;
  values: Record<string, string>;
}

interface BattlePriority {
  code: string | null;
  driver: string;
  team?: string | null;
  confidence: string;
  basis: string;
}

interface Battle {
  year: number;
  status: "ok" | "data_unavailable" | "driver_not_found" | "invalid_selection";
  source: string;
  drivers: DriverOption[];
  summary: string;
  facts?: BattleFact[];
  decision_factors?: string[];
  priority?: BattlePriority;
  recommendation: string;
  data_limitations?: string[];
  error?: string | null;
}

const year = new Date().getFullYear();

const sourceLabel = (source?: string) => source ? "official standings feed" : "standings feed";
const pointsLabel = (points: number) => Number.isInteger(points) ? String(points) : points.toFixed(1);

export default function BattlesPage() {
  const [selection, setSelection] = useState({ driver1: "", driver2: "" });
  const {
    data: driversData,
    error: driversError,
    isLoading: driversLoading,
    mutate: reloadDrivers,
  } = useSWR<DriversResponse>(
    `${API_BASE}/api/race-control/drivers/${year}`,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 180000 }
  );

  const drivers = useMemo(() => driversData?.drivers ?? [], [driversData?.drivers]);
  const defaultDriver1 = drivers[0]?.code ?? "";
  const defaultDriver2 = drivers.find((driver) => driver.code !== defaultDriver1)?.code ?? "";
  const selectedDriver1 = selection.driver1 || defaultDriver1;
  const selectedDriver2 = selection.driver2 || defaultDriver2;
  const invalidPair = Boolean(selectedDriver1 && selectedDriver2 && selectedDriver1 === selectedDriver2);
  const canCompare = drivers.length >= 2 && Boolean(selectedDriver1 && selectedDriver2) && !invalidPair;

  const {
    data,
    error: battleError,
    isLoading: battleLoading,
    mutate,
  } = useSWR<Battle>(
    canCompare ? `${API_BASE}/api/race-control/battle/${year}/${selectedDriver1}/${selectedDriver2}` : null,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 120000 }
  );

  const driverA = data?.drivers?.[0] ?? drivers.find((driver) => driver.code === selectedDriver1);
  const driverB = data?.drivers?.[1] ?? drivers.find((driver) => driver.code === selectedDriver2);
  const facts = data?.facts ?? buildFallbackFacts(driverA, driverB);
  const pageLoading = driversLoading && drivers.length === 0;

  if (pageLoading) {
    return (
      <div>
        <SectionHeader
          eyebrow="Driver Battle Analyzer"
          title="First-Call Brief"
          description="Compare two real drivers from the current standings and decide whether standings alone justify strategic priority."
        />
        <PageLoader
          title="Preparing battle analyzer"
          detail="Loading the current driver standings before the comparison controls open."
        />
      </div>
    );
  }

  return (
    <div>
      <SectionHeader
        eyebrow="Driver Battle Analyzer"
        title="First-Call Brief"
        description="A conservative strategy briefing: raw standings facts, clear gaps, and a call on whether one driver deserves first strategic attention."
      />

      <Panel className="mb-5 p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start [&>label]:flex-1">
          <DriverSelect
            label="Driver 1"
            value={selectedDriver1}
            onChange={(value) => setSelection((current) => ({ ...current, driver1: value }))}
            drivers={drivers}
            disabled={driversLoading || drivers.length === 0}
            loading={driversLoading}
          />
          <DriverSelect
            label="Driver 2"
            value={selectedDriver2}
            onChange={(value) => setSelection((current) => ({ ...current, driver2: value }))}
            drivers={drivers}
            disabled={driversLoading || drivers.length === 0}
            loading={driversLoading}
          />
          <button
            onClick={() => void mutate()}
            disabled={!canCompare || battleLoading}
            className="inline-flex h-12 w-full items-center justify-center gap-2 rounded-lg bg-[#00FF78] px-5 text-sm font-black uppercase tracking-wider text-black transition-colors hover:bg-white disabled:cursor-not-allowed disabled:bg-white/10 disabled:text-neutral-500 lg:mt-6 lg:w-[180px] lg:shrink-0"
          >
            <RefreshCw className={`h-4 w-4 ${battleLoading ? "animate-spin" : ""}`} />
            Compare
          </button>
        </div>

        <div className="mt-4 space-y-3">
          {driversError && (
            <InlineNotice title="Driver Feed Unavailable" tone="error">
              The standings-backed driver list could not be loaded.
              <button onClick={() => void reloadDrivers()} className="ml-2 font-bold text-white underline decoration-white/30">Retry</button>
            </InlineNotice>
          )}
          {driversData?.error && !driversError && (
            <InlineNotice title="No Standings Found" tone="warning">
              {driversData.error}
            </InlineNotice>
          )}
          {invalidPair && (
            <InlineNotice title="Choose Two Drivers" tone="warning">
              A battle call needs two different drivers.
            </InlineNotice>
          )}
          {!driversLoading && drivers.length > 0 && (
            <p className="text-sm text-neutral-400">
              Driver names, teams, positions, points, and wins are loaded from <span className="text-neutral-200">{sourceLabel(driversData?.source)}</span>.
            </p>
          )}
        </div>
      </Panel>

      {battleLoading ? (
        <SectionLoader
          title="Refreshing first-call brief"
          detail="Updating standings facts and the strategy recommendation for the selected drivers."
        />
      ) : (
        <WorkspaceSplit className="xl:[&>*:first-child]:basis-[58%] xl:[&>*:last-child]:flex-1">
          <Panel className="p-5" accent="#58A6FF">
            <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              <div>
                <p className="text-xs font-black uppercase tracking-[0.18em] text-neutral-400" style={rcFont}>Standings Brief</p>
                <h2 className="text-3xl font-black italic uppercase leading-none text-white" style={rcFont}>
                  {driverA && driverB ? `${driverA.code} vs ${driverB.code}` : "Select Two Drivers"}
                </h2>
                <p className="mt-2 text-sm leading-relaxed text-neutral-400">
                  Raw championship fields only. No hidden scoring, no invented pace, no tyre model.
                </p>
              </div>
              <StatusPill color="#58A6FF">Standings only</StatusPill>
            </div>

            {battleError && (
              <InlineNotice title="Battle Data Unavailable" tone="error">
                The battle API did not respond. The driver selectors stay visible so you can retry without losing context.
              </InlineNotice>
            )}
            {!battleError && data?.status && data.status !== "ok" && (
              <InlineNotice title="Battle Not Generated" tone="warning">
                {data.summary}
              </InlineNotice>
            )}

            {driverA && driverB ? (
              <div className="space-y-5">
                <div className="grid gap-3 md:grid-cols-2">
                  <BattleDriverCard driver={driverA} />
                  <BattleDriverCard driver={driverB} />
                </div>
                <BattleFactTable facts={facts} drivers={[driverA, driverB]} />
                <DecisionFactors factors={data?.decision_factors ?? []} />
              </div>
            ) : (
              <InlineNotice title="Waiting For Drivers">
                Load the driver standings feed, then select two drivers to generate a comparison.
              </InlineNotice>
            )}
          </Panel>

          <Panel className="p-5" accent="#00FF78">
            <div className="mb-5 flex items-start justify-between gap-3">
              <div>
                <p className="text-xs font-black uppercase tracking-[0.18em] text-neutral-400" style={rcFont}>Strategy Call</p>
                <h2 className="text-3xl font-black italic uppercase leading-none text-white" style={rcFont}>Who Gets First Call?</h2>
              </div>
              <Target className="h-5 w-5 text-[#00FF78]" />
            </div>

            <div className="space-y-4">
              <PrioritySummary priority={data?.priority} />
              <p className="text-base leading-relaxed text-neutral-300">
                {data?.summary ?? "Select two drivers to build a standings-backed first-call brief."}
              </p>
              <div className="rounded-lg border border-white/10 bg-white/[0.035] p-4">
                <p className="text-base leading-relaxed text-neutral-200">{data?.recommendation ?? "Recommendation pending."}</p>
              </div>
              <InlineNotice title="Data Boundary">
                <ul className="list-disc space-y-1 pl-4">
                  {(data?.data_limitations ?? ["Uses standings only. Live pace, tyre degradation, and telemetry are intentionally not shown here."]).map((item) => (
                    <li key={item}>{item}</li>
                  ))}
                </ul>
              </InlineNotice>
            </div>
          </Panel>
        </WorkspaceSplit>
      )}
    </div>
  );
}

function DriverSelect({
  label,
  value,
  onChange,
  drivers,
  disabled,
  loading,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  drivers: DriverOption[];
  disabled: boolean;
  loading: boolean;
}) {
  const selected = drivers.find((driver) => driver.code === value);

  return (
    <label className="min-w-0">
      <span className="mb-2 block text-xs font-black uppercase tracking-[0.18em] text-neutral-300" style={rcFont}>{label}</span>
      <select
        value={value}
        onChange={(event) => onChange(event.target.value)}
        disabled={disabled}
        className="h-12 w-full rounded-lg border border-white/12 bg-[#151817] px-3 text-base font-semibold text-white outline-none transition-colors focus:border-[#00FF78]/70 disabled:text-neutral-500"
      >
        <option value="">{loading ? "Loading driver standings..." : "Select a driver"}</option>
        {drivers.map((driver) => (
          <option key={driver.code} value={driver.code}>
            {driver.name} ({driver.code}) - {driver.team}
          </option>
        ))}
      </select>
      {selected && (
        <p className="mt-2 text-sm text-neutral-400">
          {selected.team} · WDC P{selected.position} · {pointsLabel(selected.points)} pts · {selected.wins} wins
        </p>
      )}
    </label>
  );
}

function BattleDriverCard({ driver }: { driver: DriverOption }) {
  const color = getTeamColor(driver.team);
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.035] p-4">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-black uppercase tracking-[0.14em]" style={{ color, ...rcFont }}>{driver.code}</p>
          <h3 className="truncate text-xl font-black text-white" style={rcFont}>{driver.name}</h3>
          <p className="truncate text-sm font-semibold" style={{ color }}>{driver.team}</p>
        </div>
        <Trophy className="h-5 w-5 shrink-0" style={{ color }} />
      </div>
      <div className="grid grid-cols-3 gap-2">
        <MiniFact label="WDC" value={`P${driver.position}`} />
        <MiniFact label="Points" value={pointsLabel(driver.points)} />
        <MiniFact label="Wins" value={String(driver.wins)} />
      </div>
    </div>
  );
}

function MiniFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-white/8 bg-black/15 p-3">
      <p className="text-[10px] font-black uppercase tracking-[0.14em] text-neutral-500">{label}</p>
      <p className="mt-1 text-lg font-black text-white" style={rcFont}>{value}</p>
    </div>
  );
}

function BattleFactTable({ facts, drivers }: { facts: BattleFact[]; drivers: DriverOption[] }) {
  return (
    <div className="overflow-hidden rounded-lg border border-white/10">
      <div className="grid grid-cols-[1.2fr_1fr_1fr] border-b border-white/10 bg-white/[0.035] px-3 py-2 text-xs font-black uppercase tracking-[0.14em] text-neutral-400" style={rcFont}>
        <span>Fact</span>
        <span>{drivers[0].code}</span>
        <span>{drivers[1].code}</span>
      </div>
      {facts.map((fact) => (
        <div key={fact.key} className="grid grid-cols-[1.2fr_1fr_1fr] border-b border-white/8 px-3 py-3 text-sm last:border-b-0">
          <span className="font-bold text-neutral-300">{fact.label}</span>
          <span className="text-white">{fact.values[drivers[0].code] ?? "-"}</span>
          <span className="text-white">{fact.values[drivers[1].code] ?? "-"}</span>
        </div>
      ))}
    </div>
  );
}

function DecisionFactors({ factors }: { factors: string[] }) {
  if (!factors.length) return null;

  return (
    <div>
      <p className="mb-2 text-xs font-black uppercase tracking-[0.18em] text-neutral-400" style={rcFont}>Why It Matters</p>
      <div className="space-y-2">
        {factors.map((factor) => (
          <div key={factor} className="flex gap-3 rounded-lg border border-white/10 bg-white/[0.025] p-3">
            <Flag className="mt-0.5 h-4 w-4 shrink-0 text-[#00FF78]" />
            <p className="text-sm leading-relaxed text-neutral-300">{factor}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function PrioritySummary({ priority }: { priority?: BattlePriority }) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.035] p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="text-xs font-black uppercase tracking-[0.18em] text-neutral-400" style={rcFont}>Priority</p>
        <StatusPill color={priorityColor(priority?.confidence)}>{priority?.confidence ?? "Pending"}</StatusPill>
      </div>
      <div className="flex items-start gap-3">
        <ShieldCheck className="mt-1 h-5 w-5 shrink-0 text-[#00FF78]" />
        <div>
          <p className="text-2xl font-black text-white" style={rcFont}>{priority?.driver ?? "No call yet"}</p>
          <p className="mt-1 text-sm text-neutral-400">
            {priority?.team ? `${priority.team} · ${priority.basis}` : priority?.basis ?? "Waiting for comparison"}
          </p>
        </div>
      </div>
    </div>
  );
}

function priorityColor(confidence?: string) {
  if (confidence === "High") return "#00FF78";
  if (confidence === "Medium") return "#FFF200";
  if (confidence === "Low") return "#58A6FF";
  return "#737373";
}

function buildFallbackFacts(driverA?: DriverOption, driverB?: DriverOption): BattleFact[] {
  if (!driverA || !driverB) return [];
  return [
    { key: "position", label: "Championship position", values: { [driverA.code]: `P${driverA.position}`, [driverB.code]: `P${driverB.position}` } },
    { key: "points", label: "Championship points", values: { [driverA.code]: pointsLabel(driverA.points), [driverB.code]: pointsLabel(driverB.points) } },
    { key: "wins", label: "Race wins", values: { [driverA.code]: String(driverA.wins), [driverB.code]: String(driverB.wins) } },
  ];
}
