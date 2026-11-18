"use client";

import Link from "next/link";
import useSWR from "swr";

import { API_BASE } from "@/app/constants/api";
import { awaitingFirstData, seededWith } from "@/app/lib/swrFallback";
import { getTeamColor } from "@/app/lib/teamColors";
import { fetcher } from "@/app/utils/fetcher";

import { InlineNotice, PageLoader } from "../../components/RaceControlPrimitives";
import { FreshnessBar } from "../FreshnessBar";
import { findCar, powerUnitsUrl, roundsByNumber, type PowerUnitsResponse } from "../powerUnitsModel";
import { Provenance } from "../SeasonPanels";

import { CarHeader } from "./CarHeader";
import { ElementLedger } from "./ElementLedger";
import { SeasonTimeline } from "./SeasonTimeline";
import { WeekendCard } from "./WeekendCard";

/** One request serves every power-unit screen; reuse it across navigations. */
const POWER_UNITS_SWR = { revalidateOnFocus: false, dedupingInterval: 120_000 } as const;

/** The loading, failure and not-yet-collected states every power-unit screen shares. */
function PowerUnitsGate({
  data,
  error,
  isLoading,
  children,
}: {
  data: PowerUnitsResponse | undefined;
  error: Error | undefined;
  isLoading: boolean;
  children: (data: PowerUnitsResponse) => React.ReactNode;
}) {
  if (awaitingFirstData(isLoading, data !== undefined)) {
    return <PageLoader title="Reading the FIA's documents" detail="Loading every car's power-unit usage." />;
  }
  // `error` alone is not a reason to blank the screen: SWR keeps the last good
  // payload when a background refresh fails, and that payload is still true.
  if (!data || data.error) {
    return (
      <InlineNotice title="Could not load power-unit usage" tone="error">
        {data?.error ?? (error ? "The power-unit service is unavailable. Please try again shortly." : null)}
      </InlineNotice>
    );
  }
  if (!data.available) {
    return (
      <>
        <FreshnessBar freshness={data.freshness} asOf={null} rounds={new Map()} />
        <InlineNotice title="Not available yet" tone="info">
          {data.reason ?? "Power-unit usage has not been collected for this season yet."}
        </InlineNotice>
      </>
    );
  }
  return <>{children(data)}</>;
}

export interface PowerUnitsSeed {
  year: number;
  data: PowerUnitsResponse | null;
}

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
