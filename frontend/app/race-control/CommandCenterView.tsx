"use client";

import { API_BASE } from "@/app/constants/api";
import { Section } from "@/app/ui/section/Section";
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
import { LiveTimingPanel } from "./components/LiveTimingPanel";
import { SectionHeader, SkeletonPanel } from "./components/RaceControlPrimitives";
import { ChampionshipStakes } from "./weekend/ChampionshipStakes";
import { CircuitHistoryPanel } from "./weekend/CircuitHistoryPanel";
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

/** The five overview payloads the server managed to prefetch. */
export interface OverviewSeed {
  year: number;
  shell: OverviewShell | null;
  strategy: OverviewStrategy | null;
  predictions: OverviewPredictions | null;
  weather: OverviewWeather | null;
  circuit: OverviewCircuit | null;
}

interface HeroSlotProps {
  shell: SectionResult<OverviewShell>;
  circuit: SectionResult<OverviewCircuit>;
  weather: SectionResult<OverviewWeather>;
}

function HeroSlot({ shell, circuit, weather }: HeroSlotProps) {
  const race = shell.data?.race;
  if (shell.status === "pending") return <SkeletonPanel className="mb-5 h-[460px]" />;
  if (!race) {
    return (
      <SectionHeader
        eyebrow="Race Weekend Command Center"
        title="Command Center"
        description={shell.reason ?? "The next race weekend appears here once the calendar is published."}
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
      <ul className="space-y-2 p-4 text-sm leading-relaxed text-neutral-400">
        {[...sources, ...assumptions].map((line) => (
          <li key={line} className="rounded-lg border border-white/8 bg-white/[0.03] px-3 py-2">
            {line}
          </li>
        ))}
      </ul>
    </Disclosure>
  );
}

export function CommandCenterView({ seed }: { seed: OverviewSeed }) {
  const { year } = seed;

  // Each segment follows the readiness probe through `useSection`, so a
  // restarting backend keeps skeletons rather than reporting a fault.
  const shell = useOverviewSegment<OverviewShell>(year, "/shell", seed.shell);
  const strategy = useOverviewSegment<OverviewStrategy>(year, "/strategy", seed.strategy);
  const predictions = useOverviewSegment<OverviewPredictions>(year, "/predictions", seed.predictions);
  const weather = useOverviewSegment<OverviewWeather>(year, "/weather", seed.weather);
  const circuit = useOverviewSegment<OverviewCircuit>(year, "/circuit", seed.circuit);

  const race = shell.data?.race;
  const context = strategy.data?.strategy_context;
  const venue = race?.location.split(",")[0] ?? "this round";

  return (
    <div>
      <HeroSlot shell={shell} circuit={circuit} weather={weather} />
      <WeekendNumbers shell={shell} strategy={strategy} weather={weather} circuit={circuit} />

      <div className="space-y-5">
        <LiveTimingPanel year={year} race={race} />

        <Section state={weather} label="Weather feed" skeletonClassName="h-[440px]">
          <WeekendForecast weather={weather.data?.session_weather} />
        </Section>

        <div className="grid gap-5 xl:grid-cols-3 [&>*]:min-w-0">
          <Section state={shell} label="Championship standings" skeletonClassName="h-[420px]">
            <ChampionshipStakes stakes={shell.data?.stakes} venue={venue} />
          </Section>
          <Section state={predictions} label="Prediction snapshot" skeletonClassName="h-[420px]">
            <PodiumPanel podium={predictions.data?.predicted_podium ?? []} />
          </Section>
          <Section state={circuit} label="Circuit history" skeletonClassName="h-[420px]">
            <CircuitHistoryPanel record={circuit.data?.record} />
          </Section>
        </div>

        <div className="flex flex-col gap-5 xl:flex-row [&>*]:min-w-0">
          <Section state={strategy} label="Baseline strategy" skeletonClassName="h-[420px]" className="flex-1">
            <BaselineStrategyPanel context={context} />
          </Section>
          <Section
            state={weather}
            label="Risk register"
            skeletonClassName="h-[420px]"
            className="xl:w-[400px] xl:shrink-0"
          >
            <RiskRegisterPanel risks={weather.data?.risk_register ?? []} />
          </Section>
        </div>

        <SourcesDisclosure assumptions={context?.assumptions ?? []} />
      </div>
    </div>
  );
}
