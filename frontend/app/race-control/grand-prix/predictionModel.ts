/** One feature's exact share of a driver's predicted finish, from the linear model. */
export interface ModelAttribution {
  feature: string;
  label: string;
  value: number;
  contribution: number;
  direction: "helps" | "hurts";
}

/** One row of the model's predicted finishing order. */
export interface DriverPrediction {
  position: number;
  driver_code: string;
  driver_name: string;
  team: string;
  confidence_low: number;
  confidence_high: number;
  factors: string[];
  model_attribution?: ModelAttribution[] | null;
}

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

/** One driver's predicted finish next to where they actually finished. */
export interface PredictionDriverResult {
  driver_code: string;
  predicted_position: number | null;
  actual_position: number | null;
  /** actual - predicted: positive means the driver finished lower than predicted. */
  position_delta: number | null;
  exact: boolean;
  status?: string | null;
  dnf: boolean;
  crash: boolean;
  predicted_dnf_risk_pct?: number | null;
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
  driver_results?: PredictionDriverResult[];
}

/**
 * Which of a race's two predictions a payload holds.
 *
 * `pre_qualifying` is the call the model makes from form and history alone;
 * `post_qualifying` is the one that has seen the grid. Both are stored per
 * race, and recomputing one never touches the other.
 */
export type PredictionPhase = "pre_qualifying" | "post_qualifying";

export const PREDICTION_PHASES: readonly PredictionPhase[] = ["pre_qualifying", "post_qualifying"];

export interface PredictionsResponse {
  year: number;
  round: number;
  grand_prix?: string;
  generated_at?: string;
  prediction_phase?: PredictionPhase | null;
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
  /** On a snapshot read: whether a compute for this phase is still in flight. */
  model_running?: boolean;
  cache?: {
    /** `computing`: the run outlasted the request and will store its snapshot when done. */
    status: "hit" | "stored" | "missing" | "computing";
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
