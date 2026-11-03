"use client";

import { History } from "lucide-react";

import { getTeamColor } from "@/app/lib/teamColors";

import { Panel, rcFont } from "../components/RaceControlPrimitives";
import { DriverLink } from "../profiles/EntityLinks";

import type { CircuitEdition, CircuitRecord } from "./weekendTypes";

const EDITIONS_SHOWN = 6;
/** Winning from this far back reads as a comeback and is called out in orange. */
const COMEBACK_GRID = 6;

function gridColor(grid: number): string {
  if (grid === 1) return "#00FF78";
  return grid >= COMEBACK_GRID ? "#FF8000" : "#F4F6FA";
}

/** Pole-to-win rate as a ring that fills on arrival. */
function PoleGauge({ wins, editions }: { wins: number; editions: number }) {
  const pct = editions > 0 ? (wins / editions) * 100 : 0;
  return (
    <div className="flex items-center gap-4">
      <svg viewBox="0 0 100 100" className="h-24 w-24 shrink-0 -rotate-90" aria-hidden="true">
        <circle cx={50} cy={50} r={40} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={10} />
        <circle
          cx={50}
          cy={50}
          r={40}
          fill="none"
          stroke="#00FF78"
          strokeWidth={10}
          strokeLinecap="round"
          pathLength={100}
          strokeDasharray="100 100"
          strokeDashoffset={100 - pct}
          className="motion-safe:animate-gauge-fill"
          style={{ filter: "drop-shadow(0 0 6px rgba(0,255,120,0.45))" }}
        />
      </svg>
      <div>
        <p className="font-mono text-3xl font-black text-white">
          {wins}
          <span className="text-lg text-[#6F7789]">/{editions}</span>
        </p>
        <p className="text-xs leading-snug text-[#AEB6C6]">won from pole in the last {editions} races here</p>
      </div>
    </div>
  );
}

function EditionRow({ edition, index }: { edition: CircuitEdition; index: number }) {
  const { winner, pole } = edition;
  const grid = winner?.grid ?? null;
  return (
    <li
      className="flex items-center gap-3 border-b border-white/[0.06] py-2 text-xs last:border-0 motion-safe:animate-fade-up"
      style={{ animationDelay: `${0.1 + index * 0.07}s` }}
    >
      <span className="w-10 shrink-0 font-mono text-[#7F8797]">{edition.year}</span>
      <span
        className="h-2 w-2 shrink-0 rounded-full"
        style={{ background: winner ? getTeamColor(winner.team_name) : "#3A4254" }}
      />
      <span className="min-w-0 flex-1 truncate font-bold text-white">
        {winner ? <DriverLink id={winner.driver_id}>{winner.driver_name}</DriverLink> : "No classified winner"}
        {pole && !edition.won_from_pole && (
          <span className="ml-1.5 font-normal text-[#6F7789]">pole {pole.driver_name.split(" ").at(-1)}</span>
        )}
      </span>
      {grid !== null && (
        <span
          className="shrink-0 rounded-sm border px-1.5 py-0.5 font-mono text-[10px] font-bold"
          style={{ color: gridColor(grid), borderColor: `${gridColor(grid)}44` }}
          title={`Started P${grid}`}
        >
          from P{grid}
        </span>
      )}
    </li>
  );
}

export function CircuitHistoryPanel({ record }: { record: CircuitRecord | null | undefined }) {
  return (
    <Panel className="flex h-full flex-col p-5">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#7F8797]" style={rcFont}>
            At this circuit
          </p>
          <h2 className="mt-1 text-xl font-semibold text-white" style={rcFont}>
            History
          </h2>
        </div>
        <History className="h-5 w-5 text-[#BE3AFF]" aria-hidden="true" />
      </div>

      {!record || record.editions.length === 0 ? (
        <p className="text-sm text-[#7F8797]">
          {record ? "This is the circuit's first Grand Prix." : "Circuit history is unavailable right now."}
        </p>
      ) : (
        <>
          <PoleGauge wins={record.pole_conversion.wins_from_pole} editions={record.pole_conversion.editions} />
          <ol className="mt-4">
            {record.editions.slice(0, EDITIONS_SHOWN).map((edition, index) => (
              // A circuit can host twice in a season (2020), so the year alone is not a key.
              <EditionRow key={`${edition.year}-${index}`} edition={edition} index={index} />
            ))}
          </ol>
          {record.active_winners.length > 0 && (
            <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-4">
              <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-[#6F7789]">On the grid:</span>
              {record.active_winners.map((driver) => (
                <span
                  key={driver.driver_id}
                  className="rounded-full border border-white/10 bg-white/[0.04] px-2 py-0.5 text-[11px] text-white"
                >
                  <DriverLink id={driver.driver_id}>{driver.driver_name.split(" ").at(-1)}</DriverLink>
                  <span className="ml-1 font-mono text-[#FFC93C]">×{driver.wins}</span>
                </span>
              ))}
            </div>
          )}
        </>
      )}
    </Panel>
  );
}
