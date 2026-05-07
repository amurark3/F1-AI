"use client";

import RaceCalendar from '@/app/components/RaceCalendar';
import RaceCountdown from '@/app/components/RaceCountdown';

export default function CalendarPage() {
  return (
    <>
      <div className="max-w-4xl mx-auto px-4 sm:px-6 pt-5">
        <RaceCountdown />
      </div>
      <RaceCalendar />
    </>
  );
}
