"use client";

import NavShell from '@/app/components/NavShell';
import Standings from '@/app/components/Standings';

export default function StandingsPage() {
  return (
    <NavShell>
      <div className="max-w-7xl mx-auto px-3 sm:px-6 py-4 sm:py-6">
        <Standings />
      </div>
    </NavShell>
  );
}
