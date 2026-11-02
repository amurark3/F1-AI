"use client";

import { MapPin } from "lucide-react";

import { LocalTime } from "@/app/components/LocalTime";

import { SkeletonPanel, StatusPill, rcFont } from "../components/RaceControlPrimitives";

import { CircuitMap } from "./CircuitMap";
import { CircuitStats, type CircuitBasics } from "./CircuitStats";
import { SessionWeatherStrip } from "./SessionWeatherStrip";
import { useClock } from "./useClock";
import { countdownParts, nextUp } from "./weekendModel";

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

const STATUS: Record<string, { label: string; color: string }> = {
  upcoming: { label: "Upcoming", color: "#4C8DFF" },
  in_progress: { label: "Weekend live", color: "#FF4655" },
  completed: { label: "Completed", color: "#7F8797" },
};

function CountdownDigit({ value, unit }: { value: string; unit: string }) {
  return (
    <div className="flex min-w-[64px] flex-col items-center rounded-md border border-white/10 bg-black/40 px-3 py-2">
      <span className="font-mono text-3xl font-black tabular-nums text-white sm:text-4xl">{value}</span>
      <span className="mt-0.5 font-mono text-[9px] font-bold uppercase tracking-[0.2em] text-[#7F8797]">{unit}</span>
    </div>
  );
}

/** Ticks once a second in the browser; the server renders dashes, as it has no honest "now". */
function NextSessionCountdown({ sessions }: { sessions: Record<string, string> }) {
  const now = useClock();
  const next = now === null ? null : nextUp(sessions, now);
  if (now !== null && next === null) {
    return <p className="font-mono text-sm uppercase tracking-[0.18em] text-[#7F8797]">Weekend complete</p>;
  }
  if (next?.live) {
    return (
      <div className="inline-flex items-center gap-3 rounded-md border border-[#FF4655]/50 bg-[#FF4655]/10 px-4 py-3">
        <span className="h-2.5 w-2.5 rounded-full bg-[#FF4655] motion-safe:animate-pulse" />
        <span className="font-mono text-sm font-bold uppercase tracking-[0.2em] text-white">
          Live now · {next.name}
        </span>
      </div>
    );
  }
  const parts = next && now !== null ? countdownParts(new Date(next.startsAt).getTime(), now) : null;
  return (
    <div>
      <p className="mb-2 font-mono text-[10px] font-bold uppercase tracking-[0.24em] text-[#7F8797]">
        Next · <span className="text-[#FF4655]">{next?.name ?? "—"}</span>
      </p>
      <div className="flex gap-2" aria-live="off">
        <CountdownDigit value={parts?.days ?? "--"} unit="days" />
        <CountdownDigit value={parts?.hours ?? "--"} unit="hrs" />
        <CountdownDigit value={parts?.minutes ?? "--"} unit="min" />
        <CountdownDigit value={parts?.seconds ?? "--"} unit="sec" />
      </div>
    </div>
  );
}

function MapSlot({ circuit, loading, name }: { circuit: OverviewCircuit | undefined; loading: boolean; name: string }) {
  if (loading) return <SkeletonPanel className="h-full min-h-[240px]" />;
  if (!circuit?.map) {
    return (
      <div className="flex h-full min-h-[240px] items-center justify-center rounded-lg border border-dashed border-white/10 text-sm text-[#6F7789]">
        Circuit map unavailable
      </div>
    );
  }
  return (
    <figure className="flex h-full flex-col">
      <div className="relative min-h-[240px] flex-1 [background-image:radial-gradient(rgba(255,255,255,0.06)_1px,transparent_1px)] [background-size:18px_18px]">
        <CircuitMap map={circuit.map} name={name} />
      </div>
      <figcaption className="mt-2 text-right font-mono text-[10px] uppercase tracking-[0.16em] text-[#5D6577]">
        Layout · {circuit.map.source} {circuit.map.season}
      </figcaption>
    </figure>
  );
}

/** The circuit's name and town, preferring f1db's record to the schedule's location. */
function circuitLabel(race: HeroRace, circuit: OverviewCircuit | undefined): { name: string; place: string } {
  const name = circuit?.record?.name ?? race.circuit?.circuit_name ?? race.location;
  const place = circuit?.record?.place ?? race.location.split(",")[0] ?? "";
  return { name, place: place === name ? "" : place };
}

function HeroTitle({ race, totalRounds, circuit, forecast }: Omit<WeekendHeroProps, "circuitLoading">) {
  const status = STATUS[race.status] ?? { label: race.status, color: "#7F8797" };
  const starts = Object.values(race.sessions).sort((a, b) => a.localeCompare(b));
  const label = circuitLabel(race, circuit);
  return (
    <div className="motion-safe:animate-fade-up">
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <span className="font-mono text-[11px] font-bold uppercase tracking-[0.24em] text-[#7F8797]">
          Round {race.round}
          {totalRounds ? ` / ${totalRounds}` : ""}
          {race.country ? ` · ${race.country}` : ""}
        </span>
        <StatusPill color={status.color}>{status.label}</StatusPill>
      </div>
      <h1 className="text-4xl font-black leading-[1.05] text-white sm:text-5xl" style={rcFont}>
        {race.name}
      </h1>
      <div className="mt-3 h-[3px] w-24 origin-left bg-[#E10600] motion-safe:animate-fill-x" />
      <p className="mt-4 flex items-center gap-2 text-sm text-[#AEB6C6]">
        <MapPin className="h-4 w-4 shrink-0 text-[#E10600]" aria-hidden="true" />
        <span className="truncate">
          {label.name}
          {label.place ? ` · ${label.place}` : ""}
        </span>
      </p>
      {starts.length > 0 && (
        <p className="mt-1 font-mono text-xs uppercase tracking-[0.14em] text-[#7F8797]">
          <LocalTime value={starts[0]} style="weekday" /> → <LocalTime value={starts.at(-1)} style="weekday" />
        </p>
      )}
      <div className="mt-5">
        <SessionWeatherStrip rows={forecast} />
      </div>
    </div>
  );
}

interface WeekendHeroProps {
  race: HeroRace;
  totalRounds: number | null;
  circuit: OverviewCircuit | undefined;
  circuitLoading: boolean;
  /** Each session's forecast, once the weather segment lands. */
  forecast: SessionWeatherRow[];
}

export function WeekendHero({ race, totalRounds, circuit, circuitLoading, forecast }: WeekendHeroProps) {
  return (
    <section className="relative mb-5 overflow-hidden rounded-md border border-[#1E2633] bg-[#0B0F18]">
      <div className="relative h-[3px] overflow-hidden bg-gradient-to-r from-[#E10600] via-[#FF4422] to-[#E10600]">
        <div className="absolute inset-y-0 w-1/3 bg-gradient-to-r from-transparent via-white/50 to-transparent motion-safe:animate-streak motion-reduce:hidden" />
      </div>
      <div className="pointer-events-none absolute -left-24 -top-24 h-80 w-80 rounded-full bg-[#E10600]/15 blur-3xl" />

      <div className="relative grid gap-6 p-5 sm:p-7 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)]">
        <div className="flex min-w-0 flex-col justify-between gap-6">
          <HeroTitle race={race} totalRounds={totalRounds} circuit={circuit} forecast={forecast} />
          <NextSessionCountdown sessions={race.sessions} />
        </div>
        <MapSlot circuit={circuit} loading={circuitLoading} name={circuitLabel(race, circuit).name} />
      </div>

      <div className="relative px-5 pb-5 sm:px-7 sm:pb-7">
        <CircuitStats
          record={circuit?.record ?? null}
          lapRecord={circuit?.lap_record ?? race.circuit?.lap_record ?? null}
          basics={race.circuit ?? {}}
        />
      </div>
    </section>
  );
}
