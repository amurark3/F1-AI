/**
 * RaceCalendar Component
 * ======================
 * Renders a grid of race-weekend cards for the selected F1 season.
 *
 * Features:
 *  - Year selector (2021–2026).
 *  - Timezone selector: browser local time or any F1 circuit timezone.
 *  - Session times converted to the selected timezone via Intl.DateTimeFormat.
 *  - Highlights the next upcoming race and dims completed weekends.
 *  - Live clock updates every 60 s so "next race" status stays accurate.
 *
 * All session timestamps are stored as UTC strings in the backend and
 * converted to display-time purely on the frontend.
 */
"use client";
import { useState, useEffect } from 'react';
import useSWR from 'swr';
import F1_TIMEZONES from '../constants/timeZone';
import { fetcher } from '../utils/fetcher';

/** Raw session object returned by the backend: { "Race": "ISO string", ... } */
interface Session {
  [key: string]: string;
}

interface RaceEvent {
  round: number;
  name: string;
  location: string;
  date: string | null;
  sessions: Session;
}

const RaceCalendar = () => {
  const currentDate = new Date();
  // In December, pre-select next year's calendar since the current season is over.
  const defaultYear = currentDate.getMonth() >= 11 ? currentDate.getFullYear() + 1 : currentDate.getFullYear();

  const [year, setYear] = useState(defaultYear);
  const [timezone, setTimezone] = useState(Intl.DateTimeFormat().resolvedOptions().timeZone);
  // `now` is initialised in an effect (not during render) to avoid hydration
  // mismatches between server and client.
  const [now, setNow] = useState<Date | null>(null);

  const { data: schedule, isLoading } = useSWR<RaceEvent[]>(
    `http://localhost:8000/api/schedule/${year}`,
    fetcher,
    {
      revalidateOnFocus: false, // Don't refetch on window focus
      dedupingInterval: 60000,  // Cache for 1 minute
    }
  );

  // Initialise and tick `now` every 60 s so "NEXT RACE" badge stays accurate.
  useEffect(() => {
    setNow(new Date());
    const timer = setInterval(() => setNow(new Date()), 60000);
    return () => clearInterval(timer);
  }, []);

  /**
   * Parses an ISO date string to a Date, appending "Z" if no timezone offset
   * is present so the browser treats it as UTC rather than local time.
   */
  const parseDate = (isoString: string | null | undefined): Date | null => {
    if (!isoString) return null;
    if (!isoString.endsWith("Z") && !isoString.includes("+")) {
      return new Date(isoString + "Z");
    }
    return new Date(isoString);
  };

  const formatTime = (isoString: string | undefined) => {
    const date = parseDate(isoString);
    if (!date) return "-";
    return new Intl.DateTimeFormat('en-US', {
      hour: '2-digit', 
      minute: '2-digit',
      timeZone: timezone,
      hour12: false 
    }).format(date);
  };

  const formatSessionDay = (isoString: string) => {
    const date = parseDate(isoString);
    if (!date) return "";
    return new Intl.DateTimeFormat('en-GB', {
        weekday: 'short',
        day: 'numeric',
        timeZone: timezone, 
    }).format(date).toUpperCase();
  };

  const getWeekendRange = (race: RaceEvent) => {
    const sessionDates = Object.values(race.sessions)
        .map(d => parseDate(d))
        .filter((d): d is Date => d !== null);

    if (sessionDates.length === 0) {
        const raceDate = parseDate(race.date);
        return raceDate 
            ? new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', timeZone: timezone }).format(raceDate).toUpperCase() 
            : "";
    }
    
    sessionDates.sort((a, b) => a.getTime() - b.getTime());
    
    const start = sessionDates[0];
    const end = sessionDates[sessionDates.length - 1];

    const fmt = new Intl.DateTimeFormat('en-GB', { day: 'numeric', month: 'short', timeZone: timezone });
    const startParts = fmt.formatToParts(start);
    const endParts = fmt.formatToParts(end);

    const startDay = startParts.find(p => p.type === 'day')?.value;
    const startMonth = startParts.find(p => p.type === 'month')?.value.toUpperCase();
    const endDay = endParts.find(p => p.type === 'day')?.value;
    const endMonth = endParts.find(p => p.type === 'month')?.value.toUpperCase();

    if (startMonth === endMonth) {
        return `${startDay}-${endDay} ${startMonth}`;
    }
    return `${startDay} ${startMonth} - ${endDay} ${endMonth}`;
  };

  /** Returns the round number of the next upcoming race, or null if none. */
  const getNextRaceId = () => {
    if (!now || !schedule) return null;
    const upcoming = schedule.find(race => {
        const raceDate = parseDate(race.sessions['Race']) || parseDate(race.date);
        return raceDate && raceDate > now;
    });
    return upcoming ? upcoming.round : null;
  };

  const nextRaceId = getNextRaceId();

  return (
    <div>
      {/* HEADER CONTROLS */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4">
        <div className="flex items-center gap-3">
            <h2 className="text-2xl font-bold uppercase tracking-wider text-white">
                F1 Schedule
            </h2>
            <select
                value={year}
                onChange={(e) => setYear(Number(e.target.value))}
                className="bg-transparent text-red-500 text-2xl font-black italic uppercase border-none focus:ring-0 cursor-pointer hover:text-red-400 transition-colors"
            >
                <option value={2021}>2021</option>
                <option value={2022}>2022</option>
                <option value={2023}>2023</option>
                <option value={2024}>2024</option>
                <option value={2025}>2025</option>
                <option value={2026}>2026</option>
            </select>
        </div>

        <div className="relative w-full sm:w-auto">
            <select 
              value={timezone} 
              onChange={(e) => setTimezone(e.target.value)}
              className="appearance-none bg-neutral-800 border border-neutral-700 text-gray-300 text-xs font-medium tracking-wide rounded p-2 pr-8 focus:ring-2 focus:ring-red-600 outline-none w-full sm:w-auto"
            >
              <option value={Intl.DateTimeFormat().resolvedOptions().timeZone}>
                📍 Local Time
              </option>
              <hr />
              {F1_TIMEZONES.map((tz) => (
                <option key={tz.value} value={tz.value}>
                  {tz.label}
                </option>
              ))}
            </select>
            <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-2 text-gray-400">
              <svg className="fill-current h-4 w-4" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20"><path d="M9.293 12.95l.707.707L15.657 8l-1.414-1.414L10 10.828 5.757 6.586 4.343 8z"/></svg>
            </div>
        </div>
      </div>

      {/* Loading skeleton */}
      {isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4 animate-pulse">
            {[1,2,3,4].map(i => (
                <div key={i} className="h-48 bg-neutral-800 rounded-xl border border-neutral-700"></div>
            ))}
        </div>
      )}

      {/* Empty state — schedule not yet published for this year */}
      {!isLoading && (!schedule || schedule.length === 0) && (
         <div className="p-12 border border-dashed border-neutral-800 rounded-xl bg-neutral-900/50 text-center">
            <h3 className="text-xl text-gray-400 font-bold mb-2">No Data for {year}</h3>
            <p className="text-gray-500 text-sm">Official session times have not been published yet.</p>
         </div>
      )}

      {/* Race weekend card grid */}
      {!isLoading && schedule && schedule.length > 0 && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {schedule.map((race) => {
            const isNext = race.round === nextRaceId;
            const raceDate = parseDate(race.sessions['Race']);
            const isWeekendDone = raceDate && now ? raceDate < now : false;

            return (
                <div 
                key={race.round}
                className={`
                    relative p-5 rounded-xl border transition-all duration-300 flex flex-col justify-between
                    ${isWeekendDone 
                        ? "bg-neutral-950/50 border-neutral-800 opacity-60 grayscale-[0.8] hover:grayscale-0 hover:opacity-100" 
                        : "bg-neutral-900 border-neutral-800"
                    }
                    ${isNext 
                        ? "bg-neutral-800 border-red-600 shadow-[0_0_15px_rgba(220,38,38,0.3)] scale-[1.02] z-10 opacity-100 grayscale-0" 
                        : ""
                    }
                `}
                >
                {isNext && (
                    <div className="absolute -top-3 right-4 bg-red-600 text-white text-[10px] font-bold px-2 py-1 rounded-full animate-pulse tracking-wider shadow-lg">
                    NEXT RACE
                    </div>
                )}
                
                {isWeekendDone && !isNext && (
                    <div className="absolute -top-3 right-4 bg-neutral-900 text-neutral-500 text-[10px] font-bold border border-neutral-800 px-2 py-1 rounded-full z-10">
                    COMPLETED
                    </div>
                )}

                <div className="mb-4">
                    <div className="flex justify-between items-start mb-2">
                         <span className={`text-[10px] font-bold tracking-widest uppercase ${isWeekendDone ? 'text-neutral-500' : 'text-red-500'}`}>
                            Round {race.round}
                        </span>
                        <span className={`text-xl font-black leading-none tracking-tighter ${isWeekendDone ? 'text-neutral-500' : 'text-white'}`}>
                            {getWeekendRange(race)}
                        </span>
                    </div>

                    <h3 className={`text-lg font-black italic leading-tight mt-1 uppercase ${isWeekendDone ? 'text-neutral-400' : 'text-gray-200'}`}>
                    {race.name.replace("Grand Prix", "GP")}
                    </h3>
                    <p className="text-xs text-gray-500 mt-1 font-medium truncate">
                    {race.location}
                    </p>
                </div>

                <div className="space-y-1.5 border-t border-neutral-700/50 pt-3">
                    {Object.entries(race.sessions).map(([name, time]) => {
                        const sessionDate = parseDate(time);
                        const isSessionDone = sessionDate && now ? sessionDate < now : false;
                        
                        const shortName = name
                            .replace('Practice 1', 'FP1')
                            .replace('Practice 2', 'FP2')
                            .replace('Practice 3', 'FP3')
                            .replace('Qualifying', 'QUALI')
                            .replace('Sprint Qualifying', 'SQ')
                            .replace('Sprint', 'SPRINT')
                            .toUpperCase();

                        return (
                            <div key={name} className="flex justify-between items-center text-xs">
                                <span className={`
                                    w-12 font-bold tracking-wider 
                                    ${isSessionDone ? 'text-neutral-600 line-through' : ''}
                                    ${!isSessionDone && name.includes("Race") ? "text-red-500" : "text-neutral-400"}
                                `}>
                                {shortName}
                                </span>
                                
                                <div className="flex items-center gap-3">
                                    <span className={`
                                        font-medium tracking-tight
                                        ${isSessionDone ? 'text-neutral-700' : 'text-neutral-500'}
                                    `}>
                                        {formatSessionDay(time)}
                                    </span>
                                    <span className={`
                                        font-mono px-1.5 py-0.5 rounded w-12 text-center
                                        ${isSessionDone ? 'text-neutral-600 bg-transparent' : 'text-white bg-neutral-950'}
                                    `}>
                                    {formatTime(time)}
                                    </span>
                                </div>
                            </div>
                        )
                    })}
                </div>
                </div>
            );
            })}
        </div>
      )}
    </div>
  );
};

export default RaceCalendar;