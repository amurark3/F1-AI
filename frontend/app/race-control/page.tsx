"use client";

import Link from "next/link";
import useSWR from "swr";
import {
  AlertTriangle,
  ArrowRight,
  CalendarClock,
  CloudRain,
  Gauge,
  Target,
  Timer,
  Trophy,
  Users,
} from "lucide-react";
import { API_BASE } from "@/app/constants/api";
import { fetcher } from "@/app/utils/fetcher";
import { MetricCard, MetricRow, PageLoader, Panel, SectionHeader, StatusPill, rcFont } from "./components/RaceControlPrimitives";

interface RaceEvent {
  round: number;
  name: string;
  location: string;
  status: string;
  sessions: Record<string, string>;
  is_sprint: boolean;
  circuit?: { circuit_name: string; laps: number; circuit_type: string } | null;
}

interface StrategyContext {
  phase: string;
  primary_call: { title: string; summary: string; confidence: string };
  decision_gates: Array<{ gate: string; trigger: string; owner: string; decision: string }>;
  stint_plan: Array<{ stint: string; compound: string; window: string; target: string }>;
  pit_model: { pit_loss_seconds: number; undercut_delta: number; overcut_delta: number; traffic_threshold: string };
  competitors: Array<{ rank: number; team: string; points: number; gap_to_leader: number; threat: string; operating_read: string }>;
  assumptions: string[];
}

interface Overview {
  focus?: string;
  race?: RaceEvent | null;
  season?: { total_events: number; completed_events: number; upcoming_events: number };
  championship?: {
    drivers: Array<{ position: number; driver: string; team: string; points: number }>;
    constructors: Array<{ position: number; team: string; points: number }>;
  };
  predicted_podium?: Array<{ driver_code: string; driver_name: string; team: string; confidence_low: number; confidence_high: number }>;
  strategy_context?: StrategyContext;
  weather?: { rain_risk: number | null; track_temp_c: number | null; wind_kph: number | null; confidence: string };
  live_status?: { connected: boolean; label: string };
  risk_register?: Array<{ level: string; title: string; detail: string }>;
}

const year = new Date().getFullYear();

const formatDate = (value?: string) => {
  if (!value) return "No date";
  return new Intl.DateTimeFormat("en-US", { weekday: "short", month: "short", day: "numeric" }).format(new Date(value));
};

const formatTime = (value?: string) => {
  if (!value) return "No time";
  return new Intl.DateTimeFormat("en-US", { hour: "2-digit", minute: "2-digit", timeZoneName: "short" }).format(new Date(value));
};

const localTimeZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone || "browser local time";

const HISTORICAL_WEATHER: Record<string, { rain_risk: number; track_temp_c: number; wind_kph: number }> = {
  street: { rain_risk: 32, track_temp_c: 30, wind_kph: 14 },
  high_speed: { rain_risk: 14, track_temp_c: 44, wind_kph: 11 },
  mixed: { rain_risk: 20, track_temp_c: 37, wind_kph: 13 },
};

function getHistoricalWeather(circuitType?: string | null) {
  if (!circuitType) return HISTORICAL_WEATHER.mixed;
  const key = circuitType.toLowerCase().replace(/[\s-]+/g, "_");
  return HISTORICAL_WEATHER[key] ?? HISTORICAL_WEATHER.mixed;
}

const formatWeatherCardValue = (value: number, fallback?: boolean) => {
  return fallback ? `~${Math.round(value)}%` : `${Math.round(value)}%`;
};

const formatCircuitDetail = (race?: RaceEvent | null) => {
  if (!race?.circuit) return race?.location ?? "Circuit feed unavailable";
  return `${race.circuit.laps} laps · ${race.circuit.circuit_type}`;
};

export default function RaceControlHome() {
  const { data, isLoading } = useSWR<Overview>(
    `${API_BASE}/api/race-control/overview/${year}`,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 120000 }
  );

  const race = data?.race;
  const context = data?.strategy_context;
  const sessions = race ? Object.entries(race.sessions).slice(0, 5) : [];
  const driverLeader = data?.championship?.drivers?.[0];
  const constructorLeader = data?.championship?.constructors?.[0];
  const podium = data?.predicted_podium ?? [];
  const weatherLive = typeof data?.weather?.rain_risk === "number";
  const histWeather = getHistoricalWeather(race?.circuit?.circuit_type);
  const effectiveWeather = weatherLive
    ? { rain_risk: data!.weather!.rain_risk as number, track_temp_c: data!.weather!.track_temp_c as number, wind_kph: data!.weather!.wind_kph as number }
    : histWeather;

  if (isLoading) {
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

  return (
    <div>
      <SectionHeader
        eyebrow="Race Weekend Command Center"
        title={race?.name ?? "Command Center"}
        description="Pre-race operating view for session timing, baseline strategy, competitor threats, and open assumptions."
      />

      <MetricRow>
        <MetricCard label="Weekend state" value={context?.phase ?? data?.focus ?? "Pre-race"} sub={race ? `${race.status} · ${race.location}` : "Awaiting schedule"} icon={Target} />
        <MetricCard label="Circuit profile" value={race?.circuit?.circuit_name ?? race?.location ?? "No circuit"} sub={formatCircuitDetail(race)} icon={CalendarClock} color="#FF8000" />
        <MetricCard label="Pit lane delta" value={context ? `${context.pit_model.pit_loss_seconds}s` : "No model"} sub={context ? `Undercut ${context.pit_model.undercut_delta}s · overcut ${context.pit_model.overcut_delta}s` : "Baseline model unavailable"} icon={Timer} color="#3671C6" />
        <MetricCard
          label="Rain risk"
          value={formatWeatherCardValue(effectiveWeather.rain_risk, !weatherLive)}
          sub={weatherLive ? (data?.weather?.confidence ?? "Live forecast") : `Historical avg · ${race?.circuit?.circuit_type ?? "mixed"} circuit`}
          icon={CloudRain}
          color="#BE3AFF"
        />
      </MetricRow>

      <div className="space-y-5">
        <Panel className="p-6" accent="#00FF78">
          <div className="flex flex-col gap-6 xl:flex-row xl:items-start">
            <div className="min-w-0 flex-1">
              <div className="mb-5 flex items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-400" style={rcFont}>Baseline strategy</p>
                  <h2 className="mt-1 text-2xl font-semibold text-white" style={rcFont}>{context?.primary_call.title ?? "Base race plan"}</h2>
                </div>
                <StatusPill color={context?.primary_call.confidence === "medium" ? "#FFF200" : "#3671C6"}>
                  {context?.primary_call.confidence ?? "draft"}
                </StatusPill>
              </div>
              <p className="max-w-4xl text-base leading-relaxed text-neutral-300">
                {context?.primary_call.summary ?? "Strategy context will populate when the next race and prediction snapshot are available."}
              </p>

              <div className="mt-6 flex flex-col gap-3 sm:flex-row [&>*]:flex-1">
                <AssumptionStat label="Undercut" value={context ? `${context.pit_model.undercut_delta}s` : "No model"} />
                <AssumptionStat label="Overcut" value={context ? `${context.pit_model.overcut_delta}s` : "No model"} />
                <AssumptionStat label="Traffic" value={context?.pit_model.traffic_threshold ?? "No model"} />
              </div>
            </div>

            <div className="min-w-0 rounded-lg border border-white/10 bg-black/20 p-5 xl:w-[460px] xl:shrink-0">
              <div className="mb-4 flex items-center justify-between">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-400" style={rcFont}>Race weekend clock</p>
                  <p className="mt-1 text-[11px] text-neutral-500">UTC race calendar, shown in {localTimeZone()}.</p>
                </div>
                <StatusPill>{race?.status ?? "No event"}</StatusPill>
              </div>
              <div className="flex min-w-0 flex-col gap-3 sm:flex-row sm:flex-wrap [&>*]:min-w-[140px] [&>*]:flex-1">
                {sessions.length > 0 ? sessions.map(([name, time]) => (
                  <div key={name} className="rounded border border-white/8 bg-white/[0.03] p-3">
                    <p className="text-[10px] font-semibold uppercase tracking-wider text-neutral-500">{name}</p>
                    <p className="mt-2 text-sm font-bold text-white">{formatDate(time)}</p>
                    <p className="mt-1 font-mono text-xs text-neutral-500">{formatTime(time)}</p>
                  </div>
                )) : (
                  <p className="text-sm text-neutral-500">Session timeline will populate once schedule data is available.</p>
                )}
              </div>
            </div>
          </div>
        </Panel>

        <div className="flex flex-col gap-5 xl:flex-row [&>*]:min-w-0 [&>*]:flex-1">
          <Panel className="p-5">
            <div className="mb-5 flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-400" style={rcFont}>Prediction snapshot</p>
                <h2 className="mt-1 text-xl font-semibold text-white" style={rcFont}>Projected Podium</h2>
              </div>
              <Trophy className="h-5 w-5 text-[#E10600]" />
            </div>
            <div className="space-y-2">
              {podium.length > 0 ? podium.map((driver, index) => {
                const confidence = Math.round((driver.confidence_low + driver.confidence_high) / 2);
                return (
                  <div key={driver.driver_code} className="flex items-center gap-3 rounded-lg bg-white/[0.035] border border-white/8 px-3 py-2.5">
                    <span className="w-8 text-sm font-semibold text-neutral-400" style={rcFont}>P{index + 1}</span>
                    <div className="flex-1 min-w-0">
                      <p className="truncate text-sm font-bold text-white">{driver.driver_name}</p>
                      <p className="truncate text-xs text-neutral-500">{driver.team}</p>
                    </div>
                    <span className="text-sm font-mono text-[#00FF78]">{confidence}%</span>
                  </div>
                );
              }) : (
                <p className="text-sm text-neutral-500">Prediction snapshot will populate when model inputs are available.</p>
              )}
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

          <Panel className="p-5">
            <div className="mb-5 flex items-center justify-between">
              <h2 className="text-xl font-semibold text-white" style={rcFont}>Weather & Risk</h2>
              <AlertTriangle className="h-5 w-5 text-[#FFF200]" />
            </div>
            {!weatherLive && (
              <div className="mb-3 flex items-center gap-2 rounded-lg border border-white/8 bg-white/[0.025] px-3 py-2">
                <span className="h-1.5 w-1.5 rounded-full bg-[#FFF200] shrink-0" />
                <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-neutral-500">Historical averages · live feed offline · values marked ~</p>
              </div>
            )}
            <div className="mb-5 flex flex-col gap-3 sm:flex-row [&>*]:flex-1">
              <AssumptionStat label="Rain" value={formatWeatherCardValue(effectiveWeather.rain_risk, !weatherLive)} />
              <AssumptionStat label="Track" value={!weatherLive ? `~${Math.round(effectiveWeather.track_temp_c)}°C` : `${Math.round(effectiveWeather.track_temp_c)}°C`} />
              <AssumptionStat label="Wind" value={!weatherLive ? `~${Math.round(effectiveWeather.wind_kph)} kph` : `${Math.round(effectiveWeather.wind_kph)} kph`} />
            </div>
            <div className="space-y-3">
              {(data?.risk_register ?? []).slice(0, 3).map((risk) => (
                <div key={risk.title} className="rounded-lg border border-white/8 bg-white/[0.03] p-3">
                  <p className="text-sm font-bold text-white">{risk.title}</p>
                  <p className="mt-1 text-xs text-neutral-500 leading-relaxed">{risk.detail}</p>
                </div>
              ))}
            </div>
          </Panel>

          <Panel className="p-5">
            <h2 className="mb-5 text-xl font-semibold text-white" style={rcFont}>Championship Control</h2>
            <div className="flex flex-col gap-3">
              <LeaderCard label="Drivers" name={driverLeader?.driver ?? "No standings"} points={driverLeader?.points ?? 0} />
              <LeaderCard label="Constructors" name={constructorLeader?.team ?? "No standings"} points={constructorLeader?.points ?? 0} />
            </div>
          </Panel>
        </div>

        <div className="flex flex-col gap-5 xl:flex-row [&>*]:min-w-0 [&>*]:flex-1">
          <Panel className="p-6">
            <div className="mb-5 flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-400" style={rcFont}>Decision gates</p>
                <h2 className="mt-1 text-xl font-semibold text-white" style={rcFont}>Call Sheet</h2>
              </div>
              <Gauge className="h-5 w-5 text-[#00FF78]" />
            </div>
            <div className="space-y-3">
              {(context?.decision_gates ?? []).map((gate) => (
                <div key={gate.gate} className="flex flex-col gap-3 rounded-lg border border-white/10 bg-white/[0.03] p-4 md:flex-row">
                  <div className="md:w-[150px] md:shrink-0">
                    <p className="text-sm font-bold text-white">{gate.gate}</p>
                    <p className="mt-1 text-xs text-[#00FF78]">{gate.trigger}</p>
                    <p className="text-xs text-neutral-500">{gate.owner}</p>
                  </div>
                  <p className="text-sm leading-relaxed text-neutral-300">{gate.decision}</p>
                </div>
              ))}
            </div>
          </Panel>

          <Panel className="p-6">
            <div className="mb-5 flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-400" style={rcFont}>Stint plan</p>
                <h2 className="mt-1 text-xl font-semibold text-white" style={rcFont}>Base Race Branch</h2>
              </div>
              <Timer className="h-5 w-5 text-[#FF8000]" />
            </div>
            <div className="overflow-x-auto rounded-lg border border-white/10">
              <table className="min-w-[720px] w-full text-left text-sm">
                <thead className="bg-white/[0.04] text-xs uppercase tracking-[0.12em] text-neutral-500">
                  <tr>
                    <th className="px-3 py-2">Stint</th>
                    <th className="px-3 py-2">Tyre</th>
                    <th className="px-3 py-2">Window</th>
                    <th className="px-3 py-2">Target</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/8">
                  {(context?.stint_plan ?? []).map((stint) => (
                    <tr key={stint.stint} className="bg-white/[0.02]">
                      <td className="px-3 py-3 font-bold text-white">{stint.stint}</td>
                      <td className="px-3 py-3 text-neutral-300">{stint.compound}</td>
                      <td className="px-3 py-3 font-mono text-[#00FF78]">{stint.window}</td>
                      <td className="px-3 py-3 text-neutral-400">{stint.target}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
        </div>

        <Panel className="p-6">
          <div className="mb-5 flex items-center justify-between">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-400" style={rcFont}>Competitor matrix</p>
              <h2 className="mt-1 text-xl font-semibold text-white" style={rcFont}>Constructor Threats</h2>
            </div>
            <Users className="h-5 w-5 text-[#3671C6]" />
          </div>
          <div className="overflow-x-auto rounded-lg border border-white/10">
            <table className="min-w-[860px] w-full text-left text-sm">
              <thead className="bg-white/[0.04] text-xs uppercase tracking-[0.12em] text-neutral-500">
                <tr>
                  <th className="px-3 py-2">Team</th>
                  <th className="px-3 py-2">Pts</th>
                  <th className="px-3 py-2">Gap</th>
                  <th className="px-3 py-2">Threat</th>
                  <th className="px-3 py-2">Operating Read</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/8">
                {(context?.competitors ?? []).map((team) => (
                  <tr key={team.team} className="bg-white/[0.02]">
                    <td className="px-3 py-3 font-bold text-white">P{team.rank} · {team.team}</td>
                    <td className="px-3 py-3 font-mono text-neutral-300">{team.points}</td>
                    <td className="px-3 py-3 font-mono text-neutral-400">{team.gap_to_leader}</td>
                    <td className="px-3 py-3"><StatusPill color={team.threat === "Primary" ? "#E10600" : team.threat === "High" ? "#FFF200" : "#3671C6"}>{team.threat}</StatusPill></td>
                    <td className="px-3 py-3 text-neutral-400">{team.operating_read}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>

        <Panel className="p-5">
          <h2 className="mb-4 text-xl font-semibold text-white" style={rcFont}>Data Assumptions</h2>
          <div className="flex flex-col gap-3 md:flex-row md:flex-wrap [&>*]:min-w-[260px] [&>*]:flex-1">
            {(context?.assumptions ?? []).map((assumption) => (
              <div key={assumption} className="rounded-lg border border-white/8 bg-white/[0.03] px-3 py-2 text-sm leading-relaxed text-neutral-400">
                {assumption}
              </div>
            ))}
          </div>
        </Panel>
      </div>
    </div>
  );
}

function AssumptionStat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3">
      <p className="text-[10px] font-black uppercase tracking-[0.12em] text-neutral-500">{label}</p>
      <p className="mt-1 text-lg font-black text-white" style={rcFont}>{value}</p>
    </div>
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
