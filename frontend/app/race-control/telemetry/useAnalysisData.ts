"use client";

import useSWR from "swr";

import { API_BASE } from "@/app/constants/api";
import { awaitingFirstData } from "@/app/lib/swrFallback";
import { fetcher } from "@/app/utils/fetcher";

import type {
  AnalysisStatus,
  ComparisonResponse,
  DegradationResponse,
  LapListResponse,
  TrackMapResponse,
  WeekendResponse,
} from "./telemetryModel";

/** While the backend reports a load still running, ask again this often. */
const PENDING_POLL_MS = 5000;
/** A finished session's analysis never changes; keep it for the visit. */
const KEEP_MS = 10 * 60 * 1000;

export interface AnalysisData<T> {
  data: T | undefined;
  error: Error | undefined;
  loading: boolean;
}

function useAnalysis<T extends AnalysisStatus>(path: string | null): AnalysisData<T> {
  const response = useSWR<T, Error>(path ? `${API_BASE}/api/analysis/${path}` : null, fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: KEEP_MS,
    refreshInterval: (latest) => (latest?.pending ? PENDING_POLL_MS : 0),
  });
  return {
    data: response.data,
    error: response.error,
    loading: awaitingFirstData(response.isLoading, response.data !== undefined),
  };
}

function query(values: Record<string, string | number | null>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) {
    if (value !== null) search.set(key, String(value));
  }
  return search.toString();
}

export function useWeekend(year: number, round: number | null) {
  return useAnalysis<WeekendResponse>(round ? `${year}/${round}/sessions` : null);
}

export function useLapList(year: number, round: number | null, session: string | null) {
  return useAnalysis<LapListResponse>(round && session ? `${year}/${round}/laps?${query({ session })}` : null);
}

export function useTrackMap(
  year: number,
  round: number | null,
  pick: { session: string | null; driver: string | null; lap: number | null },
) {
  const ready = round && pick.session && pick.driver;
  return useAnalysis<TrackMapResponse>(
    ready ? `${year}/${round}/track-map?${query({ session: pick.session, driver: pick.driver, lap: pick.lap })}` : null,
  );
}

export function useComparison(
  year: number,
  round: number | null,
  pick: { session: string | null; a: string | null; b: string | null },
) {
  const ready = round && pick.session && pick.a && pick.b && pick.a !== pick.b;
  return useAnalysis<ComparisonResponse>(
    ready ? `${year}/${round}/compare?${query({ session: pick.session, a: pick.a, b: pick.b })}` : null,
  );
}

export function useDegradation(year: number, round: number | null, session: string | null) {
  return useAnalysis<DegradationResponse>(
    round && session ? `${year}/${round}/tyre-degradation?${query({ session })}` : null,
  );
}
