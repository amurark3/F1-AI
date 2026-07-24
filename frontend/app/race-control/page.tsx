"use client";

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
import Link from "next/link";
import useSWR from "swr";

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
  data_source?: { mode: "telemetry" | "heuristic"; edition_year: number | null; sample_size: number | null };
  decision_gates: Array<{ gate: string; trigger: string; owner: string; decision: string }>;
  stint_plan: Array<{ stint: string; compound: string; window: string; target: string }>;
  pit_model: {
    pit_loss_seconds: number;
    undercut_delta: number;
    overcut_delta: number;
    undercut_modeled?: boolean;
    overcut_modeled?: boolean;
    traffic_threshold: string;
    traffic_modeled?: boolean;
  };
  stint_windows?: {
    total_laps: number;
    opening_compound: string;
    finishing_compound: string;
    offset_lap: number;
    primary_lap: number;
    late_lap: number;
    modeled?: boolean;
  };
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
  return new Intl.DateTimeFormat(undefined, { weekday: "short", month: "short", day: "numeric" }).format(new Date(value));
};

const formatTime = (value?: string) => {
  if (!value) return "No time";
  return new Intl.DateTimeFormat(undefined, { hour: "2-digit", minute: "2-digit", timeZoneName: "short" }).format(new Date(value));
};

const localTimeZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone || "browser local time";

const formatWeatherMetric = (value: number | null | undefined, unit: string) =>
  typeof value === "number" ? `${Math.round(value)}${unit}` : "—";

const formatCircuitDetail = (race?: RaceEvent | null) => {
  if (!race?.circuit) return race?.location ?? "Circuit feed unavailable";
  return `${race.circuit.laps} laps · ${race.circuit.circuit_type}`;
};

const THREAT_COLORS: Record<string, string> = {
  Primary: "#E10600",
  High: "#FFF200",
};
const threatColor = (threat: string): string => THREAT_COLORS[threat] ?? "#3671C6";

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
      <MetricCard label="Circuit profile" value={race?.circuit?.circuit_name ?? race?.location ?? "No circuit"} sub={formatCircuitDetail(race)} icon={CalendarClock} color="#FF8000" />
      <MetricCard label="Pit lane delta" value={pitValue} sub={pitSub} icon={Timer} color="#3671C6" />
      <MetricCard label="Rain risk" value={formatWeatherMetric(weather?.rain_risk, "%")} sub={rainSub} icon={CloudRain} color="#BE3AFF" />
    </MetricRow>
  );
}

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
  const weather = data?.weather;
  const weatherLive = typeof weather?.rain_risk === "number";

  if (isLoading) return <CommandCenterLoading />;

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
          <ProjectedPodiumPanel podium={podium} />
          <WeatherRiskPanel weather={weather} weatherLive={weatherLive} risks={data?.risk_register ?? []} />
          <ChampionshipControlPanel driverLeader={driverLeader} constructorLeader={constructorLeader} />
        </div>

        <div className="flex flex-col gap-5 xl:flex-row [&>*]:min-w-0 [&>*]:flex-1">
          <CallSheetPanel gates={context?.decision_gates ?? []} />
          <StintPlanPanel stints={context?.stint_plan ?? []} />
        </div>

        <CompetitorMatrixPanel competitors={context?.competitors ?? []} />
        <DataAssumptionsPanel assumptions={context?.assumptions ?? []} />
      </div>
    </div>
  );
}

function BaselineStrategyPanel({ context, race, sessions }: {
  context: StrategyContext | undefined;
  race: RaceEvent | null | undefined;
  sessions: Array<[string, string]>;
}) {
  return (
    <Panel className="p-6">
      <div className="-mx-6 -mt-6 mb-6 h-[2px] bg-[#00FF78]" />
      <div className="flex flex-col gap-6 xl:flex-row xl:items-stretch">
        <div className="flex min-w-0 flex-1 flex-col">
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

          {context?.data_source && (
            <div className="mt-4 flex items-center gap-2 rounded-lg border border-white/8 bg-white/[0.025] px-3 py-2">
              <span
                className={`h-1.5 w-1.5 shrink-0 rounded-full ${context.data_source.mode === "telemetry" ? "bg-[#00FF78]" : "bg-[#FFF200]"}`}
              />
              <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-neutral-500">
                {context.data_source.mode === "telemetry"
                  ? `Pit loss & tyre windows from ${context.data_source.edition_year} telemetry · ${context.data_source.sample_size} cars · undercut/overcut modeled`
                  : "Planning heuristics · no completed edition available for telemetry"}
              </p>
            </div>
          )}

          {context?.stint_windows && (
            <div className="mt-6 flex flex-1 flex-col justify-center">
              <StintTimeline windows={context.stint_windows} />
            </div>
          )}

          <div className="mt-6 pt-6 border-t border-white/8">
            <div className="mb-3 flex items-center gap-3">
              <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-neutral-500" style={rcFont}>Pit model</p>
              <span className="h-px flex-1 bg-white/10" />
            </div>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              <AssumptionStat label="Pit loss" value={context ? `${context.pit_model.pit_loss_seconds}s` : "No model"} />
              <AssumptionStat label="Undercut" value={context ? `${context.pit_model.undercut_delta}s` : "No model"} note={context?.pit_model.undercut_modeled ? "modeled" : undefined} />
              <AssumptionStat label="Overcut" value={context ? `${context.pit_model.overcut_delta}s` : "No model"} note={context?.pit_model.overcut_modeled ? "modeled" : undefined} />
              <AssumptionStat label="Traffic" value={context?.pit_model.traffic_threshold ?? "No model"} note={context?.pit_model.traffic_modeled ? "modeled" : undefined} />
            </div>
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
            {sessions.length === 0 && (
              <p className="text-sm text-neutral-500">Session timeline will populate once schedule data is available.</p>
            )}
            {sessions.map(([name, time]) => (
              <div key={name} className="rounded border border-white/8 bg-white/[0.03] p-3">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-neutral-500">{name}</p>
                <p className="mt-2 text-sm font-bold text-white">{formatDate(time)}</p>
                <p className="mt-1 font-mono text-xs text-neutral-500">{formatTime(time)}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </Panel>
  );
}

function ProjectedPodiumPanel({ podium }: { podium: NonNullable<Overview["predicted_podium"]> }) {
  return (
    <Panel className="p-5">
      <div className="mb-5 flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-400" style={rcFont}>Prediction snapshot</p>
          <h2 className="mt-1 text-xl font-semibold text-white" style={rcFont}>Projected Podium</h2>
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
            <div key={driver.driver_code} className="flex items-center gap-3 rounded-lg bg-white/[0.035] border border-white/8 px-3 py-2.5">
              <span className="w-8 text-sm font-semibold text-neutral-400" style={rcFont}>P{index + 1}</span>
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

function WeatherRiskPanel({ weather, weatherLive, risks }: {
  weather: Overview["weather"];
  weatherLive: boolean;
  risks: NonNullable<Overview["risk_register"]>;
}) {
  return (
    <Panel className="p-5">
      <div className="mb-5 flex items-center justify-between">
        <h2 className="text-xl font-semibold text-white" style={rcFont}>Weather & Risk</h2>
        <AlertTriangle className="h-5 w-5 text-[#FFF200]" />
      </div>
      {!weatherLive && (
        <div className="mb-3 flex items-center gap-2 rounded-lg border border-white/8 bg-white/[0.025] px-3 py-2">
          <span className="h-1.5 w-1.5 rounded-full bg-[#FFF200] shrink-0" />
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-neutral-500">{weather?.confidence ?? "Live forecast feed offline"}</p>
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

function ChampionshipControlPanel({ driverLeader, constructorLeader }: {
  driverLeader: NonNullable<Overview["championship"]>["drivers"][number] | undefined;
  constructorLeader: NonNullable<Overview["championship"]>["constructors"][number] | undefined;
}) {
  return (
    <Panel className="p-5">
      <h2 className="mb-5 text-xl font-semibold text-white" style={rcFont}>Championship Control</h2>
      <div className="flex flex-col gap-3">
        <LeaderCard label="Drivers" name={driverLeader?.driver ?? "No standings"} points={driverLeader?.points ?? 0} />
        <LeaderCard label="Constructors" name={constructorLeader?.team ?? "No standings"} points={constructorLeader?.points ?? 0} />
      </div>
    </Panel>
  );
}

function CallSheetPanel({ gates }: { gates: StrategyContext["decision_gates"] }) {
  return (
    <Panel className="p-6">
      <div className="mb-5 flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-400" style={rcFont}>Decision gates</p>
          <h2 className="mt-1 text-xl font-semibold text-white" style={rcFont}>Call Sheet</h2>
        </div>
        <Gauge className="h-5 w-5 text-[#00FF78]" />
      </div>
      <div className="space-y-3">
        {gates.map((gate) => (
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
  );
}

function StintPlanPanel({ stints }: { stints: StrategyContext["stint_plan"] }) {
  return (
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
            {stints.map((stint) => (
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
  );
}

function CompetitorMatrixPanel({ competitors }: { competitors: StrategyContext["competitors"] }) {
  return (
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
            {competitors.map((team) => (
              <tr key={team.team} className="bg-white/[0.02]">
                <td className="px-3 py-3 font-bold text-white">P{team.rank} · {team.team}</td>
                <td className="px-3 py-3 font-mono text-neutral-300">{team.points}</td>
                <td className="px-3 py-3 font-mono text-neutral-400">{team.gap_to_leader}</td>
                <td className="px-3 py-3"><StatusPill color={threatColor(team.threat)}>{team.threat}</StatusPill></td>
                <td className="px-3 py-3 text-neutral-400">{team.operating_read}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function DataAssumptionsPanel({ assumptions }: { assumptions: string[] }) {
  return (
    <Panel className="p-5">
      <h2 className="mb-4 text-xl font-semibold text-white" style={rcFont}>Data Assumptions</h2>
      <div className="flex flex-col gap-3 md:flex-row md:flex-wrap [&>*]:min-w-[260px] [&>*]:flex-1">
        {assumptions.map((assumption) => (
          <div key={assumption} className="rounded-lg border border-white/8 bg-white/[0.03] px-3 py-2 text-sm leading-relaxed text-neutral-400">
            {assumption}
          </div>
        ))}
      </div>
    </Panel>
  );
}

function AssumptionStat({ label, value, note }: { label: string; value: string | number; note?: string }) {
  return (
    <div className="rounded-lg border border-white/8 bg-white/[0.03] p-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-[10px] font-black uppercase tracking-[0.12em] text-neutral-500">{label}</p>
        {note && (
          <span className="rounded-sm bg-[#FFF200]/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-[0.1em] text-[#FFF200]">
            {note}
          </span>
        )}
      </div>
      <p className="mt-1 text-lg font-black text-white" style={rcFont}>{value}</p>
    </div>
  );
}

const COMPOUND_COLORS: Record<string, string> = {
  SOFT: "#FF3B3B",
  MEDIUM: "#FFF200",
  HARD: "#EBEBEB",
  INTERMEDIATE: "#43B02A",
  WET: "#3671C6",
};

const compoundColor = (compound: string): string =>
  COMPOUND_COLORS[compound.toUpperCase()] ?? "#8A93A6";

function StintTimeline({ windows }: { windows: NonNullable<StrategyContext["stint_windows"]> }) {
  const { total_laps, opening_compound, finishing_compound, offset_lap, primary_lap, late_lap, modeled } = windows;
  const laps = Math.max(total_laps, 1);
  const pct = (lap: number) => Math.min(100, Math.max(0, (lap / laps) * 100));
  const primaryPct = pct(primary_lap);
  const offsetPct = pct(offset_lap);
  const latePct = pct(late_lap);
  const openingColor = compoundColor(opening_compound);
  const finishingColor = compoundColor(finishing_compound);

  return (
    <div>
      <div className="mb-4 flex items-center gap-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-neutral-500" style={rcFont}>Stint windows</p>
        {modeled && (
          <span className="rounded-sm bg-[#FFF200]/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-[0.1em] text-[#FFF200]">modeled</span>
        )}
        <span className="h-px flex-1 bg-white/10" />
      </div>

      {/* median first-stop flag */}
      <div className="relative mb-1.5 h-5">
        <div className="absolute -translate-x-1/2 whitespace-nowrap text-center" style={{ left: `${primaryPct}%` }}>
          <span className="rounded bg-white/10 px-1.5 py-0.5 font-mono text-[10px] font-bold text-white">L{primary_lap}</span>
        </div>
      </div>

      {/* compound bar with first-stop window band */}
      <div className="relative h-12 w-full overflow-hidden rounded-lg border border-white/10 bg-white/[0.02]">
        <div className="absolute inset-y-0 left-0" style={{ width: `${primaryPct}%`, background: `${openingColor}1F` }} />
        <div className="absolute inset-y-0 right-0" style={{ left: `${primaryPct}%`, background: `${finishingColor}1F` }} />
        <div
          className="absolute inset-y-0 border-x border-dashed border-white/25 bg-white/[0.06]"
          style={{ left: `${offsetPct}%`, width: `${Math.max(latePct - offsetPct, 0)}%` }}
        />
        <div className="absolute inset-y-0 w-[2px] bg-white/80" style={{ left: `${primaryPct}%` }} />
        <span className="absolute left-0 top-1/2 -translate-y-1/2 px-3 text-[11px] font-bold uppercase tracking-wide" style={{ color: openingColor }}>{opening_compound}</span>
        <span className="absolute right-0 top-1/2 -translate-y-1/2 px-3 text-[11px] font-bold uppercase tracking-wide" style={{ color: finishingColor }}>{finishing_compound}</span>
      </div>

      {/* lap axis */}
      <div className="mt-2 flex items-center justify-between font-mono text-[10px] text-neutral-500">
        <span>L1</span>
        <span className="text-neutral-400">First-stop window L{offset_lap}–L{late_lap}</span>
        <span>L{laps}</span>
      </div>
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
