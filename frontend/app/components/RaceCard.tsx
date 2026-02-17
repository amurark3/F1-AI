"use client";

import { useState, useEffect, useRef } from 'react';
import useSWR from 'swr';
import { motion } from 'framer-motion';
import { Loader2, Trophy, Timer, Zap } from 'lucide-react';
import { fetcherWithTimeout } from '../utils/fetcher';
import { API_BASE } from '../constants/api';
import TrackInsights from './TrackInsights';
import PodiumDisplay from './PodiumDisplay';
import RaceResults from './RaceResults';
import QualifyingResults from './QualifyingResults';

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

interface RaceCardProps {
  race: RaceEvent;
  year: number;
  timezone: string;
  isHighlighted: boolean;
  isActive: boolean;
}

const parseDate = (isoString: string | null | undefined): Date | null => {
  if (!isoString) return null;
  const hasOffset = /Z$|[+-]\d{2}:\d{2}$/.test(isoString);
  if (!hasOffset) return new Date(isoString + "Z");
  return new Date(isoString);
};

const formatTime = (isoString: string | undefined, tz: string) => {
  const date = parseDate(isoString);
  if (!date) return "-";
  return new Intl.DateTimeFormat('en-US', {
    hour: '2-digit', minute: '2-digit', timeZone: tz, hour12: false
  }).format(date);
};

const formatSessionDay = (isoString: string, tz: string) => {
  const date = parseDate(isoString);
  if (!date) return "";
  return new Intl.DateTimeFormat('en-GB', {
    weekday: 'short', day: 'numeric', month: 'short', timeZone: tz,
  }).format(date).toUpperCase();
};

const getWeekendRange = (race: RaceEvent, tz: string) => {
  const sessionDates = Object.values(race.sessions)
    .map(d => parseDate(d))
    .filter((d): d is Date => d !== null);

  if (sessionDates.length === 0) {
    const raceDate = parseDate(race.date);
    return raceDate
      ? new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', year: 'numeric', timeZone: tz }).format(raceDate).toUpperCase()
      : "";
  }

  sessionDates.sort((a, b) => a.getTime() - b.getTime());
  const start = sessionDates[0];
  const end = sessionDates[sessionDates.length - 1];

  const fmt = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', timeZone: tz });
  const yearFmt = new Intl.DateTimeFormat('en-GB', { year: 'numeric', timeZone: tz });
  const startParts = fmt.formatToParts(start);
  const endParts = fmt.formatToParts(end);

  const startDay = startParts.find(p => p.type === 'day')?.value;
  const startMonth = startParts.find(p => p.type === 'month')?.value?.toUpperCase();
  const endDay = endParts.find(p => p.type === 'day')?.value;
  const endMonth = endParts.find(p => p.type === 'month')?.value?.toUpperCase();
  const year = yearFmt.format(end);

  if (startMonth === endMonth) return `${startDay}–${endDay} ${startMonth} ${year}`;
  return `${startDay} ${startMonth} – ${endDay} ${endMonth} ${year}`;
};

export default function RaceCard({ race, year, timezone, isHighlighted, isActive }: RaceCardProps) {
  const [resultTab, setResultTab] = useState<'race' | 'qualifying' | 'sprint' | 'sprint_quali'>('race');
  const [hasBeenActive, setHasBeenActive] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (isActive) setHasBeenActive(true);
  }, [isActive]);

  const shouldFetch = hasBeenActive && race.status === "completed";
  const { data: detail, isLoading: detailLoading, error: detailError, mutate: retryDetail } = useSWR(
    shouldFetch ? `${API_BASE}/api/race/${year}/${race.round}` : null,
    fetcherWithTimeout,
    { revalidateOnFocus: false, dedupingInterval: 300000, shouldRetryOnError: false }
  );

  const circuitInfo = detail?.circuit ?? race.circuit;

  const isCompleted = race.status === "completed";
  const isInProgress = race.status === "in_progress";
  const isUpcoming = race.status === "upcoming";

  const [countdown, setCountdown] = useState("");
  useEffect(() => {
    if (!isUpcoming) return;
    const raceTime = parseDate(race.sessions["Race"] || race.date);
    if (!raceTime) return;

    const tick = () => {
      const now = new Date();
      const diff = raceTime.getTime() - now.getTime();
      if (diff <= 0) { setCountdown("NOW"); return; }
      const days = Math.floor(diff / 86400000);
      const hours = Math.floor((diff % 86400000) / 3600000);
      const mins = Math.floor((diff % 3600000) / 60000);
      if (days > 0) setCountdown(`${days}d ${hours}h ${mins}m`);
      else setCountdown(`${hours}h ${mins}m`);
    };
    tick();
    const timer = setInterval(tick, 60000);
    return () => clearInterval(timer);
  }, [isUpcoming, race.sessions, race.date]);

  const shortName = (name: string) =>
    name
      .replace('Practice 1', 'FP1')
      .replace('Practice 2', 'FP2')
      .replace('Practice 3', 'FP3')
      .replace('Qualifying', 'QUALI')
      .replace('Sprint Qualifying', 'SQ')
      .replace('Sprint', 'SPRINT')
      .toUpperCase();

  return (
    <div
      ref={cardRef}
      id={`race-${race.round}`}
      className="snap-page min-h-[calc(100dvh-3.5rem)] px-4 sm:px-6 lg:px-8 py-4 sm:py-6 flex flex-col"
    >
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ type: "spring" as const, damping: 22, stiffness: 200 }}
        className={`flex-1 glass rounded-2xl p-4 sm:p-6 lg:p-8 overflow-y-auto relative max-w-7xl mx-auto w-full ${
          isHighlighted ? "border-red-500/40 shadow-[0_0_40px_rgba(220,38,38,0.15)]" : ""
        }`}
      >
        {/* Status badge */}
        {isHighlighted && (
          <div className="absolute top-3 right-3 sm:top-4 sm:right-4 bg-gradient-to-r from-red-600 to-orange-500 text-white text-[10px] font-bold px-3 py-1 rounded-full animate-glow-pulse tracking-wider shadow-lg shadow-red-500/40">
            {isInProgress ? "LIVE WEEKEND" : "NEXT RACE"}
          </div>
        )}
        {isCompleted && !isHighlighted && (
          <div className="absolute top-3 right-3 sm:top-4 sm:right-4 bg-neutral-800/80 text-neutral-500 text-[10px] font-bold border border-white/10 px-2.5 py-1 rounded-full">
            COMPLETED
          </div>
        )}

        {/* Header */}
        <div className="mb-4 sm:mb-6">
          <div className="flex items-center gap-2 sm:gap-3 mb-1.5">
            <span className="text-[10px] font-bold tracking-widest uppercase bg-gradient-to-r from-red-500 to-orange-400 bg-clip-text text-transparent">
              Round {race.round}
            </span>
            {race.is_sprint && (
              <span className="text-[9px] font-bold uppercase tracking-widest px-2 py-0.5 rounded-full bg-yellow-500/15 text-yellow-400 border border-yellow-500/20">
                Sprint
              </span>
            )}
            <span className="text-[11px] text-neutral-500 font-medium">
              {getWeekendRange(race, timezone)}
            </span>
          </div>
          <h2 className="text-xl sm:text-3xl lg:text-4xl font-black italic uppercase text-white leading-tight">
            {race.name}
          </h2>
          <p className="text-xs sm:text-sm text-neutral-400 mt-0.5">{race.location}</p>
        </div>

        {/* Two-panel on lg+, single-column on mobile */}
        <div className="lg:grid lg:grid-cols-[minmax(260px,320px)_1fr] lg:gap-6">
          {/* Left sidebar (lg+) / Full-width top section (mobile) */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-1 gap-3 sm:gap-4 mb-5 lg:mb-0">
            {/* Session schedule */}
            <div className="space-y-1.5">
              <h4 className="text-[10px] font-bold uppercase tracking-widest text-neutral-500 mb-1">
                Schedule
              </h4>
              {Object.entries(race.sessions).map(([name, time]) => {
                const sessionDate = parseDate(time);
                const now = new Date();
                const isDone = sessionDate ? sessionDate < now : false;

                return (
                  <div key={name} className="flex justify-between items-center">
                    <span className={`w-14 font-bold tracking-wider text-[11px] ${
                      isDone ? "text-neutral-600 line-through" :
                      name === "Race" ? "bg-gradient-to-r from-red-500 to-orange-400 bg-clip-text text-transparent" :
                      "text-neutral-400"
                    }`}>
                      {shortName(name)}
                    </span>
                    <div className="flex items-center gap-3">
                      <span className={`text-[11px] font-medium ${isDone ? "text-neutral-700" : "text-neutral-500"}`}>
                        {formatSessionDay(time, timezone)}
                      </span>
                      <span className={`font-mono text-[11px] px-1.5 py-0.5 rounded w-12 text-center ${
                        isDone ? "text-neutral-600" : "text-white bg-white/5"
                      }`}>
                        {formatTime(time, timezone)}
                      </span>
                    </div>
                  </div>
                );
              })}
            </div>

            {/* Circuit info — compact */}
            {circuitInfo && <TrackInsights circuit={circuitInfo} />}
          </div>

          {/* Right panel (lg+) / Below section (mobile) */}
          <div className="space-y-5 sm:space-y-6">
            {/* Countdown */}
            {isUpcoming && countdown && (
              <div className="glass rounded-2xl p-5 sm:p-6 text-center max-w-md mx-auto lg:mx-0 lg:max-w-none">
                <Timer className="h-5 w-5 text-red-400 mx-auto mb-2" />
                <p className="text-[10px] font-bold uppercase tracking-widest text-neutral-500 mb-1.5">
                  Lights Out In
                </p>
                <p className="text-3xl sm:text-4xl font-black bg-gradient-to-r from-red-500 to-orange-400 bg-clip-text text-transparent">
                  {countdown}
                </p>
              </div>
            )}

            {/* In-progress banner */}
            {isInProgress && (
              <div className="glass rounded-2xl p-5 text-center max-w-md mx-auto lg:mx-0 lg:max-w-none">
                <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-gradient-to-r from-red-600/15 to-orange-500/15 border border-red-500/20 text-red-400 text-xs font-bold uppercase tracking-widest mb-2">
                  <span className="inline-block h-1.5 w-1.5 rounded-full bg-red-500 animate-glow-pulse" />
                  Race Weekend In Progress
                </div>
                <p className="text-neutral-400 text-sm">
                  Check back after the race for full results.
                </p>
              </div>
            )}

            {/* Completed race content */}
            {isCompleted && (
              <>
                {/* Loading */}
                {detailLoading && !detailError && (
                  <div className="flex flex-col items-center justify-center py-8 gap-3">
                    <Loader2 className="h-6 w-6 text-red-500 animate-spin" />
                    <p className="text-xs text-neutral-500 font-medium">Loading race data...</p>
                  </div>
                )}

                {/* Error */}
                {detailError && (
                  <div className="flex flex-col items-center justify-center py-6 gap-3 text-center">
                    <p className="text-sm text-neutral-400">Failed to load race data.</p>
                    <p className="text-xs text-neutral-600">{detailError.message}</p>
                    <button
                      onClick={() => retryDetail()}
                      className="mt-1 text-xs font-bold uppercase tracking-wider px-4 py-2 rounded-xl bg-gradient-to-r from-red-600 to-orange-500 text-white shadow-lg shadow-red-600/25 hover:from-red-500 hover:to-orange-400 transition-all"
                    >
                      Retry
                    </button>
                  </div>
                )}

                {/* Podium */}
                {detail?.podium && (
                  <div>
                    <h4 className="text-[10px] font-bold uppercase tracking-widest text-neutral-500 mb-3 text-center lg:text-left">
                      Podium
                    </h4>
                    <PodiumDisplay podium={detail.podium} />
                  </div>
                )}

                {/* Results tabs */}
                {detail && !detailLoading && (detail.race_results || detail.qualifying) && (
                  <div className="space-y-3">
                    <div className="flex gap-1 glass rounded-xl p-1 max-w-lg mx-auto lg:mx-0 lg:max-w-none">
                      <button
                        onClick={() => setResultTab('race')}
                        className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 text-xs font-bold uppercase tracking-wider rounded-lg transition-all duration-300 ${
                          resultTab === 'race'
                            ? "bg-gradient-to-r from-red-600 to-orange-500 text-white shadow-lg shadow-red-600/25"
                            : "text-neutral-500 hover:text-white hover:bg-white/5"
                        }`}
                      >
                        <Trophy className="h-3 w-3" />
                        Race
                      </button>
                      <button
                        onClick={() => setResultTab('qualifying')}
                        className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 text-xs font-bold uppercase tracking-wider rounded-lg transition-all duration-300 ${
                          resultTab === 'qualifying'
                            ? "bg-gradient-to-r from-red-600 to-orange-500 text-white shadow-lg shadow-red-600/25"
                            : "text-neutral-500 hover:text-white hover:bg-white/5"
                        }`}
                      >
                        <Timer className="h-3 w-3" />
                        Quali
                      </button>
                      {detail.is_sprint && (
                        <>
                          <button
                            onClick={() => setResultTab('sprint')}
                            className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 text-xs font-bold uppercase tracking-wider rounded-lg transition-all duration-300 ${
                              resultTab === 'sprint'
                                ? "bg-gradient-to-r from-red-600 to-orange-500 text-white shadow-lg shadow-red-600/25"
                                : "text-neutral-500 hover:text-white hover:bg-white/5"
                            }`}
                          >
                            <Zap className="h-3 w-3" />
                            Sprint
                          </button>
                          <button
                            onClick={() => setResultTab('sprint_quali')}
                            className={`flex-1 flex items-center justify-center gap-1.5 py-1.5 text-xs font-bold uppercase tracking-wider rounded-lg transition-all duration-300 ${
                              resultTab === 'sprint_quali'
                                ? "bg-gradient-to-r from-red-600 to-orange-500 text-white shadow-lg shadow-red-600/25"
                                : "text-neutral-500 hover:text-white hover:bg-white/5"
                            }`}
                          >
                            <Zap className="h-3 w-3" />
                            SQ
                          </button>
                        </>
                      )}
                    </div>

                    {resultTab === 'race' && <RaceResults results={detail.race_results} />}
                    {resultTab === 'qualifying' && <QualifyingResults qualifying={detail.qualifying} />}
                    {resultTab === 'sprint' && <RaceResults results={detail.sprint_results} />}
                    {resultTab === 'sprint_quali' && <QualifyingResults qualifying={detail.sprint_qualifying} />}
                  </div>
                )}

                {/* No data */}
                {detail && !detailLoading && !detail.race_results && !detail.qualifying && (
                  <div className="text-center py-6">
                    <p className="text-neutral-500 text-sm">Results data not yet available.</p>
                  </div>
                )}
              </>
            )}
          </div>
        </div>
      </motion.div>
    </div>
  );
}
