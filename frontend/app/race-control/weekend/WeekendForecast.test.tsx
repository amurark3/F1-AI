import { render, screen, within } from "@testing-library/react";
import { useReducedMotion } from "framer-motion";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { rc } from "@/app/ui/tokens";
import { SAO_PAULO_2026, SESSION_WEATHER_2026 } from "@/test/fixtures";

import { WeekendForecast } from "./WeekendForecast";

import type { SessionWeather } from "./weekendTypes";
import type * as FramerMotion from "framer-motion";

vi.mock("framer-motion", async (importOriginal) => ({
  ...(await importOriginal<typeof FramerMotion>()),
  useReducedMotion: vi.fn(),
}));

const SAO_PAULO = SAO_PAULO_2026.weather;

/** A session's card, by the session's name. */
function card(name: string): HTMLElement {
  const found = screen.getAllByRole("article").find((article) => article.querySelector("p")?.textContent === name);
  if (!found) throw new Error(`no card for ${name}`);
  return found;
}

/** A card's readings as "label value", e.g. "Track ~30°". */
function readings(name: string): string[] {
  return within(card(name))
    .getAllByRole("term")
    .map((term) => `${term.textContent} ${term.nextElementSibling?.textContent}`);
}

function chips(): string[] {
  return [...document.querySelectorAll("p.mb-4.flex > span")].map((chip) => chip.textContent);
}

function railFillWidth(): string | undefined {
  return document.querySelector<HTMLElement>(".origin-left.bg-rc-ink-3")?.style.width;
}

describe("WeekendForecast", () => {
  beforeEach(() => {
    vi.mocked(useReducedMotion).mockReturnValue(true);
  });

  it("sums up São Paulo's weekend: race-day sky, wettest session and temperature range", () => {
    render(<WeekendForecast weather={SAO_PAULO} />);

    expect(screen.getByRole("heading", { name: "Weather, session by session" })).toBeInTheDocument();
    expect(chips()).toEqual(["Race day: Overcast · 21% rain", "Wettest: Qualifying 80%", "17–27°C across the weekend"]);
    expect(screen.getAllByRole("article")).toHaveLength(5);
    expect(screen.getAllByText("Forecast")).toHaveLength(5);
    expect(railFillWidth()).toBe("0%");
    expect(screen.getByText(/Weather data by Open-Meteo\.com\.$/)).toBeInTheDocument();
    expect(screen.queryByText(/as of/)).not.toBeInTheDocument();
  });

  it("labels the stored forecast it shows while the live feed is down with when it was fetched", () => {
    // `session_weather.build_session_weather` when the call fails and the venue's last good series is stored.
    const stored: SessionWeather = {
      ...SAO_PAULO,
      note: "The forecast feed is unavailable right now. Showing the forecast as of 14:05 UTC.",
      as_of: "2026-11-07T14:05:00Z",
      as_of_label: "as of 14:05 UTC",
    };
    render(<WeekendForecast weather={stored} />);

    expect(screen.getByText("as of 14:05 UTC")).toBeInTheDocument();
    expect(
      screen.getByText("The forecast feed is unavailable right now. Showing the forecast as of 14:05 UTC."),
    ).toBeInTheDocument();
    expect(screen.getAllByRole("article")).toHaveLength(5);
    expect(chips()[0]).toBe("Race day: Overcast · 21% rain");
  });

  it("reads each session's hours: temperature, rain, wind from its compass point, track and humidity", () => {
    render(<WeekendForecast weather={SAO_PAULO} />);

    const practice = card("Practice 1");
    expect(within(practice).getByText("°C").parentElement).toHaveTextContent("25°C");
    expect(within(practice).getByText("Overcast")).toBeInTheDocument();
    expect(within(practice).getByText("12%")).toHaveStyle({ color: rc.ink3 });
    expect(readings("Practice 1")).toEqual(["Wind 4SE", "Track ~30°", "Humidity 65%"]);
    // The arrow points where the wind goes: 115° + 180°.
    expect(practice.querySelector<HTMLElement>("dd .inline-flex")?.style.transform).toBe("rotate(295deg)");
    expect(within(practice).queryByText(/mm$/)).not.toBeInTheDocument();
    expect(within(card("Qualifying")).getByText("· 0.4 mm")).toBeInTheDocument();
  });

  it("frames the race with a red rule, and draws no backdrop, glow or dimming", () => {
    const { container } = render(<WeekendForecast weather={SAO_PAULO} />);

    expect(card("Race")).toHaveClass("border-t-2", "border-t-f1-red");
    expect(card("Race").querySelector("p")).toHaveClass("text-rc-ink");
    expect(card("Practice 1")).not.toHaveClass("border-t-2", "opacity-75");
    expect(card("Practice 1").querySelector("p")).toHaveClass("text-rc-ink-2");
    expect(container.querySelector(".wx-rain-streaks, .pointer-events-none, .blur-2xl")).toBeNull();
    expect(container.innerHTML).not.toMatch(/box-shadow|shadow-\[/);
    expect(within(card("Qualifying")).getByText("80%")).toHaveStyle({ color: rc.blue });
  });

  it("marks Mexico City's race live and the sessions before it done", () => {
    render(<WeekendForecast weather={SESSION_WEATHER_2026.mexicoCityRaceLive} />);

    expect(within(card("Race")).getByText("Live").querySelector(".rounded-full")).toBeInTheDocument();
    expect(screen.getAllByText("Done · model")).toHaveLength(4);
    expect(card("Qualifying")).not.toHaveClass("opacity-75");
    expect(railFillWidth()).toBe("100%");
    expect(within(card("Race")).getByText("· 0.1 mm")).toBeInTheDocument();
  });

  it("says when each Las Vegas forecast opens, with nothing to sum up yet", () => {
    render(<WeekendForecast weather={SESSION_WEATHER_2026.lasVegasPending} />);

    expect(chips()).toEqual([]);
    expect(within(card("Practice 1")).getByText("Forecast opens Nov 05")).toBeInTheDocument();
    expect(within(card("Race")).getByText("Forecast opens Nov 07")).toBeInTheDocument();
    expect(screen.getByText("Forecasts open 15 days before each session.")).toBeInTheDocument();
  });

  it("says plainly when a weekend is older than the forecast archive", () => {
    render(<WeekendForecast weather={SESSION_WEATHER_2026.melbourneArchived} />);

    expect(screen.getAllByText("No forecast for this session")).toHaveLength(5);
    expect(screen.getByText("This weekend is older than the forecast archive.")).toBeInTheDocument();
    expect(railFillWidth()).toBe("100%");
  });

  it("shows dashes for hours Open-Meteo left blank, never a dry zero", () => {
    // `summarise_window` keeps blank readings null (backend test: blank readings stay blank).
    const sessions = SAO_PAULO.sessions.map((row) =>
      row.name === "Race" ? { ...row, forecast: SESSION_WEATHER_2026.blankHour } : row,
    );
    const weather: SessionWeather = { ...SAO_PAULO, sessions };
    render(<WeekendForecast weather={weather} />);

    const race = card("Race");
    expect(within(race).getByText("°C").parentElement).toHaveTextContent("—°C");
    expect(within(race).getByText("Unclassified")).toBeInTheDocument();
    expect(readings("Race")).toEqual(["Wind —", "Track —", "Humidity —"]);
    expect(race.querySelector("dd .inline-flex")).not.toBeInTheDocument();
    expect(chips()).toEqual(["Race day: Unclassified", "Wettest: Qualifying 80%", "23–27°C across the weekend"]);
  });

  it("explains an empty weekend with the backend's note", () => {
    render(<WeekendForecast weather={SESSION_WEATHER_2026.noSchedule} />);

    expect(screen.getAllByText(/^Session times are not published yet\.\s?$/)).toHaveLength(2);
    expect(screen.queryByRole("article")).not.toBeInTheDocument();
  });

  it("falls back to its own copy before the weather segment lands", () => {
    render(<WeekendForecast weather={undefined} />);

    expect(screen.getByText("Session times are not published yet.")).toBeInTheDocument();
    expect(screen.getByText(/Weather data by Open-Meteo\.com\.$/)).toBeInTheDocument();
  });
});
