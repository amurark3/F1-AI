"use client";

import { useState, useEffect } from 'react';
import useSWR from 'swr';
import { fetcher } from '../utils/fetcher';
import { API_BASE } from '../constants/api';
import { PredictionDriverCard } from './PredictionDriverCard';
import { Toast, useToast } from './Toast';

interface RaceEvent {
  round: number;
  name: string;
  status: string;
  is_sprint?: boolean;
}

interface PredictionsResponse {
  year: number;
  round: number;
  grand_prix: string;
  predictions: DriverPrediction[];
  accuracy?: {
    recent_top3_pct?: number;
    races_evaluated: number;
  };
  error?: string;
}

interface DriverPrediction {
  position: number;
  driver_code: string;
  driver_name: string;
  team: string;
  confidence_low: number;
  confidence_high: number;
  factors: string[];
}

const PredictionPanel = () => {
  const currentDate = new Date();
  const year = currentDate.getMonth() >= 1 ? currentDate.getFullYear() : currentDate.getFullYear() - 1;

  const { toast, showToast, dismissToast } = useToast();

  // Step 1: Get schedule to find upcoming round
  const { data: schedule } = useSWR<RaceEvent[]>(
    `${API_BASE}/api/schedule/${year}`,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 300000 }
  );

  const upcomingRace = schedule?.find(r => r.status === 'upcoming') ?? null;
  const round = upcomingRace?.round ?? null;

  // Step 2: Fetch predictions for upcoming round
  const {
    data,
    isLoading,
    error: swrError,
    mutate,
    isValidating,
  } = useSWR<PredictionsResponse>(
    round ? `${API_BASE}/api/predictions/${year}/${round}` : null,
    fetcher,
    {
      revalidateOnFocus: false,
      dedupingInterval: 60000,
      onSuccess: (newData, key, config) => {
        // Check for HTTP 200 with error body (Pitfall 7 from research)
        if (newData?.error && data?.predictions?.length) {
          // Has stale data + backend error → show toast
          showToast(newData.error, () => mutate());
        }
      },
      onError: (err) => {
        if (data?.predictions?.length) {
          // Has stale data + network error → show toast (background refresh failure)
          showToast('Failed to refresh predictions', () => mutate());
        }
        // No stale data → let swrError render the inline error state
      }
    }
  );

  // Backend-level error on initial load (HTTP 200 + error body, no prior data)
  const backendError = !data?.predictions?.length && data?.error ? data.error : null;

  const isFirstLoad = isLoading && !data;
  const hasContent = data?.predictions && data.predictions.length > 0;
  const noUpcomingRace = !isLoading && schedule && !upcomingRace;

  return (
    <div className="relative">
      {/* First load skeleton */}
      {isFirstLoad && (
        <div className="space-y-3">
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="h-16 glass rounded-2xl animate-pulse" />
          ))}
        </div>
      )}

      {/* No upcoming race — friendly empty state (locked decision: do not hide the view) */}
      {!isFirstLoad && noUpcomingRace && (
        <div className="p-16 border border-dashed border-white/10 glass rounded-2xl text-center">
          <div className="text-4xl mb-4">🏁</div>
          <h3 className="text-xl text-white font-bold mb-2">No Upcoming Race</h3>
          <p className="text-gray-500 text-sm">Race predictions will be available closer to the next round.</p>
        </div>
      )}

      {/* First load error — inline error state with Retry */}
      {!isFirstLoad && (swrError || backendError) && !hasContent && (
        <div className="p-12 glass rounded-2xl text-center">
          <div className="text-4xl mb-4">⚠</div>
          <h3 className="text-lg text-white font-bold mb-2">Something went wrong</h3>
          <p className="text-gray-500 text-sm mb-6">
            {backendError || swrError?.message || 'Failed to load predictions'}
          </p>
          <button
            onClick={() => mutate()}
            className="px-6 py-2.5 bg-gradient-to-r from-red-600 to-orange-500 text-white text-sm font-bold rounded-xl hover:opacity-90 transition-opacity"
          >
            Retry
          </button>
        </div>
      )}

      {/* Content: driver cards */}
      {!isFirstLoad && hasContent && (
        <div>
          {/* Header */}
          <div className="flex items-center justify-between mb-4 sm:mb-6">
            <div>
              <h2 className="text-lg sm:text-xl font-black text-white">
                {data!.grand_prix}
              </h2>
              {data?.accuracy && data.accuracy.races_evaluated > 0 && (
                <p className="text-xs text-gray-500 mt-0.5">
                  Based on {data.accuracy.races_evaluated} recent race{data.accuracy.races_evaluated !== 1 ? 's' : ''}
                  {data.accuracy.recent_top3_pct != null && ` · Top-3 accuracy: ${data.accuracy.recent_top3_pct}%`}
                </p>
              )}
            </div>
          </div>

          <div className="space-y-3">
            {data!.predictions.map((prediction, index) => (
              <PredictionDriverCard
                key={prediction.driver_code}
                prediction={prediction}
                index={index}
              />
            ))}
          </div>
        </div>
      )}

      {/* Toast — background refresh failure (separate from first-load error state) */}
      {toast && (
        <Toast
          message={toast.message}
          onRetry={toast.onRetry}
          onDismiss={dismissToast}
        />
      )}
    </div>
  );
};

export default PredictionPanel;
