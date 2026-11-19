"use client";

import { use } from "react";

import type { SeasonDetail } from "@/app/lib/server/champions";
import { DriverName } from "@/app/ui/names/DriverName";
import { PageHero } from "@/app/ui/PageHero";
import { Section } from "@/app/ui/section/Section";
import { StatTile, StatTiles } from "@/app/ui/StatTile";
import { rc } from "@/app/ui/tokens";

import { titleState } from "../championsModel";
import { useSeasonDetail } from "../useChampionsSections";

import { seasonEyebrow, seasonMeta, seasonTiles } from "./seasonDetailModel";

/** The page's `h1` while the season's data loads or fails. */
export function HeroFallback({ year }: { year: number }) {
  return <PageHero className="pt-3" eyebrow={`Champions · ${year}`} title={`${year} season`} />;
}

function Hero({ d }: { d: SeasonDetail }) {
  const driver = d.driver_champion;
  // A leader is not a champion: gold only once the drivers' title is decided.
  const gold = driver !== null && titleState(d) !== "open";
  const tiles = seasonTiles(d);
  return (
    <>
      <PageHero
        className="pt-3"
        eyebrow={<span className={gold ? "text-rc-gold" : undefined}>{seasonEyebrow(d)}</span>}
        accent={gold ? rc.gold : undefined}
        title={
          driver ? (
            <DriverName name={driver.name} lastName={driver.last_name} code={driver.code} year={d.season} />
          ) : (
            "No champion recorded"
          )
        }
        meta={seasonMeta(d)}
      />
      {tiles.length > 0 && (
        <StatTiles className="mt-8">
          {tiles.map((tile) => (
            <StatTile key={tile.label} {...tile} />
          ))}
        </StatTiles>
      )}
    </>
  );
}

/** The champion (or leader) and four figures. */
export function SeasonHero({ year, seed }: { year: number; seed: Promise<SeasonDetail | null> }) {
  const state = useSeasonDetail(year, use(seed));
  return (
    <>
      {state.data === undefined && <HeroFallback year={year} />}
      <Section state={state} label={`${year} season`} skeletonClassName="h-[330px]">
        {state.data && <Hero d={state.data} />}
      </Section>
    </>
  );
}
