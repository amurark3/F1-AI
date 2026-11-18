"use client";

import { use } from "react";

import { getTeamColor } from "@/app/lib/teamColors";
import { DriverName } from "@/app/ui/names/DriverName";
import { PanelHeading } from "@/app/ui/PanelHeading";
import { RankBars } from "@/app/ui/RankBars";
import { Section } from "@/app/ui/section/Section";

import { roundRuns, type DriverStint, type PowerUnitsResponse } from "./powerUnitsModel";
import { SeatNames, UnavailableNote } from "./PowerUnitsParts";
import {
  gridPlaceRanking,
  listSeparator,
  rankingTitle,
  sharedSeatStory,
  sourceNotes,
  type SharedSeatStory,
} from "./seasonModel";
import { usePowerUnits, type PowerUnitsSeeds } from "./usePowerUnits";

const RANKING_SUB =
  "Each car's power-unit grid-place penalties this season, as the stewards imposed them. Pit-lane and back-of-grid starts carry no places, so they aren't in the bars.";

const SOURCE_LINE =
  'Source: FIA technical-delegate reports "New PU elements for this competition" and the stewards\' power-unit decisions, checked hourly · allocations as the FIA states them';

const COUNT_WORDS: Record<number, string> = { 2: "two", 3: "three", 4: "four" };

const PANEL = "rounded-md border border-rc-line bg-(--surface) p-6";

function Stint({ stint, year, withRounds }: { stint: DriverStint; year: number; withRounds: boolean }) {
  return (
    <>
      <DriverName variant="last" name={stint.name} code={stint.code} id={stint.id} year={year} /> (#{stint.car_number}
      {withRounds && `, ${roundRuns(stint.rounds)}`})
    </>
  );
}

function CarCard({ story, year }: { story: SharedSeatStory; year: number }) {
  const { car, regular, others, except } = story;
  const count = car.drivers.length;
  return (
    <figure className={PANEL}>
      <PanelHeading eyebrow={`Car ${car.car_number}`} title={`One car, ${COUNT_WORDS[count] ?? count} drivers`} />
      <p className="text-[13px] leading-relaxed text-rc-ink-2">
        <DriverName variant="last" name={regular.name} code={regular.code} id={regular.id} year={year} /> raced it as #
        {regular.car_number} in every round so far except {except}, when{" "}
        {others.map((other, index) => (
          <span key={other.id}>
            {listSeparator(index, others.length)}
            <Stint stint={other} year={year} withRounds={others.length > 1} />
          </span>
        ))}{" "}
        stood in. Elements belong to the car, so the penalties follow the car, never the driver.
      </p>
    </figure>
  );
}

function Ranking({ data, year }: { data: PowerUnitsResponse; year: number }) {
  const ranked = gridPlaceRanking(data.cars);
  return (
    <figure className={PANEL}>
      <PanelHeading
        eyebrow="Grid places"
        title={ranked.length ? rankingTitle(ranked) : "No power-unit grid-place penalty this season"}
        sub={RANKING_SUB}
      />
      {ranked.length > 0 && (
        <RankBars
          label="Power-unit grid-place penalties by car"
          items={ranked.map((car) => ({
            id: car.seat_id,
            label: (
              <>
                #{car.car_number} <SeatNames car={car} year={year} />
              </>
            ),
            value: car.penalties.grid_places,
            color: getTeamColor(car.team),
          }))}
        />
      )}
    </figure>
  );
}

function SourceNote({ data }: { data: PowerUnitsResponse }) {
  const notes = sourceNotes(data);
  return (
    <div className="mt-3.5 font-mono text-[10px] uppercase leading-[1.6] tracking-[0.1em] text-rc-ink-3">
      <p>{SOURCE_LINE}</p>
      {notes.length > 0 && (
        <ul className="mt-1.5 space-y-1 text-rc-ink-2">
          {notes.map((note) => (
            <li key={note.text}>
              {note.url ? (
                <a href={note.url} target="_blank" rel="noopener noreferrer" className="underline hover:text-rc-ink">
                  {note.text}
                </a>
              ) : (
                note.text
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function Body({ data, year }: { data: PowerUnitsResponse; year: number }) {
  const story = sharedSeatStory(data.cars);
  return (
    <>
      <div className="grid items-start gap-5 lg:grid-cols-[7fr_5fr]">
        <Ranking data={data} year={year} />
        {story && <CarCard story={story} year={year} />}
      </div>
      <SourceNote data={data} />
    </>
  );
}

/** Who paid the most in grid places, the shared car's story, and where the figures come from. */
export function GridPlacesRanking({ year, seeds }: { year: number; seeds: PowerUnitsSeeds }) {
  const state = usePowerUnits(year, use(seeds.powerUnits));
  return (
    <Section state={state} label="Grid-place ranking" skeletonClassName="h-[640px]">
      {state.data &&
        (state.data.available ? <Body data={state.data} year={year} /> : <UnavailableNote data={state.data} />)}
    </Section>
  );
}
