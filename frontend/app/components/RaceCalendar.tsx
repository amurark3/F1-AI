"use client";

import { useState } from 'react';
import useSWR from 'swr';
import { ChevronDown } from 'lucide-react';
import F1_TIMEZONES from '../constants/timeZone';
import { fetcher } from '../utils/fetcher';
import { API_BASE } from '../constants/api';
import RaceCard from './RaceCard';

interface Session {
  [key: string]: string;
}

interface CircuitInfo {
  circuit_name: string;
  track_length_km: number;
  laps: number;
  lap_record: { time: string; driver: string; year: number };
  first_gp: number;
  circuit_type: string;
}

interface RaceEvent {
  round: number;
  name: string;
  location: string;
  date: string | null;
  sessions: Session;
  status: string;
  circuit: CircuitInfo | null;
  is_sprint?: boolean;
}

const LOCAL_TZ = Intl.DateTimeFormat().resolvedOptions().timeZone;

const LOCATION_FLAGS: Record<string, string> = {
  'Bahrain': '🇧🇭', 'Saudi Arabia': '🇸🇦', 'Australia': '🇦🇺',
  'Japan': '🇯🇵', 'China': '🇨🇳', 'United States': '🇺🇸',
  'Italy': '🇮🇹', 'Monaco': '🇲🇨', 'Canada': '🇨🇦',
  'Spain': '🇪🇸', 'Austria': '🇦🇹', 'Great Britain': '🇬🇧',
  'Hungary': '🇭🇺', 'Belgium': '🇧🇪', 'Netherlands': '🇳🇱',
  'Azerbaijan': '🇦🇿', 'Singapore': '🇸🇬', 'Mexico': '🇲🇽',
  'Brazil': '🇧🇷', 'Qatar': '🇶🇦', 'United Arab Emirates': '🇦🇪',
  'Abu Dhabi': '🇦🇪', 'Las Vegas': '🇺🇸', 'Miami': '🇺🇸',
};

export const getFlag = (location: string): string => {
  const parts = location.split(',');
  const country = parts[parts.length - 1].trim();
  return LOCATION_FLAGS[country] ?? '🏁';
};

const RaceCalendar = () => {
  const currentDate = new Date();
  const defaultYear = currentDate.getMonth() >= 11
    ? currentDate.getFullYear() + 1
    : currentDate.getFullYear();

  const [year, setYear] = useState(defaultYear);
  const [timezone, setTimezone] = useState(LOCAL_TZ);
  const [expandedRound, setExpandedRound] = useState<number | null | undefined>(undefined);

  const { data: schedule, isLoading } = useSWR<RaceEvent[]>(
    `${API_BASE}/api/schedule/${year}`,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 60000 }
  );

  const targetRound = (() => {
    if (!schedule) return null;
    const live = schedule.find(r => r.status === 'in_progress');
    if (live) return live.round;
    const next = schedule.find(r => r.status === 'upcoming');
    if (next) return next.round;
    return schedule[schedule.length - 1]?.round ?? null;
  })();

  const activeExpandedRound = expandedRound === undefined ? targetRound : expandedRound;

  const toggle = (round: number) =>
    setExpandedRound(activeExpandedRound === round ? null : round);

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 pb-10">

      {/* ── Controls ─────────────────────────────── */}
      <div className="sticky top-[56px] z-20 glass-strong border-b border-white/5 -mx-4 sm:-mx-6 px-4 sm:px-6 py-2.5 mb-4 flex items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div className="w-[3px] h-5 rounded-full" style={{ background: '#E10600' }} />
          <h2
            className="text-xl font-black italic uppercase tracking-tight text-white"
            style={{ fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}
          >
            Weekend Board
          </h2>
          <div className="relative">
            <select
              value={year}
              onChange={e => {
                setYear(Number(e.target.value));
                setExpandedRound(undefined);
              }}
              className="appearance-none glass text-white text-xs font-black uppercase tracking-widest rounded-lg px-3 py-1.5 pr-7 focus:ring-1 focus:ring-[#E10600]/50 outline-none"
              style={{ fontFamily: 'var(--font-barlow, var(--font-geist-sans))' }}
            >
              {[2021,2022,2023,2024,2025,2026].map(y => <option key={y} value={y}>{y}</option>)}
            </select>
            <ChevronDown className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-neutral-500" />
          </div>
        </div>

        <div className="relative">
          <select
            value={timezone}
            onChange={e => setTimezone(e.target.value)}
            className="appearance-none glass text-neutral-400 text-xs rounded-lg px-3 py-1.5 pr-7 focus:ring-1 focus:ring-[#E10600]/50 outline-none max-w-[180px] sm:max-w-xs truncate"
          >
            <option value={LOCAL_TZ}>Local — {LOCAL_TZ.replace(/_/g, ' ')}</option>
            <hr />
            {F1_TIMEZONES.map(tz => (
              <option key={tz.value} value={tz.value}>{tz.label}</option>
            ))}
          </select>
          <ChevronDown className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 w-3 h-3 text-neutral-500" />
        </div>
      </div>

      {/* ── Loading ──────────────────────────────── */}
      {isLoading && (
        <div className="space-y-1 rounded-xl overflow-hidden glass border border-white/5">
          {Array.from({ length: 10 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3 px-4 py-3.5 animate-pulse border-b border-white/3">
              <div className="w-8 h-3 bg-white/5 rounded" />
              <div className="w-6 h-4 bg-white/5 rounded" />
              <div className="flex-1 h-3 bg-white/5 rounded" />
              <div className="w-20 h-3 bg-white/5 rounded hidden sm:block" />
              <div className="w-14 h-5 bg-white/5 rounded" />
            </div>
          ))}
        </div>
      )}

      {/* ── Empty ────────────────────────────────── */}
      {!isLoading && (!schedule || schedule.length === 0) && (
        <div className="glass rounded-xl p-12 text-center border border-dashed border-white/8">
          <p className="text-neutral-500 font-bold">No calendar data for {year}</p>
        </div>
      )}

      {/* ── Race list ────────────────────────────── */}
      {!isLoading && schedule && schedule.length > 0 && (
        <div className="rounded-xl overflow-hidden glass border border-white/6">
          {schedule.map((race, i) => (
            <RaceCard
              key={race.round}
              race={race}
              year={year}
              timezone={timezone}
              isNext={race.round === targetRound}
              expanded={activeExpandedRound === race.round}
              onToggle={() => toggle(race.round)}
              isLastRow={i === schedule.length - 1}
            />
          ))}
        </div>
      )}
    </div>
  );
};

export default RaceCalendar;
