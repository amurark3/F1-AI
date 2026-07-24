import type { DriverPrediction } from "@/app/components/PredictionDriverCard";

export interface RaceEvent {
  round: number;
  name: string;
  location: string;
  status: string;
  date?: string;
  sessions?: Record<string, string>;
  is_sprint?: boolean;
  circuit?: { circuit_name?: string; laps?: number; circuit_type?: string; length_km?: number } | null;
}

export interface DriverStanding {
  code: string;
  name: string;
  team: string;
  position: number;
  points: number;
  wins: number;
}

export interface RiskPrediction {
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

export interface PredictionReview {
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

export interface PredictionsResponse {
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

export type DriverLookup = Record<string, DriverStanding>;
export type TabKey = "predictions" | "podium" | "circuit" | "risk" | "model" | "results";
