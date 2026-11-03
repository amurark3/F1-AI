"use client";

import { Crown, Swords, Trophy } from "lucide-react";
import { useState } from "react";

import { standingsLabel } from "@/app/lib/standingsFreshness";
import { getTeamColor } from "@/app/lib/teamColors";

import { Panel, rcFont } from "../components/RaceControlPrimitives";
import { DriverLink, TeamLink } from "../profiles/EntityLinks";

import { clinchLine, formatPoints, reachLine, type ClinchTone } from "./weekendModel";

import type { ChampionshipStakes as Stakes, Contender, TableStakes } from "./weekendTypes";

type Table = "drivers" | "constructors";

const TONE: Record<ClinchTone, { color: string; icon: typeof Trophy }> = {
  decided: { color: "#00FF78", icon: Trophy },
  possible: { color: "#FFF200", icon: Crown },
  open: { color: "#4C8DFF", icon: Swords },
};

function TableToggle({ table, onChange }: { table: Table; onChange: (table: Table) => void }) {
  const options: Array<{ value: Table; label: string }> = [
    { value: "drivers", label: "Drivers" },
    { value: "constructors", label: "Teams" },
  ];
  return (
    <div
      className="inline-flex rounded-md border border-white/10 bg-black/30 p-0.5"
      role="group"
      aria-label="Championship"
    >
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          aria-pressed={table === option.value}
          onClick={() => onChange(option.value)}
          className={`rounded px-2.5 py-1 font-mono text-[10px] font-bold uppercase tracking-[0.14em] transition-colors ${
            table === option.value ? "bg-white/10 text-white" : "text-[#7F8797] hover:text-white"
          }`}
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}

function ContenderName({ contender, table }: { contender: Contender; table: Table }) {
  if (table === "constructors") return <TeamLink name={contender.name}>{contender.name}</TeamLink>;
  return (
    <DriverLink code={contender.code} name={contender.name}>
      {contender.name}
    </DriverLink>
  );
}

interface ContenderBarProps {
  contender: Contender;
  leaderPoints: number;
  table: Table;
  index: number;
}

function ContenderBar({ contender, leaderPoints, table, index }: ContenderBarProps) {
  const color = getTeamColor(contender.team);
  // The backend sends a table only once a round has scored, so the leader always has points.
  const width = Math.max(2, (contender.points / leaderPoints) * 100);
  return (
    <li className={contender.alive ? "" : "opacity-40"}>
      <div className="mb-1 flex items-baseline justify-between gap-2 text-xs">
        <span className="flex min-w-0 items-center gap-2">
          <span className="w-5 shrink-0 font-mono text-[#7F8797]">P{contender.position}</span>
          <span className="truncate font-bold text-white">
            <ContenderName contender={contender} table={table} />
          </span>
          {!contender.alive && (
            <span className="shrink-0 rounded-sm bg-white/10 px-1 font-mono text-[9px] uppercase tracking-wider text-[#AEB6C6]">
              out
            </span>
          )}
        </span>
        <span className="shrink-0 font-mono text-[#AEB6C6]">
          {formatPoints(contender.points)}
          {contender.gap > 0 && <span className="ml-1.5 text-[#6F7789]">−{formatPoints(contender.gap)}</span>}
        </span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-white/[0.06]">
        <div
          className="h-full origin-left rounded-full motion-safe:animate-fill-x"
          style={{
            width: `${width}%`,
            background: `linear-gradient(90deg, ${color}99, ${color})`,
            animationDelay: `${index * 0.08}s`,
          }}
        />
      </div>
    </li>
  );
}

function StakesTable({ stakes, table, venue }: { stakes: TableStakes; table: Table; venue: string }) {
  const headline = clinchLine(stakes, venue);
  const tone = TONE[headline.tone];
  const reach = reachLine(stakes);
  const Icon = tone.icon;
  return (
    <>
      <div
        className="mb-4 flex items-start gap-2.5 rounded-md border px-3 py-2.5 text-sm leading-snug text-white"
        style={{ borderColor: `${tone.color}55`, background: `${tone.color}12` }}
      >
        <Icon
          className={`mt-0.5 h-4 w-4 shrink-0 ${headline.tone === "possible" ? "motion-safe:animate-pulse" : ""}`}
          style={{ color: tone.color }}
          aria-hidden="true"
        />
        <p>{headline.text}</p>
      </div>
      <div className="relative">
        {reach !== null && (
          <div
            className="pointer-events-none absolute inset-y-0 z-10 border-l border-dashed border-[#FF4655]/70"
            style={{ left: `${reach}%` }}
            aria-hidden="true"
          >
            <span className="absolute -top-4 -translate-x-1/2 whitespace-nowrap font-mono text-[9px] uppercase tracking-wider text-[#FF4655]">
              max reach
            </span>
          </div>
        )}
        <ol className="space-y-3 pt-1">
          {stakes.contenders.map((contender, index) => (
            <ContenderBar
              key={contender.name}
              contender={contender}
              leaderPoints={stakes.leader.points}
              table={table}
              index={index}
            />
          ))}
        </ol>
      </div>
    </>
  );
}

export function ChampionshipStakes({ stakes, venue }: { stakes: Stakes | null | undefined; venue: string }) {
  const [table, setTable] = useState<Table>("drivers");
  const current = stakes?.[table] ?? null;
  const freshness = standingsLabel(stakes);
  return (
    <Panel className="flex h-full flex-col p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#7F8797]" style={rcFont}>
            Title fight
          </p>
          <h2 className="mt-1 text-xl font-semibold text-white" style={rcFont}>
            What&apos;s at stake
          </h2>
        </div>
        <TableToggle table={table} onChange={setTable} />
      </div>
      {current ? (
        <StakesTable stakes={current} table={table} venue={venue} />
      ) : (
        <p className="text-sm text-[#7F8797]">Standings will appear once the season&apos;s first result is in.</p>
      )}
      {stakes && (
        <p className="mt-auto pt-4 font-mono text-[10px] uppercase tracking-[0.14em] text-[#6F7789]">
          {freshness ? `Standings ${freshness} · ` : ""}
          {stakes.races_left} races · {stakes.sprints_left} sprints to count
          {current ? ` · ${formatPoints(current.max_available)} pts max` : ""}
        </p>
      )}
    </Panel>
  );
}
