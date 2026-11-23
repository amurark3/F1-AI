"use client";

import { Suspense, use, useCallback, useState } from "react";

import { API_BASE } from "@/app/constants/api";
import { useSeasonDirectory } from "@/app/race-control/profiles/EntityLinks";
import { PageHero } from "@/app/ui/PageHero";
import { RacePicker } from "@/app/ui/race-picker/RacePicker";
import { shortRaceName } from "@/app/ui/race-picker/railModel";
import { useSchedule, type ScheduleSeed } from "@/app/ui/race-picker/useSchedule";
import { Section, SectionSkeleton } from "@/app/ui/section/Section";
import { useSection } from "@/app/ui/section/useSection";
import { SectionHead } from "@/app/ui/SectionHead";

import { Panel } from "../components/RaceControlPrimitives";
import { debriefPickerRaces, resolveDebriefRound } from "../debriefs/debriefModel";

import { FlagToFinal } from "./FlagToFinal";
import { LapChanges } from "./LapChanges";
import { LapChart } from "./LapChart";
import { OrderTower } from "./OrderTower";
import { finalSource, rewindHeadline, rewindMeta, SOURCE_NOTE_LEAD } from "./rewindCopy";
import { initialStep, maxStep, stepKind } from "./rewindModel";
import { Scrubber } from "./Scrubber";
import { usePlayback } from "./usePlayback";

import type { RaceRewind, RewindResponse } from "./rewindTypes";
import type { RewindUrl } from "./useRewindUrl";

/** A classified race stops changing: no refetch on focus, a long dedupe. */
const CONFIG = { revalidateOnFocus: false, dedupingInterval: 120_000 };
const NOTE = "mt-4 font-mono text-[10px] uppercase leading-[1.6] tracking-[0.1em] text-rc-ink-3";

interface ViewProps {
  year: number;
  seeds: { schedule: Promise<ScheduleSeed> };
  url: RewindUrl;
}

function SourceNote({ data }: { data: RaceRewind }) {
  const source = data.final ? finalSource(data.final) : null;
  return (
    <p className={NOTE}>
      {SOURCE_NOTE_LEAD}
      {source && (
        <>
          {` · final order: ${source.name}`}
          {source.doc && (
            <>
              {" ("}
              {source.url ? (
                <a href={source.url} target="_blank" rel="noopener noreferrer" className="underline underline-offset-2">
                  {source.doc}
                </a>
              ) : (
                source.doc
              )}
              {")"}
            </>
          )}
        </>
      )}
    </p>
  );
}

function sectionTitle(data: RaceRewind, step: number): string {
  const at = stepKind(step, data);
  if (at.kind === "grid") return "What changed at the start";
  return at.kind === "final" ? "What changed after the flag" : `What changed on lap ${at.lap}`;
}

interface PlayerProps {
  data: RaceRewind;
  race: string;
  round: number;
  url: RewindUrl;
}

/** The replay: one step drives the scrubber, the chart, the tower and both cards. */
function Player({ data, race, round, url }: PlayerProps) {
  const directory = useSeasonDirectory();
  const [step, setStep] = useState(() => initialStep(url.step, data));
  const max = maxStep(data);
  const { setStep: writeUrl } = url;
  const move = useCallback(
    (next: number) => {
      const bounded = Math.min(Math.max(next, 0), max);
      setStep(bounded);
      writeUrl(round, bounded > data.total_laps ? "final" : bounded);
    },
    [data.total_laps, max, round, writeUrl],
  );
  const playback = usePlayback(step, max, move);
  const { pause } = playback;
  const manual = useCallback(
    (next: number) => {
      pause();
      move(next);
    },
    [move, pause],
  );

  return (
    <div>
      <PageHero
        eyebrow={`Race Rewind · Round ${round} · ${shortRaceName(race)}`}
        title={rewindHeadline(data, directory)}
        meta={rewindMeta(data, directory)}
      />
      <Scrubber data={data} step={step} playing={playback.playing} onToggle={playback.toggle} onStep={manual} />
      <div className="mt-5 grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px]">
        <LapChart data={data} step={step} />
        <OrderTower data={data} step={step} />
      </div>
      <section aria-labelledby="what-changed" className="mt-14">
        <SectionHead index={1} id="what-changed" title={sectionTitle(data, step)} />
        <div className="grid items-start gap-5 lg:grid-cols-[7fr_5fr]">
          <LapChanges data={data} step={step} />
          <FlagToFinal data={data} />
        </div>
        <SourceNote data={data} />
      </section>
    </div>
  );
}

function Unavailable({ race, round, reason }: { race: string; round: number; reason: string | null }) {
  return (
    <PageHero
      eyebrow={`Race Rewind · Round ${round} · ${shortRaceName(race)}`}
      title={race}
      meta={reason ?? undefined}
    />
  );
}

interface BodyProps {
  year: number;
  round: number;
  race: string;
  url: RewindUrl;
}

/** One round's rewind, keyed by round so a new race starts at its own default step. */
function RoundBody({ year, round, race, url }: BodyProps) {
  const rewind = useSection<RewindResponse>(`${API_BASE}/api/race-control/rewind/${year}/${round}`, { config: CONFIG });
  const { data } = rewind;
  return (
    <Section state={rewind} label="Race Rewind" skeletonClassName="h-[900px]">
      {data?.available === true && <Player data={data} race={race} round={round} url={url} />}
      {data?.available === false && <Unavailable race={race} round={round} reason={data.reason} />}
    </Section>
  );
}

function Body({ year, seeds, url }: ViewProps) {
  const calendar = useSchedule(year, use(seeds.schedule));
  const round = resolveDebriefRound(calendar.races, url.round);
  const event = calendar.races.find((entry) => entry.round === round);

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
  if (!event) {
    return (
      <PageHero
        eyebrow="Race Rewind"
        title="Race Rewind"
        meta="The first rewind appears once a race of the season is classified."
      />
    );
  }
  return (
    <div className="space-y-14">
      <RacePicker
        year={year}
        races={debriefPickerRaces(calendar.races, event.round)}
        selectedRound={event.round}
        onSelectRound={url.select}
        onSelectYear={url.selectYear}
        view="rewind"
      />
      <RoundBody key={event.round} year={year} round={event.round} race={event.name} url={url} />
    </div>
  );
}

/** The Race Rewind page's shell: it renders at once and takes the server's seed behind its own boundary. */
export function RewindView(props: ViewProps) {
  return (
    <Suspense fallback={<SectionSkeleton className="h-[520px]" />}>
      <Body {...props} />
    </Suspense>
  );
}
