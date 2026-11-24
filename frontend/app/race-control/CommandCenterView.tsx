"use client";

import { Suspense, use } from "react";

import { API_BASE } from "@/app/constants/api";
import { PageHero } from "@/app/ui/PageHero";
import { Section, SectionSkeleton } from "@/app/ui/section/Section";
import { useSection, type SectionResult } from "@/app/ui/section/useSection";

import { BaselineStrategyPanel } from "./components/BaselineStrategyPanel";
import {
  RiskRegisterPanel,
  type OverviewPredictions,
  type OverviewShell,
  type OverviewStrategy,
  type OverviewWeather,
} from "./components/CommandCenterPanels";
import { Disclosure } from "./components/Disclosure";
import { LiveTimingTower } from "./components/LiveTimingTower";
import { SkeletonPanel } from "./components/RaceControlPrimitives";
import { ChampionshipStakes } from "./weekend/ChampionshipStakes";
import { CircuitHistoryPanel } from "./weekend/CircuitHistoryPanel";
import { FiaFeedPanel } from "./weekend/FiaFeedPanel";
import { KeyNumbers } from "./weekend/KeyNumbers";
import { pitLaneFigure } from "./weekend/pitLaneFigure";
import { PodiumPanel } from "./weekend/PodiumPanel";
import { WeekendForecast } from "./weekend/WeekendForecast";
import { WeekendHero } from "./weekend/WeekendHero";

import type { OverviewCircuit } from "./weekend/weekendTypes";

const SWR_OPTIONS = { revalidateOnFocus: false, dedupingInterval: 120_000 };

/**
 * Fetch one overview segment, as its own section (`app/ui/section`).
 *
 * The command centre is assembled from five of these rather than one response,
 * so a slow input costs only the panels that depend on it — each segment is its
 * own cache entry and revalidates on its own clock.
 *
 * SWR owns the request; the server render only seeds it. When the server could
 * not reach the backend in time, the seed is absent and the browser fetches for
 * itself. A segment that has data keeps it when a refresh fails (`stale`), so a
 * tile never reads "Unavailable" over real numbers.
 */
function useOverviewSegment<T>(year: number, path: string, seed: T | null): SectionResult<T> {
  return useSection<T>(`${API_BASE}/api/race-control/overview/${year}${path}`, { seed, config: SWR_OPTIONS });
}

/** The five overview payloads, each still on its way from the server (`null` once it gave up). */
export interface OverviewSeeds {
  shell: Promise<OverviewShell | null>;
  strategy: Promise<OverviewStrategy | null>;
  predictions: Promise<OverviewPredictions | null>;
  weather: Promise<OverviewWeather | null>;
  circuit: Promise<OverviewCircuit | null>;
}

/** One segment, read from its server promise: only the slot that calls this waits for it. */
function useSegment<T>(year: number, path: string, seed: Promise<T | null>): SectionResult<T> {
  return useOverviewSegment<T>(year, path, use(seed));
}

interface HeroSlotProps {
  shell: SectionResult<OverviewShell>;
  circuit: SectionResult<OverviewCircuit>;
  weather: SectionResult<OverviewWeather>;
}

function HeroSlot({ shell, circuit, weather }: HeroSlotProps) {
  const race = shell.data?.race;
  if (shell.status === "pending") return <SkeletonPanel className="h-[460px]" />;
  if (!race) {
    return (
      <PageHero
        eyebrow="Race Control"
        title="Command Center"
        meta={shell.reason ?? "The next race weekend appears here once the calendar is published."}
      />
    );
  }
  return (
    <WeekendHero
      race={race}
      totalRounds={shell.data?.season?.total_events ?? null}
      circuit={circuit.data}
      circuitLoading={circuit.status === "pending"}
      forecast={weather.data?.session_weather?.sessions ?? []}
      forecastAsOf={weather.data?.session_weather?.as_of_label}
    />
  );
}

interface WeekendNumbersProps {
  shell: SectionResult<OverviewShell>;
  strategy: SectionResult<OverviewStrategy>;
  weather: SectionResult<OverviewWeather>;
  circuit: SectionResult<OverviewCircuit>;
}

/** The four headline numbers, each following the segment it is read from. */
function WeekendNumbers({ shell, strategy, weather, circuit }: WeekendNumbersProps) {
  const card = weather.data?.weather;
  const pitLane = pitLaneFigure(strategy.data?.strategy_context);
  const raceForecast = weather.data?.session_weather?.sessions.find((row) => row.name === "Race")?.forecast;
  return (
    <KeyNumbers
      rain={{
        value: card?.rain_risk ?? null,
        source: card?.confidence ?? "Forecast feed offline",
        forecast: raceForecast ?? null,
        state: weather,
      }}
      pit={{ ...pitLane, state: strategy }}
      title={{ stakes: shell.data?.stakes?.drivers, state: shell }}
      history={{ record: circuit.data?.record, state: circuit }}
    />
  );
}

/** Where every number on the page comes from, and what the strategy model assumes. */
function SourcesDisclosure({ assumptions }: { assumptions: string[] }) {
  const sources = [
    "Weather: Open-Meteo hourly forecast (CC BY 4.0), read over each session's hours. Track temperature is estimated. When the feed is down, the last forecast received is shown with the time it was fetched.",
    "Circuit map and corner numbers: MultiViewer (unofficial). Layout facts and history: f1db.",
    "Standings and stakes: f1db's last published round plus each later round's points from OpenF1 results, provisional until f1db publishes them. Points left count every race and sprint the standings do not include yet, at a driver's best (25 a race, 8 a sprint) or a team's one-two (43 and 15).",
    "A title is decided once the leader's lead is more than the points left. A lead exactly equal to them decides it only if the leader would still win the count-back (most Grand Prix wins, then seconds, and so on) once the rival has taken the maximum in every session left.",
    "Podium: the race model's latest stored snapshot for this round.",
  ];
  return (
    <Disclosure title="Sources & assumptions" hint={`${sources.length + assumptions.length} notes`}>
      <ul>
        {[...sources, ...assumptions].map((line) => (
          <li
            key={line}
            className="border-b border-rc-line-soft py-2.5 text-[13px] leading-relaxed text-rc-ink-2 last:border-0"
          >
            {line}
          </li>
        ))}
      </ul>
    </Disclosure>
  );
}

interface SlotProps {
  year: number;
  seeds: OverviewSeeds;
}

function Hero({ year, seeds }: SlotProps) {
  const shell = useSegment(year, "/shell", seeds.shell);
  const circuit = useSegment(year, "/circuit", seeds.circuit);
  const weather = useSegment(year, "/weather", seeds.weather);
  return <HeroSlot shell={shell} circuit={circuit} weather={weather} />;
}

function Numbers({ year, seeds }: SlotProps) {
  const shell = useSegment(year, "/shell", seeds.shell);
  const strategy = useSegment(year, "/strategy", seeds.strategy);
  const weather = useSegment(year, "/weather", seeds.weather);
  const circuit = useSegment(year, "/circuit", seeds.circuit);
  return <WeekendNumbers shell={shell} strategy={strategy} weather={weather} circuit={circuit} />;
}

function LiveSlots({ year, seeds }: SlotProps) {
  const race = useSegment(year, "/shell", seeds.shell).data?.race;
  return (
    <>
      <LiveTimingTower year={year} race={race} />
      <FiaFeedPanel year={year} race={race} />
    </>
  );
}

function WeatherFeed({ year, seeds }: SlotProps) {
  const weather = useSegment(year, "/weather", seeds.weather);
  return (
    <Section state={weather} label="Weather feed" skeletonClassName="h-[440px]">
      <WeekendForecast weather={weather.data?.session_weather} />
    </Section>
  );
}

function Stakes({ year, seeds }: SlotProps) {
  const shell = useSegment(year, "/shell", seeds.shell);
  const venue = shell.data?.race?.location.split(",")[0] ?? "this round";
  return (
    <Section state={shell} label="Championship standings" skeletonClassName="h-[420px]">
      <ChampionshipStakes stakes={shell.data?.stakes} venue={venue} />
    </Section>
  );
}

function Podium({ year, seeds }: SlotProps) {
  const predictions = useSegment(year, "/predictions", seeds.predictions);
  return (
    <Section state={predictions} label="Prediction snapshot" skeletonClassName="h-[420px]">
      <PodiumPanel podium={predictions.data?.predicted_podium ?? []} />
    </Section>
  );
}

function CircuitHistory({ year, seeds }: SlotProps) {
  const circuit = useSegment(year, "/circuit", seeds.circuit);
  return (
    <Section state={circuit} label="Circuit history" skeletonClassName="h-[420px]">
      <CircuitHistoryPanel record={circuit.data?.record} />
    </Section>
  );
}

function Baseline({ year, seeds }: SlotProps) {
  const strategy = useSegment(year, "/strategy", seeds.strategy);
  return (
    <Section state={strategy} label="Baseline strategy" skeletonClassName="h-[420px]" className="flex-1">
      <BaselineStrategyPanel context={strategy.data?.strategy_context} />
    </Section>
  );
}

function RiskRegister({ year, seeds }: SlotProps) {
  const weather = useSegment(year, "/weather", seeds.weather);
  return (
    <Section state={weather} label="Risk register" skeletonClassName="h-[420px]" className="xl:w-[400px] xl:shrink-0">
      <RiskRegisterPanel risks={weather.data?.risk_register ?? []} />
    </Section>
  );
}

function Sources({ year, seeds }: SlotProps) {
  const strategy = useSegment(year, "/strategy", seeds.strategy);
  return <SourcesDisclosure assumptions={strategy.data?.strategy_context?.assumptions ?? []} />;
}

/**
 * Every slot reads only the server promises it shows, behind its own boundary, so the
 * page frame paints at once and each section fills as its segment arrives.
 */
export function CommandCenterView({ year, seeds }: SlotProps) {
  return (
    <div className="space-y-5">
      <Suspense fallback={<SkeletonPanel className="h-[460px]" />}>
        <Hero year={year} seeds={seeds} />
      </Suspense>
      <Suspense fallback={<SectionSkeleton className="h-28" />}>
        <Numbers year={year} seeds={seeds} />
      </Suspense>
      <Suspense fallback={null}>
        <LiveSlots year={year} seeds={seeds} />
      </Suspense>
      <Suspense fallback={<SectionSkeleton className="h-[440px]" />}>
        <WeatherFeed year={year} seeds={seeds} />
      </Suspense>

      <div className="grid gap-5 xl:grid-cols-3 [&>*]:min-w-0">
        <Suspense fallback={<SectionSkeleton className="h-[420px]" />}>
          <Stakes year={year} seeds={seeds} />
        </Suspense>
        <Suspense fallback={<SectionSkeleton className="h-[420px]" />}>
          <Podium year={year} seeds={seeds} />
        </Suspense>
        <Suspense fallback={<SectionSkeleton className="h-[420px]" />}>
          <CircuitHistory year={year} seeds={seeds} />
        </Suspense>
      </div>

      <div className="flex flex-col gap-5 xl:flex-row [&>*]:min-w-0">
        <Suspense fallback={<SectionSkeleton className="h-[420px] flex-1" />}>
          <Baseline year={year} seeds={seeds} />
        </Suspense>
        <Suspense fallback={<SectionSkeleton className="h-[420px] xl:w-[400px] xl:shrink-0" />}>
          <RiskRegister year={year} seeds={seeds} />
        </Suspense>
      </div>

      <Suspense fallback={<SourcesDisclosure assumptions={[]} />}>
        <Sources year={year} seeds={seeds} />
      </Suspense>
    </div>
  );
}
