"use client";

import { use } from "react";

import { DriverName } from "@/app/ui/names/DriverName";
import { PageHero } from "@/app/ui/PageHero";
import { Section, SectionSkeleton } from "@/app/ui/section/Section";
import { StatTile, StatTiles } from "@/app/ui/StatTile";

import { UnavailableNote } from "./PowerUnitsParts";
import { heroModel, kpis, latestPenalty } from "./seasonModel";
import { usePowerUnits, type PowerUnitsSeeds } from "./usePowerUnits";

import type { PowerUnitsResponse } from "./powerUnitsModel";

const META =
  "Every car's power-unit elements against the season's allocation, and the grid penalties they cost. Read from the FIA technical delegate's reports and the stewards' decisions.";

/** The page's `h1` and a skeleton for the tiles, while the payload is still on its way. */
export function HeroFallback({ year }: { year: number }) {
  return (
    <>
      <PageHero eyebrow={`Power units · ${year}`} title="Power units" meta={META} />
      <SectionSkeleton className="mt-6 h-[132px]" />
    </>
  );
}

function Tiles({ data, year }: { data: PowerUnitsResponse; year: number }) {
  const [places, engines, pitLane] = kpis(data);
  const latest = latestPenalty(data);
  return (
    <StatTiles>
      <StatTile lead {...places} />
      <StatTile {...engines} />
      <StatTile {...pitLane} />
      <StatTile
        label="Latest"
        value={latest?.value ?? "—"}
        sub={
          latest ? (
            <>
              <DriverName variant="last" {...latest.driver} year={year} />, {latest.detail}
            </>
          ) : (
            "No power-unit penalty this season"
          )
        }
      />
    </StatTiles>
  );
}

export function PowerUnitsHero({ year, seeds }: { year: number; seeds: PowerUnitsSeeds }) {
  const state = usePowerUnits(year, use(seeds.powerUnits));
  const ready = state.data?.available ? state.data : undefined;
  const model = ready ? heroModel(ready) : null;
  return (
    <>
      <PageHero eyebrow={model?.eyebrow ?? `Power units · ${year}`} title={model?.title ?? "Power units"} meta={META} />
      <Section state={state} label="Power-unit totals" skeletonClassName="h-[132px]" className="mt-6">
        {state.data && (ready ? <Tiles data={ready} year={year} /> : <UnavailableNote data={state.data} />)}
      </Section>
    </>
  );
}
