"use client";

import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown, Timer } from "lucide-react";
import { useState, useEffect } from "react";
import useSWR from "swr";

import { API_BASE } from "../constants/api";
import { fetcherWithTimeout } from "../utils/fetcher";

import { getFlag } from "./RaceCalendar";
import { CompletedRaceResults, type CircuitInfo, type RaceDetail, type ResultTab } from "./raceResultTabs";
import TrackInsights from "./TrackInsights";

type Session = Record<string, string>;
interface RaceEvent {
  round: number;
  name: string;
  location: string;
  date: string | null;
  sessions: Session;
  status: string;
  circuit: CircuitInfo | null;
  is_sprint?: boolean;
}

interface RaceCardProps {
  race: RaceEvent;
  year: number;
  timezone: string;
  isNext: boolean;
  expanded: boolean;
  onToggle: () => void;
  isLastRow: boolean;
}

const parseDate = (s: string | null | undefined): Date | null => {
  if (!s) return null;
  return new Date(/Z$|[+-]\d{2}:\d{2}$/.test(s) ? s : `${s}Z`);
};

/** Left-border accent colour for a race row, by status. */
function accentForStatus({
  isInProgress,
  isNext,
  isCompleted,
}: {
  isInProgress: boolean;
  isNext: boolean;
  isCompleted: boolean;
}): string {
  if (isInProgress || isNext) return "#E10600";
  if (isCompleted) return "transparent";
  return "rgba(255,255,255,0.08)";
}

/** Session-name styling: struck-through when done, accented for the race. */
function sessionLabelClass(done: boolean, isRace: boolean): string {
  if (done) return "text-neutral-700 line-through";
  return isRace ? "" : "text-neutral-400";
}

const formatTime = (s: string | undefined, tz: string) => {
  const d = parseDate(s);
  if (!d) return "–";
  return new Intl.DateTimeFormat("en-US", { hour: "2-digit", minute: "2-digit", timeZone: tz, hour12: false }).format(
    d,
  );
};

const formatSessionDay = (s: string, tz: string) =>
  new Intl.DateTimeFormat("en-GB", { weekday: "short", day: "numeric", month: "short", timeZone: tz })
    .format(parseDate(s) ?? new Date())
    .toUpperCase();

const getDateRange = (race: RaceEvent, tz: string): string => {
  const dates = Object.values(race.sessions)
    .map(parseDate)
    .filter((d): d is Date => d !== null);
  if (dates.length === 0) {
    const d = parseDate(race.date);
    return d
      ? new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: tz }).format(d).toUpperCase()
      : "";
  }
  dates.sort((a, b) => a.getTime() - b.getTime());
  const fmt = (d: Date) =>
    new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: tz }).formatToParts(d);
  const s = fmt(dates[0]);
  const e = fmt(dates[dates.length - 1]);
  const sd = s.find((p) => p.type === "day")?.value;
  const sm = s.find((p) => p.type === "month")?.value?.toUpperCase();
  const ed = e.find((p) => p.type === "day")?.value;
  const em = e.find((p) => p.type === "month")?.value?.toUpperCase();
  const yr = new Intl.DateTimeFormat("en-GB", { year: "numeric", timeZone: tz }).format(dates[dates.length - 1]);
  return sm === em ? `${sd}–${ed} ${em} ${yr}` : `${sd} ${sm} – ${ed} ${em} ${yr}`;
};

const shortName = (n: string) =>
  n
    .replace("Practice 1", "FP1")
    .replace("Practice 2", "FP2")
    .replace("Practice 3", "FP3")
    .replace("Qualifying", "QUALI")
    .replace("Sprint Qualifying", "SQ")
    .replace("Sprint", "SPRINT")
    .toUpperCase();

/* ── Status badge ─────────────────────────────────────────── */
function StatusBadge({ status, isNext }: { status: string; isNext: boolean }) {
  if (status === "in_progress")
    return (
      <span
        className="flex items-center gap-1.5 text-[10px] font-black uppercase tracking-widest px-2.5 py-1 rounded"
        style={{
          background: "rgba(225,6,0,0.15)",
          color: "#E10600",
          fontFamily: "var(--font-barlow, var(--font-geist-sans))",
        }}
      >
        <span className="h-[6px] w-[6px] rounded-full animate-glow-pulse" style={{ background: "#E10600" }} />
        Live
      </span>
    );
  if (isNext && status === "upcoming")
    return (
      <span
        className="text-[10px] font-black uppercase tracking-widest px-2.5 py-1 rounded"
        style={{
          background: "rgba(225,6,0,0.12)",
          color: "#E10600",
          border: "1px solid rgba(225,6,0,0.25)",
          fontFamily: "var(--font-barlow, var(--font-geist-sans))",
        }}
      >
        Next
      </span>
    );
  if (status === "upcoming")
    return (
      <span
        className="text-[10px] font-black uppercase tracking-widest px-2.5 py-1 rounded text-neutral-500 border border-white/8"
        style={{ fontFamily: "var(--font-barlow, var(--font-geist-sans))" }}
      >
        Upcoming
      </span>
    );
  return (
    <span
      className="text-[10px] font-black uppercase tracking-widest px-2.5 py-1 rounded text-neutral-700 hidden sm:inline-block"
      style={{ fontFamily: "var(--font-barlow, var(--font-geist-sans))" }}
    >
      Done
    </span>
  );
}

export default function RaceCard({ race, year, timezone, isNext, expanded, onToggle, isLastRow }: RaceCardProps) {
  const [resultTab, setResultTab] = useState<ResultTab>("race");

  // Only fetch details once the row has been expanded at least once and race is done
  const [hasExpanded, setHasExpanded] = useState(false);

  const isCompleted = race.status === "completed";
  const isInProgress = race.status === "in_progress";
  const isUpcoming = race.status === "upcoming";

  const shouldFetch = hasExpanded && isCompleted;
  const {
    data: detail,
    isLoading: detailLoading,
    error: detailError,
    mutate: retryDetail,
  } = useSWR<RaceDetail, Error>(shouldFetch ? `${API_BASE}/api/race/${year}/${race.round}` : null, fetcherWithTimeout, {
    revalidateOnFocus: false,
    dedupingInterval: 300000,
    shouldRetryOnError: false,
  });

  const circuitInfo = detail?.circuit ?? race.circuit;

  const handleToggle = () => {
    if (!expanded) setHasExpanded(true);
    onToggle();
  };

  const [countdown, setCountdown] = useState("");
  useEffect(() => {
    if (!isUpcoming) return;
    const target = parseDate(race.sessions.Race || race.date);
    if (!target) return;
    const tick = () => {
      const diff = target.getTime() - Date.now();
      if (diff <= 0) {
        setCountdown("NOW");
        return;
      }
      const d = Math.floor(diff / 86400000);
      const h = Math.floor((diff % 86400000) / 3600000);
      const m = Math.floor((diff % 3600000) / 60000);
      setCountdown(d > 0 ? `${d}d ${h}h` : `${h}h ${m}m`);
    };
    tick();
    const id = setInterval(tick, 60000);
    return () => clearInterval(id);
  }, [isUpcoming, race.sessions, race.date]);

  const dateRange = getDateRange(race, timezone);
  const flag = getFlag(race.location);
  const isCompleted_dim = isCompleted && !isNext;

  /* ── Left accent colour based on status ─────────────────── */
  const accentColor = accentForStatus({ isInProgress, isNext, isCompleted });

  return (
    <div id={`race-${race.round}`} className={`relative ${!isLastRow ? "border-b border-white/4" : ""}`}>
      {/* Left status stripe */}
      <div className="absolute left-0 top-0 bottom-0 w-[3px]" style={{ background: accentColor }} />

      {/* ── Compact row ──────────────────────────── */}
      <RaceCardCompactRow
        race={race}
        flag={flag}
        dateRange={dateRange}
        expanded={expanded}
        dimmed={isCompleted_dim}
        isNext={isNext}
        isInProgress={isInProgress}
        isUpcoming={isUpcoming}
        countdown={countdown}
        onToggle={handleToggle}
      />

      {/* ── Expandable detail panel ──────────────── */}
      <AnimatePresence initial={false}>
        {expanded && (
          <RaceCardDetailPanel
            race={race}
            timezone={timezone}
            circuitInfo={circuitInfo}
            isUpcoming={isUpcoming}
            isInProgress={isInProgress}
            isCompleted={isCompleted}
            countdown={countdown}
            detail={detail}
            detailLoading={detailLoading}
            detailError={Boolean(detailError)}
            onRetry={() => void retryDetail()}
            resultTab={resultTab}
            onSelectTab={setResultTab}
          />
        )}
      </AnimatePresence>
    </div>
  );
}

interface RaceCardCompactRowProps {
  race: RaceEvent;
  flag: string;
  dateRange: string;
  expanded: boolean;
  dimmed: boolean;
  isNext: boolean;
  isInProgress: boolean;
  isUpcoming: boolean;
  countdown: string;
  onToggle: () => void;
}

function RaceCardCompactRow({
  race,
  flag,
  dateRange,
  expanded,
  dimmed,
  isNext,
  isInProgress,
  isUpcoming,
  countdown,
  onToggle,
}: RaceCardCompactRowProps) {
  return (
    <button
      onClick={onToggle}
      className={`w-full flex items-center gap-2 sm:gap-3 pl-5 pr-4 py-3 sm:py-3.5 text-left
        transition-colors duration-150 hover:bg-white/3
        ${expanded ? "bg-white/3" : ""}
        ${dimmed ? "opacity-60 hover:opacity-100" : ""}
      `}
    >
      {/* Round */}
      <div className="shrink-0 w-10 text-center">
        <div
          className="text-[10px] font-black uppercase tracking-widest leading-none"
          style={{
            color: isNext || isInProgress ? "#E10600" : "#404040",
            fontFamily: "var(--font-barlow, var(--font-geist-sans))",
          }}
        >
          R{String(race.round).padStart(2, "0")}
        </div>
        {race.is_sprint && (
          <div className="text-[8px] font-black uppercase tracking-widest mt-0.5" style={{ color: "#FFF200" }}>
            Sprint
          </div>
        )}
      </div>

      {/* Flag */}
      <span className="text-xl leading-none shrink-0">{flag}</span>

      {/* Name + location */}
      <div className="flex-1 min-w-0">
        <p
          className={`text-sm font-black uppercase tracking-tight truncate leading-tight ${
            dimmed ? "text-neutral-400" : "text-white"
          }`}
          style={{ fontFamily: "var(--font-barlow, var(--font-geist-sans))" }}
        >
          {race.name}
        </p>
        <p className="text-[10px] text-neutral-600 truncate mt-0.5">{race.location}</p>
      </div>

      {/* Date range — hidden on smallest screens */}
      <span className="hidden md:block text-[10px] font-mono text-neutral-600 shrink-0 w-36 text-right">
        {dateRange}
      </span>

      {/* Countdown for next race */}
      {isUpcoming && countdown && isNext && (
        <span
          className="hidden sm:block text-[11px] font-black font-mono shrink-0"
          style={{ color: "#E10600", fontFamily: "var(--font-barlow, var(--font-geist-sans))" }}
        >
          {countdown}
        </span>
      )}

      {/* Status badge */}
      <div className="shrink-0">
        <StatusBadge status={race.status} isNext={isNext} />
      </div>

      {/* Chevron */}
      <ChevronDown
        className={`w-4 h-4 shrink-0 text-neutral-600 transition-transform duration-200 ${expanded ? "rotate-180" : ""}`}
      />
    </button>
  );
}

interface RaceCardDetailPanelProps {
  race: RaceEvent;
  timezone: string;
  circuitInfo: CircuitInfo | null;
  isUpcoming: boolean;
  isInProgress: boolean;
  isCompleted: boolean;
  countdown: string;
  detail?: RaceDetail;
  detailLoading: boolean;
  detailError: boolean;
  onRetry: () => void;
  resultTab: ResultTab;
  onSelectTab: (tab: ResultTab) => void;
}

function RaceCardDetailPanel({
  race,
  timezone,
  circuitInfo,
  isUpcoming,
  isInProgress,
  isCompleted,
  countdown,
  detail,
  detailLoading,
  detailError,
  onRetry,
  resultTab,
  onSelectTab,
}: RaceCardDetailPanelProps) {
  return (
    <motion.div
      initial={{ height: 0, opacity: 0 }}
      animate={{ height: "auto", opacity: 1 }}
      exit={{ height: 0, opacity: 0 }}
      transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
      className="overflow-hidden"
    >
      <div className="border-t border-white/5 px-5 py-5 space-y-5">
        {/* Session schedule + circuit side by side */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
          {/* Sessions */}
          <SessionScheduleList sessions={race.sessions} timezone={timezone} />

          {/* Circuit info */}
          {circuitInfo && <TrackInsights circuit={circuitInfo} />}
        </div>

        {/* Countdown banner for upcoming */}
        {isUpcoming && countdown && (
          <div className="glass rounded-xl p-4 flex items-center gap-4">
            <Timer className="h-4 w-4 shrink-0" style={{ color: "#E10600" }} />
            <div>
              <p
                className="text-[10px] font-black uppercase tracking-widest text-neutral-500 mb-0.5"
                style={{ fontFamily: "var(--font-barlow, var(--font-geist-sans))" }}
              >
                Lights Out In
              </p>
              <p
                className="text-2xl font-black font-mono text-white"
                style={{ fontFamily: "var(--font-barlow, var(--font-geist-sans))" }}
              >
                {countdown}
              </p>
            </div>
          </div>
        )}

        {/* In progress */}
        {isInProgress && (
          <div className="glass rounded-xl p-4 flex items-center gap-3">
            <span className="h-2 w-2 rounded-full animate-glow-pulse shrink-0" style={{ background: "#E10600" }} />
            <p className="text-sm text-neutral-400">
              Race weekend in progress — check back after the race for full results.
            </p>
          </div>
        )}

        {/* Completed race results */}
        {isCompleted && (
          <CompletedRaceResults
            detail={detail}
            detailLoading={detailLoading}
            detailError={detailError}
            onRetry={onRetry}
            resultTab={resultTab}
            onSelectTab={onSelectTab}
          />
        )}
      </div>
    </motion.div>
  );
}

function SessionScheduleList({ sessions, timezone }: { sessions: Session; timezone: string }) {
  const now = new Date();
  return (
    <div>
      <p
        className="text-[10px] font-black uppercase tracking-[0.18em] text-neutral-600 mb-2"
        style={{ fontFamily: "var(--font-barlow, var(--font-geist-sans))" }}
      >
        Schedule
      </p>
      <div className="space-y-1.5">
        {Object.entries(sessions).map(([name, time]) => {
          const parsed = parseDate(time);
          const done = parsed ? parsed < now : false;
          const isRace = name === "Race";
          return (
            <div key={name} className="flex items-center justify-between gap-2">
              <span
                className={`text-[11px] font-black uppercase w-14 shrink-0 ${sessionLabelClass(done, isRace)}`}
                style={
                  isRace && !done
                    ? { color: "#E10600", fontFamily: "var(--font-barlow, var(--font-geist-sans))" }
                    : { fontFamily: "var(--font-barlow, var(--font-geist-sans))" }
                }
              >
                {shortName(name)}
              </span>
              <span className={`text-[10px] ${done ? "text-neutral-700" : "text-neutral-500"}`}>
                {formatSessionDay(time, timezone)}
              </span>
              <span
                className={`font-mono text-[11px] px-1.5 py-0.5 rounded tabular-nums ${
                  done ? "text-neutral-700" : "text-white bg-white/5"
                }`}
              >
                {formatTime(time, timezone)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
