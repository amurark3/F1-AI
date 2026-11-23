"use client";

import { Suspense, use } from "react";

import { Section, SectionSkeleton } from "@/app/ui/section/Section";
import { SectionHead } from "@/app/ui/SectionHead";

import { DebriefHero } from "./DebriefHero";
import { DebriefKpis } from "./DebriefKpis";
import { sourceNote } from "./debriefModel";
import { GridToFinish } from "./GridToFinish";
import { LapLeaders } from "./LapLeaders";
import { OvertakesBoard } from "./OvertakesBoard";
import { PenaltyTimeline } from "./PenaltyTimeline";
import { RaceTrace } from "./RaceTrace";
import { RadioMoments } from "./RadioMoments";
import { TitleBanners } from "./TitleBanner";
import {
  useDebriefLaps,
  useDebriefOvertakes,
  useDebriefPenalties,
  useDebriefRadio,
  useDebriefSummary,
  type DebriefSeeds,
} from "./useDebriefSections";

interface BodyProps {
  year: number;
  round: number;
  seeds: Pick<DebriefSeeds, "summary">;
}

/** One round's debrief; each section owns its fetch and its states, so one failing never blanks another. */
function Body({ year, round, seeds }: BodyProps) {
  const seed = use(seeds.summary);
  const summary = useDebriefSummary(year, round, seed?.round === round ? seed.data : null);
  const laps = useDebriefLaps(year, round);
  const penalties = useDebriefPenalties(year, round);
  const overtakes = useDebriefOvertakes(year, round);
  const radio = useDebriefRadio(year, round);
  const { data } = summary;

  return (
    <div className="space-y-14">
      <Section state={summary} label="Race result" skeletonClassName="h-[520px]">
        {data && (
          <div className="space-y-8">
            <DebriefHero summary={data} />
            <TitleBanners titles={data.titles} year={year} />
            {data.available && <DebriefKpis summary={data} overtakes={overtakes} />}
          </div>
        )}
      </Section>

      <section aria-labelledby="how-it-unfolded">
        <SectionHead index={1} id="how-it-unfolded" title="How the race unfolded" />
        <div className="space-y-5">
          <Section state={laps} label="Lap leaders" skeletonClassName="h-[160px]">
            {laps.data && <LapLeaders laps={laps.data} />}
          </Section>
          <Section state={laps} label="Race trace" skeletonClassName="h-[420px]">
            {laps.data && <RaceTrace laps={laps.data} />}
          </Section>
        </div>
      </section>

      <section aria-labelledby="who-moved">
        <SectionHead index={2} id="who-moved" title="Who moved, who paid" />
        <div className="grid items-start gap-5 lg:grid-cols-[7fr_5fr]">
          <Section state={summary} label="Grid to finish" skeletonClassName="h-[560px]">
            {data && <GridToFinish summary={data} />}
          </Section>
          <div className="min-w-0 space-y-5">
            <Section state={penalties} label="Penalties" skeletonClassName="h-[260px]">
              {penalties.data && <PenaltyTimeline penalties={penalties.data} />}
            </Section>
            <Section state={overtakes} label="Overtakes" skeletonClassName="h-[300px]">
              {overtakes.data && <OvertakesBoard overtakes={overtakes.data} />}
            </Section>
          </div>
        </div>
      </section>

      <section aria-labelledby="on-the-radio">
        <SectionHead index={3} id="on-the-radio" title="On the radio" />
        <Section state={radio} label="Team radio" skeletonClassName="h-[420px]">
          {radio.data && <RadioMoments key={`${year}-${round}`} radio={radio.data} />}
        </Section>
      </section>

      {data?.available && (
        <p className="font-mono text-[10px] uppercase tracking-[0.1em] text-rc-ink-3">{sourceNote(data)}</p>
      )}
    </div>
  );
}

/** The summary seed is `use()`d behind its own boundary, so the picker never waits on it. */
export function DebriefSections(props: BodyProps) {
  return (
    <Suspense fallback={<SectionSkeleton className="h-[520px]" />}>
      <Body {...props} />
    </Suspense>
  );
}
