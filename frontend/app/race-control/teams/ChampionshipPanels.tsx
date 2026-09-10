"use client";

import { useState, type ReactNode } from "react";

import { getTeamColor } from "@/app/components/PredictionDriverCard";

import { ChampionshipBarChart, DriverChampionshipChart } from "../components/Charts";
import { Panel, StatusPill, WorkspaceSplit, rcFont } from "../components/RaceControlPrimitives";

import { driverCode, formatPoints, type DriverStanding, type Team } from "./teamsModel";

/** How many drivers the WDC chart plots before the user picks their own set. */
const DEFAULT_CHART_DRIVERS = 10;

const CHART_HEIGHT = 260;

export function StandingsSplit({ year, drivers, teams }: { year: number; drivers: DriverStanding[]; teams: Team[] }) {
  return (
    <WorkspaceSplit className="mb-6 xl:[&>*]:flex-1">
      <ConstructorChampionshipPanel year={year} teams={teams} />
      <DriverChampionshipPanel year={year} drivers={drivers} />
    </WorkspaceSplit>
  );
}

function topDriverNames(drivers: DriverStanding[], count: number): ReadonlySet<string> {
  return new Set(
    [...drivers]
      .sort((a, b) => a.position - b.position)
      .slice(0, count)
      .map((driver) => driver.driver),
  );
}

function toChartEntry(driver: DriverStanding) {
  return {
    name: driver.driver,
    code: driverCode(driver),
    points: driver.points,
    color: getTeamColor(driver.team),
    position: driver.position,
  };
}

function DriverChampionshipPanel({ year, drivers }: { year: number; drivers: DriverStanding[] }) {
  // `null` means "the user has not picked yet", so the chart keeps tracking the
  // running top 10 as the feed updates instead of freezing the first names seen.
  const [picked, setPicked] = useState<ReadonlySet<string> | null>(null);
  const selected = picked ?? topDriverNames(drivers, DEFAULT_CHART_DRIVERS);
  const charted = drivers.filter((driver) => selected.has(driver.driver));

  const toggleDriver = (name: string) => {
    const next = new Set(selected);
    if (next.has(name)) {
      next.delete(name);
    } else {
      next.add(name);
    }
    setPicked(next);
  };

  return (
    <Panel className="p-5" accent="#00FF78">
      <ChampionshipPanelHeader
        eyebrow="World Drivers' Championship"
        title="Driver Order"
        pill={`${year} WDC`}
        color="#00FF78"
      />
      {charted.length > 0 ? (
        <DriverChampionshipChart data={charted.map(toChartEntry)} height={CHART_HEIGHT} />
      ) : (
        <EmptyChartNotice />
      )}
      <DriverFilterChips
        drivers={drivers}
        selected={selected}
        onToggle={toggleDriver}
        onSelectDefault={() => setPicked(topDriverNames(drivers, DEFAULT_CHART_DRIVERS))}
        onSelectAll={() => setPicked(new Set(drivers.map((driver) => driver.driver)))}
      />
      <div className="mt-5 space-y-2">
        {drivers.length > 0 ? (
          drivers.map((driver) => <DriverStandingRow key={`${driver.position}-${driver.driver}`} driver={driver} />)
        ) : (
          <p className="text-sm text-neutral-500">Driver standings are not available for this season yet.</p>
        )}
      </div>
    </Panel>
  );
}

function ConstructorChampionshipPanel({ year, teams }: { year: number; teams: Team[] }) {
  return (
    <Panel className="p-5" accent="#E10600">
      <ChampionshipPanelHeader
        eyebrow="World Constructors' Championship"
        title="Constructor Order"
        pill={`${year} WCC`}
        color="#E10600"
      />
      <ChampionshipBarChart
        data={teams.map((team) => ({
          name: team.name,
          points: team.points,
          color: team.color,
          position: team.position,
        }))}
        height={Math.max(230, teams.length * 34)}
      />
      <div className="mt-5 space-y-2">
        {teams.length > 0 ? (
          teams.map((team) => <ConstructorStandingRow key={team.slug} team={team} />)
        ) : (
          <p className="text-sm text-neutral-500">Constructor standings are not available for this season yet.</p>
        )}
      </div>
    </Panel>
  );
}

function EmptyChartNotice() {
  return (
    <div
      className="flex items-center justify-center rounded-lg border border-dashed border-white/10 text-sm text-neutral-500"
      style={{ height: CHART_HEIGHT }}
    >
      Pick at least one driver to plot.
    </div>
  );
}

function DriverFilterChips({
  drivers,
  selected,
  onToggle,
  onSelectDefault,
  onSelectAll,
}: {
  drivers: DriverStanding[];
  selected: ReadonlySet<string>;
  onToggle: (name: string) => void;
  onSelectDefault: () => void;
  onSelectAll: () => void;
}) {
  if (drivers.length === 0) {
    return null;
  }
  return (
    <div className="mt-4 border-t border-white/5 pt-4">
      <div className="mb-2.5 flex items-center justify-between gap-2">
        <p className="text-[10px] font-black uppercase tracking-[0.16em] text-neutral-500" style={rcFont}>
          Chart drivers · {selected.size}/{drivers.length}
        </p>
        <div className="flex gap-1.5">
          <PresetButton onClick={onSelectDefault}>Top {DEFAULT_CHART_DRIVERS}</PresetButton>
          <PresetButton onClick={onSelectAll}>All</PresetButton>
        </div>
      </div>
      <div className="flex flex-wrap gap-1.5">
        {drivers.map((driver) => (
          <DriverChip key={driver.driver} driver={driver} active={selected.has(driver.driver)} onToggle={onToggle} />
        ))}
      </div>
    </div>
  );
}

function DriverChip({
  driver,
  active,
  onToggle,
}: {
  driver: DriverStanding;
  active: boolean;
  onToggle: (name: string) => void;
}) {
  const color = getTeamColor(driver.team);
  return (
    <button
      type="button"
      aria-pressed={active}
      title={`P${driver.position} ${driver.driver} · ${driver.team}`}
      onClick={() => onToggle(driver.driver)}
      className="rounded px-2 py-1 text-[11px] font-black uppercase tracking-wide transition-colors"
      style={
        active
          ? { color, background: `${color}26`, border: `1px solid ${color}66` }
          : { color: "#6b6b6b", background: "transparent", border: "1px solid rgba(255,255,255,0.10)" }
      }
    >
      {driverCode(driver)}
    </button>
  );
}

function PresetButton({ onClick, children }: { onClick: () => void; children: ReactNode }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="rounded border border-white/10 bg-white/[0.04] px-2 py-1 text-[10px] font-bold uppercase tracking-wide text-neutral-300 transition-colors hover:bg-white/[0.08] hover:text-white"
    >
      {children}
    </button>
  );
}

function ChampionshipPanelHeader({
  eyebrow,
  title,
  pill,
  color,
}: {
  eyebrow: string;
  title: string;
  pill: string;
  color: string;
}) {
  return (
    <div className="mb-5 flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
      <div>
        <p className="text-xs font-black uppercase tracking-[0.18em] text-neutral-400" style={rcFont}>
          {eyebrow}
        </p>
        <h2 className="mt-1 text-3xl font-black italic uppercase leading-none text-white" style={rcFont}>
          {title}
        </h2>
      </div>
      <StatusPill color={color}>{pill}</StatusPill>
    </div>
  );
}

function DriverStandingRow({ driver }: { driver: DriverStanding }) {
  const color = getTeamColor(driver.team);
  return (
    <div className="flex items-center gap-3 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2.5">
      <div className="w-10 shrink-0 text-center text-lg font-black italic text-neutral-300" style={rcFont}>
        P{driver.position}
      </div>
      <span
        className="hidden rounded px-2 py-0.5 text-xs font-black sm:inline-flex"
        style={{ color, background: `${color}20` }}
      >
        {driverCode(driver)}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-bold text-white">{driver.driver}</p>
        <p className="truncate text-xs font-semibold" style={{ color }}>
          {driver.team}
        </p>
      </div>
      <div className="shrink-0 text-right">
        <p className="text-sm font-black text-white" style={rcFont}>
          {formatPoints(driver.points)}
        </p>
        <p className="text-[10px] text-neutral-500">
          {driver.wins} win{driver.wins === 1 ? "" : "s"}
        </p>
      </div>
    </div>
  );
}

function ConstructorStandingRow({ team }: { team: Team }) {
  return (
    <div className="flex items-center gap-3 rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2.5">
      <div className="w-10 shrink-0 text-center text-lg font-black italic text-neutral-300" style={rcFont}>
        P{team.position}
      </div>
      <span className="h-7 w-1.5 shrink-0 rounded-full" style={{ background: team.color }} />
      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-bold text-white">{team.name}</p>
        <p className="truncate text-xs text-neutral-500">
          {team.drivers.map((driver) => driver.driver).join(" / ") || "Roster pending"}
        </p>
      </div>
      <div className="shrink-0 text-right">
        <p className="text-sm font-black text-white" style={rcFont}>
          {formatPoints(team.points)}
        </p>
        <p className="text-[10px] text-neutral-500">
          {team.wins} win{team.wins === 1 ? "" : "s"}
        </p>
      </div>
    </div>
  );
}
