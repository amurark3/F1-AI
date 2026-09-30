"use client";

import { useEffect, useState } from "react";

import RaceCountdown from "@/app/components/RaceCountdown";

interface WeekendCountdownProps {
  /** Session name to UTC start time, for the weekend currently under way. */
  sessions: Record<string, string> | null;
  /** The weekend these sessions belong to, shown above the clock. */
  weekendName: string | null;
}

interface NextSession {
  label: string;
  startMs: number;
}

interface Countdown {
  days: number;
  hours: number;
  minutes: number;
  seconds: number;
}

const UNITS = ["DAYS", "HRS", "MIN", "SEC"] as const;

/** The earliest session of this weekend still ahead of `nowMs`. */
function findNextSession(sessions: Record<string, string>, nowMs: number): NextSession | null {
  return (
    Object.entries(sessions)
      .map(([label, iso]) => ({ label, startMs: new Date(iso).getTime() }))
      .filter((session) => !Number.isNaN(session.startMs) && session.startMs > nowMs)
      .sort((a, b) => a.startMs - b.startMs)[0] ?? null
  );
}

function calcCountdown(targetMs: number, nowMs: number): Countdown {
  const diff = Math.max(0, targetMs - nowMs);
  return {
    days: Math.floor(diff / 86_400_000),
    hours: Math.floor((diff % 86_400_000) / 3_600_000),
    minutes: Math.floor((diff % 3_600_000) / 60_000),
    seconds: Math.floor((diff % 60_000) / 1_000),
  };
}

/** Epoch milliseconds, ticking once a second. Null until the first tick lands. */
function useNowMs(): number | null {
  const [now, setNow] = useState<number | null>(null);

  useEffect(() => {
    const tick = () => setNow(Date.now());
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);

  return now;
}

/**
 * What the live desk counts down to.
 *
 * A race weekend has five sessions across three days, so counting to the next
 * *race* is wrong for most of it: mid-Spanish-GP the desk advertised Baku in
 * twelve days. While any session of this weekend is still to come, that is the
 * clock the desk needs; once the chequered flag falls, the next race is.
 */
export default function WeekendCountdown({ sessions, weekendName }: WeekendCountdownProps) {
  const now = useNowMs();
  const next = sessions && now !== null ? findNextSession(sessions, now) : null;

  if (now === null) return null;
  if (!next) return <RaceCountdown />;

  const countdown = calcCountdown(next.startMs, now);
  const values = [countdown.days, countdown.hours, countdown.minutes, countdown.seconds];

  return (
    <div className="glass mb-6 overflow-hidden rounded-xl">
      <div className="h-[3px]" style={{ background: "linear-gradient(90deg, #3671C6, #4F8FE0 60%, transparent)" }} />

      <div className="flex flex-col items-start justify-between gap-4 px-4 py-4 sm:flex-row sm:items-center sm:px-6">
        <div className="flex items-start gap-3">
          <span className="mt-1.5 h-[8px] w-[8px] shrink-0 rounded-full bg-[#3671C6]" />
          <div>
            <div
              className="mb-1 text-[10px] font-black uppercase tracking-[0.2em]"
              style={{ color: "#3671C6", fontFamily: "var(--font-barlow, var(--font-geist-sans))" }}
            >
              Next Session
            </div>
            <h3
              className="text-xl font-black italic uppercase leading-none tracking-tight text-white sm:text-2xl"
              style={{ fontFamily: "var(--font-barlow, var(--font-geist-sans))" }}
            >
              {next.label}
            </h3>
            {weekendName && <p className="mt-1 text-xs text-neutral-500">{weekendName}</p>}
          </div>
        </div>

        <div className="flex shrink-0 items-end gap-1 sm:gap-2">
          {values.map((val, i) => (
            <div key={UNITS[i]} className="flex flex-col items-center">
              <div
                className="font-mono text-3xl font-black leading-none tabular-nums text-white sm:text-4xl"
                style={{ fontFamily: "var(--font-barlow, var(--font-geist-sans))" }}
              >
                {String(val).padStart(2, "0")}
              </div>
              <div
                className="mt-1 text-[9px] font-black uppercase tracking-widest"
                style={{ color: "#525252", fontFamily: "var(--font-barlow, var(--font-geist-sans))" }}
              >
                {UNITS[i]}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
