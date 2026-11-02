"use client";

import useSWR from "swr";

import { API_BASE } from "@/app/constants/api";
import { useServerStatus } from "@/app/hooks/useServerStatus";
import { awaitingFirstData, seededWith } from "@/app/lib/swrFallback";
import { fetcher } from "@/app/utils/fetcher";

import {
  BaselineStrategyPanel,
  RiskRegisterPanel,
  type OverviewPredictions,
  type OverviewShell,
  type OverviewStrategy,
  type OverviewWeather,
  type StrategyContext,
} from "./components/CommandCenterPanels";
import { Disclosure } from "./components/Disclosure";
import { LiveTimingPanel } from "./components/LiveTimingPanel";
import { InlineNotice, Panel, SectionHeader, SkeletonPanel } from "./components/RaceControlPrimitives";
import { ChampionshipStakes } from "./weekend/ChampionshipStakes";
import { CircuitHistoryPanel } from "./weekend/CircuitHistoryPanel";
import { KeyNumbers, type TileState } from "./weekend/KeyNumbers";
import { PodiumPanel } from "./weekend/PodiumPanel";
import { WeekendForecast } from "./weekend/WeekendForecast";
import { WeekendHero } from "./weekend/WeekendHero";

import type { OverviewCircuit } from "./weekend/weekendTypes";

const SWR_OPTIONS = { revalidateOnFocus: false, dedupingInterval: 120_000 };

/** Where one overview segment currently stands. */
interface SegmentState {
  /** True while the segment has neither a seed nor a fetched response. */
  loading: boolean;
  /** A user-facing reason the segment has no data, or null when it is fine. */
  failure: string | null;
  /** True when the only thing wrong is that the backend has not woken yet. */
  warming: boolean;
}

interface Segment<T> extends SegmentState {
  data?: T;
}

/**
 * Turns a fetch failure into something worth reading.
 *
 * A transport error surfaces as the browser's own "Failed to fetch", which
 * tells a reader nothing and — while the backend is still spinning up — is not
 * even the right story. The readiness probe already knows which case this is,
 * so warming gets named as warming and only a genuine fault reports as one.
 */
function describeFailure(error: Error | undefined, backendReady: boolean): string | null {
  if (!error) return null;
  if (!backendReady) return "Waiting for the server to finish waking up.";

  // A transport failure has no useful message; anything else came from us.
  return error.message === "Failed to fetch" ? "Could not reach the server." : error.message;
}

/**
 * Fetch one overview segment.
 *
 * The command centre is assembled from five of these rather than one response,
 * so a slow input costs only the panels that depend on it — each segment is its
 * own cache entry and revalidates on its own clock.
 *
 * SWR owns the request; the server render only seeds it. That split matters:
 * when the server could not reach the backend in time, the seed is absent and
 * the browser fetches for itself, which is the difference between a page that
 * recovers and a page that caches an apology. A handled backend failure answers
 * 200 with an `error` field, so a healthy transport does not imply a healthy
 * segment.
 */
function useOverviewSegment<T extends { error?: string | null }>(
  year: number,
  path: string,
  seed: T | null,
  backendReady: boolean,
): Segment<T> {
  const { data, error, isLoading } = useSWR<T, Error>(`${API_BASE}/api/race-control/overview/${year}${path}`, fetcher, {
    ...SWR_OPTIONS,
    ...seededWith(seed),
  });

  return {
    data,
    loading: awaitingFirstData(isLoading, data !== undefined),
    failure: describeFailure(error, backendReady) ?? data?.error ?? null,
    warming: Boolean(error) && !backendReady,
  };
}

/** Merge the states of the segments a single panel needs. */
function combined(...states: SegmentState[]): SegmentState {
  return {
    loading: states.some((state) => state.loading),
    failure: states.map((state) => state.failure).find((failure) => failure !== null) ?? null,
    warming: states.some((state) => state.warming),
  };
}

const pending = (state: SegmentState) => state.loading || state.warming;

/** A key-number tile follows its own segment: pending, failed, or ready. */
function tileState(state: SegmentState): TileState {
  if (pending(state)) return "pending";
  return state.failure === null ? "ready" : "failed";
}

/**
 * Renders a panel once its segment has landed: a skeleton while it is still in
 * flight, and the reason it is missing if it failed outright.
 */
function SegmentSlot({
  state,
  title,
  height,
  children,
}: {
  state: SegmentState;
  title: string;
  height: string;
  children: React.ReactNode;
}) {
  // A waking backend is not a fault, so it keeps the skeleton rather than
  // filling the page with red panels the reader can do nothing about.
  if (pending(state)) return <SkeletonPanel className={height} />;
  if (state.failure !== null) {
    return (
      <Panel className="p-5">
        <InlineNotice title={title} tone="error">
          {state.failure}
        </InlineNotice>
      </Panel>
    );
  }
  return <>{children}</>;
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
  shell: Segment<OverviewShell>;
  circuit: Segment<OverviewCircuit>;
  weather: Segment<OverviewWeather>;
}

function HeroSlot({ shell, circuit, weather }: HeroSlotProps) {
  const race = shell.data?.race;
  if (pending(shell)) return <SkeletonPanel className="mb-5 h-[460px]" />;
  if (!race) {
    return (
      <SectionHeader
        eyebrow="Race Weekend Command Center"
        title="Command Center"
        description={shell.failure ?? "The next race weekend appears here once the calendar is published."}
      />
    );
  }
  return (
    <WeekendHero
      race={race}
      totalRounds={shell.data?.season?.total_events ?? null}
      circuit={circuit.data}
      circuitLoading={pending(circuit)}
      forecast={weather.data?.session_weather?.sessions ?? []}
    />
  );
}

function pitDetail(context: StrategyContext | undefined): string {
  const pit = context?.pit_model;
  if (!pit) return "Baseline model unavailable";
  return `Undercut ${pit.undercut_delta}s · overcut ${pit.overcut_delta}s${pit.undercut_modeled ? " · modeled" : ""}`;
}

interface WeekendNumbersProps {
  shell: Segment<OverviewShell>;
  strategy: Segment<OverviewStrategy>;
  weather: Segment<OverviewWeather>;
  circuit: Segment<OverviewCircuit>;
}

/** The four headline numbers, each following the segment it is read from. */
function WeekendNumbers({ shell, strategy, weather, circuit }: WeekendNumbersProps) {
  const card = weather.data?.weather;
  const context = strategy.data?.strategy_context;
  const raceForecast = weather.data?.session_weather?.sessions.find((row) => row.name === "Race")?.forecast;
  return (
    <KeyNumbers
      rain={{
        value: card?.rain_risk ?? null,
        source: card?.confidence ?? "Forecast feed offline",
        forecast: raceForecast ?? null,
        state: tileState(weather),
      }}
      pit={{
        lossSeconds: context?.pit_model.pit_loss_seconds ?? null,
        detail: pitDetail(context),
        state: tileState(strategy),
      }}
      title={{ stakes: shell.data?.stakes?.drivers, state: tileState(shell) }}
      history={{ record: circuit.data?.record, state: tileState(circuit) }}
    />
  );
}

/** Where every number on the page comes from, and what the strategy model assumes. */
function SourcesDisclosure({ assumptions }: { assumptions: string[] }) {
  const sources = [
    "Weather: Open-Meteo hourly forecast (CC BY 4.0), read over each session's hours. Track temperature is estimated.",
    "Circuit map and corner numbers: MultiViewer (unofficial). Layout facts and history: f1db.",
    "Standings and stakes: f1db's last published round plus each later round's points from OpenF1 results, provisional until f1db publishes them. Points left count every race (25) and sprint (8) the standings do not include yet.",
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

  // The readiness probe in the root layout is already tracking the backend's
  // wake-up; reuse its verdict so the panels and the banner tell one story.
  const { status } = useServerStatus();
  const backendReady = status === "ready";

  const shell = useOverviewSegment<OverviewShell>(year, "/shell", seed.shell, backendReady);
  const strategy = useOverviewSegment<OverviewStrategy>(year, "/strategy", seed.strategy, backendReady);
  const predictions = useOverviewSegment<OverviewPredictions>(year, "/predictions", seed.predictions, backendReady);
  const weather = useOverviewSegment<OverviewWeather>(year, "/weather", seed.weather, backendReady);
  const circuit = useOverviewSegment<OverviewCircuit>(year, "/circuit", seed.circuit, backendReady);

  const race = shell.data?.race;
  const context = strategy.data?.strategy_context;
  const venue = race?.location.split(",")[0] ?? "this round";

  return (
    <div>
      <HeroSlot shell={shell} circuit={circuit} weather={weather} />
      <WeekendNumbers shell={shell} strategy={strategy} weather={weather} circuit={circuit} />

      <div className="space-y-5">
        <LiveTimingPanel year={year} race={race} />

        <SegmentSlot state={weather} title="Weather feed unavailable" height="h-[440px]">
          <WeekendForecast weather={weather.data?.session_weather} />
        </SegmentSlot>

        <div className="grid gap-5 xl:grid-cols-3 [&>*]:min-w-0">
          <SegmentSlot state={shell} title="Championship standings unavailable" height="h-[420px]">
            <ChampionshipStakes stakes={shell.data?.stakes} venue={venue} />
          </SegmentSlot>
          <SegmentSlot state={predictions} title="Prediction snapshot unavailable" height="h-[420px]">
            <PodiumPanel podium={predictions.data?.predicted_podium ?? []} />
          </SegmentSlot>
          <SegmentSlot state={circuit} title="Circuit history unavailable" height="h-[420px]">
            <CircuitHistoryPanel record={circuit.data?.record} />
          </SegmentSlot>
        </div>

        <div className="flex flex-col gap-5 xl:flex-row [&>*]:min-w-0">
          <div className="flex-1">
            <SegmentSlot state={combined(shell, strategy)} title="Baseline strategy unavailable" height="h-[420px]">
              <BaselineStrategyPanel context={context} />
            </SegmentSlot>
          </div>
          <div className="xl:w-[400px] xl:shrink-0">
            <SegmentSlot state={weather} title="Risk register unavailable" height="h-[420px]">
              <RiskRegisterPanel risks={weather.data?.risk_register ?? []} />
            </SegmentSlot>
          </div>
        </div>

        <SourcesDisclosure assumptions={context?.assumptions ?? []} />
      </div>
    </div>
  );
}
