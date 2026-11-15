"use client";

import Link from "next/link";

import { API_BASE } from "@/app/constants/api";
import { grandPrixHref } from "@/app/lib/entityLinks";
import { getTeamColor } from "@/app/lib/teamColors";
import { CircuitMap } from "@/app/ui/CircuitMap";
import { Countdown } from "@/app/ui/Countdown";
import { DriverName } from "@/app/ui/names/DriverName";
import { TeamName } from "@/app/ui/names/TeamName";
import { nextUp } from "@/app/ui/nextUp";
import { Section } from "@/app/ui/section/Section";
import { useSection, type SectionResult } from "@/app/ui/section/useSection";
import { EYEBROW } from "@/app/ui/typography";
import { useClock } from "@/app/ui/useClock";

import { raceWinner, type RoundCircuit } from "./weekendTabModel";

import type { RaceEvent } from "./predictionModel";
import type { RaceResultsResponse } from "./resultsModel";

/** Time to the next session, "Live now" while one is on track, and "complete" once the weekend is over. */
function NextSession({ sessions }: { sessions: Record<string, string> }) {
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

/** Who won, from the FIA classification, and the way into it. */
function Winner({ year, round }: { year: number; round: number }) {
  const state = useSection<RaceResultsResponse>(`${API_BASE}/api/race-control/results/${year}/${round}`, {
    config: { revalidateOnFocus: false, dedupingInterval: 120_000 },
  });
  const winner = raceWinner(state.data);
  const final = state.data?.race?.final ?? false;
  return (
    <div>
      <p className={`${EYEBROW} mb-2.5`}>Winner{state.data?.race && !final ? " · provisional" : ""}</p>
      {winner ? (
        <p className="font-display text-[44px] font-extrabold uppercase leading-none text-rc-gold">
          <DriverName name={winner.driver_name} code={winner.driver_code} />
        </p>
      ) : (
        <p className="text-sm text-rc-ink-2">
          {state.status === "pending" ? "Reading the classification…" : "The classification is not published yet."}
        </p>
      )}
      {winner && (
        <p className="mt-2 flex items-center gap-2 text-sm text-rc-ink-2">
          <span className="h-3 w-[3px] rounded-full" style={{ background: getTeamColor(winner.team) }} />
          <TeamName name={winner.team} />
        </p>
      )}
      <Link
        href={grandPrixHref(round, "results")}
        className="mt-4 inline-block font-mono text-xs font-semibold uppercase tracking-[0.14em] text-rc-ink hover:underline"
      >
        Final classification →
      </Link>
    </div>
  );
}

function MapFigure({ circuit, name }: { circuit: RoundCircuit | undefined; name: string }) {
  if (!circuit?.map) {
    return (
      <div className="flex h-full min-h-[240px] items-center justify-center rounded-md border border-dashed border-rc-line text-sm text-rc-ink-3">
        Circuit map unavailable
      </div>
    );
  }
  return (
    <figure className="flex h-full flex-col">
      <div className="min-h-[240px] flex-1">
        <CircuitMap map={circuit.map} name={name} />
      </div>
      <figcaption className="mt-2 text-right font-mono text-[10px] uppercase tracking-[0.16em] text-rc-ink-3">
        Layout · {circuit.map.source} {circuit.map.season}
      </figcaption>
    </figure>
  );
}

/**
 * The weekend's hero band: what is next (or who won) beside the circuit.
 * Once the race is classified the countdown gives way to the winner and a
 * link to Results; the tab does not print results itself.
 */
export function WeekendHero({
  year,
  race,
  circuit,
}: {
  year: number;
  race: RaceEvent;
  circuit: SectionResult<RoundCircuit>;
}) {
  const name = circuit.data?.record?.name ?? race.circuit?.circuit_name ?? race.location;
  return (
    <section className="grid gap-6 rounded-md border border-rc-line bg-rc-hero p-5 sm:p-7 lg:grid-cols-[5fr_6fr]">
      <div className="flex flex-col justify-between gap-6">
        <p className={EYEBROW}>{name}</p>
        {race.status === "completed" ? (
          <Winner year={year} round={race.round} />
        ) : (
          <NextSession sessions={race.sessions ?? {}} />
        )}
      </div>
      <Section state={circuit} label="Circuit map" skeletonClassName="h-[260px]" className="h-full">
        <MapFigure circuit={circuit.data} name={name} />
      </Section>
    </section>
  );
}
