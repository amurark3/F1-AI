"use client";

import { motion } from "framer-motion";
import { useState, useEffect } from "react";
import useSWR from "swr";

import { API_BASE } from "../constants/api";
import { fetcher } from "../utils/fetcher";

interface RaceEvent {
  round: number;
  name: string;
  location: string;
  date: string | null;
  sessions?: Record<string, string>;
  status: string;
}

/**
 * When the race actually starts, in epoch milliseconds.
 *
 * The schedule's `date` field is the event's calendar date at midnight UTC, not
 * a session time — counting down to it lands hours early (Hungary 2026: midnight
 * vs the 13:00Z start). The Race session carries the real lights-out time; `date`
 * is only a fallback for events whose sessions have not been published yet.
 *
 * Null when the backend published neither, or published a value the browser
 * cannot parse as a date.
 */
function raceStartMs(event: RaceEvent): number | null {
  const start = event.sessions?.Race ?? event.date;
  if (!start) return null;
  const ms = new Date(start).getTime();
  return Number.isNaN(ms) ? null : ms;
}

/**
 * The next race still to be run.
 *
 * Selected by race start time, never by weekend status: a weekend turns
 * `in_progress` the moment FP1 begins and stays that way until Sunday evening,
 * so filtering on `status === "upcoming"` skipped the race that was minutes from
 * starting and counted down to the *following* event instead.
 */
function findNextRace(schedule: RaceEvent[], nowMs: number): RaceEvent | null {
  return (
    schedule.find((event) => {
      const startMs = raceStartMs(event);
      return startMs !== null && startMs > nowMs;
    }) ?? null
  );
}

interface Countdown {
  days: number;
  hours: number;
  minutes: number;
  seconds: number;
}

function calcCountdown(targetMs: number, nowMs: number): Countdown {
  const diff = targetMs - nowMs;
  if (diff <= 0) return { days: 0, hours: 0, minutes: 0, seconds: 0 };
  return {
    days: Math.floor(diff / 86_400_000),
    hours: Math.floor((diff % 86_400_000) / 3_600_000),
    minutes: Math.floor((diff % 3_600_000) / 60_000),
    seconds: Math.floor((diff % 60_000) / 1_000),
  };
}

const UNITS = ["DAYS", "HRS", "MIN", "SEC"] as const;

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

export default function RaceCountdown() {
  const year = new Date().getFullYear();

  const { data: schedule } = useSWR<RaceEvent[]>(`${API_BASE}/api/schedule/${year}`, fetcher, {
    revalidateOnFocus: false,
    dedupingInterval: 300_000,
  });

  // One clock drives both halves: which race is next, and how long until it
  // starts. Re-selecting on every tick lets the card roll over to the following
  // event by itself the moment the current race goes green.
  const now = useNowMs();
  const nextRace = schedule && now !== null ? findNextRace(schedule, now) : null;
  const startMs = nextRace ? raceStartMs(nextRace) : null;

  if (!nextRace || startMs === null || now === null) return null;

  const countdown = calcCountdown(startMs, now);
  const values = [countdown.days, countdown.hours, countdown.minutes, countdown.seconds];

  return (
    <motion.div
      initial={{ opacity: 0, y: -12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
      className="glass rounded-xl overflow-hidden mb-6"
    >
      {/* Red accent stripe */}
      <div className="h-[3px]" style={{ background: "linear-gradient(90deg, #E10600, #FF4422 60%, transparent)" }} />

      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 px-4 sm:px-6 py-4">
        {/* Race info */}
        <div className="flex items-start gap-3">
          <span
            className="h-[8px] w-[8px] rounded-full mt-1.5 shrink-0 animate-glow-pulse"
            style={{ background: "#E10600" }}
          />
          <div>
            <div
              className="text-[10px] font-black uppercase tracking-[0.2em] mb-1"
              style={{ color: "#E10600", fontFamily: "var(--font-barlow, var(--font-geist-sans))" }}
            >
              Next Race — Round {nextRace.round}
            </div>
            <h3
              className="text-xl sm:text-2xl font-black italic uppercase tracking-tight text-white leading-none"
              style={{ fontFamily: "var(--font-barlow, var(--font-geist-sans))" }}
            >
              {nextRace.name}
            </h3>
            <p className="text-xs text-neutral-500 mt-1">{nextRace.location}</p>
          </div>
        </div>

        {/* Countdown digits */}
        <div className="flex items-end gap-1 sm:gap-2 shrink-0">
          {values.map((val, i) => (
            <div key={UNITS[i]} className="flex flex-col items-center">
              <motion.div
                key={val}
                initial={{ y: -6, opacity: 0 }}
                animate={{ y: 0, opacity: 1 }}
                transition={{ duration: 0.18 }}
                className="text-3xl sm:text-4xl font-black font-mono tabular-nums text-white leading-none"
                style={{ fontFamily: "var(--font-barlow, var(--font-geist-sans))" }}
              >
                {String(val).padStart(2, "0")}
              </motion.div>
              <div
                className="text-[9px] font-black uppercase tracking-widest mt-1"
                style={{ color: "#525252", fontFamily: "var(--font-barlow, var(--font-geist-sans))" }}
              >
                {UNITS[i]}
              </div>
              {/* separator colon (not after last) */}
              {i < 3 && (
                <span
                  className="absolute text-2xl font-black text-neutral-700 animate-pit-blink"
                  style={{ marginLeft: "calc(100% + 2px)", marginTop: "-4px" }}
                />
              )}
            </div>
          ))}
        </div>
      </div>
    </motion.div>
  );
}
