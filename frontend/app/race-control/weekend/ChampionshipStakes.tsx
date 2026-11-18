"use client";

import { useState } from "react";

import type { ChampionshipTable } from "@/app/lib/clinch";
import { standingsLabel } from "@/app/lib/standingsFreshness";
import { getTeamColor } from "@/app/lib/teamColors";
import { DriverName } from "@/app/ui/names/DriverName";
import { TeamName } from "@/app/ui/names/TeamName";
import { PanelHeading } from "@/app/ui/PanelHeading";
import { Segmented } from "@/app/ui/Segmented";

import { Panel } from "../components/RaceControlPrimitives";
import { DriverLink, TeamLink } from "../profiles/EntityLinks";

import { clinchLine, formatPoints, reachLine, type ClinchTone } from "./weekendModel";

import type { ChampionshipStakes as Stakes, Contender, TableStakes } from "./weekendTypes";

type Table = ChampionshipTable;

/** Gold when the title is decided or decidable this weekend, blue while it is open. */
const TONE: Record<ClinchTone, string> = {
  decided: "border-rc-gold/35 bg-rc-gold/[0.06]",
  possible: "border-rc-gold/35 bg-rc-gold/[0.06]",
  open: "border-rc-blue/35 bg-rc-blue/[0.06]",
};

const TABLE_OPTIONS: Array<{ value: Table; label: string }> = [
  { value: "drivers", label: "Drivers" },
  { value: "constructors", label: "Teams" },
];

function ContenderName({ contender, table }: { contender: Contender; table: Table }) {
  if (table === "constructors") {
    return (
      <TeamLink name={contender.name}>
        <TeamName name={contender.name} />
      </TeamLink>
    );
  }
  return (
    <DriverLink code={contender.code} name={contender.name}>
      <DriverName variant="codeLast" name={contender.name} code={contender.code} />
    </DriverLink>
  );
}

interface ContenderBarProps {
  contender: Contender;
  leaderPoints: number;
  reach: number | null;
  table: Table;
  index: number;
}

function ContenderBar({ contender, leaderPoints, reach, table, index }: ContenderBarProps) {
  // The backend sends a table only once a round has scored, so the leader always has points.
  const width = Math.max(2, (contender.points / leaderPoints) * 100);
  return (
    <li className={contender.alive ? "" : "opacity-60"}>
      <div className="mb-1.5 flex items-baseline justify-between gap-2.5 text-[13px]">
        <span className="flex min-w-0 items-baseline gap-2.5">
          <span className="w-[22px] shrink-0 font-mono text-[11px] text-rc-ink-3">P{contender.position}</span>
          <span className="truncate font-semibold text-rc-ink">
            <ContenderName contender={contender} table={table} />
          </span>
          {!contender.alive && (
            <span className="shrink-0 rounded-sm bg-white/[0.08] px-1.5 py-[3px] font-mono text-[9px] font-semibold uppercase tracking-[0.14em] text-rc-ink-2">
              out
            </span>
          )}
        </span>
        <span className="shrink-0 font-mono text-[13px] font-semibold text-rc-ink">
          {formatPoints(contender.points)}
          {contender.gap > 0 && (
            <span className="ml-1.5 font-medium text-rc-ink-3">−{formatPoints(contender.gap)}</span>
          )}
        </span>
      </div>
      <div className="relative h-2.5 rounded-full bg-white/[0.04]">
        <div
          className="absolute inset-y-0 left-0 origin-left rounded-full motion-safe:animate-fill-x"
          style={{
            width: `${width}%`,
            background: getTeamColor(contender.team),
            animationDelay: `${index * 0.08}s`,
          }}
        />
        {reach !== null && (
          <span
            aria-hidden="true"
            className="absolute -inset-y-1 border-l border-dashed border-rc-ink/55"
            style={{ left: `${reach}%` }}
          />
        )}
      </div>
    </li>
  );
}

function StakesTable({ stakes, table, venue }: { stakes: TableStakes; table: Table; venue: string }) {
  const headline = clinchLine(stakes, venue, table);
  const reach = reachLine(stakes);
  return (
    <>
      <p className={`mb-5 rounded-md border px-3.5 py-3 text-sm leading-snug text-rc-ink ${TONE[headline.tone]}`}>
        {headline.text}
      </p>
      <ol className="space-y-3.5 pt-1">
        {stakes.contenders.map((contender, index) => (
          <ContenderBar
            key={contender.name}
            contender={contender}
            leaderPoints={stakes.leader.points}
            reach={reach}
            table={table}
            index={index}
          />
        ))}
      </ol>
    </>
  );
}

export function ChampionshipStakes({ stakes, venue }: { stakes: Stakes | null | undefined; venue: string }) {
  const [table, setTable] = useState<Table>("drivers");
  const current = stakes?.[table] ?? null;
  const freshness = standingsLabel(stakes);
  return (
    <Panel className="flex h-full flex-col p-5 sm:p-6">
      <PanelHeading
        as="h2"
        eyebrow="Title fight"
        title="What's at stake"
        aside={<Segmented label="Championship" options={TABLE_OPTIONS} value={table} onChange={setTable} />}
      />
      {current ? (
        <StakesTable stakes={current} table={table} venue={venue} />
      ) : (
        <p className="text-sm text-rc-ink-3">Standings will appear once the season&apos;s first result is in.</p>
      )}
      {stakes && (
        <p className="mt-auto pt-4 font-mono text-[10px] uppercase leading-[1.6] tracking-[0.1em] text-rc-ink-3">
          {freshness ? `Standings ${freshness} · ` : ""}
          {stakes.races_left} races · {stakes.sprints_left} sprints to count
          {current ? ` · ${formatPoints(current.max_available)} pts max` : ""}
          {current && reachLine(current) !== null
            ? " · dashed mark = the leader's total less the points left: a bar short of it can no longer catch the leader"
            : ""}
        </p>
      )}
    </Panel>
  );
}
