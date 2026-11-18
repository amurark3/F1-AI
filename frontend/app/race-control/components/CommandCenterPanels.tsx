/**
 * Command-centre panel set: the overview's payload types and the risk
 * register. The baseline strategy panel lives in `./BaselineStrategyPanel`,
 * the race-weekend showcase panels in `../weekend`.
 *
 * No client boundary: these panels are pure functions of their props, so the
 * server renders them straight into the overview HTML.
 */
import type { StandingsFreshness } from "@/app/lib/standingsFreshness";
import { PanelHeading } from "@/app/ui/PanelHeading";
import { f1, rc } from "@/app/ui/tokens";

import { Panel } from "./RaceControlPrimitives";

import type { ChampionshipStakes, LapRecord, RiskCard, RiskLevel, SessionWeather } from "../weekend/weekendTypes";

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

/** How far the baseline plan can be trusted: the sample and the edition's age and rules. */
export type PlanConfidence = "high" | "medium" | "low";

/** One stint of the headline sequence, on the edition's own laps. */
export interface PlanStint {
  compound: string;
  start_lap: number;
  end_lap: number;
}

/** The compound sequence most of the edition's finishers ran, drawn on its median stop laps. */
export interface StrategyPlan {
  /** Every compound in order, middle stints included: "Medium", "Soft", "Medium". */
  compounds: string[];
  stops: number;
  /** The finishers who ran it, in finishing order. */
  drivers: string[];
  finishers: number;
  total_laps: number;
  /** Empty when a set was changed under a red flag, so there is no stop lap to split on. */
  stints: PlanStint[];
}

/** Where the plan came from. `mode` is "edition" with a plan, "none" without one. */
export interface StrategySource {
  mode: "edition" | "none";
  edition_year: number | null;
  event_name?: string | null;
  previous_regulations?: boolean;
  /** Classified finishers in the sample. */
  sample_size: number | null;
  sources?: string[];
  /** Newer editions that could not be read right now. */
  unread_years?: number[];
}

/**
 * The baseline strategy segment's context. Every figure is measured from the
 * latest same-circuit edition; nothing is modelled (no undercut, overcut or
 * traffic). Fields added in P0b.4 are optional so an older backend still reads.
 */
export interface StrategyContext {
  primary_call: {
    title: string;
    summary: string;
    confidence: PlanConfidence | null;
    confidence_basis?: string | null;
  };
  data_source?: StrategySource;
  plan?: StrategyPlan | null;
  alternatives?: Array<{ compounds: string[]; stops: number; drivers: number }>;
  stop_counts?: Array<{ stops: number; drivers: number }>;
  first_stop?: { median_lap: number; p25_lap: number; p75_lap: number; drivers: number } | null;
  pit_model?: { pit_lane_seconds: number | null; pit_lane_stops: number | null };
  /** Set when the race-day forecast makes this dry plan the secondary branch. */
  rain_branch?: { rain_pct: number; threshold_pct: number; note: string } | null;
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

const RISK_STYLE: Record<RiskLevel, { rule: string; text: string }> = {
  High: { rule: f1.red, text: "text-rc-red-text" },
  Medium: { rule: rc.ink2, text: "text-rc-ink-2" },
  Low: { rule: rc.line, text: "text-rc-ink-3" },
};

/** The risk register as short cards, graded from the race-day forecast and the standings. */
export function RiskRegisterPanel({ risks }: { risks: RiskCard[] }) {
  return (
    <Panel className="h-full p-5 sm:p-6">
      <PanelHeading as="h2" eyebrow="Risk register" title="Weekend risks" />
      {risks.length === 0 && <p className="text-sm text-rc-ink-3">No risks graded for this weekend.</p>}
      <ul className="space-y-2.5">
        {risks.map((risk, index) => {
          const style = RISK_STYLE[risk.level];
          return (
            <li
              key={risk.title}
              className="rounded border border-l-[3px] border-rc-line px-3.5 py-3 motion-safe:animate-fade-up"
              style={{ borderLeftColor: style.rule, animationDelay: `${index * 0.08}s` }}
            >
              <div className="flex items-center justify-between gap-2">
                <p className="text-sm font-semibold text-rc-ink">{risk.title}</p>
                <span className={`font-mono text-[9px] font-semibold uppercase tracking-[0.16em] ${style.text}`}>
                  {risk.level}
                </span>
              </div>
              <p className="mt-1 text-xs leading-relaxed text-rc-ink-3">{risk.detail}</p>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}
