"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import { BarChart3, Gauge, Target, Trophy } from "lucide-react";
import { type DriverPrediction } from "@/app/components/PredictionDriverCard";
import { API_BASE } from "@/app/constants/api";
import { fetcher } from "@/app/utils/fetcher";
import { MetricCard, MetricRow, PageLoader, Panel, SectionHeader } from "../components/RaceControlPrimitives";
import { RacePredictionBoard } from "./RacePredictionBoard";
import { SeasonForecastBoard } from "./SeasonForecastBoard";
import {
  ChampionshipScenarioBoard,
  buildScenarioRows,
  buildScenarioPreset,
  scenarioSlotGroup,
  RACE_POINT_SLOTS,
  SPRINT_POINT_SLOTS,
  type ScenarioPicks,
  type ScenarioPreset,
  type PointsSlotKey,
} from "./ChampionshipScenarioBoard";

interface RaceEvent {
  round: number;
  name: string;
  location: string;
  status: string;
  is_sprint?: boolean;
}

interface DriverStanding {
  code: string;
  name: string;
  team: string;
  position: number;
  points: number;
  wins: number;
}

interface DriversResponse {
  drivers: DriverStanding[];
  error?: string | null;
}

interface ForecastResponse {
  year: number;
  completed_events: number;
  remaining_events: number;
  recent_window: number;
  drivers: Array<{ key: string; code?: string | null; name: string; team: string; current_position: number; projected_position: number; position_delta: number; current_points: number; projected_points: number; wins: number; season_points_per_event: number; recent_points_per_event: number; trend: string; confidence: string }>;
  constructors: Array<{ key: string; code?: string | null; name: string; team: string; current_position: number; projected_position: number; position_delta: number; current_points: number; projected_points: number; wins: number; season_points_per_event: number; recent_points_per_event: number; trend: string; confidence: string }>;
  notes?: string[];
  error?: string | null;
}

interface PredictionsResponse {
  year: number;
  round: number;
  grand_prix?: string;
  predictions: DriverPrediction[];
  accuracy?: { recent_top3_pct?: number; races_evaluated: number };
  error?: string;
  warnings?: string[];
  data_sources?: string[];
  model_summary?: { leader?: string | null; leader_code?: string | null; average_top3_confidence?: number | null; source_count?: number; status?: string; snapshot_policy?: string };
  model_inputs?: Array<{ label: string; status: string; impact: string; source: string }>;
  model_limitations?: string[];
  cache?: { status: "hit" | "stored"; stored_at?: string | null; valid_until?: string | null; policy?: string };
}

type LabMode = "race" | "season" | "scenario";

const year = new Date().getFullYear();

function pointsLabel(points: number) {
  return Number.isInteger(points) ? String(points) : points.toFixed(1);
}

function modeTitle(mode: LabMode) {
  if (mode === "race") return "Race Forecast";
  if (mode === "season") return "Season Forecast";
  return "What-If Scenario";
}

export default function RaceControlPredictionsPage() {
  const [mode, setMode] = useState<LabMode>("race");
  const [selectedRound, setSelectedRound] = useState<number | null>(null);
  const [requested, setRequested] = useState(false);
  const [scenarioPicks, setScenarioPicks] = useState<ScenarioPicks>({});

  const { data: scheduleResponse, error: scheduleError, isLoading: scheduleLoading, mutate: reloadSchedule } = useSWR<RaceEvent[] | { error: string }>(
    `${API_BASE}/api/schedule/${year}`, fetcher, { revalidateOnFocus: false, dedupingInterval: 300000 }
  );

  const { data: driversData, error: driversError, isLoading: driversLoading, mutate: reloadDrivers } = useSWR<DriversResponse>(
    `${API_BASE}/api/race-control/drivers/${year}`, fetcher, { revalidateOnFocus: false, dedupingInterval: 180000 }
  );

  const schedule = useMemo(() => Array.isArray(scheduleResponse) ? scheduleResponse : [], [scheduleResponse]);
  const defaultRace = useMemo(() => {
    if (!schedule.length) return null;
    return schedule.find((r) => r.status === "upcoming" || r.status === "next")
      ?? [...schedule].reverse().find((r) => r.status === "completed")
      ?? schedule[0];
  }, [schedule]);

  const effectiveRound = selectedRound ?? defaultRace?.round ?? null;
  const selectedRace = schedule.find((r) => r.round === effectiveRound) ?? defaultRace;

  const { data, error: predictionError, isLoading: predictionLoading, mutate: reloadPrediction } = useSWR<PredictionsResponse>(
    requested && effectiveRound ? `${API_BASE}/api/predictions/${year}/${effectiveRound}` : null,
    fetcher, { revalidateOnFocus: false, dedupingInterval: 60000 }
  );

  const { data: forecastData, error: forecastError, isLoading: forecastLoading, mutate: reloadForecast } = useSWR<ForecastResponse>(
    mode === "season" ? `${API_BASE}/api/race-control/forecast/${year}` : null,
    fetcher, { revalidateOnFocus: false, dedupingInterval: 180000 }
  );

  const predictions = data?.predictions ?? [];
  const podium = predictions.slice(0, 3);
  const leader = predictions[0];
  const raceName = data?.grand_prix ?? selectedRace?.name ?? "Select A Race";
  const backendError = data?.error && predictions.length === 0 ? data.error : null;
  const drivers = driversData?.drivers ?? [];
  const upcomingRaces = schedule.filter((r) => r.status !== "completed");
  const scenarioRows = buildScenarioRows(drivers, upcomingRaces, scenarioPicks);
  const scenarioLeader = scenarioRows[0];
  const currentLeader = drivers[0];
  const aliveCount = scenarioRows.filter((r) => r.titleState !== "out").length;
  const pageLoading = (scheduleLoading && schedule.length === 0) || (driversLoading && drivers.length === 0);

  const handleSetPick = (round: number, slot: PointsSlotKey, code: string) => {
    setScenarioPicks((current) => {
      const nextRace = { ...(current[round] ?? {}) };
      const slotGroup = scenarioSlotGroup(slot);
      for (const s of [...RACE_POINT_SLOTS, ...SPRINT_POINT_SLOTS]) {
        if (s.event === slotGroup && s.key !== slot && code && nextRace[s.key] === code) {
          delete nextRace[s.key];
        }
      }
      if (code) { nextRace[slot] = code; } else { delete nextRace[slot]; }
      return { ...current, [round]: nextRace };
    });
  };

  if (pageLoading) {
    return (
      <div>
        <SectionHeader eyebrow="Forecast Center" title={modeTitle(mode)} description="Race forecasts, season championship projections, and manual what-if scenarios." />
        <PageLoader title="Preparing prediction lab" detail="Loading the race calendar and championship table before the forecast tools open." />
      </div>
    );
  }

  return (
    <div>
      <SectionHeader eyebrow="Forecast Center" title={modeTitle(mode)} description="Race forecasts, season championship projections, and manual what-if scenarios in one strategy workspace." />

      <MetricRow>
        <MetricCard label="Current Leader" value={currentLeader?.name ?? "No standings"} sub={currentLeader ? `${currentLeader.team} · ${pointsLabel(currentLeader.points)} pts` : "Standings unavailable"} icon={Trophy} />
        <MetricCard label="Race Call" value={leader ? (leader.driver_name ?? leader.driver_code) : "Not loaded"} sub={leader ? `${leader.team} win forecast` : "Choose a race and load the model"} icon={Target} color="#FF8000" />
        <MetricCard label="Scenario Leader" value={scenarioLeader?.name ?? "No picks"} sub={scenarioLeader ? `${scenarioLeader.team} · ${pointsLabel(scenarioLeader.projected)} pts` : "Try a what-if scenario"} icon={Gauge} color="#BE3AFF" />
        <MetricCard label="Title Paths" value={String(aliveCount)} sub="Alive or countback possible" icon={BarChart3} color="#3671C6" />
      </MetricRow>

      {/* Mode switcher */}
      <Panel className="p-2 mb-5">
        <div className="flex flex-col gap-2 md:flex-row [&>button]:flex-1">
          {(["race", "season", "scenario"] as LabMode[]).map((m) => (
            <button
              key={m}
              onClick={() => setMode(m)}
              className={`rounded-lg px-4 py-3 text-sm font-black uppercase tracking-wider transition-colors ${
                mode === m ? "bg-[#00FF78] text-black" : "text-neutral-300 hover:bg-white/[0.05]"
              }`}
            >
              {m === "race" ? "Race Prediction" : m === "season" ? "Season Forecast" : "What-If Scenario"}
            </button>
          ))}
        </div>
      </Panel>

      {mode === "race" && (
        <RacePredictionBoard
          schedule={schedule}
          scheduleError={Boolean(scheduleError) || Boolean(!Array.isArray(scheduleResponse) && (scheduleResponse as { error: string })?.error)}
          scheduleLoading={scheduleLoading}
          selectedRound={effectiveRound}
          selectedRace={selectedRace ?? null}
          requested={requested}
          data={data}
          predictions={predictions}
          podium={podium}
          leader={leader}
          drivers={drivers}
          raceName={raceName}
          predictionLoading={predictionLoading}
          predictionError={Boolean(predictionError || backendError)}
          onSelectRound={(round) => { setSelectedRound(round); setRequested(false); }}
          onRun={() => { setRequested(true); void reloadPrediction(); }}
          onRetry={() => void reloadPrediction()}
          onReloadSchedule={() => void reloadSchedule()}
        />
      )}

      {mode === "season" && (
        <SeasonForecastBoard
          data={forecastData}
          isLoading={forecastLoading}
          error={forecastError}
          onRetry={() => void reloadForecast()}
        />
      )}

      {mode === "scenario" && (
        <ChampionshipScenarioBoard
          drivers={drivers}
          driversLoading={driversLoading}
          driversError={driversError || driversData?.error}
          upcomingRaces={upcomingRaces}
          scenarioPicks={scenarioPicks}
          scenarioRows={scenarioRows}
          onSetPick={handleSetPick}
          onApplyPreset={(preset: ScenarioPreset) => setScenarioPicks(buildScenarioPreset(drivers, upcomingRaces, preset))}
          onClear={() => setScenarioPicks({})}
          onRetry={() => void reloadDrivers()}
        />
      )}
    </div>
  );
}
