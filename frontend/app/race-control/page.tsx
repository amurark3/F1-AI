"use client";

import { AlertTriangle, ArrowRight, CalendarClock, CloudRain, Target, Timer, Trophy } from "lucide-react";
import Link from "next/link";
import useSWR from "swr";

import { API_BASE } from "@/app/constants/api";
import { fetcher } from "@/app/utils/fetcher";

import {
  AssumptionStat,
  BaselineStrategyPanel,
  CallSheetPanel,
  CompetitorMatrixPanel,
  StintPlanPanel,
  formatCircuitDetail,
  formatWeatherMetric,
  type Overview,
  type OverviewPredictions,
  type OverviewShell,
  type OverviewStrategy,
  type OverviewWeather,
  type RaceEvent,
  type StrategyContext,
} from "./components/CommandCenterPanels";
import {
  InlineNotice,
  MetricCard,
  MetricRow,
  Panel,
  SectionHeader,
  SkeletonPanel,
  rcFont,
} from "./components/RaceControlPrimitives";

const year = new Date().getFullYear();

const SWR_OPTIONS = { revalidateOnFocus: false, dedupingInterval: 120_000 };

/** Where one overview segment currently stands. */
interface SegmentState {
  loading: boolean;
  /** A user-facing reason the segment has no data, or null while it is fine. */
  failure: string | null;
}

interface Segment<T> extends SegmentState {
  data?: T;
}

/**
 * Fetch one overview segment.
 *
 * The command centre is assembled from four of these rather than one response,
 * so a cold telemetry load on the backend delays only the panels that depend
 * on it — the race name, calendar, and championship arrive immediately.
 */
function useOverviewSegment<T extends { error?: string | null }>(path: string): Segment<T> {
  const { data, error, isLoading } = useSWR<T, Error>(
    `${API_BASE}/api/race-control/overview/${year}${path}`,
    fetcher,
    SWR_OPTIONS,
  );

  // A handled backend failure answers 200 with an `error` field, so a healthy
  // transport does not imply a healthy segment.
  const failure = error?.message ?? data?.error ?? null;
  return { data, loading: isLoading, failure };
}

/** Merge the states of the segments a single panel needs. */
function combined(...states: SegmentState[]): SegmentState {
  return {
    loading: states.some((state) => state.loading),
    failure: states.map((state) => state.failure).find((failure) => failure !== null) ?? null,
  };
}

/**
 * Render a panel once its segment has landed: a skeleton while it is in
 * flight, and the reason it is missing if it failed.
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
  if (state.loading) return <SkeletonPanel className={height} />;
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

/** Metric values track their own segment: pending, failed, or ready. */
function metricValue(state: SegmentState, value: string): string {
  if (state.loading) return "…";
  if (state.failure !== null) return "Unavailable";
  return value;
}

interface CommandMetricsProps {
  race: RaceEvent | null | undefined;
  context: StrategyContext | undefined;
  weather: Overview["weather"];
  focus: string | undefined;
  shell: SegmentState;
  strategy: SegmentState;
  weatherState: SegmentState;
}

function CommandMetrics({ race, context, weather, focus, shell, strategy, weatherState }: CommandMetricsProps) {
  const weekendSub = race ? `${race.status} · ${race.location}` : "Awaiting schedule";
  const pitValue = context ? `${context.pit_model.pit_loss_seconds}s` : "No model";
  const pitSub = context
    ? `Undercut ${context.pit_model.undercut_delta}s · overcut ${context.pit_model.overcut_delta}s${context.pit_model.undercut_modeled ? " · modeled" : ""}`
    : "Baseline model unavailable";
  const rainSub = weather?.confidence ?? "Live feed offline";
  const weekendState = combined(shell, strategy);

  return (
    <MetricRow>
      <MetricCard
        label="Weekend state"
        value={metricValue(weekendState, context?.phase ?? focus ?? "Pre-race")}
        sub={weekendSub}
        icon={Target}
      />
      <MetricCard
        label="Circuit profile"
        value={metricValue(shell, race?.circuit?.circuit_name ?? race?.location ?? "No circuit")}
        sub={formatCircuitDetail(race)}
        icon={CalendarClock}
        color="#FF8000"
      />
      <MetricCard
        label="Pit lane delta"
        value={metricValue(strategy, pitValue)}
        sub={pitSub}
        icon={Timer}
        color="#3671C6"
      />
      <MetricCard
        label="Rain risk"
        value={metricValue(weatherState, formatWeatherMetric(weather?.rain_risk, "%"))}
        sub={rainSub}
        icon={CloudRain}
        color="#BE3AFF"
      />
    </MetricRow>
  );
}

export default function RaceControlHome() {
  // Four parallel requests, each rendered the moment it lands. The shell is
  // schedule and standings only, so the page has a race name and a calendar
  // while the telemetry-backed panels are still being built.
  const shell = useOverviewSegment<OverviewShell>("/shell");
  const strategy = useOverviewSegment<OverviewStrategy>("/strategy");
  const predictions = useOverviewSegment<OverviewPredictions>("/predictions");
  const weather = useOverviewSegment<OverviewWeather>("/weather");

  const race = shell.data?.race;
  const context = strategy.data?.strategy_context;
  const sessions = race ? Object.entries(race.sessions).slice(0, 5) : [];
  const forecast = weather.data?.weather;

  return (
    <div>
      <SectionHeader
        eyebrow="Race Weekend Command Center"
        title={race?.name ?? "Command Center"}
        description="Pre-race operating view for session timing, baseline strategy, competitor threats, and open assumptions."
      />

      <CommandMetrics
        race={race}
        context={context}
        weather={forecast}
        focus={shell.data?.focus}
        shell={shell}
        strategy={strategy}
        weatherState={weather}
      />

      <div className="space-y-5">
        <SegmentSlot state={combined(shell, strategy)} title="Baseline strategy unavailable" height="h-[420px]">
          <BaselineStrategyPanel context={context} race={race} sessions={sessions} />
        </SegmentSlot>

        <div className="flex flex-col gap-5 xl:flex-row [&>*]:min-w-0 [&>*]:flex-1">
          <SegmentSlot state={predictions} title="Prediction snapshot unavailable" height="h-96">
            <ProjectedPodiumPanel podium={predictions.data?.predicted_podium ?? []} />
          </SegmentSlot>
          <SegmentSlot state={weather} title="Weather feed unavailable" height="h-96">
            <WeatherRiskPanel weather={forecast} risks={weather.data?.risk_register ?? []} />
          </SegmentSlot>
          <SegmentSlot state={shell} title="Championship standings unavailable" height="h-96">
            <ChampionshipControlPanel championship={shell.data?.championship} />
          </SegmentSlot>
        </div>

        <div className="flex flex-col gap-5 xl:flex-row [&>*]:min-w-0 [&>*]:flex-1">
          <SegmentSlot state={strategy} title="Call sheet unavailable" height="h-96">
            <CallSheetPanel context={context} />
          </SegmentSlot>
          <SegmentSlot state={strategy} title="Stint plan unavailable" height="h-96">
            <StintPlanPanel context={context} />
          </SegmentSlot>
        </div>

        <SegmentSlot state={strategy} title="Competitor matrix unavailable" height="h-72">
          <CompetitorMatrixPanel context={context} />
        </SegmentSlot>
        <SegmentSlot state={strategy} title="Data assumptions unavailable" height="h-40">
          <DataAssumptionsPanel context={context} />
        </SegmentSlot>
      </div>
    </div>
  );
}

function ProjectedPodiumPanel({ podium }: { podium: NonNullable<Overview["predicted_podium"]> }) {
  return (
    <Panel className="p-5">
      <div className="mb-5 flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-400" style={rcFont}>
            Prediction snapshot
          </p>
          <h2 className="mt-1 text-xl font-semibold text-white" style={rcFont}>
            Projected Podium
          </h2>
        </div>
        <Trophy className="h-5 w-5 text-[#E10600]" />
      </div>
      <div className="space-y-2">
        {podium.length === 0 && (
          <p className="text-sm text-neutral-500">Prediction snapshot will populate when model inputs are available.</p>
        )}
        {podium.map((driver, index) => {
          const confidence = Math.round((driver.confidence_low + driver.confidence_high) / 2);
          return (
            <div
              key={driver.driver_code}
              className="flex items-center gap-3 rounded-lg bg-white/[0.035] border border-white/8 px-3 py-2.5"
            >
              <span className="w-8 text-sm font-semibold text-neutral-400" style={rcFont}>
                P{index + 1}
              </span>
              <div className="flex-1 min-w-0">
                <p className="truncate text-sm font-bold text-white">{driver.driver_name}</p>
                <p className="truncate text-xs text-neutral-500">{driver.team}</p>
              </div>
              <span className="text-sm font-mono text-[#00FF78]">{confidence}%</span>
            </div>
          );
        })}
      </div>
      <div className="mt-5 border-t border-white/10 pt-4">
        <Link
          href="/race-control/predictions"
          className="inline-flex w-full items-center justify-center gap-2 rounded-lg border border-[#00FF78]/35 bg-[#00FF78]/10 px-4 py-3 text-sm font-semibold uppercase tracking-wider text-[#00FF78] transition-colors hover:bg-[#00FF78] hover:text-black focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#00FF78]/60"
        >
          Open predictions
          <ArrowRight className="h-4 w-4" />
        </Link>
      </div>
    </Panel>
  );
}

function WeatherRiskPanel({
  weather,
  risks,
}: {
  weather: Overview["weather"];
  risks: NonNullable<Overview["risk_register"]>;
}) {
  const weatherLive = typeof weather?.rain_risk === "number";
  return (
    <Panel className="p-5">
      <div className="mb-5 flex items-center justify-between">
        <h2 className="text-xl font-semibold text-white" style={rcFont}>
          Weather & Risk
        </h2>
        <AlertTriangle className="h-5 w-5 text-[#FFF200]" />
      </div>
      {!weatherLive && (
        <div className="mb-3 flex items-center gap-2 rounded-lg border border-white/8 bg-white/[0.025] px-3 py-2">
          <span className="h-1.5 w-1.5 rounded-full bg-[#FFF200] shrink-0" />
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-neutral-500">
            {weather?.confidence ?? "Live forecast feed offline"}
          </p>
        </div>
      )}
      <div className="mb-5 flex flex-col gap-3 sm:flex-row [&>*]:flex-1">
        <AssumptionStat label="Rain" value={formatWeatherMetric(weather?.rain_risk, "%")} />
        <AssumptionStat label="Track" value={formatWeatherMetric(weather?.track_temp_c, "°C")} />
        <AssumptionStat label="Wind" value={formatWeatherMetric(weather?.wind_kph, " kph")} />
      </div>
      <div className="space-y-3">
        {risks.slice(0, 3).map((risk) => (
          <div key={risk.title} className="rounded-lg border border-white/8 bg-white/[0.03] p-3">
            <p className="text-sm font-bold text-white">{risk.title}</p>
            <p className="mt-1 text-xs text-neutral-500 leading-relaxed">{risk.detail}</p>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function ChampionshipControlPanel({ championship }: { championship: Overview["championship"] }) {
  const driverLeader = championship?.drivers?.[0];
  const constructorLeader = championship?.constructors?.[0];
  return (
    <Panel className="p-5">
      <h2 className="mb-5 text-xl font-semibold text-white" style={rcFont}>
        Championship Control
      </h2>
      <div className="flex flex-col gap-3">
        <LeaderCard label="Drivers" name={driverLeader?.driver ?? "No standings"} points={driverLeader?.points ?? 0} />
        <LeaderCard
          label="Constructors"
          name={constructorLeader?.team ?? "No standings"}
          points={constructorLeader?.points ?? 0}
        />
      </div>
    </Panel>
  );
}

function DataAssumptionsPanel({ context }: { context?: StrategyContext }) {
  const assumptions = context?.assumptions ?? [];
  return (
    <Panel className="p-5">
      <h2 className="mb-4 text-xl font-semibold text-white" style={rcFont}>
        Data Assumptions
      </h2>
      <div className="flex flex-col gap-3 md:flex-row md:flex-wrap [&>*]:min-w-[260px] [&>*]:flex-1">
        {assumptions.map((assumption) => (
          <div
            key={assumption}
            className="rounded-lg border border-white/8 bg-white/[0.03] px-3 py-2 text-sm leading-relaxed text-neutral-400"
          >
            {assumption}
          </div>
        ))}
      </div>
    </Panel>
  );
}

function LeaderCard({ label, name, points }: { label: string; name: string; points: number }) {
  return (
    <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3">
      <p className="text-[10px] font-black uppercase tracking-[0.14em] text-neutral-500">{label}</p>
      <p className="mt-1 truncate text-base font-bold text-white">{name}</p>
      <p className="mt-1 text-sm text-neutral-500">{points} pts</p>
    </div>
  );
}
