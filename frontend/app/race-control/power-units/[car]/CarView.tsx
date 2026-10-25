"use client";

import Link from "next/link";
import useSWR from "swr";

import { API_BASE } from "@/app/constants/api";
import { seededWith } from "@/app/lib/swrFallback";
import { getTeamColor } from "@/app/lib/teamColors";
import { fetcher } from "@/app/utils/fetcher";

import { InlineNotice } from "../../components/RaceControlPrimitives";
import { FreshnessBar } from "../FreshnessBar";
import { findCar, powerUnitsUrl, roundsByNumber, type PowerUnitsResponse } from "../powerUnitsModel";
import { POWER_UNITS_SWR, PowerUnitsGate, type PowerUnitsSeed } from "../PowerUnitsView";
import { Provenance } from "../SeasonPanels";

import { CarHeader } from "./CarHeader";
import { ElementLedger } from "./ElementLedger";
import { SeasonTimeline } from "./SeasonTimeline";
import { WeekendCard } from "./WeekendCard";

function CarScreen({ data, segment }: { data: PowerUnitsResponse; segment: string }) {
  const car = findCar(data.cars, segment);
  if (!car) {
    return (
      <InlineNotice title="No such car" tone="warning">
        No {data.year} car runs as #{segment}.{" "}
        <Link href="/race-control/power-units" className="underline">
          See every car
        </Link>
        .
      </InlineNotice>
    );
  }

  const rounds = roundsByNumber(data.rounds);
  const color = getTeamColor(car.team);
  const newestFirst = [...car.events].sort((a, b) => b.round - a.round);
  const carWarnings = car.warnings.length ? { ...data, warnings: car.warnings, unread: [], withdrawn: [] } : null;

  return (
    <div className="flex flex-col gap-5">
      <div>
        <FreshnessBar freshness={data.freshness} asOf={data.as_of} rounds={rounds} />
        <CarHeader car={car} cars={data.cars} />
      </div>
      <ElementLedger car={car} elements={data.elements ?? []} rounds={rounds} teamColor={color} />
      <SeasonTimeline
        rounds={data.rounds ?? []}
        events={car.events}
        teamColor={color}
        latestRound={data.as_of?.round ?? null}
      />
      <section aria-labelledby="weekends-heading" className="flex flex-col gap-3">
        <h2
          id="weekends-heading"
          className="font-mono text-[11px] font-bold uppercase tracking-[0.28em] text-[#7F8797]"
        >
          Weekend by weekend
        </h2>
        {newestFirst.length === 0 ? (
          <p className="text-sm text-[#8E96A8]">No new units recorded for this car yet.</p>
        ) : (
          newestFirst.map((event) => (
            <WeekendCard key={event.round} event={event} round={rounds.get(event.round)} car={car} teamColor={color} />
          ))
        )}
      </section>
      {carWarnings && <Provenance data={carWarnings} />}
    </div>
  );
}

export function CarView({ seed, segment }: { seed: PowerUnitsSeed; segment: string }) {
  const { data, error, isLoading } = useSWR<PowerUnitsResponse, Error>(powerUnitsUrl(API_BASE, seed.year), fetcher, {
    ...POWER_UNITS_SWR,
    ...seededWith(seed.data),
  });

  return (
    <div className="w-full min-w-0">
      <PowerUnitsGate data={data} error={error} isLoading={isLoading}>
        {(ready) => <CarScreen data={ready} segment={segment} />}
      </PowerUnitsGate>
    </div>
  );
}
