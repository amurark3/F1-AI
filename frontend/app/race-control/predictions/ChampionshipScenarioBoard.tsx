"use client";

import { useState } from "react";
import { AlertTriangle, RotateCcw } from "lucide-react";
import { getTeamColor } from "@/app/components/PredictionDriverCard";
import { InlineNotice, Panel, SectionLoader, StatusPill, WorkspaceSplit, rcFont } from "../components/RaceControlPrimitives";

interface RaceEvent {
  round: number;
  name: string;
  location: string;
  status: string;
  is_sprint?: boolean;
}

interface DriverStanding {
  code: string;
  name: string;
  team: string;
  position: number;
  points: number;
  wins: number;
}

type ScenarioEvent = "race" | "sprint";
type RacePointPosition = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10;
type SprintPointPosition = 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8;
export type PointsSlotKey = `race_p${RacePointPosition}` | `sprint_p${SprintPointPosition}`;
export type ScenarioPicks = Record<number, Partial<Record<PointsSlotKey, string>>>;
export type ScenarioPreset = "leader-protect" | "chaser-attack" | "top-three-split";

interface ScenarioSlot {
  key: PointsSlotKey;
  event: ScenarioEvent;
  label: string;
  shortLabel: string;
  position: number;
  points: number;
}

export interface ScenarioRow extends DriverStanding {
  projected: number;
  scenarioWins: number;
  scenarioPodiums: number;
  scenarioSprintScores: number;
  scenarioPoints: number;
  maxPossible: number;
  maxPotentialWins: number;
  pointsToLead: number;
  titleState: "leads" | "alive" | "countback" | "out";
  alive: boolean;
}

const RACE_POINTS = [25, 18, 15, 12, 10, 8, 6, 4, 2, 1] as const;
const SPRINT_POINTS = [8, 7, 6, 5, 4, 3, 2, 1] as const;

export const RACE_POINT_SLOTS: ScenarioSlot[] = RACE_POINTS.map((points, i) => {
  const position = (i + 1) as RacePointPosition;
  return { key: `race_p${position}` as PointsSlotKey, event: "race", label: `Race P${position}`, shortLabel: `GP P${position}`, position, points };
});

export const SPRINT_POINT_SLOTS: ScenarioSlot[] = SPRINT_POINTS.map((points, i) => {
  const position = (i + 1) as SprintPointPosition;
  return { key: `sprint_p${position}` as PointsSlotKey, event: "sprint", label: `Sprint P${position}`, shortLabel: `Sprint P${position}`, position, points };
});

function pointsLabel(points: number) {
  return Number.isInteger(points) ? String(points) : points.toFixed(1);
}

export function scenarioSlotGroup(slot: PointsSlotKey): ScenarioEvent {
  return slot.startsWith("sprint") ? "sprint" : "race";
}

function titleStateLabel(state: ScenarioRow["titleState"]) {
  if (state === "leads") return "Leads scenario";
  if (state === "alive") return "Title alive";
  if (state === "countback") return "Countback possible";
  return "Not alive";
}

function titleStateColor(state: ScenarioRow["titleState"]) {
  if (state === "leads") return "#00FF78";
  if (state === "alive") return "#3671C6";
  if (state === "countback") return "#FFF200";
  return "#737373";
}

function scenarioEventsForRace(race: RaceEvent): ScenarioEvent[] {
  return race.is_sprint ? ["sprint", "race"] : ["race"];
}

function scenarioSlotsForRaceEvent(race: RaceEvent, event: ScenarioEvent) {
  if (event === "sprint") return race.is_sprint ? SPRINT_POINT_SLOTS : [];
  return RACE_POINT_SLOTS;
}

function PointsScenarioSelect({
  race, slot, drivers, picks, onChange,
}: {
  race: RaceEvent;
  slot: ScenarioSlot;
  drivers: DriverStanding[];
  picks: Partial<Record<PointsSlotKey, string>>;
  onChange: (code: string) => void;
}) {
  const selectedCodes = new Set(
    Object.entries(picks)
      .filter(([key, code]) => key !== slot.key && scenarioSlotGroup(key as PointsSlotKey) === slot.event && Boolean(code))
      .map(([, code]) => code)
  );
  const value = picks[slot.key] ?? "";

  return (
    <label className="flex flex-col gap-2 rounded-lg border border-white/8 bg-black/15 p-2 sm:flex-row sm:items-center">
      <span className="w-28 shrink-0 text-xs font-black uppercase tracking-[0.14em] text-neutral-400">
        {slot.shortLabel} · {slot.points} pts
      </span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="h-10 min-w-0 flex-1 rounded-lg border border-white/12 bg-[#151817] px-3 text-sm font-semibold text-white outline-none focus:border-[#00FF78]/70"
      >
        <option value="">Pick {slot.label}</option>
        {drivers.map((driver) => (
          <option key={`${race.round}-${slot.key}-${driver.code}`} value={driver.code} disabled={selectedCodes.has(driver.code)}>
            {driver.name} ({driver.code}) - {driver.team}
          </option>
        ))}
      </select>
    </label>
  );
}

function ScenarioRaceEditor({
  race, drivers, picks, pickCount, onSetPick,
}: {
  race: RaceEvent;
  drivers: DriverStanding[];
  picks: Partial<Record<PointsSlotKey, string>>;
  pickCount: number;
  onSetPick: (round: number, slot: PointsSlotKey, code: string) => void;
}) {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.03] p-4">
      <div className="mb-4 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.18em] text-neutral-400" style={rcFont}>Editing Scenario Event</p>
          <h3 className="text-2xl font-black italic uppercase text-white" style={rcFont}>{race.name}</h3>
          <p className="mt-1 text-sm text-neutral-500">{race.location}</p>
        </div>
        <div className="flex flex-wrap gap-2 sm:justify-end">
          <StatusPill color={race.is_sprint ? "#FF8000" : "#3671C6"}>{race.is_sprint ? "Sprint weekend" : "Grand Prix"}</StatusPill>
          <StatusPill>{pickCount} picks</StatusPill>
        </div>
      </div>

      {race.is_sprint && (
        <div className="mb-5">
          <p className="mb-2 text-xs font-black uppercase tracking-[0.14em] text-neutral-500">Sprint points positions</p>
          <div className="grid gap-2 sm:grid-cols-2">
            {SPRINT_POINT_SLOTS.map((slot) => (
              <PointsScenarioSelect key={`${race.round}-${slot.key}`} race={race} slot={slot} drivers={drivers} picks={picks} onChange={(code) => onSetPick(race.round, slot.key, code)} />
            ))}
          </div>
        </div>
      )}

      <div>
        <p className="mb-2 text-xs font-black uppercase tracking-[0.14em] text-neutral-500">Grand Prix points positions</p>
        <div className="grid gap-2 sm:grid-cols-2">
          {RACE_POINT_SLOTS.map((slot) => (
            <PointsScenarioSelect key={`${race.round}-${slot.key}`} race={race} slot={slot} drivers={drivers} picks={picks} onChange={(code) => onSetPick(race.round, slot.key, code)} />
          ))}
        </div>
      </div>

      <p className="mt-3 text-xs leading-relaxed text-neutral-500">
        GP: P1 25, P2 18, P3 15, P4 12, P5 10, P6 8, P7 6, P8 4, P9 2, P10 1. Sprint: P1 8 through P8 1.
      </p>
    </div>
  );
}

function TitlePathPanel({ rows }: { rows: ScenarioRow[] }) {
  const leader = rows[0];
  if (!leader) return null;
  const contenders = rows.slice(0, Math.min(6, rows.length));

  return (
    <div className="mt-4 rounded-lg border border-white/10 bg-white/[0.035] p-4">
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <p className="text-xs font-black uppercase tracking-[0.18em] text-neutral-400" style={rcFont}>Title Path</p>
          <h3 className="text-xl font-black italic uppercase text-white" style={rcFont}>Points Swing Required</h3>
        </div>
        <StatusPill color="#3671C6">Permutation desk</StatusPill>
      </div>
      <div className="space-y-2">
        {contenders.map((row) => {
          const color = getTeamColor(row.team);
          const availableSwing = Math.max(0, row.maxPossible - row.projected);
          return (
            <div key={row.code} className="flex flex-col gap-3 rounded-lg border border-white/10 bg-black/15 p-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="rounded px-2 py-0.5 text-xs font-black" style={{ color, background: `${color}20` }}>{row.code}</span>
                  <p className="truncate text-sm font-bold text-white">{row.name}</p>
                </div>
                <p className="mt-1 text-xs text-neutral-500">
                  {pointsLabel(row.projected)} pts projected · {row.maxPotentialWins} possible wins · +{pointsLabel(availableSwing)} still available
                </p>
              </div>
              <div className="flex shrink-0 flex-wrap items-center gap-2 sm:justify-end">
                <StatusPill color={titleStateColor(row.titleState)}>{titleStateLabel(row.titleState)}</StatusPill>
                {row.pointsToLead > 0 && (
                  <span className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-1.5 text-xs font-black text-neutral-300">
                    Needs +{pointsLabel(row.pointsToLead)}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function ScenarioRowCard({ row, index, leaderPoints }: { row: ScenarioRow; index: number; leaderPoints: number }) {
  const color = getTeamColor(row.team);
  const width = leaderPoints > 0 ? Math.max(3, (row.projected / leaderPoints) * 100) : 0;

  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2.5">
      <div className="flex items-center gap-3">
        <div className="w-11 shrink-0 text-center text-lg font-black italic text-neutral-300" style={rcFont}>P{index + 1}</div>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="rounded px-2 py-0.5 text-xs font-black" style={{ color, background: `${color}20` }}>{row.code}</span>
            <p className="truncate text-sm font-bold text-white">{row.name}</p>
          </div>
          <p className="mt-0.5 truncate text-xs font-semibold" style={{ color }}>{row.team}</p>
        </div>
        <div className="shrink-0 text-right">
          <p className="text-base font-black text-white" style={rcFont}>{pointsLabel(row.projected)}</p>
          <p className="text-[10px] text-neutral-500">max {pointsLabel(row.maxPossible)}</p>
        </div>
      </div>
      <div className="mt-2 h-2 overflow-hidden rounded-full bg-white/10">
        <div className="h-full rounded-full" style={{ width: `${width}%`, background: color }} />
      </div>
      <div className="mt-2 flex flex-col gap-2 text-xs sm:flex-row sm:items-center sm:justify-between">
        <span className="text-neutral-500">
          {row.scenarioWins}W · {row.scenarioPodiums} GP podiums · {row.scenarioSprintScores} sprint scores · +{pointsLabel(row.scenarioPoints)}
        </span>
        <span className="font-bold" style={{ color: titleStateColor(row.titleState) }}>{titleStateLabel(row.titleState)}</span>
      </div>
    </div>
  );
}

export interface ChampionshipScenarioBoardProps {
  drivers: DriverStanding[];
  driversLoading: boolean;
  driversError: unknown;
  upcomingRaces: RaceEvent[];
  scenarioPicks: ScenarioPicks;
  scenarioRows: ScenarioRow[];
  onSetPick: (round: number, slot: PointsSlotKey, code: string) => void;
  onApplyPreset: (preset: ScenarioPreset) => void;
  onClear: () => void;
  onRetry: () => void;
}

export function ChampionshipScenarioBoard({
  drivers, driversLoading, driversError, upcomingRaces,
  scenarioPicks, scenarioRows, onSetPick, onApplyPreset, onClear, onRetry,
}: ChampionshipScenarioBoardProps) {
  const selectedCount = Object.values(scenarioPicks).reduce((count, picks) => count + Object.values(picks).filter(Boolean).length, 0);
  const selectedRaceCount = Object.values(scenarioPicks).filter((picks) => Object.values(picks).some(Boolean)).length;
  const leader = scenarioRows[0];
  const aliveRows = scenarioRows.filter((row) => row.titleState !== "out");
  const [selectedScenarioRound, setSelectedScenarioRound] = useState<number | null>(null);
  const [showFullTable, setShowFullTable] = useState(false);
  const selectedRace = upcomingRaces.find((race) => race.round === (selectedScenarioRound ?? upcomingRaces[0]?.round)) ?? upcomingRaces[0];
  const selectedRacePicks = selectedRace ? scenarioPicks[selectedRace.round] ?? {} : {};
  const selectedRacePickCount = Object.values(selectedRacePicks).filter(Boolean).length;
  const visibleScenarioRows = showFullTable ? scenarioRows : scenarioRows.slice(0, 10);

  if (driversLoading) {
    return <SectionLoader title="Refreshing championship table" detail="Updating the standings used by the title scenario model." />;
  }

  if (driversError || drivers.length === 0) {
    return (
      <Panel className="p-8">
        <div className="flex items-start gap-4">
          <AlertTriangle className="mt-1 h-6 w-6 text-[#E10600]" />
          <div>
            <h2 className="text-2xl font-black italic uppercase text-white" style={rcFont}>Championship Table Unavailable</h2>
            <p className="mt-2 text-base text-neutral-400">The standings feed could not be loaded.</p>
            <button onClick={onRetry} className="mt-5 rounded-lg border border-white/10 bg-white/[0.04] px-4 py-2 text-sm font-bold text-neutral-200 hover:text-white">
              Retry Standings
            </button>
          </div>
        </div>
      </Panel>
    );
  }

  return (
    <div className="space-y-5">
      <Panel className="p-5" accent="#00FF78">
        <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0">
            <p className="text-xs font-black uppercase tracking-[0.18em] text-neutral-400" style={rcFont}>Manual Championship What-If</p>
            <h2 className="text-3xl font-black italic uppercase text-white leading-tight" style={rcFont}>Edit One Future Race</h2>
            <p className="mt-2 max-w-4xl text-sm leading-relaxed text-neutral-400">
              Current points include completed races including sprint points. Use this to change future race outcomes.
            </p>
          </div>
          <div className="flex shrink-0 flex-wrap gap-2 lg:justify-end">
            <StatusPill>{upcomingRaces.length} future events</StatusPill>
            <StatusPill color="#3671C6">{selectedCount} total picks</StatusPill>
          </div>
        </div>
      </Panel>

      <WorkspaceSplit>
        <Panel className="p-5" accent="#00FF78">
          <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-end">
            <label className="min-w-0 flex-1">
              <span className="block text-xs font-black uppercase tracking-[0.18em] text-neutral-300 mb-2" style={rcFont}>Future event</span>
              <select
                value={selectedRace?.round ?? ""}
                onChange={(e) => setSelectedScenarioRound(Number(e.target.value))}
                className="h-12 w-full rounded-lg border border-white/12 bg-[#151817] px-3 text-base font-semibold text-white outline-none focus:border-[#00FF78]/70"
              >
                {upcomingRaces.map((race) => (
                  <option key={race.round} value={race.round}>{race.name}{race.is_sprint ? " · sprint" : ""}</option>
                ))}
              </select>
            </label>
            <button onClick={onClear} className="inline-flex h-12 items-center justify-center gap-2 rounded-lg border border-white/10 bg-white/[0.04] px-4 text-sm font-bold text-neutral-300 hover:text-white">
              <RotateCcw className="h-4 w-4" />
              Clear all
            </button>
          </div>

          <div className="mb-4 grid gap-2 sm:grid-cols-3">
            {[
              { preset: "leader-protect" as ScenarioPreset, label: "Current Order", detail: "Fill all future races from WDC order." },
              { preset: "chaser-attack" as ScenarioPreset, label: "Chaser Run", detail: "Let P2 win out against the leader." },
              { preset: "top-three-split" as ScenarioPreset, label: "Top 3 Split", detail: "Rotate outcomes among contenders." },
            ].map(({ preset, label, detail }) => (
              <button key={preset} onClick={() => onApplyPreset(preset)} className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2 text-left text-sm font-bold text-neutral-200 transition-colors hover:border-[#00FF78]/40 hover:text-white">
                {label}
                <span className="mt-1 block text-xs font-normal text-neutral-500">{detail}</span>
              </button>
            ))}
          </div>

          {selectedRace ? (
            <ScenarioRaceEditor race={selectedRace} drivers={drivers} picks={selectedRacePicks} pickCount={selectedRacePickCount} onSetPick={onSetPick} />
          ) : (
            <InlineNotice title="Season Complete">No remaining races are available.</InlineNotice>
          )}
        </Panel>

        <Panel className="p-5">
          <div className="mb-5 flex items-start justify-between gap-3">
            <div>
              <p className="text-xs font-black uppercase tracking-[0.18em] text-neutral-400" style={rcFont}>Projected Championship</p>
              <h2 className="text-3xl font-black italic uppercase text-white leading-none" style={rcFont}>{leader?.name ?? "Scenario"} Leads</h2>
              <p className="mt-2 text-sm text-neutral-400">
                {selectedCount} slot{selectedCount === 1 ? "" : "s"} across {selectedRaceCount} race{selectedRaceCount === 1 ? "" : "s"}.
              </p>
            </div>
            <StatusPill>{aliveRows.length} title alive</StatusPill>
          </div>

          <InlineNotice title="Alive Definition">
            Alive when projected score can still pass the scenario leader. Countback when future wins could break a tie.
          </InlineNotice>

          <TitlePathPanel rows={scenarioRows} />

          <div className="mt-5 border-t border-white/10 pt-4">
            <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <p className="text-sm font-bold text-white">Championship table</p>
                <p className="text-xs text-neutral-500">
                  Showing {visibleScenarioRows.length} of {scenarioRows.length} drivers. Expand only when you need the full field.
                </p>
              </div>
              {scenarioRows.length > 10 && (
                <button
                  onClick={() => setShowFullTable((current) => !current)}
                  className="inline-flex h-10 items-center justify-center rounded-lg border border-white/10 bg-white/[0.04] px-4 text-sm font-bold text-neutral-200 transition-colors hover:bg-white/[0.08] hover:text-white"
                >
                  {showFullTable ? "Show top 10" : `Show all ${scenarioRows.length}`}
                </button>
              )}
            </div>
            <div className="space-y-2">
              {visibleScenarioRows.map((driver, index) => (
                <ScenarioRowCard key={driver.code} row={driver} index={index} leaderPoints={leader?.projected ?? driver.projected} />
              ))}
            </div>
          </div>
        </Panel>
      </WorkspaceSplit>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Pure computation helpers (exported for use in page.tsx)
// ---------------------------------------------------------------------------
export function buildScenarioRows(drivers: DriverStanding[], upcomingRaces: RaceEvent[], scenarioPicks: ScenarioPicks): ScenarioRow[] {
  const rows = drivers.map((driver) => {
    let scenarioPoints = 0;
    let scenarioWins = 0;
    let scenarioPodiums = 0;
    let scenarioSprintScores = 0;
    let maxAdditional = 0;
    let maxPotentialWins = driver.wins;

    for (const race of upcomingRaces) {
      const racePicks = scenarioPicks[race.round] ?? {};
      for (const eventType of scenarioEventsForRace(race)) {
        const slots = scenarioSlotsForRaceEvent(race, eventType);
        const selectedSlot = slots.find((slot) => racePicks[slot.key] === driver.code);
        if (selectedSlot) {
          scenarioPoints += selectedSlot.points;
          maxAdditional += selectedSlot.points;
          if (selectedSlot.event === "race") {
            if (selectedSlot.position <= 3) scenarioPodiums += 1;
            if (selectedSlot.position === 1) { scenarioWins += 1; maxPotentialWins += 1; }
          } else {
            scenarioSprintScores += 1;
          }
          continue;
        }
        const bestOpenSlot = slots.find((slot) => !racePicks[slot.key]);
        if (bestOpenSlot) {
          maxAdditional += bestOpenSlot.points;
          if (bestOpenSlot.key === "race_p1") maxPotentialWins += 1;
        }
      }
    }

    return {
      ...driver,
      projected: driver.points + scenarioPoints,
      scenarioWins, scenarioPodiums, scenarioSprintScores, scenarioPoints,
      maxPossible: driver.points + maxAdditional,
      maxPotentialWins,
      pointsToLead: 0,
      titleState: "out" as const,
      alive: false,
    };
  });

  const sorted = rows.sort((a, b) => b.projected - a.projected || b.maxPossible - a.maxPossible || a.position - b.position);
  const leader = sorted[0];
  if (!leader) return [];

  const leaderWins = leader.wins + leader.scenarioWins;
  return sorted.map((row) => {
    const pointsToLead = row.code === leader.code ? 0 : Math.max(0, leader.projected - row.projected + 1);
    let titleState: ScenarioRow["titleState"] = "out";
    if (row.code === leader.code) titleState = "leads";
    else if (row.maxPossible > leader.projected) titleState = "alive";
    else if (row.maxPossible === leader.projected && row.maxPotentialWins > leaderWins) titleState = "countback";
    return { ...row, pointsToLead, titleState, alive: titleState !== "out" };
  });
}

export function buildScenarioPreset(drivers: DriverStanding[], upcomingRaces: RaceEvent[], preset: ScenarioPreset): ScenarioPicks {
  const contenders = drivers.slice(0, Math.min(10, drivers.length));
  if (contenders.length < 3) return {};

  return upcomingRaces.reduce<ScenarioPicks>((picks, race, raceIndex) => {
    const raceOrder = presetOrder(contenders, preset, raceIndex, "race");
    const eventPicks: Partial<Record<PointsSlotKey, string>> = {};
    RACE_POINT_SLOTS.forEach((slot, i) => { const d = raceOrder[i]; if (d) eventPicks[slot.key] = d.code; });
    if (race.is_sprint) {
      const sprintOrder = presetOrder(contenders, preset, raceIndex, "sprint");
      SPRINT_POINT_SLOTS.forEach((slot, i) => { const d = sprintOrder[i]; if (d) eventPicks[slot.key] = d.code; });
    }
    picks[race.round] = eventPicks;
    return picks;
  }, {});
}

function presetOrder(contenders: DriverStanding[], preset: ScenarioPreset, raceIndex: number, eventType: ScenarioEvent) {
  if (preset === "leader-protect") return contenders;
  if (preset === "chaser-attack") {
    return eventType === "sprint"
      ? [contenders[1], contenders[2], contenders[0], ...contenders.slice(3)]
      : [contenders[1], contenders[0], contenders[2], ...contenders.slice(3)];
  }
  const offset = (raceIndex + (eventType === "sprint" ? 1 : 0)) % Math.min(3, contenders.length);
  const front = contenders.slice(0, 3);
  return [...front.slice(offset), ...front.slice(0, offset), ...contenders.slice(3)];
}
