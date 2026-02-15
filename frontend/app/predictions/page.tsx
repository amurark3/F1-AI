"use client";

import { useState } from 'react';
import useSWR from 'swr';
import NavShell from '@/app/components/NavShell';
import { fetcher } from '../utils/fetcher';
import { API_BASE } from '../constants/api';

interface RaceEvent {
  round: number;
  name: string;
}

export default function PredictionsPage() {
  const currentYear = new Date().getFullYear();
  const [year, setYear] = useState(currentYear);

  // Race prediction state.
  const [selectedRace, setSelectedRace] = useState('');
  const [prediction, setPrediction] = useState<string | null>(null);
  const [predLoading, setPredLoading] = useState(false);

  // Scenario state.
  const [driver, setDriver] = useState('');
  const [scenarioYear, setScenarioYear] = useState(currentYear - 1);
  const [scenario, setScenario] = useState<string | null>(null);
  const [scenLoading, setScenLoading] = useState(false);

  const { data: schedule } = useSWR<RaceEvent[]>(
    `${API_BASE}/api/schedule/${year}`,
    fetcher,
    { revalidateOnFocus: false, dedupingInterval: 60000 }
  );

  const handlePredict = async () => {
    if (!selectedRace) return;
    setPredLoading(true);
    setPrediction(null);
    try {
      const res = await fetch(`${API_BASE}/api/predictions/${year}/${encodeURIComponent(selectedRace)}`);
      const data = await res.json();
      setPrediction(data.prediction || data.error || 'No prediction available.');
    } catch (e) {
      setPrediction(`Error: ${e}`);
    } finally {
      setPredLoading(false);
    }
  };

  const handleScenario = async () => {
    if (!driver.trim()) return;
    setScenLoading(true);
    setScenario(null);
    try {
      const res = await fetch(`${API_BASE}/api/scenario/${scenarioYear}/${encodeURIComponent(driver.trim())}`);
      const data = await res.json();
      setScenario(data.scenario || data.error || 'No scenario data available.');
    } catch (e) {
      setScenario(`Error: ${e}`);
    } finally {
      setScenLoading(false);
    }
  };

  return (
    <NavShell>
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-6 space-y-8 sm:space-y-10">
        {/* Race Prediction Section */}
        <section>
          <div className="mb-6">
            <h2 className="text-2xl font-black italic uppercase tracking-tight text-white mb-1">
              Race <span className="text-red-500">Predictions</span>
            </h2>
            <p className="text-sm text-neutral-500">
              ML model trained on 2018-2025 historical data predicts finishing order.
            </p>
          </div>

          <div className="grid grid-cols-[auto_1fr] sm:flex sm:flex-wrap items-end gap-3 mb-6">
            <div>
              <label className="text-[10px] text-neutral-500 uppercase tracking-widest font-bold block mb-1">Season</label>
              <select
                value={year}
                onChange={(e) => { setYear(Number(e.target.value)); setSelectedRace(''); }}
                className="bg-neutral-900 text-white text-sm font-bold border border-neutral-800 rounded-lg px-3 py-2.5 focus:ring-2 focus:ring-red-600 outline-none"
              >
                {[2021, 2022, 2023, 2024, 2025, 2026].map((y) => (
                  <option key={y} value={y}>{y}</option>
                ))}
              </select>
            </div>

            <div className="sm:flex-1">
              <label className="text-[10px] text-neutral-500 uppercase tracking-widest font-bold block mb-1">Grand Prix</label>
              <select
                value={selectedRace}
                onChange={(e) => setSelectedRace(e.target.value)}
                className="w-full bg-neutral-900 text-white text-sm border border-neutral-800 rounded-lg px-3 py-2.5 focus:ring-2 focus:ring-red-600 outline-none"
              >
                <option value="">Select a race...</option>
                {schedule?.map((r) => (
                  <option key={r.round} value={r.name}>{r.name}</option>
                ))}
              </select>
            </div>

            <button
              onClick={handlePredict}
              disabled={!selectedRace || predLoading}
              className="col-span-2 sm:col-span-1 bg-red-600 hover:bg-red-500 text-white text-sm font-bold uppercase tracking-wider px-6 py-2.5 rounded-lg disabled:opacity-40 disabled:cursor-not-allowed transition-all"
            >
              {predLoading ? 'Predicting...' : 'Predict'}
            </button>
          </div>

          {prediction && (
            <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-4 sm:p-6">
              <pre className="whitespace-pre-wrap font-mono text-sm text-gray-300 leading-relaxed">
                {prediction}
              </pre>
            </div>
          )}
        </section>

        {/* Divider */}
        <div className="border-t border-neutral-800" />

        {/* Championship Scenario Section */}
        <section>
          <div className="mb-6">
            <h2 className="text-2xl font-black italic uppercase tracking-tight text-white mb-1">
              Championship <span className="text-red-500">Scenarios</span>
            </h2>
            <p className="text-sm text-neutral-500">
              See how many points a driver needed per remaining race to win the title.
            </p>
          </div>

          <div className="grid grid-cols-[auto_1fr] sm:flex sm:flex-wrap items-end gap-3 mb-6">
            <div>
              <label className="text-[10px] text-neutral-500 uppercase tracking-widest font-bold block mb-1">Season</label>
              <select
                value={scenarioYear}
                onChange={(e) => setScenarioYear(Number(e.target.value))}
                className="bg-neutral-900 text-white text-sm font-bold border border-neutral-800 rounded-lg px-3 py-2.5 focus:ring-2 focus:ring-red-600 outline-none"
              >
                {[2021, 2022, 2023, 2024, 2025].map((y) => (
                  <option key={y} value={y}>{y}</option>
                ))}
              </select>
            </div>

            <div className="sm:flex-1">
              <label className="text-[10px] text-neutral-500 uppercase tracking-widest font-bold block mb-1">Driver (last name)</label>
              <input
                type="text"
                value={driver}
                onChange={(e) => setDriver(e.target.value)}
                placeholder="e.g. Norris, Verstappen"
                className="w-full bg-neutral-900 text-white text-sm border border-neutral-800 rounded-lg px-3 py-2.5 focus:ring-2 focus:ring-red-600 outline-none placeholder:text-neutral-600"
                onKeyDown={(e) => e.key === 'Enter' && handleScenario()}
              />
            </div>

            <button
              onClick={handleScenario}
              disabled={!driver.trim() || scenLoading}
              className="col-span-2 sm:col-span-1 bg-red-600 hover:bg-red-500 text-white text-sm font-bold uppercase tracking-wider px-6 py-2.5 rounded-lg disabled:opacity-40 disabled:cursor-not-allowed transition-all"
            >
              {scenLoading ? 'Calculating...' : 'Calculate'}
            </button>
          </div>

          {scenario && (
            <div className="bg-neutral-900 border border-neutral-800 rounded-xl p-6 overflow-x-auto">
              <pre className="whitespace-pre-wrap font-mono text-sm text-gray-300 leading-relaxed">
                {scenario}
              </pre>
            </div>
          )}
        </section>
      </div>
    </NavShell>
  );
}
