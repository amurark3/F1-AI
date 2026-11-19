"use client";

import Link from "next/link";
import { use } from "react";

import type { SeasonChampion } from "@/app/lib/server/champions";
import { getTeamColor } from "@/app/lib/teamColors";
import { DriverName } from "@/app/ui/names/DriverName";
import { Section } from "@/app/ui/section/Section";

import { cellLabel, decades, sourceNote } from "./championsModel";
import { useChampionList, type ChampionsSeeds } from "./useChampionsSections";

const CELL =
  "relative block overflow-hidden rounded-[3px] border px-2 pb-2.5 pt-2 transition-colors hover:border-rc-ink-3";

function Cell({ season, latest }: { season: SeasonChampion; latest: boolean }) {
  const driver = season.driver_champion;
  const constructor = season.constructor_champion;
  return (
    <li>
      <Link
        href={`/race-control/champions/${season.season}`}
        prefetch={false}
        aria-label={cellLabel(season)}
        className={`${CELL} ${latest ? "border-rc-gold bg-rc-gold/[0.08]" : "border-rc-line bg-(--surface)"}`}
      >
        <span className="block font-mono text-[10px] font-semibold leading-none text-rc-ink-3">{season.season}</span>
        <span className="mt-1.5 block truncate font-display text-[15px] font-extrabold uppercase leading-[1.1] text-rc-ink">
          {!driver?.title_decided ? (
            <span className="text-rc-ink-3">Open</span>
          ) : (
            <DriverName
              variant="last"
              name={driver.name}
              lastName={driver.last_name}
              code={driver.code}
              year={season.season}
            />
          )}
        </span>
        {constructor?.title_decided && (
          <i
            aria-hidden="true"
            className="absolute inset-x-0 bottom-0 h-[3px]"
            style={{ backgroundColor: getTeamColor(constructor.name) }}
          />
        )}
      </Link>
    </li>
  );
}

/** Every season, by decade, newest first: the champion's surname and the constructors' champion's bar. */
export function ChampionWall({ seeds }: { seeds: Pick<ChampionsSeeds, "champions"> }) {
  const list = useChampionList(use(seeds.champions));
  const seasons = list.data?.seasons ?? [];
  const latest = seasons.find((s) => s.driver_champion?.title_decided)?.season;
  return (
    <Section state={list} label="Champions" skeletonClassName="h-[640px]">
      {decades(seasons).map(({ label, seasons: group }) => (
        <div
          key={label}
          className="grid grid-cols-[56px_minmax(0,1fr)] gap-3.5 border-b border-rc-line-soft py-3 sm:grid-cols-[70px_minmax(0,1fr)]"
        >
          <h3 className="pt-2 font-display text-[22px] font-extrabold leading-none text-rc-ink-3">{label}</h3>
          <ul className="grid grid-cols-3 gap-1.5 sm:grid-cols-5 lg:grid-cols-10">
            {group.map((season) => (
              <Cell key={season.season} season={season} latest={season.season === latest} />
            ))}
          </ul>
        </div>
      ))}
      <p className="mt-3.5 font-mono text-[10px] font-medium uppercase leading-[1.6] tracking-[0.1em] text-rc-ink-3">
        {sourceNote(seasons)}
      </p>
    </Section>
  );
}
