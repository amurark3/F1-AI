"use client";

import Link from 'next/link';
import { useState } from 'react';
import RaceCalendar from '@/app/components/RaceCalendar';
import Standings from '@/app/components/Standings';

export default function Home() {
  // State to control active view
  const [activeTab, setActiveTab] = useState<'calendar' | 'standings'>('calendar');

  return (
    <main className="min-h-screen bg-neutral-900 text-white">
      {/* Hero Section */}
      <div className="bg-gradient-to-r from-red-950 to-neutral-900 p-8 lg:p-12 border-b border-red-900/30">
        <div className="max-w-7xl mx-auto flex flex-col md:flex-row justify-between items-center gap-6">
          <div>
            <h1 className="text-4xl md:text-6xl font-black italic tracking-tighter uppercase mb-2">
              F1 <span className="text-red-600">AI</span>
            </h1>
          </div>
          
          <Link href="/chat">
            <button className="bg-red-600 hover:bg-red-500 text-white font-bold py-4 px-8 rounded-lg uppercase tracking-widest transition-all shadow-[0_0_20px_rgba(220,38,38,0.5)] hover:shadow-[0_0_30px_rgba(220,38,38,0.7)] flex items-center gap-3">
              Enter Pit Wall 
              <span className="text-xl">→</span>
            </button>
          </Link>
        </div>
      </div>

      {/* Main Content Area */}
      <div className="max-w-7xl mx-auto p-6">
        
        {/* TAB NAVIGATION */}
        <div className="flex items-center gap-6 mb-8 border-b border-neutral-800 pb-1">
            <button
                onClick={() => setActiveTab('calendar')}
                className={`pb-3 text-lg font-bold uppercase tracking-widest transition-all ${
                    activeTab === 'calendar' 
                    ? 'text-red-500 border-b-2 border-red-500' 
                    : 'text-gray-500 hover:text-white'
                }`}
            >
                Race Calendar
            </button>
            <button
                onClick={() => setActiveTab('standings')}
                className={`pb-3 text-lg font-bold uppercase tracking-widest transition-all ${
                    activeTab === 'standings' 
                    ? 'text-red-500 border-b-2 border-red-500' 
                    : 'text-gray-500 hover:text-white'
                }`}
            >
                Championship Standings
            </button>
        </div>
        
        {/* CONDITIONAL RENDERING */}
        <div className="animate-in fade-in duration-500">
            {activeTab === 'calendar' ? <RaceCalendar /> : <Standings />}
        </div>

      </div>
    </main>
  );
}