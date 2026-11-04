import { describe, expect, it } from "vitest";

import { SAO_PAULO_2026, SESSION_WEATHER_2026, STAKES_2026 } from "@/test/fixtures";

import {
  ambienceFor,
  clinchLine,
  compassPoint,
  formatPoints,
  railFill,
  rainColor,
  reachLine,
  summariseWeekend,
} from "./weekendModel";

import type { SessionForecast, SessionWeatherRow, TableStakes } from "./weekendTypes";

/** The forecast of a captured session, by name. */
function forecastOf(rows: SessionWeatherRow[], name: string): SessionForecast {
  const forecast = rows.find((row) => row.name === name)?.forecast;
  if (!forecast) throw new Error(`no forecast for ${name}`);
  return forecast;
}

function tableOf(stakes: TableStakes | null): TableStakes {
  if (!stakes) throw new Error("no table in the captured stakes");
  return stakes;
}

const SAO_PAULO_ROWS = SAO_PAULO_2026.weather.sessions;

describe("rainColor", () => {
  it("bands São Paulo's captured rain chances as dry, mixed and likely wet", () => {
    expect(rainColor(forecastOf(SAO_PAULO_ROWS, "Practice 1").rain_probability_pct)).toBe("#00FF78");
    expect(rainColor(forecastOf(SAO_PAULO_ROWS, "Race").rain_probability_pct)).toBe("#FFF200");
    expect(rainColor(forecastOf(SAO_PAULO_ROWS, "Qualifying").rain_probability_pct)).toBe("#4C8DFF");
  });

  it("starts the mixed band at 20% and the wet band at 50%", () => {
    expect([19, 20, 49, 50].map(rainColor)).toEqual(["#00FF78", "#FFF200", "#FFF200", "#4C8DFF"]);
  });

  it("greys out a session with no rain reading", () => {
    expect(rainColor(SESSION_WEATHER_2026.blankHour.rain_probability_pct)).toBe("#3A4254");
  });
});

describe("compassPoint", () => {
  it("names the point the captured wind blows from", () => {
    expect(compassPoint(forecastOf(SAO_PAULO_ROWS, "Practice 1").wind_direction_deg)).toBe("SE");
    expect(compassPoint(forecastOf(SAO_PAULO_ROWS, "Practice 3").wind_direction_deg)).toBe("NW");
  });

  it("wraps bearings past north either way", () => {
    expect([0, 359, 360, -45, 720].map(compassPoint)).toEqual(["N", "N", "N", "NW", "N"]);
  });

  it("has no point for a missing or unreadable bearing", () => {
    expect(compassPoint(SESSION_WEATHER_2026.blankHour.wind_direction_deg)).toBeNull();
    expect(compassPoint(Number.NaN)).toBeNull();
  });
});

describe("ambienceFor", () => {
  it.each([
    ["clear", true, "sun"],
    ["partly_cloudy", null, "sun"],
    ["clear", false, "night"],
    ["partly_cloudy", false, "night"],
    ["cloudy", false, "cloud"],
    ["fog", true, "cloud"],
    ["drizzle", true, "rain"],
    ["rain", null, "rain"],
    ["storm", true, "storm"],
    ["snow", true, "snow"],
    ["unknown", null, "none"],
  ] as const)("gives %s (day: %s) the %s backdrop", (condition, isDay, ambience) => {
    expect(ambienceFor(condition, isDay)).toBe(ambience);
  });

  it("reads Singapore's evening sessions as night only under a clear sky", () => {
    const rows = SESSION_WEATHER_2026.singaporeDone.sessions;
    const sprintQualifying = forecastOf(rows, "Sprint Qualifying");
    const race = forecastOf(rows, "Race");
    expect(ambienceFor(sprintQualifying.condition, sprintQualifying.is_day)).toBe("night");
    expect(ambienceFor(race.condition, race.is_day)).toBe("cloud");
  });
});

describe("railFill", () => {
  const phases = (rows: SessionWeatherRow[]) => rows.map((row) => row.phase);

  it("is empty before the first session", () => {
    expect(railFill(phases(SAO_PAULO_ROWS))).toBe(0);
  });

  it("puts the fill on the live session's node", () => {
    expect(railFill(phases(SESSION_WEATHER_2026.mexicoCityRaceLive.sessions))).toBe(1);
    expect(railFill(["done", "live", "upcoming", "upcoming", "upcoming"])).toBe(0.25);
  });

  it("stops halfway to the next node between sessions", () => {
    expect(railFill(["done", "done", "upcoming", "upcoming", "upcoming"])).toBe(0.375);
  });

  it("is full once every session is done", () => {
    expect(railFill(phases(SESSION_WEATHER_2026.singaporeDone.sessions))).toBe(1);
  });

  it("fills a one-session weekend only once it is done", () => {
    expect(railFill(["upcoming"])).toBe(0);
    expect(railFill(["live"])).toBe(0);
    expect(railFill(["done"])).toBe(1);
    expect(railFill([])).toBe(0);
  });
});

describe("summariseWeekend", () => {
  it("finds the wettest session and the temperature range", () => {
    const summary = summariseWeekend(SAO_PAULO_ROWS);
    expect(summary.wettest?.name).toBe("Qualifying");
    expect(summary).toMatchObject({ coolest: 16.5, warmest: 27.2 });
  });

  it("has nothing to summarise before the forecasts open", () => {
    expect(summariseWeekend(SESSION_WEATHER_2026.lasVegasPending.sessions)).toEqual({
      wettest: null,
      coolest: null,
      warmest: null,
    });
  });

  it("skips readings Open-Meteo left blank", () => {
    const [practice, ...rest] = SAO_PAULO_ROWS;
    const rows = [{ ...practice, forecast: SESSION_WEATHER_2026.blankHour }, ...rest];
    const summary = summariseWeekend(rows);
    expect(summary.wettest?.name).toBe("Qualifying");
    expect(summary).toMatchObject({ coolest: 16.5, warmest: 27.2 });

    const blankOnly = summariseWeekend([{ ...practice, forecast: SESSION_WEATHER_2026.blankHour }]);
    expect(blankOnly).toEqual({ wettest: null, coolest: null, warmest: null });
  });
});

describe("formatPoints", () => {
  it("prints whole points as integers and half points to one place", () => {
    expect(formatPoints(380)).toBe("380");
    expect(formatPoints(12.5)).toBe("12.5");
  });
});

describe("clinchLine", () => {
  it("reads the backend's decided flag: Antonelli's title after round 19", () => {
    expect(clinchLine(tableOf(SAO_PAULO_2026.stakes.drivers), "São Paulo", "drivers")).toEqual({
      tone: "decided",
      text: "Kimi Antonelli has already clinched the title.",
    });
  });

  it("quotes the margin the leader must outscore the rival by", () => {
    expect(clinchLine(tableOf(SAO_PAULO_2026.stakes.constructors), "São Paulo", "constructors")).toEqual({
      tone: "possible",
      text: "Mercedes clinches in São Paulo by outscoring Ferrari by 4+ pts.",
    });
  });

  it("turns a lead already past the points left after the round into the rival's target", () => {
    // After round 18: 365 to Russell's 242 with 100 left after Mexico City.
    expect(clinchLine(tableOf(STAKES_2026.afterRound18.drivers), "Mexico City", "drivers")).toEqual({
      tone: "possible",
      text: "Kimi Antonelli clinches in Mexico City unless George Russell outscores them by 23+ pts.",
    });
  });

  it("says the title cannot be settled when one weekend is not enough", () => {
    expect(clinchLine(tableOf(STAKES_2026.afterRound1.drivers), "Shanghai", "drivers")).toEqual({
      tone: "open",
      text: "The title can't be settled in Shanghai — 598 pts still on offer.",
    });
  });

  it("is open when there is no clinch to chase this weekend", () => {
    const drivers = tableOf(STAKES_2026.afterRound1.drivers);
    expect(clinchLine({ ...drivers, clinch: null }, "Shanghai", "drivers").tone).toBe("open");
  });
});

describe("reachLine", () => {
  it("marks the leader's points minus what is left, on a leader-scaled bar", () => {
    // 380 − 100 = 280 of 380.
    expect(reachLine(tableOf(SAO_PAULO_2026.stakes.drivers))).toBeCloseTo((280 / 380) * 100);
  });

  it("is null while every bar still clears it", () => {
    expect(reachLine(tableOf(STAKES_2026.afterRound1.drivers))).toBeNull();
  });
});
