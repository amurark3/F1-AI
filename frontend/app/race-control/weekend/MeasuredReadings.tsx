import { formatSignedDegrees, rainReadings, trackDelta } from "./weekendModel";

import type { MeasuredWeather, SessionWeatherRow } from "./weekendTypes";

const LABEL = "font-mono text-[9px] font-medium uppercase tracking-[0.14em] text-rc-ink-3";
const CAPTION = "mt-1 block font-mono text-[10px] font-medium text-rc-ink-3";

const dash = "—";
const whole = (value: number | null, prefix = "") => (value === null ? dash : `${prefix}${Math.round(value)}°`);
const tenth = (value: number | null) => (value === null ? dash : `${value.toFixed(1)}°`);

function rainWord(wet: number, total: number): string {
  if (total === 0) return dash;
  return wet === 0 ? "Dry" : "Wet";
}

function Note({ row }: { row: SessionWeatherRow }) {
  return (
    <div className="mt-3.5 rounded border border-dashed border-rc-line px-3 py-2.5 text-xs leading-normal text-rc-ink-3">
      <b className={`mb-1.5 block font-semibold tracking-[0.16em] ${LABEL}`}>
        {row.phase === "live" ? "Measured after the flag" : "No trackside reading"}
      </b>
      {row.measured_note}
    </div>
  );
}

function TickStrip({ rainfall, wet, total }: { rainfall: boolean[]; wet: number; total: number }) {
  return (
    <>
      <div role="img" aria-label={`Rain reported in ${wet} of ${total} readings`} className="mt-2.5 flex h-2.5 gap-px">
        {rainfall.map((isWet, index) => (
          <i key={index} className={`flex-1 rounded-[1px] ${isWet ? "bg-rc-ink-2" : "bg-rc-line"}`} />
        ))}
      </div>
      <div aria-hidden="true" className={`mt-1 flex justify-between ${LABEL}`}>
        <span>Start</span>
        <span>Rain reported</span>
        <span>End</span>
      </div>
    </>
  );
}

function Table({ row, measured }: { row: SessionWeatherRow; measured: MeasuredWeather }) {
  const forecast = row.forecast;
  const { wet, total } = rainReadings(measured.rainfall);
  const hasRange = measured.track_temp_min_c !== null && measured.track_temp_max_c !== null;
  const rain = forecast?.rain_probability_pct ?? null;
  const delta = trackDelta(forecast, measured);
  return (
    <div className="mt-3.5 border-t border-rc-line pt-3">
      <table className="w-full font-mono text-xs tabular-nums">
        <caption className={`pb-2.5 text-left font-semibold tracking-[0.16em] ${LABEL}`}>Forecast vs measured</caption>
        <thead>
          <tr className={LABEL}>
            <th scope="col" className="pb-2 text-left font-medium">
              <span className="sr-only">Reading</span>
            </th>
            <th scope="col" className="pb-2 text-right font-medium">
              Fcst
            </th>
            <th scope="col" className="pb-2 text-right font-medium">
              Trackside
            </th>
          </tr>
        </thead>
        <tbody className="align-top">
          <tr>
            <th scope="row" className={`pt-[7px] text-left ${LABEL}`}>
              Track
            </th>
            <td className="pt-[7px] text-right text-rc-ink-2">
              {whole(forecast?.track_temp_c ?? null, "~")}
              <small className={CAPTION}>estimate</small>
            </td>
            <td className="pt-[7px] text-right font-semibold text-rc-ink">
              {tenth(measured.track_temp_c)}
              {hasRange && (
                <small className={CAPTION}>
                  {measured.track_temp_min_c?.toFixed(1)}–{measured.track_temp_max_c?.toFixed(1)}
                </small>
              )}
            </td>
          </tr>
          <tr>
            <th scope="row" className={`pt-[7px] text-left ${LABEL}`}>
              Air
            </th>
            <td className="pt-[7px] text-right text-rc-ink-2">{whole(forecast?.air_temp_c ?? null)}</td>
            <td className="pt-[7px] text-right font-semibold text-rc-ink">{tenth(measured.air_temp_c)}</td>
          </tr>
          <tr>
            <th scope="row" className={`pt-[7px] text-left ${LABEL}`}>
              Rain
            </th>
            <td className="pt-[7px] text-right text-rc-ink-2">{rain === null ? dash : `${rain}%`}</td>
            <td className="pt-[7px] text-right font-semibold text-rc-ink">
              {rainWord(wet, total)}
              {wet > 0 && (
                <small className={CAPTION}>
                  {wet} of {total} readings
                </small>
              )}
            </td>
          </tr>
        </tbody>
      </table>
      {delta !== null && (
        <p className="mt-2.5 text-xs text-rc-ink-2">
          Track <b className="font-mono font-semibold text-rc-ink">{formatSignedDegrees(delta)}</b> on the estimate
        </p>
      )}
      {wet > 0 && <TickStrip rainfall={measured.rainfall} wet={wet} total={total} />}
    </div>
  );
}

/** OpenF1's trackside readings beside a finished session's forecast, or the reason there are none. */
export function MeasuredReadings({ row }: { row: SessionWeatherRow }) {
  if (row.measured) return <Table row={row} measured={row.measured} />;
  return row.measured_note ? <Note row={row} /> : null;
}
