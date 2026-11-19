"use client";

import { use } from "react";

import { Legend } from "@/app/ui/Legend";
import { Section } from "@/app/ui/section/Section";
import { f1, rc } from "@/app/ui/tokens";

import { StateTag } from "../grand-prix/StateTag";
import { AllocationTable } from "../profiles/CarAllocations";
import { useTeams } from "../standings/useStandingsSections";

import { SeatNames, UnavailableNote } from "./PowerUnitsParts";
import { standingsOrder } from "./seasonModel";
import { usePowerUnits, type PowerUnitsSeeds } from "./usePowerUnits";

import type { PowerUnitsResponse } from "./powerUnitsModel";

const LEGEND = [
  { label: "Used within the allocation", color: rc.ink2 },
  { label: "Still available", color: rc.ink3, mark: "outline" },
  { label: "Beyond the allocation (penalty)", color: f1.red },
] as const;

function Body({
  data,
  year,
  teams,
}: {
  data: PowerUnitsResponse;
  year: number;
  teams: Parameters<typeof standingsOrder>[1];
}) {
  const order = standingsOrder(data.cars, teams);
  return (
    <figure className="rounded-md border border-rc-line bg-(--surface) p-6">
      <AllocationTable
        cars={order.cars}
        elements={data.elements ?? []}
        caption={`Power-unit elements used by all ${data.cars.length} cars against the ${year} allocation`}
        nameFor={(car) => <SeatNames car={car} year={year} tagShared />}
      />
      <div className="mt-4 flex flex-wrap items-center justify-between gap-x-6 gap-y-3.5">
        <div className="flex flex-wrap items-center gap-x-[18px] gap-y-2">
          <Legend items={LEGEND} label="Legend" />
          <span className="inline-flex items-center gap-[7px] font-mono text-[11px] text-rc-ink-3">
            <StateTag tone="blue">Shared seat</StateTag> more than one driver raced this car
          </span>
        </div>
        <p className="font-mono text-[11px] text-rc-ink-3">
          {order.byStandings ? "In constructors' championship order" : "In car-number order: standings not loaded"}
        </p>
      </div>
    </figure>
  );
}

/** Every car's elements against the allocation, in constructors' order. */
export function AllocationMatrix({ year, seeds }: { year: number; seeds: PowerUnitsSeeds }) {
  const state = usePowerUnits(year, use(seeds.powerUnits));
  const teams = useTeams(year, use(seeds.teams));
  return (
    <Section state={state} label="Allocation by car" skeletonClassName="h-[1000px]">
      {state.data &&
        (state.data.available ? (
          <Body data={state.data} year={year} teams={teams.data} />
        ) : (
          <UnavailableNote data={state.data} />
        ))}
    </Section>
  );
}
