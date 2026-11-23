"use client";

import { ChevronDown } from "lucide-react";
import { useMemo } from "react";

import type { RaceEvent } from "@/app/race-control/grand-prix/predictionModel";

import { DISPLAY } from "../typography";

import { AllRacesPopover } from "./AllRacesPopover";
import { FIRST_RACE_SEASON } from "./raceUrl";
import { raceDay, seasonRail, shortRaceName, type RailTick } from "./railModel";
import { SeasonRail } from "./SeasonRail";
import { ThisRace } from "./ThisRace";
import { useRaceWinners } from "./useSchedule";

import type { RaceView } from "../shell/navConfig";

/** A 34 px square control (`grand-prix.html` `.step`). */
const STEP =
  "grid size-[34px] shrink-0 place-items-center rounded border border-rc-line font-mono text-base leading-none text-rc-ink-2 transition-colors hover:border-rc-ink-3 disabled:cursor-not-allowed disabled:opacity-35 disabled:hover:border-rc-line";

export interface RacePickerProps {
  year: number;
  races: readonly RaceEvent[];
  /** The round on screen; null or a round off the calendar asks for one. */
  selectedRound: number | null;
  onSelectRound: (round: number) => void;
  /** The race view that hosts the picker, when it also provides the switcher. */
  view?: RaceView;
  /** Given, a season select leads the picker; the page writes the year (and drops the round) to its URL. */
  onSelectYear?: (year: number) => void;
}

/** Every season the race views cover, newest first. */
function raceSeasons(): number[] {
  const latest = new Date().getFullYear();
  return Array.from({ length: latest - FIRST_RACE_SEASON + 1 }, (_, index) => latest - index);
}

const SEASON_TEXT = "font-mono text-[10px] font-semibold uppercase leading-none tracking-[0.18em]";

/**
 * The season as the eyebrow over the round (`grand-prix.html` `.season-pick`): a native select, so phones get
 * their own wheel, and a way back to the current season from an old one.
 */
function SeasonSelect({ year, onSelect }: { year: number; onSelect: (year: number) => void }) {
  const seasons = raceSeasons();
  const latest = seasons[0];
  return (
    <div className="mb-3 flex items-center gap-3.5">
      <span className="relative inline-flex items-center">
        {/* `color-scheme` keeps the opened list dark where the browser draws it from the page's colours. */}
        <select
          aria-label="Season"
          value={year}
          onChange={(event) => onSelect(Number(event.target.value))}
          className={`${SEASON_TEXT} cursor-pointer appearance-none bg-transparent py-0.5 pr-4 text-rc-ink-2 [color-scheme:dark] hover:text-rc-ink`}
        >
          {seasons.map((season) => (
            <option key={season} value={season}>
              {season} season
            </option>
          ))}
        </select>
        <ChevronDown aria-hidden="true" className="pointer-events-none absolute right-0 size-3 text-rc-ink-3" />
      </span>
      {year === latest ? null : (
        <button
          type="button"
          onClick={() => onSelect(latest)}
          className={`${SEASON_TEXT} text-rc-ink-3 transition-colors hover:text-rc-ink`}
        >
          Back to {latest} →
        </button>
      )}
    </div>
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
export function RacePicker({ year, races, selectedRound, onSelectRound, view, onSelectYear }: RacePickerProps) {
  const winners = useRaceWinners(year);
  const rail = useMemo(() => seasonRail(races, winners), [races, winners]);
  const current = rail.ticks.find((tick) => tick.race.round === selectedRound);
  const selected = current ? rail.ticks.indexOf(current) : -1;
  const choose = (index: number) => onSelectRound(rail.ticks[index].race.round);
  const hasRaces = rail.ticks.length > 0;

  return (
    <div>
      <div
        role="group"
        aria-label={`${year} race picker`}
        className="grid gap-x-10 gap-y-4 border-b border-rc-line pb-3.5 pt-2 lg:grid-cols-[auto_minmax(0,1fr)] lg:items-center"
      >
        <div>
          {onSelectYear ? <SeasonSelect year={year} onSelect={onSelectYear} /> : null}
          <div className="relative flex flex-wrap items-center gap-x-3.5 gap-y-3">
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
        </div>
        {hasRaces ? <SeasonRail rail={rail} year={year} selected={selected} onSelect={choose} /> : null}
      </div>
      {view && current && <ThisRace year={year} race={current.race} view={view} />}
    </div>
  );
}
