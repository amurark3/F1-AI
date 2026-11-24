"use client";

import { use, useState } from "react";

import type { ChampionshipTable } from "@/app/lib/clinch";
import { DriverName } from "@/app/ui/names/DriverName";
import { TeamName } from "@/app/ui/names/TeamName";
import { PageHero } from "@/app/ui/PageHero";
import { Section } from "@/app/ui/section/Section";
import { Segmented } from "@/app/ui/Segmented";
import { SourceBadge } from "@/app/ui/SourceBadge";
import { StatTile } from "@/app/ui/StatTile";
import { rc } from "@/app/ui/tokens";
import { EYEBROW } from "@/app/ui/typography";

import { ClinchHeroLine } from "../clinch/ClinchText";
import { useSeasonDirectory } from "../profiles/EntityLinks";

import { heroModel, type HeroModel } from "./standingsModel";
import { useProgression, useShell, useTeams, type StandingsSeeds } from "./useStandingsSections";

const OPTIONS = [
  { value: "drivers", label: "Drivers" },
  { value: "constructors", label: "Constructors" },
] as const;

function Tiles({ model }: { model: HeroModel }) {
  return (
    // A set width: names shorten to surnames once the directory lands, and an auto column would re-wrap the leader's name.
    <div className="grid gap-[18px] lg:w-[230px] lg:border-l lg:border-rc-line lg:pl-7">
      {model.tiles.map((tile) => (
        <StatTile key={tile.label} label={tile.label} value={tile.value} unit={tile.unit} sub={tile.sub} />
      ))}
    </div>
  );
}

function Leader({ table, model }: { table: ChampionshipTable; model: HeroModel }) {
  const { name, code } = model.leader;
  return table === "drivers" ? <DriverName name={name} code={code} variant="full" /> : <TeamName name={name} />;
}

function Meta({ model }: { model: HeroModel }) {
  return (
    <span className="flex items-center gap-2.5">
      {model.swatch && (
        <i aria-hidden="true" className="h-[18px] w-1 rounded-[1px]" style={{ backgroundColor: model.swatch }} />
      )}
      {model.meta}
    </span>
  );
}

function HeroBody({ year, table, model }: { year: number; table: ChampionshipTable; model: HeroModel }) {
  return (
    // The mockup's `auto 1fr auto`: the tiles take their own column, so the name gets the room in the middle.
    <div className="grid items-end gap-10 border-b border-rc-line pb-9 lg:grid-cols-[auto_minmax(0,1fr)_auto]">
      <p className="font-display text-[clamp(120px,15vw,220px)] font-extrabold leading-[0.8] tabular-nums">
        {model.figure}
        <span className="ml-[0.15em] text-[0.2em] font-bold tracking-[0.04em] text-rc-ink-3">pts</span>
      </p>
      <PageHero
        eyebrow={<span className="text-rc-gold">{model.eyebrow}</span>}
        title={<Leader table={table} model={model} />}
        accent={rc.gold}
        meta={<Meta model={model} />}
      >
        <ClinchHeroLine year={year} table={table} fallback={model.line} />
      </PageHero>
      <Tiles model={model} />
    </div>
  );
}

/** The champion's hero, or the leader's while the title is open; the switch picks which championship. */
export function StandingsHero({ year, seeds }: { year: number; seeds: StandingsSeeds }) {
  const teams = useTeams(year, use(seeds.teams));
  const shell = useShell(year, use(seeds.shell));
  const progression = useProgression(year, use(seeds.progression));
  const directory = useSeasonDirectory();
  const [table, setTable] = useState<ChampionshipTable>("drivers");

  const model = teams.data
    ? heroModel(table, teams.data, { year, stakes: shell.data?.stakes, progression: progression.data, directory })
    : null;

  return (
    <Section state={teams} label="Standings" skeletonClassName="h-[420px]">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <p className={EYEBROW}>{year} World Championship</p>
          <SourceBadge freshness={teams.data} asOf={teams.data?.generated_at} />
        </div>
        <Segmented label="Championship" options={OPTIONS} value={table} onChange={setTable} />
      </div>
      <div className="mt-[18px]">
        {model ? (
          <HeroBody year={year} table={table} model={model} />
        ) : (
          <PageHero title="Standings" meta="No round has paid points yet." />
        )}
      </div>
    </Section>
  );
}
