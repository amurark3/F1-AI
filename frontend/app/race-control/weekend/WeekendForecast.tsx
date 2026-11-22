"use client";

import { ArrowUp, Check, CloudSun } from "lucide-react";

import { LocalTime } from "@/app/components/LocalTime";
import { formatUtc } from "@/app/lib/formatTime";
import { AnimatedNumber } from "@/app/ui/AnimatedNumber";
import { PanelHeading } from "@/app/ui/PanelHeading";

import { Panel } from "../components/RaceControlPrimitives";
import { StateTag } from "../grand-prix/StateTag";

import { MeasuredReadings } from "./MeasuredReadings";
import { WeatherGlyph } from "./WeatherGlyph";
import { compassPoint, railFill, rainColor, summariseWeekend } from "./weekendModel";

import type { SessionForecast, SessionPhase, SessionWeather, SessionWeatherRow } from "./weekendTypes";
import type { CSSProperties } from "react";

const RACE = "Race";
const stagger = (index: number, step = 0.08): CSSProperties => ({ animationDelay: `${index * step}s` });

/* -- one session ---------------------------------------------------------- */

const PHASE_TAG: Record<SessionPhase, { label: string; text: string }> = {
  done: { label: "Done · model", text: "text-rc-ink-3" },
  live: { label: "Live", text: "text-rc-red-text" },
  upcoming: { label: "Forecast", text: "text-rc-blue" },
};

function PhaseTag({ phase }: { phase: SessionPhase }) {
  const tag = PHASE_TAG[phase];
  return (
    <span
      className={`inline-flex items-center gap-1.5 font-mono text-[9px] font-semibold uppercase tracking-[0.16em] ${tag.text}`}
    >
      {phase === "live" && <span className="h-1.5 w-1.5 rounded-full bg-rc-red-text motion-safe:animate-pulse" />}
      {phase === "done" && <Check className="h-3 w-3" aria-hidden="true" />}
      {tag.label}
    </span>
  );
}

function RainBar({ pct, precipitation, index }: { pct: number | null; precipitation: number | null; index: number }) {
  const color = rainColor(pct);
  return (
    <div className="mt-4">
      <div className="flex items-baseline justify-between font-mono text-[10px] uppercase tracking-[0.14em] text-rc-ink-3">
        <span>
          Rain
          {precipitation !== null && precipitation > 0 && (
            <span className="ml-1 normal-case">· {precipitation} mm</span>
          )}
        </span>
        <span className="text-xs font-semibold" style={{ color }}>
          {pct === null ? "—" : `${pct}%`}
        </span>
      </div>
      <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/[0.06]">
        <div
          className="h-full origin-left rounded-full motion-safe:animate-fill-x"
          style={{ width: `${pct ?? 0}%`, background: color, ...stagger(index, 0.12) }}
        />
      </div>
    </div>
  );
}

function WindReading({ kph, degrees }: { kph: number | null; degrees: number | null }) {
  const from = compassPoint(degrees);
  return (
    <div className="min-w-0">
      <dt className="text-[9px] uppercase tracking-[0.14em] text-rc-ink-3">Wind</dt>
      <dd className="mt-0.5 flex items-center gap-1 text-rc-ink">
        {degrees !== null && (
          // The arrow points where the wind is going: 180° from where it blows from.
          <span className="inline-flex" style={{ transform: `rotate(${degrees + 180}deg)` }} aria-hidden="true">
            <ArrowUp className="h-3.5 w-3.5 origin-center text-rc-ink-2 motion-safe:animate-wx-sway" />
          </span>
        )}
        <span className="truncate">{kph === null ? "—" : `${Math.round(kph)}`}</span>
        <span className="text-rc-ink-3">{from ?? ""}</span>
      </dd>
    </div>
  );
}

function Reading({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <dt className="text-[9px] uppercase tracking-[0.14em] text-rc-ink-3">{label}</dt>
      <dd className="mt-0.5 truncate text-rc-ink">{value}</dd>
    </div>
  );
}

const reading = (value: number | null, unit: string, prefix = "") =>
  value === null ? "—" : `${prefix}${Math.round(value)}${unit}`;

function ForecastBody({ forecast, index }: { forecast: SessionForecast; index: number }) {
  return (
    <>
      <div className="mt-3 flex items-center gap-3">
        <WeatherGlyph condition={forecast.condition} isDay={forecast.is_day} size={48} />
        <div className="min-w-0">
          <p className="font-display text-[34px] font-extrabold leading-none text-rc-ink">
            {forecast.air_temp_c === null ? "—" : <AnimatedNumber value={Math.round(forecast.air_temp_c)} />}
            <span className="ml-0.5 text-[0.5em] text-rc-ink-3">°C</span>
          </p>
          <p className="mt-1 line-clamp-2 text-xs leading-tight text-rc-ink-2">{forecast.label}</p>
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
    <div className="mt-3 flex min-h-[148px] flex-col items-center justify-center gap-2 rounded-md border border-dashed border-rc-line text-center">
      <CloudSun className="h-7 w-7 text-rc-dim" aria-hidden="true" />
      <p className="px-2 text-xs text-rc-ink-3">
        {opens ? `Forecast opens ${formatUtc(opens, "dayShort", opens)}` : "No forecast for this session"}
      </p>
    </div>
  );
}

function SessionCard({ row, index }: { row: SessionWeatherRow; index: number }) {
  const isRace = row.name === RACE;
  return (
    <article
      className={`min-w-0 rounded-md border border-rc-line p-4 motion-safe:animate-fade-up ${isRace ? "border-t-2 border-t-f1-red" : ""}`}
      style={stagger(index)}
    >
      <div className="flex items-center justify-between gap-2">
        <p
          className={`truncate font-mono text-[10px] font-semibold uppercase tracking-[0.18em] ${isRace ? "text-rc-ink" : "text-rc-ink-2"}`}
        >
          {row.name}
        </p>
        <PhaseTag phase={row.phase} />
      </div>
      <p className="mt-1 text-[13px] font-semibold text-rc-ink">
        <LocalTime value={row.starts_at} style="weekday" fallback="No date" />
      </p>
      <p className="font-mono text-[11px] text-rc-ink-3">
        <LocalTime value={row.starts_at} style="time" fallback="No time" />
      </p>
      {row.forecast ? (
        <ForecastBody forecast={row.forecast} index={index} />
      ) : (
        <NoForecast opens={row.forecast_opens} />
      )}
      <MeasuredReadings row={row} />
    </article>
  );
}

/* -- the weekend ---------------------------------------------------------- */

const RAIL_NODE: Record<SessionPhase, string> = {
  done: "border-rc-ink-3 bg-rc-ink-3",
  live: "border-rc-red-text bg-rc-red-text motion-safe:animate-pulse",
  upcoming: "border-rc-line bg-(--surface)",
};

/** The weekend as a line through the sessions, filled up to now. Wide screens only. */
function WeekendRail({ rows }: { rows: SessionWeatherRow[] }) {
  const phases = rows.map((row) => row.phase);
  const inset = `${50 / rows.length}%`;
  return (
    <div className="relative mb-3 hidden h-4 lg:block" aria-hidden="true">
      <div className="absolute top-1/2 h-[2px] -translate-y-1/2 bg-rc-line" style={{ left: inset, right: inset }}>
        <div
          className="h-full origin-left bg-rc-ink-3 motion-safe:animate-fill-x"
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
  return (
    <p className="mb-4 flex flex-wrap gap-x-5 gap-y-1.5 text-[13px] text-rc-ink-2">
      {race && (
        <span>
          Race day: <b className="font-semibold text-rc-ink">{race.label}</b>
          {race.rain_probability_pct !== null && (
            <b className="font-semibold text-rc-ink"> · {race.rain_probability_pct}% rain</b>
          )}
        </span>
      )}
      {wettest && wettestRain !== null && (
        <span>
          Wettest: <b className="font-semibold text-rc-ink">{wettest.name}</b>{" "}
          <b className="font-semibold text-rc-ink">{wettestRain}%</b>
        </span>
      )}
      {coolest !== null && warmest !== null && (
        <span>
          <b className="font-semibold text-rc-ink">
            {Math.round(coolest)}–{Math.round(warmest)}°C
          </b>{" "}
          across the weekend
        </span>
      )}
    </p>
  );
}

export function WeekendForecast({ weather }: { weather: SessionWeather | null | undefined }) {
  const sessions = weather?.sessions ?? [];
  return (
    <Panel className="p-5 sm:p-6">
      <PanelHeading
        as="h2"
        eyebrow="Weekend forecast"
        title="Weather, session by session"
        aside={
          <div className="flex flex-wrap gap-2">
            {weather?.as_of_label && <StateTag>{weather.as_of_label}</StateTag>}
            <StateTag tone="blue">Open-Meteo · hourly</StateTag>
            {sessions.some((row) => row.measured) && <StateTag>OpenF1 · trackside</StateTag>}
          </div>
        }
      />

      {sessions.length === 0 ? (
        <p className="text-sm text-rc-ink-3">{weather?.note ?? "Session times are not published yet."}</p>
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

      <p className="mt-4 text-xs leading-relaxed text-rc-ink-3">
        {weather?.note && <span className="text-rc-ink-2">{weather.note} </span>}
        Each session reads the hours it runs through: worst-hour rain and wind, average temperature. The forecast&apos;s
        track temperature is estimated from air temperature and cloud. Trackside rows are OpenF1&apos;s circuit weather
        station, read about once a minute: track and air are the session average (track with its low–high), rain is
        whether any reading reported rainfall, never an amount.{" "}
        {weather?.attribution ?? "Weather data by Open-Meteo.com"}.
      </p>
    </Panel>
  );
}
