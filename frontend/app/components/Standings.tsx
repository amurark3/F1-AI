/**
 * Standings Component
 * ===================
 * Displays the World Drivers' Championship or World Constructors' Championship
 * standings table for a user-selected season.
 *
 * Data is fetched from the backend via SWR with a 1-minute deduplication
 * window to avoid unnecessary API calls when switching tabs.
 */
"use client";

import { useState } from 'react';
import useSWR from 'swr';
import { fetcher } from '../utils/fetcher';
import { API_BASE } from '../constants/api';

const Standings = () => {
  const currentDate = new Date();
  // Default to the previous year before March (season hasn't started yet).
  const defaultYear = currentDate.getMonth() >= 1 ? currentDate.getFullYear() : currentDate.getFullYear() - 1;

  const [year, setYear] = useState(defaultYear);
  const [type, setType] = useState<'drivers' | 'constructors'>('drivers');

  const { data, isLoading } = useSWR<any[]>(
    `${API_BASE}/api/standings/${type}/${year}`,
    fetcher,
    {
      revalidateOnFocus: false, // Don't refetch when the window regains focus
      dedupingInterval: 60000,  // Cache responses for 1 minute
    }
  );

  return (
    <div>
      {/* Controls: toggle between Drivers / Constructors and select season year */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center mb-6 gap-4">
        <div className="flex bg-neutral-800 rounded-lg p-1 border border-neutral-700">
            <button onClick={() => setType('drivers')} className={`px-4 py-2 rounded-md text-sm font-bold uppercase tracking-wider transition-all ${type === 'drivers' ? 'bg-red-600 text-white shadow-lg' : 'text-gray-400 hover:text-white'}`}>Drivers</button>
            <button onClick={() => setType('constructors')} className={`px-4 py-2 rounded-md text-sm font-bold uppercase tracking-wider transition-all ${type === 'constructors' ? 'bg-red-600 text-white shadow-lg' : 'text-gray-400 hover:text-white'}`}>Constructors</button>
        </div>
        <div className="flex items-center gap-3">
            <span className="text-gray-400 text-xs font-bold uppercase tracking-widest">Season</span>
            <select value={year} onChange={(e) => setYear(Number(e.target.value))} className="bg-neutral-800 text-white text-sm font-bold border border-neutral-700 rounded p-2 focus:ring-2 focus:ring-red-600 outline-none">
                <option value={2021}>2021</option>
                <option value={2022}>2022</option>
                <option value={2023}>2023</option>
                <option value={2024}>2024</option>
                <option value={2025}>2025</option>
                <option value={2026}>2026</option>
            </select>
        </div>
      </div>

      {/* TABLE */}
      {isLoading ? (
        <div className="space-y-4">
          <div className="flex items-center justify-center gap-3 py-4">
            <div className="relative h-8 w-8">
              <div className="absolute inset-0 rounded-full border-2 border-red-500/20" />
              <div className="absolute inset-0 rounded-full border-2 border-transparent border-t-red-500 animate-spin" />
              <div className="absolute inset-[6px] rounded-full bg-neutral-900 border border-neutral-800" />
            </div>
            <span className="text-sm text-gray-400 font-medium tracking-wide">Loading {type} standings<span className="animate-pulse">...</span></span>
          </div>
          <div className="overflow-hidden rounded-xl border border-neutral-800 animate-pulse">
            <div className="h-10 bg-neutral-800" />
            {[1,2,3,4,5,6,7,8].map(i => (
              <div key={i} className="flex items-center gap-4 px-6 py-4 border-t border-neutral-800/50">
                <div className="h-4 w-8 bg-neutral-700/50 rounded" />
                <div className="h-4 w-32 bg-neutral-700/50 rounded" />
                <div className="h-4 w-24 bg-neutral-700/30 rounded ml-auto" />
                <div className="h-4 w-12 bg-neutral-700/50 rounded" />
              </div>
            ))}
          </div>
        </div>
      ) : !data || data.length === 0 ? (
        <div className="p-12 border border-dashed border-neutral-800 rounded-xl bg-neutral-900/50 text-center">
            <h3 className="text-xl text-gray-400 font-bold mb-2">No Standings Data</h3>
            <p className="text-gray-500 text-sm">Data for {year} is not available yet.</p>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-neutral-800">
            <table className="w-full text-left text-sm text-gray-400">
                <thead className="bg-neutral-800 text-gray-200 uppercase font-black text-xs tracking-wider">
                    <tr>
                        <th className="px-6 py-4">Pos</th>
                        <th className="px-6 py-4">{type === 'drivers' ? 'Driver' : 'Team'}</th>
                        {type === 'drivers' && <th className="px-6 py-4">Team</th>}
                        <th className="px-6 py-4 text-right">Wins</th>
                        <th className="px-6 py-4 text-right">Points</th>
                    </tr>
                </thead>
                <tbody className="divide-y divide-neutral-800 bg-neutral-900/50">
                    {data.map((row) => (
                        <tr key={row.position} className="hover:bg-neutral-800/50 transition-colors">
                            <td className="px-6 py-4 font-mono text-white">{row.position === 1 ? '🥇' : row.position === 2 ? '🥈' : row.position === 3 ? '🥉' : row.position}</td>
                            <td className="px-6 py-4 font-bold text-white">{type === 'drivers' ? row.driver : row.team}</td>
                            {type === 'drivers' && <td className="px-6 py-4 text-gray-500">{row.team}</td>}
                            <td className="px-6 py-4 text-right font-mono">{row.wins}</td>
                            <td className="px-6 py-4 text-right font-mono text-white font-bold">{row.points}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
      )}
    </div>
  );
};
export default Standings;