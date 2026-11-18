"use client";

import { getTeamColor } from "@/app/lib/teamColors";
import { DriverName } from "@/app/ui/names/DriverName";
import { PanelHeading } from "@/app/ui/PanelHeading";
import { StatTile } from "@/app/ui/StatTile";
import { rc } from "@/app/ui/tokens";
import { EYEBROW } from "@/app/ui/typography";

import { Panel } from "../components/RaceControlPrimitives";
import { DriverLink } from "../profiles/EntityLinks";

import type { CircuitEdition, CircuitRecord } from "./weekendTypes";

const EDITIONS_SHOWN = 6;
/** Winning from this far back reads as places gained. */
const COMEBACK_GRID = 6;

function EditionRow({ edition, index }: { edition: CircuitEdition; index: number }) {
  const { winner, pole } = edition;
  const grid = winner?.grid ?? null;
  return (
    <li
      className="grid grid-cols-[44px_4px_minmax(0,1fr)_auto] items-center gap-3 border-b border-rc-line-soft py-[11px] text-[13px] last:border-0 motion-safe:animate-fade-up"
      style={{ animationDelay: `${0.1 + index * 0.07}s` }}
    >
      <span className="font-mono font-semibold text-rc-ink-3">{edition.year}</span>
      <span
        className="h-[26px] rounded-[2px]"
        style={{ background: winner ? getTeamColor(winner.team_name) : rc.dim }}
      />
      <span className="min-w-0 font-semibold text-rc-ink sm:truncate">
        {winner ? (
          <DriverLink id={winner.driver_id}>
            <DriverName
              name={winner.driver_name}
              lastName={winner.last_name}
              id={winner.driver_id}
              year={edition.year}
            />
          </DriverLink>
        ) : (
          "No classified winner"
        )}
        {pole && !edition.won_from_pole && (
          <span className="text-xs font-normal text-rc-ink-3 max-sm:block sm:ml-1.5">
            pole{" "}
            <DriverName
              variant="last"
              name={pole.driver_name}
              lastName={pole.last_name}
              id={pole.driver_id}
              year={edition.year}
            />
          </span>
        )}
      </span>
      {grid !== null && (
        <span
          className={`rounded-sm px-1.5 py-[3px] font-mono text-[9px] font-semibold uppercase tracking-[0.14em] ${
            grid >= COMEBACK_GRID ? "bg-rc-gain/[0.14] text-rc-gain" : "bg-white/[0.08] text-rc-ink-2"
          }`}
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
    <Panel className="flex h-full flex-col p-5 sm:p-6">
      <PanelHeading as="h2" eyebrow="At this circuit" title="History" />

      {!record || record.editions.length === 0 ? (
        <p className="text-sm text-rc-ink-3">
          {record ? "This is the circuit's first Grand Prix." : "Circuit history is unavailable right now."}
        </p>
      ) : (
        <>
          <StatTile
            label="Pole → win"
            value={record.pole_conversion.wins_from_pole}
            unit={`/${record.pole_conversion.editions}`}
            sub={`won from pole in the last ${record.pole_conversion.editions} races here`}
          />
          <ol className="mt-4">
            {record.editions.slice(0, EDITIONS_SHOWN).map((edition, index) => (
              // A circuit can host twice in a season (2020), so the year alone is not a key.
              <EditionRow key={`${edition.year}-${index}`} edition={edition} index={index} />
            ))}
          </ol>
          {record.active_winners.length > 0 && (
            <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-4">
              <span className={`${EYEBROW} mr-1`}>On the grid</span>
              {record.active_winners.map((driver) => (
                <span
                  key={driver.driver_id}
                  className="rounded-sm bg-white/[0.08] px-[7px] py-1 text-[11px] text-rc-ink"
                >
                  <DriverLink id={driver.driver_id}>
                    <DriverName variant="last" name={driver.driver_name} lastName={driver.last_name} />
                  </DriverLink>
                  <span className="ml-1 font-mono font-semibold text-rc-gold">×{driver.wins}</span>
                </span>
              ))}
            </div>
          )}
        </>
      )}
    </Panel>
  );
}
