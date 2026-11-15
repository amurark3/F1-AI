"use client";

import { useMemo } from "react";

import type { RaceEvent } from "@/app/race-control/grand-prix/predictionModel";

import { DISPLAY } from "../typography";

import { AllRacesPopover } from "./AllRacesPopover";
import { raceDay, seasonRail, shortRaceName, type RailTick } from "./railModel";
import { SeasonRail } from "./SeasonRail";
import { useRaceWinners } from "./useSchedule";

/** A 34 px square control (`grand-prix.html` `.step`). */
const STEP =
  "grid size-[34px] shrink-0 place-items-center rounded border border-rc-line font-mono text-base leading-none text-rc-ink-2 transition-colors hover:border-rc-ink-3 disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:border-rc-line";

export interface SeasonChoice {
  years: readonly number[];
  onSelect: (year: number) => void;
}

export interface RacePickerProps {
  year: number;
  races: readonly RaceEvent[];
  /** The round on screen; null or a round off the calendar asks for one. */
  selectedRound: number | null;
  onSelectRound: (round: number) => void;
  /** Past seasons to choose from (the Telemetry Lab); a season select then leads the picker. */
  seasons?: SeasonChoice;
}

function SeasonSelect({ year, seasons }: { year: number; seasons: SeasonChoice }) {
  return (
    <select
      aria-label="Season"
      value={year}
      onChange={(event) => seasons.onSelect(Number(event.target.value))}
      className="h-[34px] cursor-pointer rounded border border-rc-line bg-background px-3 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-rc-ink-2"
    >
      {seasons.years.map((season) => (
        <option key={season} value={season}>
          {season}
        </option>
      ))}
    </select>
  );
}

/** "R20", the race's name and where and when it runs. */
function CurrentRound({ tick }: { tick: RailTick | undefined }) {
  if (!tick) return <p className={`${DISPLAY} text-[22px] text-rc-ink-2`}>Choose a round</p>;
  const { race } = tick;
  return (
    <>
      <span
        className={`${DISPLAY} min-w-[3.25rem] text-center text-[34px] text-rc-red-text sm:min-w-[70px] sm:text-[44px]`}
      >
        R{race.round}
      </span>
      {/* Capped so a long circuit name gives way (truncated) rather than squeezing the rail; a phone shows the date only. */}
      <div className="min-w-0 flex-1 sm:max-w-64 sm:flex-none">
        <p className={`${DISPLAY} truncate text-lg sm:text-[22px]`}>{shortRaceName(race.name)}</p>
        <p className="mt-1.5 flex gap-1.5 font-mono text-[11px] uppercase leading-none tracking-[0.08em] text-rc-ink-3">
          <span className="hidden truncate sm:block">{race.circuit?.circuit_name ?? race.location}</span>
          <span aria-hidden="true" className="hidden sm:inline">
            ·
          </span>
          <span className="shrink-0">{raceDay(race)}</span>
        </p>
      </div>
    </>
  );
}

/**
 * The race picker (`grand-prix.html`): the round on screen with ‹ › to step,
 * "All races" to choose by name, and the season as a rail placed by date,
 * each tick in the colour of the team that won it. It reports a choice and
 * leaves the URL to the page, which keeps its own `?round=` contract.
 */
export function RacePicker({ year, races, selectedRound, onSelectRound, seasons }: RacePickerProps) {
  const winners = useRaceWinners(year);
  const rail = useMemo(() => seasonRail(races, winners), [races, winners]);
  const current = rail.ticks.find((tick) => tick.race.round === selectedRound);
  const selected = current ? rail.ticks.indexOf(current) : -1;
  const choose = (index: number) => onSelectRound(rail.ticks[index].race.round);
  const hasRaces = rail.ticks.length > 0;

  return (
    <div
      role="group"
      aria-label={`${year} race picker`}
      className="grid gap-x-10 gap-y-4 border-b border-rc-line pb-3.5 pt-2 lg:grid-cols-[auto_minmax(0,1fr)] lg:items-center"
    >
      <div className="relative flex flex-wrap items-center gap-x-3.5 gap-y-3">
        {seasons ? <SeasonSelect year={year} seasons={seasons} /> : null}
        {hasRaces ? (
          <>
            <button
              type="button"
              aria-label="Previous round"
              disabled={selected <= 0}
              onClick={() => choose(selected - 1)}
              className={STEP}
            >
              ‹
            </button>
            <CurrentRound tick={current} />
            <button
              type="button"
              aria-label="Next round"
              disabled={selected === -1 || selected === rail.ticks.length - 1}
              onClick={() => choose(selected + 1)}
              className={STEP}
            >
              ›
            </button>
            <AllRacesPopover ticks={rail.ticks} year={year} selected={selected} onSelect={choose} />
          </>
        ) : (
          <p className="font-mono text-[11px] text-rc-ink-3">Season calendar unavailable.</p>
        )}
      </div>
      {hasRaces ? <SeasonRail rail={rail} year={year} selected={selected} onSelect={choose} /> : null}
    </div>
  );
}
