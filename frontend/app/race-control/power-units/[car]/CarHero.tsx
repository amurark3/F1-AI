"use client";

import Link from "next/link";

import { getTeamColor } from "@/app/lib/teamColors";
import { DriverName } from "@/app/ui/names/DriverName";
import { TeamName } from "@/app/ui/names/TeamName";
import { PageHero } from "@/app/ui/PageHero";
import { Section, SectionSkeleton } from "@/app/ui/section/Section";
import { StatTile, StatTiles } from "@/app/ui/StatTile";

import { StateTag } from "../../grand-prix/StateTag";
import { DriverLink, TeamLink } from "../../profiles/EntityLinks";
import { roundsByNumber, type PowerUnitCar, type PowerUnitsResponse } from "../powerUnitsModel";
import { UnavailableNote } from "../PowerUnitsParts";
import { heroModel } from "../seasonModel";

import { carKpis, engineFigure, heroMeta, lineup } from "./carModel";
import { useCar, type CarSectionProps } from "./useCar";

/** The `h1` and a skeleton for the tiles, while the payload is still on its way. */
export function CarHeroFallback({ year, segment }: Pick<CarSectionProps, "year" | "segment">) {
  return (
    <>
      <PageHero band eyebrow={`Power units · ${year}`} title={`Car ${segment}`} />
      <SectionSkeleton className="mt-5 h-[132px]" />
    </>
  );
}

function Lineup({ car, year }: { car: PowerUnitCar; year: number }) {
  const color = getTeamColor(car.team);
  return (
    <div className="grid h-full content-center divide-y divide-rc-line">
      {lineup(car).map(({ stint, standIn, first, rulings }) => (
        <div
          key={stint.id}
          className="grid grid-cols-[60px_minmax(0,1fr)] items-center gap-4 px-5 py-5 sm:grid-cols-[104px_minmax(0,1fr)] sm:gap-[22px] sm:px-8 sm:py-[26px]"
        >
          <span
            className="text-right font-display text-[54px] font-extrabold leading-[0.85] sm:text-[88px]"
            style={{ color }}
          >
            {stint.car_number}
          </span>
          <div className="min-w-0">
            <h2 className="flex flex-wrap items-center gap-x-2.5 gap-y-1.5 font-display text-2xl font-extrabold uppercase leading-none text-rc-ink sm:text-[30px]">
              <DriverLink id={stint.id} name={stint.name} code={stint.code} className="hover:underline">
                <DriverName name={stint.name} code={stint.code} id={stint.id} year={year} />
              </DriverLink>
              {standIn && <StateTag tone="blue">Stand-in</StateTag>}
            </h2>
            <p className="mt-2 font-mono text-xs font-medium uppercase leading-normal tracking-[0.06em] text-rc-ink-3">
              <b className="font-semibold text-rc-ink">{first.bold}</b>
              {first.rest}
            </p>
            <p className="mt-0.5 font-mono text-xs font-medium uppercase leading-normal tracking-[0.06em] text-rc-ink-3">
              At his weekends: <b className="font-semibold text-rc-ink">{rulings}</b>
            </p>
          </div>
        </div>
      ))}
    </div>
  );
}

function EngineFigure({ car, cars }: { car: PowerUnitCar; cars: PowerUnitCar[] }) {
  const figure = engineFigure(car, cars);
  if (!figure) return null;
  return (
    <div className="flex flex-wrap items-baseline gap-x-4 gap-y-2">
      <b className="font-display text-[60px] font-extrabold leading-[0.9] text-rc-ink sm:text-[76px]">
        {figure.value}
        <span className="ml-[0.15em] text-[0.45em] font-bold tracking-[0.04em] text-rc-ink-3">{figure.unit}</span>
      </b>
      <span className="max-w-[30ch] text-[15px] text-rc-ink-2">{figure.line}</span>
    </div>
  );
}

/** What the page says when no car runs under the number in the URL. */
function MissingCar({ year, segment }: { year: number; segment: string }) {
  return (
    <div className="rounded-md border border-rc-line bg-(--surface) p-8">
      <p className="text-rc-ink-2">
        No {year} car runs as #{segment}.
      </p>
      <Link
        href="/race-control/power-units"
        className="mt-4 inline-block text-rc-ink underline decoration-rc-dim underline-offset-2"
      >
        See every car
      </Link>
    </div>
  );
}

/** The four totals; or why there are none: season not collected, or no such car. */
function Totals({
  data,
  car,
  year,
  segment,
}: {
  data: PowerUnitsResponse;
  car?: PowerUnitCar;
  year: number;
  segment: string;
}) {
  if (!data.available) return <UnavailableNote data={data} />;
  if (!car) return <MissingCar year={year} segment={segment} />;
  return (
    <StatTiles>
      {carKpis(car, roundsByNumber(data.rounds)).map((kpi, index) => (
        <StatTile key={kpi.label} lead={index === 0} {...kpi} />
      ))}
    </StatTiles>
  );
}

/** The team-colour band (the `h1` is there before any data), and the four totals under it. */
export function CarHero(props: CarSectionProps) {
  const { year, segment } = props;
  const { state, data, car } = useCar(props);
  return (
    <>
      <PageHero
        band
        accent={car ? getTeamColor(car.team) : null}
        eyebrow={data ? heroModel(data).eyebrow : `Power units · ${year}`}
        title={
          car ? (
            <>
              Car <span style={{ color: getTeamColor(car.team) }}>{car.car_number}</span>
            </>
          ) : (
            `Car ${segment}`
          )
        }
        meta={
          car && (
            <>
              <TeamLink
                id={car.team_id}
                name={car.team}
                className="underline decoration-rc-line underline-offset-[3px]"
              >
                <TeamName name={car.team} id={car.team_id} year={year} />
              </TeamLink>
              . {heroMeta(car)}
            </>
          )
        }
        aside={car && <Lineup car={car} year={year} />}
      >
        {car && data && <EngineFigure car={car} cars={data.cars} />}
      </PageHero>
      <Section state={state} label="Car totals" className="mt-5" skeletonClassName="h-[132px]">
        {state.data && <Totals data={state.data} car={car} year={year} segment={segment} />}
      </Section>
    </>
  );
}
