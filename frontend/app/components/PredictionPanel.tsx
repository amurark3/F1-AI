"use client";

import { useState } from 'react';
import useSWR from 'swr';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertTriangle, BarChart3, ClipboardList, Gauge, Target } from 'lucide-react';
import { fetcher } from '../utils/fetcher';
import { API_BASE } from '../constants/api';
import { PredictionDriverCard, getTeamColor, type DriverPrediction } from './PredictionDriverCard';
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

/* ── Podium card ─────────────────────────────────────────────── */
interface PodiumCardProps { p: DriverPrediction; rank: 1 | 2 | 3; delay: number; }

const PODIUM_HEIGHT: Record<1 | 2 | 3, string> = { 1: '168px', 2: '132px', 3: '108px' };
const MEDAL_COLOR:  Record<1 | 2 | 3, string>  = { 1: '#FFD700', 2: '#C0C0C0', 3: '#CD7F32' };

function PodiumCard({ p, rank, delay }: PodiumCardProps) {
  const teamColor  = getTeamColor(p.team);
  const midConf    = Math.round((p.confidence_low + p.confidence_high) / 2);
  const medalColor = MEDAL_COLOR[rank];

  return (
    <motion.div
      initial={{ opacity: 0, y: 30 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay, ease: [0.22, 1, 0.36, 1] }}
      className="flex flex-col items-center flex-1"
    >
      <div
        className="relative w-full rounded-xl overflow-hidden flex flex-col items-center justify-end text-center pb-4 pt-3 px-2"
        style={{
          height: PODIUM_HEIGHT[rank],
          background: `linear-gradient(to bottom, ${teamColor}28, ${teamColor}0a)`,
          border: `1px solid ${teamColor}30`,
        }}
      >
        <div className="absolute top-0 left-0 right-0 h-[3px]" style={{ background: teamColor }} />
        <div
          className="absolute top-3 left-3 text-xs font-black w-6 h-6 rounded flex items-center justify-center"
          style={{ background: `${medalColor}22`, color: medalColor, fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}
        >
          {rank}
        </div>
        <div
          className="text-2xl sm:text-3xl font-black italic tracking-tighter text-white mb-1 leading-none"
          style={{ fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}
        >
          {p.driver_code}
        </div>
        <div className="text-[11px] font-bold text-white/80 truncate w-full px-1 leading-tight">{p.driver_name}</div>
        <div className="text-[9px] font-semibold mt-0.5 truncate w-full" style={{ color: teamColor }}>{p.team}</div>
        <div
          className="mt-2 text-base sm:text-lg font-black font-mono"
          style={{ color: medalColor, fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}
        >
          {midConf}%
        </div>
        <div className="mt-2 w-full px-2">
          <div className="h-1 bg-white/10 rounded-full overflow-hidden">
            <motion.div
              className="h-full rounded-full"
              initial={{ width: 0 }}
              animate={{ width: `${midConf}%` }}
              transition={{ duration: 0.9, delay: delay + 0.2, ease: [0.22, 1, 0.36, 1] }}
              style={{ background: teamColor }}
            />
          </div>
        </div>
      </div>
      <div className="w-full rounded-b-lg" style={{ height: rank === 1 ? 20 : rank === 2 ? 14 : 8, background: `${teamColor}55` }} />
    </motion.div>
  );
}

/* ── Main panel ──────────────────────────────────────────────── */
const PredictionPanel = () => {
  const year = new Date().getMonth() >= 1 ? new Date().getFullYear() : new Date().getFullYear() - 1;
  const { toast, showToast, dismissToast } = useToast();

  // User must click "Run Predictions" — we don't fetch until they ask
  const [requested, setRequested] = useState(false);

  const { data: schedule } = useSWR<RaceEvent[]>(
    `${API_BASE}/api/schedule/${year}`, fetcher,
    { revalidateOnFocus: false, dedupingInterval: 300_000 }
  );

  const upcomingRace = schedule?.find(r => r.status === 'upcoming') ?? null;
  const round        = upcomingRace?.round ?? null;

  const { data, isLoading, error: swrError, mutate } = useSWR<PredictionsResponse>(
    // Only fires when user has clicked the button
    requested && round ? `${API_BASE}/api/predictions/${year}/${round}` : null,
    fetcher,
    {
      revalidateOnFocus: false,
      dedupingInterval: 60_000,
      onSuccess: (newData) => {
        if (newData?.error && data?.predictions?.length) showToast(newData.error, () => mutate());
      },
      onError: () => {
        if (data?.predictions?.length) showToast('Failed to refresh predictions', () => mutate());
      },
    }
  );

  const backendError = !data?.predictions?.length && data?.error ? data.error : null;
  const hasContent   = (data?.predictions?.length ?? 0) > 0;
  const noUpcoming   = !schedule && false || (schedule !== undefined && !upcomingRace);
  const qualPending  = requested && !isLoading && !swrError && !backendError && !hasContent && !!upcomingRace && data !== undefined;

  const podium = data?.predictions?.slice(0, 3) ?? [];
  const grid   = data?.predictions?.slice(3)    ?? [];

  /* ── Pre-request: show race info + CTA ──────────────────── */
  if (!requested) {
    const scheduleReady = schedule !== undefined;

    return (
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
        className="flex flex-col items-center justify-center min-h-[50vh] text-center px-4"
      >
        <div
          className="h-14 w-14 rounded-xl flex items-center justify-center border mb-6"
          style={{ borderColor: 'rgba(225,6,0,0.32)', background: 'rgba(225,6,0,0.10)' }}
        >
          <Target className="h-7 w-7" style={{ color: '#E10600' }} />
        </div>

        <div
          className="text-[10px] font-black uppercase tracking-[0.22em] mb-4"
          style={{ color: '#E10600', fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}
        >
          AI Race Engineer — Predictions
        </div>

        {!scheduleReady ? (
          /* Loading schedule */
          <div className="flex gap-2 mb-6">
            {[0, 1, 2].map(i => (
              <div key={i} className="h-2 w-2 rounded-full bg-neutral-600 animate-pulse" style={{ animationDelay: `${i * 0.15}s` }} />
            ))}
          </div>
        ) : noUpcoming ? (
          /* Off season */
          <>
            <h2
              className="text-3xl sm:text-4xl font-black italic uppercase tracking-tight text-white mb-3 leading-none"
              style={{ fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}
            >
              Off Season
            </h2>
            <p className="text-neutral-500 text-sm max-w-sm">
              Predictions will be available once the next race weekend is confirmed.
            </p>
          </>
        ) : (
          /* Upcoming race found — show CTA */
          <>
            <h2
              className="text-3xl sm:text-4xl font-black italic uppercase tracking-tight text-white mb-2 leading-none"
              style={{ fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}
            >
              {upcomingRace!.name}
            </h2>
            <p className="text-neutral-500 text-sm mb-8 max-w-sm">
              Build a race-order branch from qualifying, team performance, circuit characteristics, and recent form.
            </p>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 sm:gap-3 mb-10 w-full max-w-3xl">
              {[
                { label: 'Podium branch', desc: 'P1 - P3', icon: Target },
                { label: 'Full order', desc: 'P4 - P20', icon: ClipboardList },
                { label: 'Confidence', desc: 'Driver bands', icon: Gauge },
                { label: 'Model review', desc: 'Accuracy', icon: BarChart3 },
              ].map(({ label, desc, icon: Icon }) => (
                <div key={label} className="glass rounded-xl px-3 py-3 text-left">
                  <Icon className="h-4 w-4 mb-3" style={{ color: '#E10600' }} />
                  <div className="text-xs font-bold text-white mb-0.5">{label}</div>
                  <div className="text-[10px] text-neutral-600">{desc}</div>
                </div>
              ))}
            </div>

            <motion.button
              whileHover={{ scale: 1.04 }}
              whileTap={{ scale: 0.96 }}
              onClick={() => setRequested(true)}
              className="px-8 py-3.5 text-white font-black uppercase tracking-widest rounded-xl text-sm shadow-lg"
              style={{
                background: 'linear-gradient(135deg, #E10600 0%, #FF3300 100%)',
                boxShadow: '0 6px 28px rgba(225,6,0,0.4)',
                fontFamily: 'var(--font-barlow, var(--font-geist-sans))',
              }}
            >
              Run Predictions
            </motion.button>
          </>
        )}
      </motion.div>
    );
  }

  /* ── Post-request states ─────────────────────────────────── */
  return (
    <div className="relative">

      {/* Loading skeleton */}
      {isLoading && (
        <div className="space-y-2.5">
          <div className="flex gap-3 mb-6">
            {[132, 168, 108].map((h, i) => (
              <div key={i} className="flex-1 glass rounded-xl animate-pulse" style={{ height: h }} />
            ))}
          </div>
          {Array.from({ length: 7 }).map((_, i) => (
            <div key={i} className="h-14 glass rounded-xl animate-pulse" />
          ))}
        </div>
      )}

      {/* Qualifying not done yet */}
      {qualPending && (
        <div className="p-14 glass rounded-xl border border-dashed border-white/8 text-center">
          <Gauge className="h-10 w-10 mx-auto mb-4 text-neutral-600" />
          <h3 className="text-xl font-black uppercase italic text-white mb-2"
            style={{ fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}>
            {upcomingRace?.name}
          </h3>
          <p className="text-neutral-500 text-sm">Predictions unlock after qualifying.</p>
        </div>
      )}

      {/* Error */}
      {!isLoading && (swrError || backendError) && !hasContent && (
        <div className="p-12 glass rounded-xl text-center">
          <AlertTriangle className="h-10 w-10 mx-auto mb-4 text-red-400" />
          <h3 className="text-lg font-black text-white mb-2 uppercase italic"
            style={{ fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}>
            Something went wrong
          </h3>
          <p className="text-neutral-500 text-sm mb-6">
            {backendError || swrError?.message || 'Failed to load predictions'}
          </p>
          <div className="flex items-center justify-center gap-3">
            <button
              onClick={() => mutate()}
              className="px-6 py-2.5 text-white text-sm font-black uppercase tracking-widest rounded-xl"
              style={{ background: '#E10600', fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}
            >
              Retry
            </button>
            <button
              onClick={() => setRequested(false)}
              className="px-6 py-2.5 text-neutral-400 text-sm font-bold rounded-xl glass hover:text-white transition-colors"
            >
              Back
            </button>
          </div>
        </div>
      )}

      {/* ── Predictions content ──────────────────── */}
      <AnimatePresence>
        {!isLoading && hasContent && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.3 }}
          >
            {/* Header */}
            <div className="flex flex-col sm:flex-row sm:items-end justify-between mb-6 gap-2">
              <div>
                <div
                  className="text-[10px] font-black uppercase tracking-[0.2em] mb-1"
                  style={{ color: '#E10600', fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}
                >
                  AI Prediction — Round {data!.round}
                </div>
                <h2
                  className="text-2xl sm:text-3xl font-black italic uppercase tracking-tight text-white leading-none"
                  style={{ fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}
                >
                  {data!.grand_prix}
                </h2>
              </div>

              <div className="flex items-center gap-2">
                {data?.accuracy && data.accuracy.races_evaluated > 0 && (
                  <div className="glass rounded-lg px-4 py-2 text-right">
                    {data.accuracy.recent_top3_pct != null && (
                      <div
                        className="text-xl font-black font-mono"
                        style={{ color: '#00CC00', fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}
                      >
                        {data.accuracy.recent_top3_pct}%
                      </div>
                    )}
                    <div className="text-[10px] text-neutral-500 uppercase tracking-wider">
                      Top-3 accuracy · {data.accuracy.races_evaluated} races
                    </div>
                  </div>
                )}
                <button
                  onClick={() => { setRequested(false); }}
                  className="glass px-3 py-2 rounded-lg text-[10px] font-black uppercase tracking-wider text-neutral-500 hover:text-white transition-colors"
                  style={{ fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}
                >
                  Reset
                </button>
              </div>
            </div>

            {/* Podium */}
            {podium.length >= 3 && (
              <div className="mb-6">
                <p
                  className="text-[10px] font-black uppercase tracking-[0.2em] text-neutral-600 mb-3"
                  style={{ fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}
                >
                  Predicted Podium
                </p>
                <div className="flex items-end gap-2 sm:gap-3">
                  <PodiumCard p={podium[1]} rank={2} delay={0.1} />
                  <PodiumCard p={podium[0]} rank={1} delay={0}   />
                  <PodiumCard p={podium[2]} rank={3} delay={0.2} />
                </div>
              </div>
            )}

            {/* Grid P4+ */}
            {grid.length > 0 && (
              <>
                <div className="flex items-center gap-3 mb-4">
                  <div className="h-px flex-1 bg-white/5" />
                  <span
                    className="text-[10px] font-black uppercase tracking-[0.2em] text-neutral-600"
                    style={{ fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}
                  >
                    Points &amp; Beyond
                  </span>
                  <div className="h-px flex-1 bg-white/5" />
                </div>
                <div className="space-y-1.5">
                  {grid.map((prediction, i) => (
                    <PredictionDriverCard
                      key={prediction.driver_code}
                      prediction={prediction}
                      index={i + 3}
                    />
                  ))}
                </div>
              </>
            )}
          </motion.div>
        )}
      </AnimatePresence>

      {toast && <Toast message={toast.message} onRetry={toast.onRetry} onDismiss={dismissToast} />}
    </div>
  );
};

export default PredictionPanel;
