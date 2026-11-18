"use client";

import { LocalTime } from "@/app/components/LocalTime";
import { CircuitMap } from "@/app/ui/CircuitMap";
import { Countdown } from "@/app/ui/Countdown";
import { nextUp } from "@/app/ui/nextUp";
import { PageHero } from "@/app/ui/PageHero";
import { EYEBROW } from "@/app/ui/typography";
import { useClock } from "@/app/ui/useClock";

import { SkeletonPanel } from "../components/RaceControlPrimitives";
import { StateTag, type StateTone } from "../grand-prix/StateTag";

import { CircuitStats, type CircuitBasics } from "./CircuitStats";
import { SessionWeatherStrip } from "./SessionWeatherStrip";

import type { OverviewCircuit, SessionWeatherRow } from "./weekendTypes";

/** The slice of the selected race the hero needs. */
export interface HeroRace {
  round: number;
  name: string;
  location: string;
  country?: string | null;
  status: string;
  sessions: Record<string, string>;
  circuit?: (CircuitBasics & { circuit_name?: string | null; lap_record?: OverviewCircuit["lap_record"] }) | null;
}

const STATUS: Record<string, { label: string; tone: StateTone }> = {
  upcoming: { label: "Upcoming", tone: "blue" },
  in_progress: { label: "Weekend live", tone: "red" },
  completed: { label: "Completed", tone: "neutral" },
};

/** Time to the next session, "Live now" while one is on track, and "complete" once the weekend is over. */
function NextSessionCountdown({ sessions }: { sessions: Record<string, string> }) {
  const now = useClock();
  const next = now === null ? null : nextUp(sessions, now);
  if (now !== null && next === null) return <p className={EYEBROW}>Weekend complete</p>;
  if (next?.live) {
    return (
      <p className="font-mono text-sm font-semibold uppercase tracking-[0.2em] text-rc-red-text">
        Live now · {next.name}
      </p>
    );
  }
  return (
    <div>
      <p className={`${EYEBROW} mb-2.5`}>
        Next · <span className="text-rc-blue">{next?.name ?? "session"}</span>
      </p>
      <Countdown target={next?.startsAt ?? ""} label={`Time to ${next?.name ?? "the next session"}`} />
    </div>
  );
}

function MapSlot({ circuit, loading, name }: { circuit: OverviewCircuit | undefined; loading: boolean; name: string }) {
  if (loading) return <SkeletonPanel className="h-full min-h-[240px]" />;
  if (!circuit?.map) {
    return (
      <div className="flex h-full min-h-[240px] items-center justify-center rounded-md border border-dashed border-rc-line text-sm text-rc-ink-3">
        Circuit map unavailable
      </div>
    );
  }
  return (
    <figure className="flex h-full flex-col rounded-md border border-rc-line bg-rc-hero p-5 [background-image:radial-gradient(rgba(255,255,255,0.06)_1px,transparent_1px)] [background-size:18px_18px] sm:p-[22px]">
      <div className="min-h-[240px] flex-1">
        <CircuitMap map={circuit.map} name={name} />
      </div>
      <figcaption className="mt-2 text-right font-mono text-[10px] uppercase tracking-[0.16em] text-rc-ink-3">
        Layout · {circuit.map.source} {circuit.map.season}
      </figcaption>
    </figure>
  );
}

/** The circuit's name and town, preferring f1db's record to the schedule's location. */
function circuitLabel(race: HeroRace, circuit: OverviewCircuit | undefined): { name: string; place: string } {
  const name = circuit?.record?.name ?? race.circuit?.circuit_name ?? race.location;
  const place = circuit?.record?.place ?? race.location.split(",")[0];
  return { name, place: place === name ? "" : place };
}

interface WeekendHeroProps {
  race: HeroRace;
  totalRounds: number | null;
  circuit: OverviewCircuit | undefined;
  circuitLoading: boolean;
  /** Each session's forecast, once the weather segment lands. */
  forecast: SessionWeatherRow[];
  /** The stored forecast's "as of" label, when the live feed failed. */
  forecastAsOf?: string | null;
}

export function WeekendHero({ race, totalRounds, circuit, circuitLoading, forecast, forecastAsOf }: WeekendHeroProps) {
  const status = STATUS[race.status] ?? { label: race.status, tone: "neutral" as const };
  const starts = Object.values(race.sessions).sort((a, b) => a.localeCompare(b));
  const label = circuitLabel(race, circuit);
  return (
    <div>
      <PageHero
        eyebrow={
          <span className="inline-flex flex-wrap items-center gap-3">
            Command Center · Round {race.round}
            {totalRounds ? ` / ${totalRounds}` : ""}
            {race.country ? ` · ${race.country}` : ""}
            <StateTag tone={status.tone}>{status.label}</StateTag>
          </span>
        }
        title={race.name}
        meta={
          <>
            {label.name}
            {label.place ? ` · ${label.place}` : ""}
            {starts.length > 0 && (
              <span className={`mt-2.5 block ${EYEBROW}`}>
                <LocalTime value={starts[0]} style="weekday" /> → <LocalTime value={starts.at(-1)} style="weekday" />
              </span>
            )}
          </>
        }
        aside={<MapSlot circuit={circuit} loading={circuitLoading} name={label.name} />}
      >
        <div className="space-y-8">
          <SessionWeatherStrip rows={forecast} asOf={forecastAsOf} />
          <NextSessionCountdown sessions={race.sessions} />
        </div>
      </PageHero>
      <CircuitStats
        className="mt-7"
        record={circuit?.record ?? null}
        lapRecord={circuit?.lap_record ?? race.circuit?.lap_record ?? null}
        basics={race.circuit ?? {}}
      />
    </div>
  );
}
