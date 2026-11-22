import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MeasuredReadings } from "./MeasuredReadings";

import type { MeasuredWeather, SessionForecast, SessionWeatherRow } from "./weekendTypes";

// Hand-built to the shape `measured_weather.with_measured` returns for a finished session.
const FORECAST = {
  condition: "clear",
  label: "Clear night",
  is_day: false,
  air_temp_c: 14.2,
  track_temp_c: 15,
  rain_probability_pct: 0,
  precipitation_mm: 0,
  wind_kph: 9,
  wind_direction_deg: 45,
  humidity_pct: 31,
  cloud_cover_pct: 0,
} satisfies SessionForecast;

const MEASURED: MeasuredWeather = {
  track_temp_c: 18.4,
  track_temp_min_c: 17.1,
  track_temp_max_c: 19.6,
  air_temp_c: 14.6,
  rainfall: [false, false, false],
};

const row = (patch: Partial<SessionWeatherRow>): SessionWeatherRow => ({
  name: "Practice 1",
  starts_at: "2026-11-20T00:30:00Z",
  ends_at: "2026-11-20T01:30:00Z",
  phase: "done",
  forecast: FORECAST,
  forecast_opens: null,
  ...patch,
});

describe("MeasuredReadings", () => {
  it("renders nothing for an upcoming session or an older backend", () => {
    const { container } = render(<MeasuredReadings row={row({ phase: "upcoming" })} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("says a live session's readings follow the flag, in the backend's words", () => {
    const note = "OpenF1 closes its feed while a session runs; trackside readings follow once it ends.";
    render(<MeasuredReadings row={row({ phase: "live", measured: null, measured_note: note })} />);

    expect(screen.getByText("Measured after the flag")).toBeInTheDocument();
    expect(screen.getByText(note, { exact: false })).toBeInTheDocument();
  });

  it("says a finished session has no trackside reading", () => {
    render(
      <MeasuredReadings
        row={row({ measured: null, measured_note: "OpenF1 has no weather readings for this session." })}
      />,
    );

    expect(screen.getByText("No trackside reading")).toBeInTheDocument();
    expect(screen.getByText("OpenF1 has no weather readings for this session.", { exact: false })).toBeInTheDocument();
  });

  it("sets the forecast beside the dry trackside reading, with the estimate labelled", () => {
    render(<MeasuredReadings row={row({ measured: MEASURED })} />);

    const table = screen.getByRole("table", { name: "Forecast vs measured" });
    for (const text of ["~15°", "estimate", "18.4°", "17.1–19.6", "14°", "14.6°", "0%", "Dry"]) {
      expect(within(table).getByText(text)).toBeInTheDocument();
    }
    expect(screen.getByText("on the estimate", { exact: false }).textContent).toBe("Track +3.4° on the estimate");
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("shows wet readings with a tick strip, one tick per reading", () => {
    const rainfall = Array.from({ length: 61 }, (_, index) => index >= 23 && index < 32);
    render(<MeasuredReadings row={row({ measured: { ...MEASURED, rainfall } })} />);

    expect(screen.getByText("Wet")).toBeInTheDocument();
    expect(screen.getByText("9 of 61 readings")).toBeInTheDocument();
    const strip = screen.getByRole("img", { name: "Rain reported in 9 of 61 readings" });
    expect(strip.children).toHaveLength(61);
    expect(strip.querySelectorAll(".bg-rc-ink-2")).toHaveLength(9);
  });

  it("prints dashes for missing figures and drops the delta and range", () => {
    const measured: MeasuredWeather = { ...MEASURED, track_temp_c: null, track_temp_min_c: null, air_temp_c: null };
    const forecast = { ...FORECAST, track_temp_c: null, air_temp_c: null, rain_probability_pct: null };
    render(<MeasuredReadings row={row({ forecast, measured })} />);

    expect(screen.getAllByText("—")).toHaveLength(5);
    expect(screen.queryByText(/on the estimate/)).not.toBeInTheDocument();
    expect(screen.queryByText(/–/)).not.toBeInTheDocument();
  });

  it("prints a dash for rain when the station reported no rainfall flags, and no range without both ends", () => {
    render(<MeasuredReadings row={row({ measured: { ...MEASURED, track_temp_max_c: null, rainfall: [] } })} />);

    expect(within(screen.getByRole("table")).getAllByRole("row").at(-1)).toHaveTextContent("Rain0%—");
    expect(screen.queryByText("17.1–19.6")).not.toBeInTheDocument();
    expect(screen.queryByText(/17\.1/)).not.toBeInTheDocument();
  });

  it("copes with a session whose forecast is missing", () => {
    render(<MeasuredReadings row={row({ forecast: null, measured: MEASURED })} />);

    expect(screen.getByText("18.4°")).toBeInTheDocument();
    expect(screen.queryByText(/on the estimate/)).not.toBeInTheDocument();
  });
});
