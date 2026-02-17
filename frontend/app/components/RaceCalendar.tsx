/**
 * RaceCalendar Component
 * ======================
 * Full-viewport snap-scroll race calendar. Each race is a "page" in a
 * vertical scroll. Auto-scrolls to the current/next race on load.
 */
"use client";
import { useState, useEffect, useRef, useCallback } from 'react';
import useSWR from 'swr';
import { ChevronDown } from 'lucide-react';
import F1_TIMEZONES from '../constants/timeZone';
import { fetcher } from '../utils/fetcher';
import { API_BASE } from '../constants/api';
import RaceCard from './RaceCard';
import RaceJumpNav from './RaceJumpNav';

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

const RaceCalendar = () => {
  const currentDate = new Date();
  const defaultYear = currentDate.getMonth() >= 11 ? currentDate.getFullYear() + 1 : currentDate.getFullYear();

  const [year, setYear] = useState(defaultYear);
  const [timezone, setTimezone] = useState(LOCAL_TZ);
  const [activeRound, setActiveRound] = useState<number | null>(null);
  const [hasAutoScrolled, setHasAutoScrolled] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const { data: schedule, isLoading } = useSWR<RaceEvent[]>(
    `${API_BASE}/api/schedule/${year}`,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 60000 }
  );

  // Find the target race to scroll to (first upcoming or in_progress)
  const getTargetRound = useCallback((): number | null => {
    if (!schedule) return null;
    const inProgress = schedule.find(r => r.status === 'in_progress');
    if (inProgress) return inProgress.round;
    const upcoming = schedule.find(r => r.status === 'upcoming');
    if (upcoming) return upcoming.round;
    // All completed — go to last race
    return schedule[schedule.length - 1]?.round ?? null;
  }, [schedule]);

  // Auto-scroll to current race on first load
  useEffect(() => {
    if (!schedule || hasAutoScrolled) return;
    const targetRound = getTargetRound();
    if (targetRound === null) return;

    setActiveRound(targetRound);

    // Small delay so DOM is rendered
    const timer = setTimeout(() => {
      const el = document.getElementById(`race-${targetRound}`);
      if (el) {
        el.scrollIntoView({ behavior: 'instant' as ScrollBehavior });
        setHasAutoScrolled(true);
      }
    }, 100);
    return () => clearTimeout(timer);
  }, [schedule, hasAutoScrolled, getTargetRound]);

  // Reset auto-scroll when year changes
  useEffect(() => {
    setHasAutoScrolled(false);
    setActiveRound(null);
  }, [year]);

  // Track active race via IntersectionObserver
  useEffect(() => {
    if (!schedule || !containerRef.current) return;

    const observers: IntersectionObserver[] = [];
    schedule.forEach((race) => {
      const el = document.getElementById(`race-${race.round}`);
      if (!el) return;
      const observer = new IntersectionObserver(
        ([entry]) => {
          if (entry.isIntersecting) {
            setActiveRound(race.round);
          }
        },
        { root: containerRef.current, threshold: 0.5 }
      );
      observer.observe(el);
      observers.push(observer);
    });

    return () => observers.forEach(o => o.disconnect());
  }, [schedule]);

  const handleJump = (round: number) => {
    const el = document.getElementById(`race-${round}`);
    if (el) {
      el.scrollIntoView({ behavior: 'smooth' });
      setActiveRound(round);
    }
  };

  return (
    <div className="relative h-[calc(100dvh-3.5rem)] flex flex-col">
      {/* Floating controls bar */}
      <div className="sticky top-0 z-30 glass-strong border-b border-white/5 px-4 sm:px-6 py-2.5 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2">
        <div className="flex items-center gap-2 sm:gap-3">
          <h2 className="text-lg sm:text-xl font-bold uppercase tracking-wider text-white">
            Calendar
          </h2>
          <div className="relative">
            <select
              value={year}
              onChange={(e) => setYear(Number(e.target.value))}
              className="appearance-none glass border-white/10 text-gray-300 text-xs font-medium tracking-wide rounded-xl p-2 pr-8 focus:ring-2 focus:ring-red-500/40 outline-none"
            >
              <option value={2021}>2021</option>
              <option value={2022}>2022</option>
              <option value={2023}>2023</option>
              <option value={2024}>2024</option>
              <option value={2025}>2025</option>
              <option value={2026}>2026</option>
            </select>
            <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-gray-400">
              <ChevronDown className="h-4 w-4" />
            </div>
          </div>
        </div>

        <div className="relative">
          <select
            value={timezone}
            onChange={(e) => setTimezone(e.target.value)}
            className="appearance-none glass border-white/10 text-gray-300 text-xs font-medium tracking-wide rounded-xl p-2 pr-8 focus:ring-2 focus:ring-red-500/40 outline-none"
          >
            <option value={LOCAL_TZ}>
              Local ({LOCAL_TZ.replace(/_/g, ' ')})
            </option>
            <hr />
            {F1_TIMEZONES.map((tz) => (
              <option key={tz.value} value={tz.value}>{tz.label}</option>
            ))}
          </select>
          <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-gray-400">
            <ChevronDown className="h-4 w-4" />
          </div>
        </div>
      </div>

      {/* Loading skeleton */}
      {isLoading && (
        <div className="flex-1 flex items-center justify-center">
          <div className="text-center space-y-3">
            <div className="h-8 w-48 bg-white/5 rounded-xl animate-pulse mx-auto" />
            <div className="h-4 w-32 bg-white/3 rounded animate-pulse mx-auto" />
            <div className="h-3 w-24 bg-white/3 rounded animate-pulse mx-auto" />
          </div>
        </div>
      )}

      {/* Empty state */}
      {!isLoading && (!schedule || schedule.length === 0) && (
        <div className="flex-1 flex items-center justify-center">
          <div className="glass rounded-2xl p-12 text-center">
            <h3 className="text-xl text-gray-400 font-bold mb-2">No Data for {year}</h3>
            <p className="text-gray-500 text-sm">Official session times have not been published yet.</p>
          </div>
        </div>
      )}

      {/* Snap-scroll race cards */}
      {!isLoading && schedule && schedule.length > 0 && (
        <div
          ref={containerRef}
          className="flex-1 overflow-y-auto snap-container scroll-smooth"
        >
          {schedule.map((race) => (
            <RaceCard
              key={race.round}
              race={race}
              year={year}
              timezone={timezone}
              isHighlighted={race.round === (getTargetRound() ?? -1)}
              isActive={race.round === activeRound}
            />
          ))}
        </div>
      )}

      {/* Jump navigation */}
      {schedule && schedule.length > 0 && (
        <RaceJumpNav
          schedule={schedule}
          activeRound={activeRound}
          onJump={handleJump}
        />
      )}
    </div>
  );
};

export default RaceCalendar;
