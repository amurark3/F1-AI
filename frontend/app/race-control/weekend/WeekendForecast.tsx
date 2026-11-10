"use client";

import { ArrowUp, Check, CloudSun } from "lucide-react";

import { LocalTime } from "@/app/components/LocalTime";
import { formatUtc } from "@/app/lib/formatTime";
import { AnimatedNumber } from "@/app/ui/AnimatedNumber";

import { Panel, StatusPill, rcFont } from "../components/RaceControlPrimitives";

import { WeatherGlyph } from "./WeatherGlyph";
import { ambienceFor, compassPoint, railFill, rainColor, summariseWeekend, type Ambience } from "./weekendModel";

import type { SessionForecast, SessionPhase, SessionWeather, SessionWeatherRow } from "./weekendTypes";
import type { CSSProperties } from "react";

const RACE = "Race";
const stagger = (index: number, step = 0.08): CSSProperties => ({ animationDelay: `${index * step}s` });

/* -- ambient backdrops ---------------------------------------------------- */

const NIGHT_STARS = [
  { left: "14%", top: "18%", wait: 0 },
  { left: "72%", top: "12%", wait: 0.8 },
  { left: "86%", top: "34%", wait: 1.6 },
  { left: "40%", top: "8%", wait: 2.1 },
];

function Ambient({ ambience }: { ambience: Ambience }) {
  switch (ambience) {
    case "sun":
      return (
        <div className="pointer-events-none absolute -right-10 -top-10 h-36 w-36 rounded-full bg-[#FFC93C]/20 blur-2xl motion-safe:animate-wx-glow" />
      );
    case "night":
      return (
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-[#1B2440]/70 to-transparent">
          {NIGHT_STARS.map((star) => (
            <span
              key={star.left}
              className="absolute h-[3px] w-[3px] rounded-full bg-white motion-safe:animate-wx-twinkle"
              style={{ left: star.left, top: star.top, animationDelay: `${star.wait}s` }}
            />
          ))}
        </div>
      );
    case "rain":
    case "storm":
      return (
        <>
          <div className="wx-rain-streaks pointer-events-none absolute inset-0 opacity-80 motion-safe:animate-wx-rain" />
          {ambience === "storm" && (
            <div className="pointer-events-none absolute inset-0 bg-[#FFF200]/[0.06] opacity-0 motion-safe:animate-wx-flash" />
          )}
        </>
      );
    case "cloud":
    case "snow":
      return (
        <div className="pointer-events-none absolute inset-0 bg-gradient-to-b from-[#97A3B8]/[0.09] to-transparent" />
      );
    default:
      return null;
  }
}

/* -- one session ---------------------------------------------------------- */

const PHASE_TAG: Record<SessionPhase, { label: string; color: string }> = {
  done: { label: "Done · model", color: "#7F8797" },
  live: { label: "Live", color: "#FF4655" },
  upcoming: { label: "Forecast", color: "#4C8DFF" },
};

function PhaseTag({ phase }: { phase: SessionPhase }) {
  const tag = PHASE_TAG[phase];
  return (
    <span
      className="inline-flex items-center gap-1.5 font-mono text-[9px] font-bold uppercase tracking-[0.16em]"
      style={{ color: tag.color }}
    >
      {phase === "live" && <span className="h-1.5 w-1.5 rounded-full bg-[#FF4655] motion-safe:animate-pulse" />}
      {phase === "done" && <Check className="h-3 w-3" aria-hidden="true" />}
      {tag.label}
    </span>
  );
}

function RainBar({ pct, precipitation, index }: { pct: number | null; precipitation: number | null; index: number }) {
  const color = rainColor(pct);
  return (
    <div className="mt-4">
      <div className="flex items-baseline justify-between font-mono text-[10px] uppercase tracking-[0.14em] text-[#7F8797]">
        <span>
          Rain
          {precipitation !== null && precipitation > 0 && (
            <span className="ml-1 normal-case">· {precipitation} mm</span>
          )}
        </span>
        <span className="text-xs font-bold" style={{ color }}>
          {pct === null ? "—" : `${pct}%`}
        </span>
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/10">
        <div
          className="h-full origin-left rounded-full motion-safe:animate-fill-x"
          style={{
            width: `${pct ?? 0}%`,
            background: color,
            boxShadow: `0 0 10px ${color}66`,
            ...stagger(index, 0.12),
          }}
        />
      </div>
    </div>
  );
}

function WindReading({ kph, degrees }: { kph: number | null; degrees: number | null }) {
  const from = compassPoint(degrees);
  return (
    <div className="min-w-0">
      <dt className="text-[9px] uppercase tracking-[0.14em] text-[#6F7789]">Wind</dt>
      <dd className="mt-0.5 flex items-center gap-1 text-white">
        {degrees !== null && (
          // The arrow points where the wind is going: 180° from where it blows from.
          <span className="inline-flex" style={{ transform: `rotate(${degrees + 180}deg)` }} aria-hidden="true">
            <ArrowUp className="h-3.5 w-3.5 origin-center text-[#9FB4D6] motion-safe:animate-wx-sway" />
          </span>
        )}
        <span className="truncate">{kph === null ? "—" : `${Math.round(kph)}`}</span>
        <span className="text-[#6F7789]">{from ?? ""}</span>
      </dd>
    </div>
  );
}

function Reading({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[9px] uppercase tracking-[0.14em] text-[#6F7789]">{label}</dt>
      <dd className="mt-0.5 truncate text-white">{value}</dd>
    </div>
  );
}

const reading = (value: number | null, unit: string, prefix = "") =>
  value === null ? "—" : `${prefix}${Math.round(value)}${unit}`;

function ForecastBody({ forecast, index }: { forecast: SessionForecast; index: number }) {
  return (
    <>
      <div className="mt-3 flex items-center gap-3">
        <WeatherGlyph condition={forecast.condition} isDay={forecast.is_day} size={58} />
        <div className="min-w-0">
          <p className="text-3xl font-black leading-none text-white" style={rcFont}>
            {forecast.air_temp_c === null ? "—" : <AnimatedNumber value={Math.round(forecast.air_temp_c)} />}
            <span className="text-lg text-[#8E96A8]">°C</span>
          </p>
          <p className="mt-1 line-clamp-2 text-xs leading-tight text-[#AEB6C6]">{forecast.label}</p>
        </div>
      </div>
      <RainBar pct={forecast.rain_probability_pct} precipitation={forecast.precipitation_mm} index={index} />
      <dl className="mt-3 grid grid-cols-3 gap-2 font-mono text-[11px]">
        <WindReading kph={forecast.wind_kph} degrees={forecast.wind_direction_deg} />
        <Reading label="Track" value={reading(forecast.track_temp_c, "°", "~")} />
        <Reading label="Humidity" value={reading(forecast.humidity_pct, "%")} />
      </dl>
    </>
  );
}

function NoForecast({ opens }: { opens: string | null }) {
  return (
    <div className="mt-3 flex min-h-[148px] flex-col items-center justify-center gap-2 rounded-md border border-dashed border-white/10 text-center">
      <CloudSun className="h-7 w-7 text-[#3A4254]" aria-hidden="true" />
      <p className="px-2 text-xs text-[#7F8797]">
        {opens ? `Forecast opens ${formatUtc(opens, "dayShort", opens)}` : "No forecast for this session"}
      </p>
    </div>
  );
}

function SessionCard({ row, index }: { row: SessionWeatherRow; index: number }) {
  const isRace = row.name === RACE;
  const ambience = row.forecast ? ambienceFor(row.forecast.condition, row.forecast.is_day) : "none";
  const frame = isRace
    ? "border-[#E10600]/50 bg-[#E10600]/[0.05] shadow-[0_0_32px_rgba(225,6,0,0.10)]"
    : "border-white/10 bg-white/[0.025]";
  return (
    <article
      className={`relative min-w-0 overflow-hidden rounded-lg border p-4 motion-safe:animate-fade-up ${frame} ${row.phase === "done" ? "opacity-75" : ""}`}
      style={stagger(index)}
    >
      <Ambient ambience={ambience} />
      <div className="relative">
        <div className="flex items-center justify-between gap-2">
          <p
            className={`truncate font-mono text-[10px] font-bold uppercase tracking-[0.18em] ${isRace ? "text-[#FF4655]" : "text-[#B7BDCA]"}`}
          >
            {row.name}
          </p>
          <PhaseTag phase={row.phase} />
        </div>
        <p className="mt-1 text-sm font-bold text-white">
          <LocalTime value={row.starts_at} style="weekday" fallback="No date" />
        </p>
        <p className="font-mono text-[11px] text-[#7F8797]">
          <LocalTime value={row.starts_at} style="time" fallback="No time" />
        </p>
        {row.forecast ? (
          <ForecastBody forecast={row.forecast} index={index} />
        ) : (
          <NoForecast opens={row.forecast_opens} />
        )}
      </div>
    </article>
  );
}

/* -- the weekend ---------------------------------------------------------- */

const RAIL_NODE: Record<SessionPhase, string> = {
  done: "border-[#00FF78] bg-[#00FF78]",
  live: "border-[#FF4655] bg-[#FF4655] motion-safe:animate-pulse",
  upcoming: "border-[#3A4254] bg-[#0D111B]",
};

/** The weekend as a line through the sessions, filled up to now. Wide screens only. */
function WeekendRail({ rows }: { rows: SessionWeatherRow[] }) {
  const phases = rows.map((row) => row.phase);
  const inset = `${50 / rows.length}%`;
  return (
    <div className="relative mb-3 hidden h-4 lg:block" aria-hidden="true">
      <div className="absolute top-1/2 h-[2px] -translate-y-1/2 bg-white/10" style={{ left: inset, right: inset }}>
        <div
          className="h-full origin-left bg-gradient-to-r from-[#00FF78] to-[#00FF78]/60 motion-safe:animate-fill-x"
          style={{ width: `${railFill(phases) * 100}%` }}
        />
      </div>
      <div className="absolute inset-0 grid" style={{ gridTemplateColumns: `repeat(${rows.length}, minmax(0, 1fr))` }}>
        {rows.map((row) => (
          <span key={row.name} className="flex items-center justify-center">
            <span className={`h-3 w-3 rounded-full border-2 ${RAIL_NODE[row.phase]}`} />
          </span>
        ))}
      </div>
    </div>
  );
}

function SummaryChips({ sessions }: { sessions: SessionWeatherRow[] }) {
  const { wettest, coolest, warmest } = summariseWeekend(sessions);
  const race = sessions.find((row) => row.name === RACE)?.forecast;
  const wettestRain = wettest?.forecast?.rain_probability_pct ?? null;
  const chip = "rounded-full border border-white/10 bg-white/[0.03] px-3 py-1 text-xs text-[#AEB6C6]";
  return (
    <div className="mb-4 flex flex-wrap gap-2">
      {race && (
        <span className={chip}>
          Race day: <b className="text-white">{race.label}</b>
          {race.rain_probability_pct !== null && (
            <b style={{ color: rainColor(race.rain_probability_pct) }}> · {race.rain_probability_pct}% rain</b>
          )}
        </span>
      )}
      {wettest && wettestRain !== null && (
        <span className={chip}>
          Wettest: <b className="text-white">{wettest.name}</b>{" "}
          <b style={{ color: rainColor(wettestRain) }}>{wettestRain}%</b>
        </span>
      )}
      {coolest !== null && warmest !== null && (
        <span className={chip}>
          <b className="text-white">
            {Math.round(coolest)}–{Math.round(warmest)}°C
          </b>{" "}
          across the weekend
        </span>
      )}
    </div>
  );
}

export function WeekendForecast({ weather }: { weather: SessionWeather | null | undefined }) {
  const sessions = weather?.sessions ?? [];
  return (
    <Panel className="p-5 sm:p-6">
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-[#7F8797]" style={rcFont}>
            Weekend forecast
          </p>
          <h2 className="mt-1 text-xl font-semibold text-white sm:text-2xl" style={rcFont}>
            Weather, session by session
          </h2>
        </div>
        <div className="flex flex-wrap gap-2">
          {weather?.as_of_label && <StatusPill>{weather.as_of_label}</StatusPill>}
          <StatusPill color="#4C8DFF">Open-Meteo · hourly</StatusPill>
        </div>
      </div>

      {sessions.length === 0 ? (
        <p className="text-sm text-[#7F8797]">{weather?.note ?? "Session times are not published yet."}</p>
      ) : (
        <>
          <SummaryChips sessions={sessions} />
          <WeekendRail rows={sessions} />
          <div
            className="grid gap-3 sm:grid-cols-2 lg:[grid-template-columns:repeat(var(--sessions),minmax(0,1fr))]"
            style={{ "--sessions": sessions.length } as CSSProperties}
          >
            {sessions.map((row, index) => (
              <SessionCard key={row.name} row={row} index={index} />
            ))}
          </div>
        </>
      )}

      <p className="mt-4 text-[11px] leading-relaxed text-[#6F7789]">
        {weather?.note && <span className="text-[#B7BDCA]">{weather.note} </span>}
        Each session reads the hours it runs through: worst-hour rain and wind, average temperature. Completed sessions
        show the model&apos;s reading for that hour, not trackside sensors; track temperature is estimated from air
        temperature and cloud. {weather?.attribution ?? "Weather data by Open-Meteo.com"}.
      </p>
    </Panel>
  );
}
