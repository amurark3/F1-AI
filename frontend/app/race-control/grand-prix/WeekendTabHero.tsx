"use client";

import Link from "next/link";

import { API_BASE } from "@/app/constants/api";
import { grandPrixHref } from "@/app/lib/entityLinks";
import { getTeamColor } from "@/app/lib/teamColors";
import { CIRCUIT_FRAME, CircuitMap } from "@/app/ui/CircuitMap";
import { Countdown } from "@/app/ui/Countdown";
import { DriverName } from "@/app/ui/names/DriverName";
import { TeamName } from "@/app/ui/names/TeamName";
import { nextUp } from "@/app/ui/nextUp";
import { Section } from "@/app/ui/section/Section";
import { useSection, type SectionResult } from "@/app/ui/section/useSection";
import { DISPLAY, EYEBROW } from "@/app/ui/typography";
import { useClock } from "@/app/ui/useClock";

import { STATUS_LABELS } from "./HubHeader";
import { StateTag, type StateTone } from "./StateTag";
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
        href={grandPrixHref(round, "results", year)}
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
      <div
        className={`flex h-full items-center justify-center rounded-md border border-dashed border-rc-line text-sm text-rc-ink-3 ${CIRCUIT_FRAME}`}
      >
        Circuit map unavailable
      </div>
    );
  }
  return (
    <figure
      className={`flex h-full flex-col rounded-md border border-rc-line bg-rc-hero p-5 sm:p-[22px] ${CIRCUIT_FRAME}`}
    >
      <div className="relative flex-1">
        <CircuitMap map={circuit.map} name={name} />
      </div>
      <figcaption className="mt-2 text-right font-mono text-[10px] uppercase tracking-[0.16em] text-rc-ink-3">
        Layout · {circuit.map.source} {circuit.map.season}
      </figcaption>
    </figure>
  );
}

const STATUS_TONES: Record<string, StateTone> = { upcoming: "blue", in_progress: "red", live: "red" };

/** "Las Vegas, United States" → city and country; the calendar may carry the city alone. */
function placeParts(location: string): { city: string; country: string | null } {
  const [city, ...rest] = location.split(", ");
  return { city, country: rest.length > 0 ? rest.join(", ") : null };
}

/**
 * The Weekend tab's hero (`grand-prix.html`), above the tabs: the round, the
 * race in display type, the circuit, and what is next (or who won) beside the
 * map. Once the race is classified the countdown gives way to the winner and a
 * link to Results; the tab does not print results itself.
 */
export function WeekendHero({
  year,
  race,
  circuit,
  totalRounds,
}: {
  year: number;
  race: RaceEvent;
  circuit: SectionResult<RoundCircuit>;
  totalRounds: number;
}) {
  const { city, country } = placeParts(race.location);
  const name = circuit.data?.record?.name ?? race.circuit?.circuit_name ?? city;
  return (
    <section className="grid gap-8 lg:grid-cols-[5fr_6fr]">
      <div className="flex flex-col justify-between gap-9">
        <div>
          <div className="flex flex-wrap items-center gap-3">
            <p className={EYEBROW}>
              Round {race.round} / {totalRounds}
              {country ? ` · ${country}` : ""}
            </p>
            <StateTag tone={STATUS_TONES[race.status] ?? "neutral"}>
              {STATUS_LABELS[race.status] ?? race.status}
            </StateTag>
          </div>
          {/* A no-break space keeps "Grand Prix" on one line when the name wraps. */}
          <h1 className={`${DISPLAY} mt-3.5 text-[clamp(48px,5.6vw,84px)] text-rc-ink`}>
            {race.name.replace(" Prix", "\u00a0Prix")}
          </h1>
          <div aria-hidden="true" className="my-[22px] h-[3px] w-24 origin-left bg-f1-red motion-safe:animate-fill-x" />
          <p className="text-[15px] text-rc-ink-2">
            {name}
            {name === city ? "" : ` · ${city}`}
          </p>
        </div>
        {race.status === "completed" ? (
          <Winner year={year} round={race.round} />
        ) : (
          <NextSession sessions={race.sessions ?? {}} />
        )}
      </div>
      <Section state={circuit} label="Circuit map" skeletonClassName={`h-full ${CIRCUIT_FRAME}`} className="h-full">
        <MapFigure circuit={circuit.data} name={name} />
      </Section>
    </section>
  );
}
