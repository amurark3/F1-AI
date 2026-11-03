import { render, screen } from "@testing-library/react";
import { renderToString } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { SAO_PAULO_2026, SESSION_WEATHER_2026 } from "@/test/fixtures";

import { WeatherGlyph } from "./WeatherGlyph";

import type { WeatherCondition } from "./weekendTypes";

const CONDITIONS: WeatherCondition[] = [
  "clear",
  "partly_cloudy",
  "cloudy",
  "fog",
  "drizzle",
  "rain",
  "storm",
  "snow",
  "unknown",
];

/** Counts of the glyph's parts: sun disc, moon, clouds, drops, flakes, fog bands, bolt. */
function parts(svg: Element) {
  const circles = [...svg.querySelectorAll("circle")];
  const lines = [...svg.querySelectorAll("line")];
  return {
    sun: circles.filter((circle) => circle.getAttribute("fill") === "#FFC93C").length,
    moon: svg.querySelectorAll('path[fill="#E9E4CF"]').length,
    clouds: svg.querySelectorAll('path[d^="M20 46H46"]').length,
    drops: lines.filter((line) => line.getAttribute("stroke") === "#4C8DFF").length,
    flakes: circles.filter((circle) => circle.getAttribute("fill") === "#EEF4FF").length,
    fogBands: svg.querySelectorAll('g[stroke="#97A3B8"] line').length,
    bolt: svg.querySelectorAll("polygon").length,
  };
}

function glyph(condition: WeatherCondition, isDay: boolean | null): Element {
  const { container } = render(<WeatherGlyph condition={condition} isDay={isDay} />);
  const svg = container.querySelector("svg");
  if (!svg) throw new Error("no glyph drawn");
  return svg;
}

describe("WeatherGlyph", () => {
  it("names the captured race-day forecast when given a label, and hides from readers otherwise", () => {
    const race = SAO_PAULO_2026.weather.sessions.at(-1)?.forecast;
    if (!race) throw new Error("no race forecast");
    render(<WeatherGlyph condition={race.condition} isDay={race.is_day} size={34} label={race.label} />);
    const named = screen.getByRole("img", { name: "Overcast" });
    expect(named).toHaveAttribute("width", "34");
    expect(named).not.toHaveAttribute("aria-hidden");

    const { container } = render(<WeatherGlyph condition={race.condition} isDay={race.is_day} className="mx-auto" />);
    const hidden = container.querySelector("svg");
    expect(hidden).toHaveAttribute("aria-hidden", "true");
    expect(hidden).toHaveAttribute("width", "64");
    expect(hidden).toHaveClass("overflow-visible", "mx-auto");
  });

  it.each([
    ["clear", true, { sun: 2, moon: 0, clouds: 0 }],
    ["clear", false, { sun: 0, moon: 1, clouds: 0 }],
    ["partly_cloudy", true, { sun: 2, moon: 0, clouds: 1 }],
    ["partly_cloudy", false, { sun: 0, moon: 1, clouds: 1 }],
    ["cloudy", null, { clouds: 2 }],
    ["fog", true, { clouds: 1, fogBands: 2 }],
    ["drizzle", true, { clouds: 1, drops: 3 }],
    ["rain", true, { clouds: 1, drops: 5 }],
    ["storm", true, { clouds: 1, drops: 3, bolt: 1 }],
    ["snow", true, { clouds: 1, flakes: 4 }],
  ] as const)("draws %s (day: %s) from its parts", (condition, isDay, expected) => {
    expect(parts(glyph(condition, isDay))).toMatchObject(expected);
  });

  it("scales the moon down beside a cloud and leaves the clear-night moon full size", () => {
    expect(glyph("partly_cloudy", false).querySelector("g[transform^='translate']")).toHaveAttribute(
      "transform",
      "translate(8 5) scale(0.75)",
    );
    const fullMoon = glyph("clear", false).querySelector('path[fill="#E9E4CF"]')?.parentElement;
    expect(fullMoon).not.toHaveAttribute("transform");
  });

  it("outlines an unclassified sky as a still, dashed cloud", () => {
    const blank = SESSION_WEATHER_2026.blankHour;
    const cloud = glyph(blank.condition, blank.is_day).querySelector("path");
    expect(cloud).toHaveAttribute("fill", "none");
    expect(cloud).toHaveAttribute("stroke-dasharray", "4 3");
    expect(cloud?.getAttribute("class")).toBe("");
    expect(cloud?.parentElement).not.toHaveAttribute("transform");
  });

  it.each(CONDITIONS)("keeps every %s animation behind motion-safe in the server HTML", (condition) => {
    const html = renderToString(<WeatherGlyph condition={condition} isDay={false} />);
    expect(html).not.toMatch(/(?<!motion-safe:)animate-/);
  });
});
