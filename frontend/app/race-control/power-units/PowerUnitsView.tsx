"use client";

import { Cpu, FileX2, Gavel, TriangleAlert } from "lucide-react";
import useSWR from "swr";

import { API_BASE } from "@/app/constants/api";
import { awaitingFirstData, seededWith } from "@/app/lib/swrFallback";
import { fetcher } from "@/app/utils/fetcher";

import { InlineNotice, MetricCard, MetricRow, PageLoader, SectionHeader } from "../components/RaceControlPrimitives";

import { AllocationMatrix } from "./AllocationMatrix";
import { FreshnessBar } from "./FreshnessBar";
import { powerUnitsUrl, roundsByNumber, seasonTotals, type PowerUnitsResponse } from "./powerUnitsModel";
import { AllowanceLegend, PenaltyLog, Provenance } from "./SeasonPanels";

/** One request serves every power-unit screen; reuse it across navigations. */
export const POWER_UNITS_SWR = { revalidateOnFocus: false, dedupingInterval: 120_000 } as const;

/** The loading, failure and not-yet-collected states every power-unit screen shares. */
export function PowerUnitsGate({
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

function SeasonMetrics({ data }: { data: PowerUnitsResponse }) {
  const totals = seasonTotals(data.cars);
  const withdrawn = data.withdrawn?.length ?? 0;
  const setAside = withdrawn + data.unread.length;
  return (
    <MetricRow>
      <MetricCard
        label="Cars beyond allowance"
        value={`${totals.carsOver} / ${data.cars.length}`}
        sub="At least one element past the season's allowance"
        icon={Cpu}
        color="#E10600"
      />
      <MetricCard
        label="PU grid places"
        value={totals.gridPlaces ? `−${totals.gridPlaces}` : "0"}
        sub={`Dropped through stewards' decisions${totals.pitLaneStarts ? `, plus ${totals.pitLaneStarts} pit-lane start(s)` : ""}`}
        icon={Gavel}
        color="#F5C542"
      />
      <MetricCard
        label="Decisions pending"
        value={String(totals.pending)}
        sub="Units beyond the allowance the stewards have not ruled on yet"
        icon={TriangleAlert}
        color={totals.pending ? "#F5C542" : "#00FF78"}
      />
      <MetricCard
        label="Documents not counted"
        value={String(setAside)}
        sub={`${withdrawn} withdrawn or replaced by the FIA, ${data.unread.length} unreadable — each listed below`}
        icon={FileX2}
        color="#3671C6"
      />
    </MetricRow>
  );
}

export interface PowerUnitsSeed {
  year: number;
  data: PowerUnitsResponse | null;
}

export function PowerUnitsView({ seed }: { seed: PowerUnitsSeed }) {
  const { data, error, isLoading } = useSWR<PowerUnitsResponse, Error>(powerUnitsUrl(API_BASE, seed.year), fetcher, {
    ...POWER_UNITS_SWR,
    ...seededWith(seed.data),
  });

  return (
    <div className="w-full min-w-0">
      <SectionHeader
        eyebrow={`${seed.year} · FIA Technical Delegate & Stewards`}
        title="Power Unit Tracker"
        description="Every car's engine allocation, the Grand Prix where each new unit arrived, and the grid penalties it cost — read from the FIA's own race-weekend documents. Select a car for its weekend-by-weekend story."
      />
      <PowerUnitsGate data={data} error={error} isLoading={isLoading}>
        {(ready) => {
          const rounds = roundsByNumber(ready.rounds);
          return (
            <div className="flex flex-col gap-5">
              <div>
                <FreshnessBar freshness={ready.freshness} asOf={ready.as_of} rounds={rounds} />
                <SeasonMetrics data={ready} />
              </div>
              <AllocationMatrix cars={ready.cars} elements={ready.elements ?? []} />
              <div className="grid gap-5 xl:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
                <PenaltyLog cars={ready.cars} rounds={rounds} />
                <div className="flex min-w-0 flex-col gap-5">
                  <AllowanceLegend elements={ready.elements ?? []} />
                  <Provenance data={ready} />
                </div>
              </div>
            </div>
          );
        }}
      </PowerUnitsGate>
    </div>
  );
}
