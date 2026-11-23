"use client";

import { Suspense, use } from "react";

import { PageHero } from "@/app/ui/PageHero";
import { RacePicker } from "@/app/ui/race-picker/RacePicker";
import { useSchedule } from "@/app/ui/race-picker/useSchedule";
import { SectionSkeleton } from "@/app/ui/section/Section";

import { Panel } from "../components/RaceControlPrimitives";

import { debriefPickerRaces, resolveDebriefRound } from "./debriefModel";
import { DebriefSections } from "./DebriefSections";

import type { DebriefSeeds } from "./useDebriefSections";
import type { DebriefUrl } from "./useDebriefUrl";

interface ViewProps {
  year: number;
  seeds: DebriefSeeds;
  url: DebriefUrl;
}

function Body({ year, seeds, url }: ViewProps) {
  const calendar = useSchedule(year, use(seeds.schedule));
  const round = resolveDebriefRound(calendar.races, url.round);

  if (calendar.pending) return <SectionSkeleton className="h-[520px]" />;
  if (calendar.failed && calendar.races.length === 0) {
    return (
      <Panel className="space-y-3 p-5">
        <p className="text-sm text-rc-ink-2">The race calendar couldn&apos;t load.</p>
        <button
          type="button"
          onClick={calendar.retry}
          className="rounded-sm border border-rc-line px-3 py-2 font-mono text-[11px] font-semibold uppercase tracking-[0.14em] text-rc-ink hover:border-rc-ink-3"
        >
          Retry
        </button>
      </Panel>
    );
  }
  if (round === null) {
    return (
      <PageHero
        eyebrow="Race debrief"
        title="Debrief"
        meta="The first debrief appears once a race of the season is classified."
      />
    );
  }
  return (
    <div className="space-y-14">
      <RacePicker
        year={year}
        races={debriefPickerRaces(calendar.races, round)}
        selectedRound={round}
        onSelectRound={url.select}
        onSelectYear={url.selectYear}
        view="debrief"
      />
      <DebriefSections key={round} year={year} round={round} seeds={seeds} />
    </div>
  );
}

/** The Debriefs page's shell: it renders at once and takes the server's seeds behind its own boundaries. */
export function DebriefsView(props: ViewProps) {
  return (
    <Suspense fallback={<SectionSkeleton className="h-[520px]" />}>
      <Body {...props} />
    </Suspense>
  );
}
