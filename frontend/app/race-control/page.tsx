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
  type RaceEvent,
  type StrategyContext,
} from "./components/CommandCenterPanels";
import { MetricCard, MetricRow, PageLoader, Panel, SectionHeader, rcFont } from "./components/RaceControlPrimitives";

const year = new Date().getFullYear();

function CommandCenterLoading() {
  return (
    <div>
      <SectionHeader
        eyebrow="Race Weekend Command Center"
        title="Command Center"
        description="Loading race context, championship pressure, strategy assumptions, and decision gates."
      />
      <PageLoader
        title="Preparing command center"
        detail="Loading the race weekend picture, strategy assumptions, competitor threat matrix, and prediction snapshot."
      />
    </div>
  );
}

interface CommandMetricsProps {
  race: RaceEvent | null | undefined;
  context: StrategyContext | undefined;
  weather: Overview["weather"];
  focus: string | undefined;
}

function CommandMetrics({ race, context, weather, focus }: CommandMetricsProps) {
  const weatherLive = typeof weather?.rain_risk === "number";
  const weekendSub = race ? `${race.status} · ${race.location}` : "Awaiting schedule";
  const pitValue = context ? `${context.pit_model.pit_loss_seconds}s` : "No model";
  const pitSub = context
    ? `Undercut ${context.pit_model.undercut_delta}s · overcut ${context.pit_model.overcut_delta}s${context.pit_model.undercut_modeled ? " · modeled" : ""}`
    : "Baseline model unavailable";
  const rainSub = weather?.confidence ?? (weatherLive ? "Live forecast" : "Live feed offline");

  return (
    <MetricRow>
      <MetricCard label="Weekend state" value={context?.phase ?? focus ?? "Pre-race"} sub={weekendSub} icon={Target} />
      <MetricCard
        label="Circuit profile"
        value={race?.circuit?.circuit_name ?? race?.location ?? "No circuit"}
        sub={formatCircuitDetail(race)}
        icon={CalendarClock}
        color="#FF8000"
      />
      <MetricCard label="Pit lane delta" value={pitValue} sub={pitSub} icon={Timer} color="#3671C6" />
      <MetricCard
        label="Rain risk"
        value={formatWeatherMetric(weather?.rain_risk, "%")}
        sub={rainSub}
        icon={CloudRain}
        color="#BE3AFF"
      />
    </MetricRow>
  );
}

export default function RaceControlHome() {
  const { data, isLoading } = useSWR<Overview>(`${API_BASE}/api/race-control/overview/${year}`, fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 120000,
  });

  if (isLoading) return <CommandCenterLoading />;

  return <CommandCenterView data={data} />;
}

function CommandCenterView({ data }: { data?: Overview }) {
  const race = data?.race;
  const context = data?.strategy_context;
  const sessions = race ? Object.entries(race.sessions).slice(0, 5) : [];
  const weather = data?.weather;

  return (
    <div>
      <SectionHeader
        eyebrow="Race Weekend Command Center"
        title={race?.name ?? "Command Center"}
        description="Pre-race operating view for session timing, baseline strategy, competitor threats, and open assumptions."
      />

      <CommandMetrics race={race} context={context} weather={weather} focus={data?.focus} />

      <div className="space-y-5">
        <BaselineStrategyPanel context={context} race={race} sessions={sessions} />

        <div className="flex flex-col gap-5 xl:flex-row [&>*]:min-w-0 [&>*]:flex-1">
          <ProjectedPodiumPanel podium={data?.predicted_podium ?? []} />
          <WeatherRiskPanel weather={weather} risks={data?.risk_register ?? []} />
          <ChampionshipControlPanel championship={data?.championship} />
        </div>

        <div className="flex flex-col gap-5 xl:flex-row [&>*]:min-w-0 [&>*]:flex-1">
          <CallSheetPanel context={context} />
          <StintPlanPanel context={context} />
        </div>

        <CompetitorMatrixPanel context={context} />
        <DataAssumptionsPanel context={context} />
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
