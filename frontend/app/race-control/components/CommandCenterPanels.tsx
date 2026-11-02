/**
 * Command-centre panel set: the overview's payload types and the strategy
 * baseline panels. The race-weekend showcase panels live in `../weekend`.
 *
 * No client boundary: these panels are pure functions of their props, so the
 * server renders them straight into the overview HTML.
 */
import { ShieldAlert } from "lucide-react";

import type { StandingsFreshness } from "@/app/lib/standingsFreshness";

import { Panel, StatusPill, rcFont } from "./RaceControlPrimitives";

import type { ChampionshipStakes, LapRecord, RiskCard, SessionWeather } from "../weekend/weekendTypes";

export interface RaceEvent {
  round: number;
  name: string;
  location: string;
  country?: string | null;
  status: string;
  sessions: Record<string, string>;
  is_sprint: boolean;
  circuit?: {
    circuit_name: string;
    laps: number;
    circuit_type: string;
    track_length_km?: number | null;
    first_gp?: number | null;
    lap_record?: LapRecord | null;
  } | null;
}

export interface StrategyContext {
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
  competitors: Array<{
    rank: number;
    team: string;
    points: number;
    gap_to_leader: number;
    threat: string;
    operating_read: string;
  }>;
  assumptions: string[];
}

/**
 * The command centre is served as five independently fetchable segments so the
 * page can render each as it arrives instead of waiting on the slowest one.
 */
export interface OverviewShell {
  focus?: string;
  race?: RaceEvent | null;
  season?: { total_events: number; completed_events: number; upcoming_events: number };
  championship?: StandingsFreshness & {
    drivers: Array<{ position: number; driver: string; team: string; points: number }>;
    constructors: Array<{ position: number; team: string; points: number }>;
  };
  stakes?: ChampionshipStakes;
  live_status?: { connected: boolean; label: string };
  error?: string | null;
}

export interface WeatherCard {
  rain_risk: number | null;
  track_temp_c: number | null;
  wind_kph: number | null;
  confidence: string;
}

export interface OverviewWeather {
  weather?: WeatherCard;
  session_weather?: SessionWeather;
  risk_register?: RiskCard[];
  error?: string | null;
}

export interface OverviewPredictions {
  predicted_podium?: Array<{
    driver_code: string;
    driver_name: string;
    team: string;
    confidence_low: number;
    confidence_high: number;
  }>;
  error?: string | null;
}

export interface OverviewStrategy {
  strategy_context?: StrategyContext;
  workstreams?: Array<{ id: string; title: string; owner: string; priority: string; status: string; href: string }>;
  error?: string | null;
}

const COMPOUND_COLORS: Record<string, string> = {
  SOFT: "#FF3B3B",
  MEDIUM: "#FFF200",
  HARD: "#EBEBEB",
  INTERMEDIATE: "#43B02A",
  WET: "#3671C6",
};

const compoundColor = (compound: string): string => COMPOUND_COLORS[compound.toUpperCase()] ?? "#8A93A6";

export function AssumptionStat({ label, value, note }: { label: string; value: string | number; note?: string }) {
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
      <p className="mt-1 text-lg font-black text-white" style={rcFont}>
        {value}
      </p>
    </div>
  );
}

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
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-neutral-500" style={rcFont}>
          Stint windows
        </p>
        {modeled && (
          <span className="rounded-sm bg-[#FFF200]/10 px-1.5 py-0.5 text-[9px] font-bold uppercase tracking-[0.1em] text-[#FFF200]">
            modeled
          </span>
        )}
        <span className="h-px flex-1 bg-white/10" />
      </div>

      {/* median first-stop flag */}
      <div className="relative mb-1.5 h-5">
        <div className="absolute -translate-x-1/2 whitespace-nowrap text-center" style={{ left: `${primaryPct}%` }}>
          <span className="rounded bg-white/10 px-1.5 py-0.5 font-mono text-[10px] font-bold text-white">
            L{primary_lap}
          </span>
        </div>
      </div>

      {/* compound bar with first-stop window band; each stint grows in from the start line */}
      <div className="relative h-12 w-full overflow-hidden rounded-lg border border-white/10 bg-white/[0.02]">
        <div
          className="absolute inset-y-0 left-0 origin-left motion-safe:animate-fill-x"
          style={{ width: `${primaryPct}%`, background: `${openingColor}1F` }}
        />
        <div
          className="absolute inset-y-0 right-0 origin-left motion-safe:animate-fill-x"
          style={{ left: `${primaryPct}%`, background: `${finishingColor}1F`, animationDelay: "0.5s" }}
        />
        <div
          className="absolute inset-y-0 border-x border-dashed border-white/25 bg-white/[0.06]"
          style={{ left: `${offsetPct}%`, width: `${Math.max(latePct - offsetPct, 0)}%` }}
        />
        <div className="absolute inset-y-0 w-[2px] bg-white/80" style={{ left: `${primaryPct}%` }} />
        <span
          className="absolute left-0 top-1/2 -translate-y-1/2 px-3 text-[11px] font-bold uppercase tracking-wide"
          style={{ color: openingColor }}
        >
          {opening_compound}
        </span>
        <span
          className="absolute right-0 top-1/2 -translate-y-1/2 px-3 text-[11px] font-bold uppercase tracking-wide"
          style={{ color: finishingColor }}
        >
          {finishing_compound}
        </span>
      </div>

      {/* lap axis */}
      <div className="mt-2 flex items-center justify-between font-mono text-[10px] text-neutral-500">
        <span>L1</span>
        <span className="text-neutral-400">
          First-stop window L{offset_lap}–L{late_lap}
        </span>
        <span>L{laps}</span>
      </div>
    </div>
  );
}

function StrategyDataSource({ source }: { source: NonNullable<StrategyContext["data_source"]> }) {
  const isTelemetry = source.mode === "telemetry";
  return (
    <div className="mt-4 flex items-center gap-2 rounded-lg border border-white/8 bg-white/[0.025] px-3 py-2">
      <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${isTelemetry ? "bg-[#00FF78]" : "bg-[#FFF200]"}`} />
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-neutral-500">
        {isTelemetry
          ? `Pit loss & tyre windows from ${source.edition_year} telemetry · ${source.sample_size} cars · undercut/overcut modeled`
          : "Planning heuristics · no completed edition available for telemetry"}
      </p>
    </div>
  );
}

function PitModelGrid({ context }: { context?: StrategyContext }) {
  const pit = context?.pit_model;
  return (
    <div className="mt-6 border-t border-white/8 pt-6">
      <div className="mb-3 flex items-center gap-3">
        <p className="text-[11px] font-semibold uppercase tracking-[0.14em] text-neutral-500" style={rcFont}>
          Pit model
        </p>
        <span className="h-px flex-1 bg-white/10" />
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <AssumptionStat label="Pit loss" value={pit ? `${pit.pit_loss_seconds}s` : "No model"} />
        <AssumptionStat
          label="Undercut"
          value={pit ? `${pit.undercut_delta}s` : "No model"}
          note={pit?.undercut_modeled ? "modeled" : undefined}
        />
        <AssumptionStat
          label="Overcut"
          value={pit ? `${pit.overcut_delta}s` : "No model"}
          note={pit?.overcut_modeled ? "modeled" : undefined}
        />
        <AssumptionStat
          label="Traffic"
          value={pit?.traffic_threshold ?? "No model"}
          note={pit?.traffic_modeled ? "modeled" : undefined}
        />
      </div>
    </div>
  );
}

export function BaselineStrategyPanel({ context }: { context: StrategyContext | undefined }) {
  const primaryCall = context?.primary_call;
  const confidence = primaryCall?.confidence;

  return (
    <Panel className="h-full p-6">
      <div className="-mx-6 -mt-6 mb-6 h-[2px] bg-[#00FF78]" />
      <div className="mb-5 flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-400" style={rcFont}>
            Baseline strategy
          </p>
          <h2 className="mt-1 text-2xl font-semibold text-white" style={rcFont}>
            {primaryCall?.title ?? "Base race plan"}
          </h2>
        </div>
        <StatusPill color={confidence === "medium" ? "#FFF200" : "#3671C6"}>{confidence ?? "draft"}</StatusPill>
      </div>
      <p className="max-w-4xl text-base leading-relaxed text-neutral-300">
        {primaryCall?.summary ??
          "Strategy context will populate when the next race and prediction snapshot are available."}
      </p>

      {context?.data_source && <StrategyDataSource source={context.data_source} />}

      {context?.stint_windows && (
        <div className="mt-6">
          <StintTimeline windows={context.stint_windows} />
        </div>
      )}

      <PitModelGrid context={context} />
    </Panel>
  );
}

const RISK_COLORS: Record<string, string> = { High: "#FF4655", Medium: "#FFF200", Low: "#00FF78" };

/** The risk register as short cards, graded from the race-day forecast and the standings. */
export function RiskRegisterPanel({ risks }: { risks: RiskCard[] }) {
  return (
    <Panel className="h-full p-5">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-neutral-400" style={rcFont}>
            Risk register
          </p>
          <h2 className="mt-1 text-xl font-semibold text-white" style={rcFont}>
            Weekend risks
          </h2>
        </div>
        <ShieldAlert className="h-5 w-5 text-[#FFF200]" aria-hidden="true" />
      </div>
      {risks.length === 0 && <p className="text-sm text-neutral-500">No risks graded for this weekend.</p>}
      <ul className="space-y-2.5">
        {risks.map((risk, index) => {
          const color = RISK_COLORS[risk.level] ?? "#7F8797";
          return (
            <li
              key={risk.title}
              className="rounded-lg border border-white/8 bg-white/[0.03] p-3 motion-safe:animate-fade-up"
              style={{ borderLeft: `3px solid ${color}`, animationDelay: `${index * 0.08}s` }}
            >
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-bold text-white">{risk.title}</p>
                <span className="font-mono text-[9px] font-bold uppercase tracking-[0.16em]" style={{ color }}>
                  {risk.level}
                </span>
              </div>
              <p className="mt-1 text-xs leading-relaxed text-neutral-500">{risk.detail}</p>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}
