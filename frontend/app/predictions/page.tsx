"use client";

import NavShell from '@/app/components/NavShell';
import PredictionPanel from '@/app/components/PredictionPanel';

export default function PredictionsPage() {
  return (
    <NavShell>
      <div className="max-w-7xl mx-auto px-3 sm:px-6 py-4 sm:py-6">
        <PredictionPanel />
      </div>
    </NavShell>
  );
}
