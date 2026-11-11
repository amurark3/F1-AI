"use client";

import { WeatherGlyph } from "./WeatherGlyph";
import { rainColor } from "./weekendModel";

import type { SessionWeatherRow } from "./weekendTypes";

/** Session names as the timing screens abbreviate them. */
const SHORT_NAMES: Record<string, string> = {
  "Practice 1": "FP1",
  "Practice 2": "FP2",
  "Practice 3": "FP3",
  "Sprint Qualifying": "SQ",
  "Sprint Shootout": "SQ",
  Sprint: "Sprint",
  Qualifying: "Quali",
  Race: "Race",
};

/**
 * The weekend's weather in one line: a glyph, temperature and rain chance per session.
 * `asOf` is the stored forecast's label ("as of 14:05 UTC") when the live feed failed.
 */
export function SessionWeatherStrip({ rows, asOf }: { rows: SessionWeatherRow[]; asOf?: string | null }) {
  if (rows.length === 0) return null;
  return (
    <>
      <SessionCells rows={rows} />
      {asOf && <p className="mt-2 font-mono text-[10px] uppercase tracking-[0.14em] text-rc-ink-3">Forecast {asOf}</p>}
    </>
  );
}

function SessionCells({ rows }: { rows: SessionWeatherRow[] }) {
  return (
    <ul className="grid grid-cols-3 gap-2 sm:grid-cols-5" aria-label="Weather by session">
      {rows.map((row, index) => {
        const forecast = row.forecast;
        const rain = forecast?.rain_probability_pct ?? null;
        return (
          <li
            key={row.name}
            className={`flex min-w-0 flex-col items-center rounded-md border bg-black/30 px-1.5 py-2 motion-safe:animate-fade-up ${
              row.name === "Race" ? "border-[#E10600]/50 bg-[#E10600]/[0.06]" : "border-white/10"
            }`}
            style={{ animationDelay: `${0.3 + index * 0.08}s` }}
          >
            <span className="font-mono text-[9px] font-bold uppercase tracking-[0.16em] text-[#7F8797]">
              {SHORT_NAMES[row.name] ?? row.name}
            </span>
            {forecast ? (
              <WeatherGlyph condition={forecast.condition} isDay={forecast.is_day} size={34} label={forecast.label} />
            ) : (
              <span className="my-1 h-7 w-7 rounded-full border border-dashed border-white/15" aria-hidden="true" />
            )}
            <span className="whitespace-nowrap font-mono text-xs font-bold text-white">
              {forecast?.air_temp_c == null ? "—" : `${Math.round(forecast.air_temp_c)}°`}
              {rain !== null && (
                <span className="ml-1.5" style={{ color: rainColor(rain) }}>
                  {rain}%
                </span>
              )}
            </span>
          </li>
        );
      })}
    </ul>
  );
}
