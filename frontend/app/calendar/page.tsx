"use client";

import NavShell from '@/app/components/NavShell';
import RaceCalendar from '@/app/components/RaceCalendar';

export default function CalendarPage() {
  return (
    <NavShell>
      <div className="max-w-7xl mx-auto px-3 sm:px-6 py-4 sm:py-6">
        <RaceCalendar />
      </div>
    </NavShell>
  );
}
