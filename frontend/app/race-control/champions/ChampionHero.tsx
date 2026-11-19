"use client";

import { use } from "react";

import { PageHero } from "@/app/ui/PageHero";
import { Section } from "@/app/ui/section/Section";
import { rc } from "@/app/ui/tokens";

import { heroCopy, type HeroFact } from "./championsModel";
import { useLatestChampion, type ChampionsSeeds } from "./useChampionsSections";

function Records({ facts }: { facts: HeroFact[] }) {
  return (
    <ul aria-label="Records" className="grid gap-3.5">
      {facts.map((fact, index) => (
        <li
          key={fact.caption}
          className="border-l-2 border-rc-gold pl-3.5 motion-safe:animate-fade-up"
          style={{ animationDelay: `${index * 80}ms` }}
        >
          <b className="block font-display text-[34px] font-extrabold leading-none text-rc-ink">{fact.value}</b>
          <span className="mt-1 block text-xs text-rc-ink-3">{fact.caption}</span>
        </li>
      ))}
    </ul>
  );
}

/** The newest champion, with the three records the title sets. */
export function ChampionHero({ seeds }: { seeds: Pick<ChampionsSeeds, "latest"> }) {
  const latest = useLatestChampion(use(seeds.latest));
  const copy = latest.data && !latest.data.error ? heroCopy(latest.data) : null;
  return (
    <Section state={latest} label="Latest champion" skeletonClassName="h-[360px]">
      {copy && (
        <PageHero
          eyebrow={<span className="text-rc-gold">{copy.eyebrow}</span>}
          title={copy.title}
          meta={copy.meta}
          accent={rc.gold}
          className="border-b border-rc-line pb-8 lg:items-end"
          aside={<Records facts={copy.facts} />}
        />
      )}
    </Section>
  );
}
