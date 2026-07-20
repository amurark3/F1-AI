"use client";

import { useMemo, useState } from "react";
import useSWR from "swr";
import { AlertTriangle } from "lucide-react";
import { type DriverPrediction } from "@/app/components/PredictionDriverCard";
import { API_BASE } from "@/app/constants/api";
import { fetcher } from "@/app/utils/fetcher";
import { PageLoader } from "../components/RaceControlPrimitives";
import { RacePredictionBoard } from "./RacePredictionBoard";

interface RaceEvent {
  round: number;
  name: string;
  location: string;
  status: string;
  date?: string;
  sessions?: Record<string, string>;
  is_sprint?: boolean;
  circuit?: { circuit_name?: string; laps?: number; circuit_type?: string; length_km?: number } | null;
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

interface RiskPrediction {
  driver_code: string;
  driver_name: string;
  team: string;
  projected_finish: number;
  dnf_risk_pct: number;
  crash_risk_pct: number;
  mechanical_risk_pct: number;
  risk_level: "low" | "medium" | "high";
  factors: string[];
}

interface PredictionReview {
  evaluated: boolean;
  reason?: string;
  winner_correct?: boolean;
  predicted_winner?: string;
  actual_winner?: string;
  top3_correct?: number;
  top3_possible?: number;
  top10_correct?: number;
  top10_possible?: number;
  exact_position_hits?: number;
  drivers_compared?: number;
  avg_position_error?: number;
  dnf_correct?: number;
  dnf_predicted?: number;
  dnf_actual?: number;
  crash_correct?: number;
  crash_predicted?: number;
  crash_actual?: number;
}

interface PredictionsResponse {
  year: number;
  round: number;
  grand_prix?: string;
  generated_at?: string;
  prediction_phase?: "pre_qualifying" | "post_qualifying";
  predictions: DriverPrediction[];
  risk_predictions?: RiskPrediction[];
  prediction_review?: PredictionReview;
  accuracy?: {
    recent_winner_pct?: number;
    recent_top3_pct?: number;
    recent_top10_pct?: number;
    exact_position_pct?: number;
    avg_position_error?: number;
    dnf_capture_pct?: number | null;
    crash_capture_pct?: number | null;
    races_evaluated: number;
    rolling_window?: number;
  };
  error?: string;
  warnings?: string[];
  data_sources?: string[];
  model_summary?: {
    leader?: string | null;
    leader_code?: string | null;
    average_top3_confidence?: number | null;
    source_count?: number;
    status?: string;
    snapshot_policy?: string;
    risk_count?: number;
  };
  model_inputs?: Array<{ label: string; status: string; impact: string; source: string }>;
  model_limitations?: string[];
  cache?: {
    status: "hit" | "stored" | "missing";
    stored_at?: string | null;
    updated_at?: string | null;
    valid_until?: string | null;
    policy?: string;
    snapshot_id?: string | null;
    snapshot_count?: number;
    recompute_count?: number;
    reason?: string | null;
  };
}

const year = new Date().getFullYear();

async function postPredictionCompute(url: string) {
  const response = await fetch(url, { method: "POST" });
  if (!response.ok) {
    throw new Error(`Prediction request failed with ${response.status}`);
  }
  return response.json() as Promise<PredictionsResponse>;
}

export default function RaceControlPredictionsPage() {
  const [selectedRound, setSelectedRound] = useState<number | null>(null);
  const [computeError, setComputeError] = useState<string | null>(null);
  const [computeReason, setComputeReason] = useState<"manual_compute" | "qualifying_recompute" | null>(null);

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

  const {
    data,
    error: predictionError,
    isLoading: predictionLoading,
    mutate: mutatePrediction,
  } = useSWR<PredictionsResponse>(
    effectiveRound ? `${API_BASE}/api/predictions/${year}/${effectiveRound}/snapshot` : null,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 60000 }
  );

  const predictions = data?.predictions ?? [];
  const riskPredictions = data?.risk_predictions ?? [];
  const podium = predictions.slice(0, 3);
  const raceName = data?.grand_prix ?? selectedRace?.name ?? "Select A Race";
  const backendError = data?.error && predictions.length === 0 ? data.error : null;
  const drivers = driversData?.drivers ?? [];
  const pageLoading = (scheduleLoading && schedule.length === 0) || (driversLoading && drivers.length === 0);
  const isComputing = computeReason !== null;

  const computePrediction = async (reason: "manual_compute" | "qualifying_recompute") => {
    if (!effectiveRound || isComputing) return;
    setComputeError(null);
    setComputeReason(reason);
    try {
      const result = await postPredictionCompute(`${API_BASE}/api/predictions/${year}/${effectiveRound}/compute?reason=${reason}`);
      await mutatePrediction(result, { revalidate: false });
    } catch (error) {
      setComputeError(error instanceof Error ? error.message : "Prediction compute failed.");
    } finally {
      setComputeReason(null);
    }
  };

  if (pageLoading) {
    return (
      <div>
        <PageLoader title="Preparing prediction workspace" detail="Loading the race calendar and championship table." />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {computeError && (
        <div className="mb-5 flex items-center gap-3 rounded-md border border-[#E10600]/35 bg-[#E10600]/10 px-4 py-3 text-sm text-red-100">
          <AlertTriangle className="h-4 w-4 shrink-0 text-[#E10600]" />
          <span>{computeError}</span>
        </div>
      )}

      <RacePredictionBoard
        schedule={schedule}
        scheduleError={Boolean(scheduleError) || Boolean(!Array.isArray(scheduleResponse) && (scheduleResponse as { error: string })?.error)}
        scheduleLoading={scheduleLoading}
        selectedRound={effectiveRound}
        selectedRace={selectedRace ?? null}
        data={data}
        predictions={predictions}
        riskPredictions={riskPredictions}
        podium={podium}
        drivers={drivers}
        driversError={Boolean(driversError || driversData?.error)}
        raceName={raceName}
        predictionLoading={predictionLoading}
        predictionError={Boolean(predictionError || backendError)}
        isComputing={isComputing}
        computeReason={computeReason}
        onSelectRound={(round) => { setSelectedRound(round); setComputeError(null); }}
        onRun={() => void computePrediction("manual_compute")}
        onQualifyingRecompute={() => void computePrediction("qualifying_recompute")}
        onRetry={() => void mutatePrediction()}
        onReloadSchedule={() => void reloadSchedule()}
        onReloadDrivers={() => void reloadDrivers()}
      />
    </div>
  );
}
