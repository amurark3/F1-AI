"use client";

import { AlertTriangle } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import useSWR from "swr";

import type { DriverPrediction } from "@/app/components/PredictionDriverCard";
import { API_BASE } from "@/app/constants/api";
import { fetcher } from "@/app/utils/fetcher";

import { PageLoader } from "../components/RaceControlPrimitives";

import { RacePredictionBoard, type RacePredictionBoardProps } from "./RacePredictionBoard";

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

/** True when the schedule endpoint returned an `{ error }` payload rather than an array. */
function hasScheduleErrorPayload(response: RaceEvent[] | { error: string } | undefined): boolean {
  return !Array.isArray(response) && Boolean(response?.error);
}

type ComputeReason = "manual_compute" | "qualifying_recompute";

/** Resolve which round/race is in focus from the selection and schedule defaults. */
function resolveRound(schedule: RaceEvent[], selectedRound: number | null, defaultRace: RaceEvent | null) {
  const effectiveRound = selectedRound ?? defaultRace?.round ?? null;
  const selectedRace = schedule.find((r) => r.round === effectiveRound) ?? defaultRace;
  return { effectiveRound, selectedRace };
}

/** Derive the display-ready prediction slices from the snapshot payload. */
function derivePredictionView(data: PredictionsResponse | undefined, selectedRace: RaceEvent | null) {
  const predictions = data?.predictions ?? [];
  const backendError = data?.error && predictions.length === 0 ? data.error : null;
  return {
    predictions,
    riskPredictions: data?.risk_predictions ?? [],
    podium: predictions.slice(0, 3),
    raceName: data?.grand_prix ?? selectedRace?.name ?? "Select A Race",
    backendError,
  };
}

function usePredictionWorkspace() {
  const [selectedRound, setSelectedRound] = useState<number | null>(null);
  const [computeError, setComputeError] = useState<string | null>(null);
  const [computeReason, setComputeReason] = useState<ComputeReason | null>(null);

  const {
    data: scheduleResponse,
    error: scheduleError,
    isLoading: scheduleLoading,
    mutate: reloadSchedule,
  } = useSWR<RaceEvent[] | { error: string }, Error>(`${API_BASE}/api/schedule/${year}`, fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 300000,
  });

  const {
    data: driversData,
    error: driversError,
    isLoading: driversLoading,
    mutate: reloadDrivers,
  } = useSWR<DriversResponse, Error>(`${API_BASE}/api/race-control/drivers/${year}`, fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 180000,
  });

  const schedule = useMemo(() => (Array.isArray(scheduleResponse) ? scheduleResponse : []), [scheduleResponse]);
  const defaultRace = useMemo(() => {
    if (!schedule.length) return null;
    return (
      schedule.find((r) => r.status === "upcoming" || r.status === "next") ??
      [...schedule].reverse().find((r) => r.status === "completed") ??
      schedule[0]
    );
  }, [schedule]);

  const { effectiveRound, selectedRace } = resolveRound(schedule, selectedRound, defaultRace);

  const {
    data,
    error: predictionError,
    isLoading: predictionLoading,
    mutate: mutatePrediction,
  } = useSWR<PredictionsResponse, Error>(
    effectiveRound ? `${API_BASE}/api/predictions/${year}/${effectiveRound}/snapshot` : null,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 60000 },
  );

  const view = derivePredictionView(data, selectedRace ?? null);
  const drivers = driversData?.drivers ?? [];
  const pageLoading = (scheduleLoading && schedule.length === 0) || (driversLoading && drivers.length === 0);
  const isComputing = computeReason !== null;

  const computePrediction = useCallback(
    async (reason: ComputeReason) => {
      if (!effectiveRound || isComputing) return;
      setComputeError(null);
      setComputeReason(reason);
      try {
        const result = await postPredictionCompute(
          `${API_BASE}/api/predictions/${year}/${effectiveRound}/compute?reason=${reason}`,
        );
        await mutatePrediction(result, { revalidate: false });
      } catch (error) {
        setComputeError(error instanceof Error ? error.message : "Prediction compute failed.");
      } finally {
        setComputeReason(null);
      }
    },
    [effectiveRound, isComputing, mutatePrediction],
  );

  const boardProps: RacePredictionBoardProps = {
    schedule,
    scheduleError: Boolean(scheduleError) || hasScheduleErrorPayload(scheduleResponse),
    scheduleLoading,
    selectedRound: effectiveRound,
    selectedRace: selectedRace ?? null,
    data,
    predictions: view.predictions,
    riskPredictions: view.riskPredictions,
    podium: view.podium,
    drivers,
    driversError: Boolean(driversError || driversData?.error),
    raceName: view.raceName,
    predictionLoading,
    predictionError: Boolean(predictionError || view.backendError),
    isComputing,
    computeReason,
    onSelectRound: (round) => {
      setSelectedRound(round);
      setComputeError(null);
    },
    onRun: () => void computePrediction("manual_compute"),
    onQualifyingRecompute: () => void computePrediction("qualifying_recompute"),
    onRetry: () => void mutatePrediction(),
    onReloadSchedule: () => void reloadSchedule(),
    onReloadDrivers: () => void reloadDrivers(),
  };

  return { pageLoading, computeError, boardProps };
}

function ComputeErrorBanner({ message }: { message: string }) {
  return (
    <div className="mb-5 flex items-center gap-3 rounded-md border border-[#E10600]/35 bg-[#E10600]/10 px-4 py-3 text-sm text-red-100">
      <AlertTriangle className="h-4 w-4 shrink-0 text-[#E10600]" />
      <span>{message}</span>
    </div>
  );
}

export default function RaceControlPredictionsPage() {
  const { pageLoading, computeError, boardProps } = usePredictionWorkspace();

  if (pageLoading) {
    return (
      <div>
        <PageLoader title="Preparing prediction workspace" detail="Loading the race calendar and championship table." />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {computeError && <ComputeErrorBanner message={computeError} />}
      <RacePredictionBoard {...boardProps} />
    </div>
  );
}
