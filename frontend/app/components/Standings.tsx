/**
 * Standings Component
 * ===================
 * Displays F1 driver / constructor championship standings with glass rows.
 */
"use client";

import { useState } from 'react';
import useSWR from 'swr';
import { motion } from 'framer-motion';
import { fetcher } from '../utils/fetcher';
import { API_BASE } from '../constants/api';

/** Accent colour per constructor (approximation of official team colours). */
const TEAM_COLORS: Record<string, string> = {
  "Red Bull":         "#3671C6",
  "Mercedes":         "#27F4D2",
  "Ferrari":          "#E8002D",
  "McLaren":          "#FF8000",
  "Aston Martin":     "#229971",
  "Alpine F1 Team":   "#FF87BC",
  "Williams":         "#64C4FF",
  "RB F1 Team":       "#6692FF",
  "Haas F1 Team":     "#B6BABD",
  "Audi":             "#FF0000",
  "Cadillac F1 Team": "#E0D4B8",
};

const getTeamColor = (team: string) => TEAM_COLORS[team] ?? "#6B7280";

const Standings = () => {
  const currentDate = new Date();
  const defaultYear = currentDate.getMonth() >= 1 ? currentDate.getFullYear() : currentDate.getFullYear() - 1;

  const [year, setYear] = useState(defaultYear);
  const [type, setType] = useState<'drivers' | 'constructors'>('drivers');

  const { data, isLoading } = useSWR<any[]>(
    `${API_BASE}/api/standings/${type}/${year}`,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 60000 }
  );

  return (
    <div>
      {/* Controls */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 sm:mb-8 gap-3 sm:gap-4">
        <div className="flex glass rounded-2xl p-1">
          <button
            onClick={() => setType('drivers')}
            className={`px-4 sm:px-5 py-2 rounded-xl text-xs sm:text-sm font-bold uppercase tracking-wider transition-all duration-300 ${
              type === 'drivers'
                ? 'bg-gradient-to-r from-red-600 to-orange-500 text-white shadow-lg shadow-red-600/25'
                : 'text-gray-500 hover:text-white hover:bg-white/5'
            }`}
          >
            Drivers
          </button>
          <button
            onClick={() => setType('constructors')}
            className={`px-4 sm:px-5 py-2 rounded-xl text-xs sm:text-sm font-bold uppercase tracking-wider transition-all duration-300 ${
              type === 'constructors'
                ? 'bg-gradient-to-r from-red-600 to-orange-500 text-white shadow-lg shadow-red-600/25'
                : 'text-gray-500 hover:text-white hover:bg-white/5'
            }`}
          >
            Constructors
          </button>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-gray-500 text-xs font-bold uppercase tracking-widest">Season</span>
          <select
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            className="appearance-none glass border-white/10 text-white text-sm font-bold rounded-xl px-3 py-2 focus:ring-2 focus:ring-red-500/40 outline-none"
          >
            {[2021, 2022, 2023, 2024, 2025, 2026].map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>
        </div>
      </div>

      {/* Loading skeleton */}
      {isLoading && (
        <div className="space-y-3">
          {Array.from({ length: 10 }).map((_, i) => (
            <div key={i} className="flex items-center gap-3 sm:gap-4 p-3 sm:p-4 glass rounded-2xl animate-pulse">
              <div className="h-7 w-7 sm:h-8 sm:w-8 bg-white/5 rounded-lg shrink-0" />
              <div className="h-4 flex-1 max-w-[10rem] bg-white/5 rounded" />
              <div className="h-4 w-12 sm:w-16 bg-white/5 rounded ml-auto" />
            </div>
          ))}
        </div>
      )}

      {/* Empty state */}
      {!isLoading && (!data || data.length === 0) && (
        <div className="p-16 border border-dashed border-white/10 glass rounded-2xl text-center">
          <h3 className="text-xl text-gray-400 font-bold mb-2">No Standings Data</h3>
          <p className="text-gray-600 text-sm">Data for {year} is not available yet.</p>
        </div>
      )}

      {/* Driver standings */}
      {!isLoading && data && data.length > 0 && type === 'drivers' && (
        <div className="space-y-3">
          {data.map((row, index) => {
            const color = getTeamColor(row.team);
            const isTopThree = row.position <= 3;
            return (
              <motion.div
                key={row.position}
                initial={{ opacity: 0, x: 30 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ type: "spring", damping: 20, stiffness: 200, delay: index * 0.03 }}
                whileHover={{ scale: 1.01, x: 4 }}
                className={`
                  group relative flex items-center gap-2 sm:gap-4 p-3 sm:p-4 rounded-2xl transition-all duration-200
                  ${isTopThree
                    ? 'glass border-white/8 hover:border-white/15'
                    : 'bg-white/3 border border-white/5 hover:bg-white/6'
                  }
                `}
              >
                {/* Team colour accent */}
                <div className="absolute left-0 top-3 bottom-3 w-1 rounded-full" style={{ backgroundColor: color }} />

                {/* Position */}
                <div className={`w-8 sm:w-10 text-center font-black text-base sm:text-lg ${isTopThree ? 'text-white' : 'text-neutral-500'}`}>
                  {row.position}
                </div>

                {/* Driver + Team */}
                <div className="flex-1 min-w-0">
                  <p className={`font-bold truncate ${isTopThree ? 'text-white text-sm sm:text-base' : 'text-gray-300 text-sm'}`}>
                    {row.driver}
                  </p>
                  <p className="text-[10px] sm:text-xs font-medium truncate" style={{ color }}>
                    {row.team}
                  </p>
                </div>

                {/* Wins */}
                <div className="text-center w-12 sm:w-16 hidden sm:block">
                  <p className={`font-mono text-sm ${row.wins > 0 ? 'text-white' : 'text-neutral-600'}`}>{row.wins}</p>
                  <p className="text-[10px] text-neutral-600 uppercase tracking-wider">Wins</p>
                </div>

                {/* Points */}
                <div className="text-right w-14 sm:w-20">
                  <p className={`font-mono font-black text-base sm:text-lg ${isTopThree ? 'text-white' : 'text-gray-300'}`}>
                    {row.points}
                  </p>
                  <p className="text-[10px] text-neutral-600 uppercase tracking-wider">Pts</p>
                </div>
              </motion.div>
            );
          })}
        </div>
      )}

      {/* Constructor standings */}
      {!isLoading && data && data.length > 0 && type === 'constructors' && (
        <div className="space-y-3">
          {data.map((row, index) => {
            const color = getTeamColor(row.team);
            const isTopThree = row.position <= 3;
            return (
              <motion.div
                key={row.position}
                initial={{ opacity: 0, x: 30 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ type: "spring", damping: 20, stiffness: 200, delay: index * 0.03 }}
                whileHover={{ scale: 1.01, x: 4 }}
                className={`
                  group relative flex items-center gap-2 sm:gap-4 p-3 sm:p-4 rounded-2xl transition-all duration-200
                  ${isTopThree
                    ? 'glass border-white/8 hover:border-white/15'
                    : 'bg-white/3 border border-white/5 hover:bg-white/6'
                  }
                `}
              >
                {/* Team colour bar */}
                <div className="absolute left-0 top-3 bottom-3 w-1 rounded-full" style={{ backgroundColor: color }} />

                {/* Position */}
                <div className={`w-8 sm:w-10 text-center font-black text-base sm:text-lg ${isTopThree ? 'text-white' : 'text-neutral-500'}`}>
                  {row.position}
                </div>

                {/* Team name + colour dot */}
                <div className="flex-1 flex items-center gap-2 sm:gap-3 min-w-0">
                  <div className="h-3 w-3 rounded-full shrink-0" style={{ backgroundColor: color }} />
                  <p className={`font-bold truncate ${isTopThree ? 'text-white text-sm sm:text-base' : 'text-gray-300 text-sm'}`}>
                    {row.team}
                  </p>
                </div>

                {/* Wins */}
                <div className="text-center w-12 sm:w-16 hidden sm:block">
                  <p className={`font-mono text-sm ${row.wins > 0 ? 'text-white' : 'text-neutral-600'}`}>{row.wins}</p>
                  <p className="text-[10px] text-neutral-600 uppercase tracking-wider">Wins</p>
                </div>

                {/* Points */}
                <div className="text-right w-14 sm:w-20">
                  <p className={`font-mono font-black text-base sm:text-lg ${isTopThree ? 'text-white' : 'text-gray-300'}`}>
                    {row.points}
                  </p>
                  <p className="text-[10px] text-neutral-600 uppercase tracking-wider">Pts</p>
                </div>
              </motion.div>
            );
          })}
        </div>
      )}
    </div>
  );
};

export default Standings;
